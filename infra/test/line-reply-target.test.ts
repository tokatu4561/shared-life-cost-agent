import { receiptPushTargetId, resolveLineReplyTarget } from '../../core-app/lambda/shared/lineReplyTarget'
import type { ReceiptProcessingMessage } from '../../core-app/lambda/shared/types'

describe('LINE reply target resolution', () => {
  test('uses groupId for group source', () => {
    expect(resolveLineReplyTarget({ type: 'group', userId: 'U123', groupId: 'G456' })).toEqual({
      lineReplyToId: 'G456',
      lineReplySourceType: 'group',
    })
  })

  test('uses roomId for room source', () => {
    expect(resolveLineReplyTarget({ type: 'room', userId: 'U123', roomId: 'R456' })).toEqual({
      lineReplyToId: 'R456',
      lineReplySourceType: 'room',
    })
  })

  test('uses userId for user source', () => {
    expect(resolveLineReplyTarget({ type: 'user', userId: 'U123' })).toEqual({
      lineReplyToId: 'U123',
      lineReplySourceType: 'user',
    })
  })

  test('does not fall back to userId when group target is missing', () => {
    expect(resolveLineReplyTarget({ type: 'group', userId: 'U123' })).toBeUndefined()
  })

  test('push target prefers the original conversation target', () => {
    const message: ReceiptProcessingMessage = {
      lineUserId: 'U123',
      lineDisplayName: '太郎',
      lineMessageId: 'M123',
      lineReplyToId: 'G456',
      lineReplySourceType: 'group',
      bucket: 'bucket',
      key: 'receipts/U123/M123.jpg',
      imageUrl: 'https://example.com/receipts/U123/M123.jpg',
    }

    expect(receiptPushTargetId(message)).toBe('G456')
  })
})
