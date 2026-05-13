import type { LineWebhookEvent, ReceiptProcessingMessage } from './types'

export interface LineReplyTarget {
  lineReplyToId: string
  lineReplySourceType: string
}

export function resolveLineReplyTarget(source: LineWebhookEvent['source']): LineReplyTarget | undefined {
  if (!source) {
    return undefined
  }

  if (source.type === 'group') {
    return source.groupId
      ? {
          lineReplyToId: source.groupId,
          lineReplySourceType: source.type,
        }
      : undefined
  }

  if (source.type === 'room') {
    return source.roomId
      ? {
          lineReplyToId: source.roomId,
          lineReplySourceType: source.type,
        }
      : undefined
  }

  if (source.userId) {
    return {
      lineReplyToId: source.userId,
      lineReplySourceType: source.type,
    }
  }

  return undefined
}

export function receiptPushTargetId(message: ReceiptProcessingMessage): string {
  return message.lineReplyToId || message.lineUserId
}
