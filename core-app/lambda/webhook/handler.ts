import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from 'aws-lambda'
import { PutObjectCommand, S3Client } from '@aws-sdk/client-s3'
import { SendMessageCommand, SQSClient } from '@aws-sdk/client-sqs'
import { DynamoDBDocumentClient, PutCommand, UpdateCommand } from '@aws-sdk/lib-dynamodb'
import { DynamoDBClient } from '@aws-sdk/client-dynamodb'
import { requiredEnv } from '../shared/env'
import { logger } from '../shared/logger'
import { getJsonSecret, requireSecretValue, type LineSecret } from '../shared/secrets'
import type { LineWebhookBody, LineWebhookEvent, ReceiptProcessingMessage } from '../shared/types'
import { LineClient } from './lineClient'
import { verifyLineSignature } from './signature'

const s3Client = new S3Client({})
const sqsClient = new SQSClient({})
const dynamoClient = DynamoDBDocumentClient.from(new DynamoDBClient({}))

const receiptImageBucket = requiredEnv('RECEIPT_IMAGE_BUCKET')
const receiptEventsTable = requiredEnv('RECEIPT_EVENTS_TABLE')
const processingQueueUrl = requiredEnv('RECEIPT_PROCESSING_QUEUE_URL')
const lineSecretArn = requiredEnv('LINE_SECRET_ARN')
const awsRegion = process.env.AWS_REGION ?? 'ap-northeast-1'

let cachedLineSecret: LineSecret | undefined

export async function handler(event: APIGatewayProxyEventV2): Promise<APIGatewayProxyStructuredResultV2> {
  const rawBody = event.isBase64Encoded
    ? Buffer.from(event.body ?? '', 'base64').toString('utf8')
    : event.body ?? ''
  const channelSecret = await getLineChannelSecret()

  if (!verifyLineSignature(rawBody, channelSecret, getHeader(event.headers, 'x-line-signature'))) {
    logger.warn('Rejected request with invalid LINE signature')
    return { statusCode: 401, body: 'invalid signature' }
  }

  const lineClient = new LineClient(await getLineChannelAccessToken())
  const parsedBody = JSON.parse(rawBody) as LineWebhookBody

  for (const lineEvent of parsedBody.events ?? []) {
    await handleLineEvent(lineEvent, lineClient)
  }

  return { statusCode: 200, body: 'ok' }
}

async function handleLineEvent(lineEvent: LineWebhookEvent, lineClient: LineClient): Promise<void> {
  if (!lineEvent.replyToken) {
    logger.warn('Ignored LINE event without replyToken', { eventType: lineEvent.type })
    return
  }

  if (lineEvent.type !== 'message' || lineEvent.message?.type !== 'image') {
    await lineClient.replyText(lineEvent.replyToken, 'レシート画像を送ってください。')
    return
  }

  const lineUserId = lineEvent.source?.userId
  const lineMessageId = lineEvent.message.id
  if (!lineUserId) {
    await lineClient.replyText(lineEvent.replyToken, 'ユーザー情報を確認できませんでした。もう一度送ってください。')
    return
  }

  const createdAt = new Date().toISOString()
  const lineDisplayName = await getLineDisplayName(lineClient, lineUserId, lineMessageId)
  const wasCreated = await createReceiptEvent(lineMessageId, lineUserId, lineDisplayName, createdAt)
  if (!wasCreated) {
    await lineClient.replyText(lineEvent.replyToken, 'このレシートはすでに受け付けています。読み取り結果をお待ちください。')
    return
  }

  try {
    const imageBytes = await lineClient.getMessageContent(lineMessageId)
    const key = `receipts/${lineUserId}/${lineMessageId}.jpg`
    const imageUrl = publicS3ObjectUrl(receiptImageBucket, key)

    await s3Client.send(
      new PutObjectCommand({
        Bucket: receiptImageBucket,
        Key: key,
        Body: imageBytes,
        ContentType: 'image/jpeg',
      }),
    )

    const message: ReceiptProcessingMessage = {
      lineUserId,
      lineDisplayName,
      lineMessageId,
      bucket: receiptImageBucket,
      key,
      imageUrl,
    }
    await sqsClient.send(
      new SendMessageCommand({
        QueueUrl: processingQueueUrl,
        MessageBody: JSON.stringify(message),
      }),
    )

    await updateReceiptEvent(lineMessageId, {
      status: 'QUEUED',
      imageUrl,
      updatedAt: new Date().toISOString(),
    })
    await lineClient.replyText(lineEvent.replyToken, '受け付けました。読み取り後に結果を送ります。')
  } catch (error) {
    logger.error('Failed to enqueue receipt image', {
      lineMessageId,
      error: error instanceof Error ? error.message : String(error),
    })
    await updateReceiptEvent(lineMessageId, {
      status: 'FAILED',
      errorMessage: error instanceof Error ? error.message : String(error),
      updatedAt: new Date().toISOString(),
    })
    await lineClient.replyText(lineEvent.replyToken, '画像の受け付けに失敗しました。時間をおいてもう一度送ってください。')
  }
}

function publicS3ObjectUrl(bucket: string, key: string): string {
  const encodedKey = key.split('/').map(encodeURIComponent).join('/')
  return `https://${bucket}.s3.${awsRegion}.amazonaws.com/${encodedKey}`
}

async function getLineDisplayName(
  lineClient: LineClient,
  lineUserId: string,
  lineMessageId: string,
): Promise<string> {
  try {
    const profile = await lineClient.getProfile(lineUserId)
    return profile.displayName
  } catch (error) {
    logger.warn('Failed to fetch LINE profile; continuing without display name', {
      lineMessageId,
      lineUserId,
      error: error instanceof Error ? error.message : String(error),
    })
    return ''
  }
}

async function createReceiptEvent(
  lineMessageId: string,
  lineUserId: string,
  lineDisplayName: string,
  createdAt: string,
): Promise<boolean> {
  try {
    await dynamoClient.send(
      new PutCommand({
        TableName: receiptEventsTable,
        Item: {
          lineMessageId,
          lineUserId,
          lineDisplayName,
          status: 'RECEIVED',
          createdAt,
          updatedAt: createdAt,
        },
        ConditionExpression: 'attribute_not_exists(lineMessageId)',
      }),
    )
    return true
  } catch (error) {
    if ((error as { name?: string }).name === 'ConditionalCheckFailedException') {
      return false
    }
    throw error
  }
}

async function updateReceiptEvent(lineMessageId: string, values: Record<string, string>): Promise<void> {
  const names: Record<string, string> = {}
  const expressionValues: Record<string, string> = {}
  const assignments: string[] = []

  for (const [key, value] of Object.entries(values)) {
    names[`#${key}`] = key
    expressionValues[`:${key}`] = value
    assignments.push(`#${key} = :${key}`)
  }

  await dynamoClient.send(
    new UpdateCommand({
      TableName: receiptEventsTable,
      Key: { lineMessageId },
      UpdateExpression: `SET ${assignments.join(', ')}`,
      ExpressionAttributeNames: names,
      ExpressionAttributeValues: expressionValues,
    }),
  )
}

async function getLineChannelSecret(): Promise<string> {
  const secret = await getLineSecret()
  return requireSecretValue(secret.channelSecret, 'channelSecret', lineSecretArn)
}

async function getLineChannelAccessToken(): Promise<string> {
  const secret = await getLineSecret()
  return requireSecretValue(secret.channelAccessToken, 'channelAccessToken', lineSecretArn)
}

async function getLineSecret(): Promise<LineSecret> {
  cachedLineSecret ??= await getJsonSecret<LineSecret>(lineSecretArn)
  return cachedLineSecret
}

function getHeader(headers: Record<string, string | undefined>, name: string): string | undefined {
  const lowerName = name.toLowerCase()
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() === lowerName) {
      return value
    }
  }
  return undefined
}
