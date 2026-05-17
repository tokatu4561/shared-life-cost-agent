import { createHmac } from 'node:crypto'
import type { APIGatewayProxyEventV2 } from 'aws-lambda'

const mockInvokeExpenseQueryAgent = jest.fn()
const mockDynamoSend = jest.fn()
const mockS3Send = jest.fn()
const mockSqsSend = jest.fn()
const mockLineSecret = {
  channelSecret: 'channel-secret',
  channelAccessToken: 'channel-token',
  allowedExpenseQuerySourceIds: ['G001'],
}

jest.mock('@aws-sdk/client-s3', () => ({
  S3Client: jest.fn(() => ({ send: mockS3Send })),
  PutObjectCommand: jest.fn(),
}))

jest.mock('@aws-sdk/client-sqs', () => ({
  SQSClient: jest.fn(() => ({ send: mockSqsSend })),
  SendMessageCommand: jest.fn(),
}))

jest.mock('@aws-sdk/client-dynamodb', () => ({
  DynamoDBClient: jest.fn(),
}))

jest.mock('@aws-sdk/lib-dynamodb', () => ({
  DynamoDBDocumentClient: {
    from: jest.fn(() => ({ send: mockDynamoSend })),
  },
  PutCommand: jest.fn(),
  UpdateCommand: jest.fn(),
}))

jest.mock('../../core-app/lambda/shared/secrets', () => ({
  getJsonSecret: jest.fn(async () => mockLineSecret),
  requireSecretValue: jest.fn((value: string) => value),
}))

jest.mock('../../core-app/lambda/worker/agentCoreClient', () => ({
  AgentCoreClient: jest.fn().mockImplementation(() => ({
    invokeExpenseQueryAgent: mockInvokeExpenseQueryAgent,
  })),
}))

describe('webhook handler', () => {
  const originalEnv = process.env
  const originalFetch = global.fetch

  beforeEach(() => {
    jest.resetModules()
    jest.clearAllMocks()
    process.env = {
      ...originalEnv,
      LINE_SECRET_ARN: 'line-secret',
      RECEIPT_IMAGE_BUCKET: 'receipt-bucket',
      RECEIPT_EVENTS_TABLE: 'events-table',
      RECEIPT_PROCESSING_QUEUE_URL: 'queue-url',
      AGENT_CORE_RUNTIME_ARN: 'agent-runtime-arn',
    }
    mockLineSecret.allowedExpenseQuerySourceIds = ['G001']
    mockDynamoSend.mockResolvedValue({})
    mockS3Send.mockResolvedValue({})
    mockSqsSend.mockResolvedValue({})
  })

  afterEach(() => {
    process.env = originalEnv
    global.fetch = originalFetch
  })

  test('passes text messages to AgentCore and replies with the answer', async () => {
    mockInvokeExpenseQueryAgent.mockResolvedValue({
      success: true,
      status: 'answered',
      replyMessage: '2026-05 の全体合計は 1,500円です。',
    })
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ displayName: '太郎' }),
      })
      .mockResolvedValueOnce({
        ok: true,
      })
    global.fetch = fetchMock as unknown as typeof fetch

    const body = JSON.stringify({
      events: [
        {
          type: 'message',
          replyToken: 'reply-token',
          source: { type: 'group', userId: 'U001', groupId: 'G001' },
          message: { id: 'm001', type: 'text', text: '今月の全体はいくら？' },
        },
      ],
    })
    const { handler } = await import('../../core-app/lambda/webhook/handler')
    const response = await handler(_lineEvent(body))

    expect(response).toEqual({ statusCode: 200, body: 'ok' })
    expect(mockInvokeExpenseQueryAgent).toHaveBeenCalledWith({
      task: 'expense_query',
      lineUserId: 'U001',
      lineDisplayName: '太郎',
      lineMessageId: 'm001',
      text: '今月の全体はいくら？',
    })
    expect(fetchMock).toHaveBeenLastCalledWith('https://api.line.me/v2/bot/message/reply', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer channel-token',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        replyToken: 'reply-token',
        messages: [{ type: 'text', text: '2026-05 の全体合計は 1,500円です。' }],
      }),
    })
  })

  test('uses group member profile for group receipt image sender display name', async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ displayName: 'ゆきほ' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
      })
      .mockResolvedValueOnce({
        ok: true,
      })
    global.fetch = fetchMock as unknown as typeof fetch

    const body = JSON.stringify({
      events: [
        {
          type: 'message',
          replyToken: 'reply-token',
          source: { type: 'group', userId: 'U001', groupId: 'G001' },
          message: { id: 'm001', type: 'image' },
        },
      ],
    })
    const { handler } = await import('../../core-app/lambda/webhook/handler')
    await handler(_lineEvent(body))
    const { SendMessageCommand } = jest.requireMock('@aws-sdk/client-sqs')

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'https://api.line.me/v2/bot/group/G001/member/U001', {
      method: 'GET',
      headers: {
        Authorization: 'Bearer channel-token',
      },
    })
    expect(SendMessageCommand).toHaveBeenCalledWith({
      QueueUrl: 'queue-url',
      MessageBody: JSON.stringify({
        lineUserId: 'U001',
        lineDisplayName: 'ゆきほ',
        lineMessageId: 'm001',
        lineReplyToId: 'G001',
        lineReplySourceType: 'group',
        bucket: 'receipt-bucket',
        key: 'receipts/U001/m001.jpg',
        imageUrl: 'https://receipt-bucket.s3.ap-northeast-1.amazonaws.com/receipts/U001/m001.jpg',
      }),
    })
  })

  test('continues group receipt image processing without display name when group profile fetch fails', async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
      })
      .mockResolvedValueOnce({
        ok: true,
        arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
      })
      .mockResolvedValueOnce({
        ok: true,
      })
    global.fetch = fetchMock as unknown as typeof fetch

    const body = JSON.stringify({
      events: [
        {
          type: 'message',
          replyToken: 'reply-token',
          source: { type: 'group', userId: 'U001', groupId: 'G001' },
          message: { id: 'm001', type: 'image' },
        },
      ],
    })
    const { handler } = await import('../../core-app/lambda/webhook/handler')
    await handler(_lineEvent(body))
    const { SendMessageCommand } = jest.requireMock('@aws-sdk/client-sqs')

    expect(SendMessageCommand).toHaveBeenCalledWith({
      QueueUrl: 'queue-url',
      MessageBody: JSON.stringify({
        lineUserId: 'U001',
        lineDisplayName: '',
        lineMessageId: 'm001',
        lineReplyToId: 'G001',
        lineReplySourceType: 'group',
        bucket: 'receipt-bucket',
        key: 'receipts/U001/m001.jpg',
        imageUrl: 'https://receipt-bucket.s3.ap-northeast-1.amazonaws.com/receipts/U001/m001.jpg',
      }),
    })
  })

  test('rejects text expense queries from unapproved LINE sources', async () => {
    mockLineSecret.allowedExpenseQuerySourceIds = ['G-approved']
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ displayName: '太郎' }),
      })
      .mockResolvedValueOnce({
        ok: true,
      })
    global.fetch = fetchMock as unknown as typeof fetch

    const body = JSON.stringify({
      events: [
        {
          type: 'message',
          replyToken: 'reply-token',
          source: { type: 'user', userId: 'U001' },
          message: { id: 'm001', type: 'text', text: '今月の全体はいくら？' },
        },
      ],
    })
    const { handler } = await import('../../core-app/lambda/webhook/handler')
    const response = await handler(_lineEvent(body))

    expect(response).toEqual({ statusCode: 200, body: 'ok' })
    expect(mockInvokeExpenseQueryAgent).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenLastCalledWith('https://api.line.me/v2/bot/message/reply', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer channel-token',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        replyToken: 'reply-token',
        messages: [{ type: 'text', text: 'このトークでは集計を確認できません。' }],
      }),
    })
  })

  test('rejects text expense queries from unapproved LINE groups', async () => {
    mockLineSecret.allowedExpenseQuerySourceIds = ['G-approved']
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ displayName: '太郎' }),
      })
      .mockResolvedValueOnce({
        ok: true,
      })
    global.fetch = fetchMock as unknown as typeof fetch

    const body = JSON.stringify({
      events: [
        {
          type: 'message',
          replyToken: 'reply-token',
          source: { type: 'group', userId: 'U001', groupId: 'G001' },
          message: { id: 'm001', type: 'text', text: '今月の全体はいくら？' },
        },
      ],
    })
    const { handler } = await import('../../core-app/lambda/webhook/handler')
    await handler(_lineEvent(body))

    expect(mockInvokeExpenseQueryAgent).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenLastCalledWith('https://api.line.me/v2/bot/message/reply', expect.objectContaining({
      body: JSON.stringify({
        replyToken: 'reply-token',
        messages: [{ type: 'text', text: 'このグループでは集計を確認できません。' }],
      }),
    }))
  })

  test('rejects text expense queries from non-group sources even when the user id is allowed', async () => {
    mockLineSecret.allowedExpenseQuerySourceIds = ['U001']
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ displayName: '太郎' }),
      })
      .mockResolvedValueOnce({
        ok: true,
      })
    global.fetch = fetchMock as unknown as typeof fetch

    const body = JSON.stringify({
      events: [
        {
          type: 'message',
          replyToken: 'reply-token',
          source: { type: 'user', userId: 'U001' },
          message: { id: 'm001', type: 'text', text: '今月の全体はいくら？' },
        },
      ],
    })
    const { handler } = await import('../../core-app/lambda/webhook/handler')
    await handler(_lineEvent(body))

    expect(mockInvokeExpenseQueryAgent).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenLastCalledWith('https://api.line.me/v2/bot/message/reply', expect.objectContaining({
      body: JSON.stringify({
        replyToken: 'reply-token',
        messages: [{ type: 'text', text: 'このトークでは集計を確認できません。' }],
      }),
    }))
  })

  test('rejects text expense queries when the allow list is not an array', async () => {
    ;(mockLineSecret as { allowedExpenseQuerySourceIds: unknown }).allowedExpenseQuerySourceIds = 'U001'
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ displayName: '太郎' }),
      })
      .mockResolvedValueOnce({
        ok: true,
      })
    global.fetch = fetchMock as unknown as typeof fetch

    const body = JSON.stringify({
      events: [
        {
          type: 'message',
          replyToken: 'reply-token',
          source: { type: 'group', userId: 'U001', groupId: 'G001' },
          message: { id: 'm001', type: 'text', text: '今月の全体はいくら？' },
        },
      ],
    })
    const { handler } = await import('../../core-app/lambda/webhook/handler')
    await handler(_lineEvent(body))

    expect(mockInvokeExpenseQueryAgent).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenLastCalledWith('https://api.line.me/v2/bot/message/reply', expect.objectContaining({
      body: JSON.stringify({
        replyToken: 'reply-token',
        messages: [{ type: 'text', text: 'このグループでは集計を確認できません。' }],
      }),
    }))
  })
})

function _lineEvent(body: string): APIGatewayProxyEventV2 {
  const signature = createHmac('sha256', 'channel-secret').update(body).digest('base64')
  return {
    version: '2.0',
    routeKey: 'POST /line/webhook',
    rawPath: '/line/webhook',
    rawQueryString: '',
    headers: {
      'x-line-signature': signature,
    },
    requestContext: {} as APIGatewayProxyEventV2['requestContext'],
    isBase64Encoded: false,
    body,
  }
}
