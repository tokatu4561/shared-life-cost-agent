export type ReceiptCategory = '食費' | '日用品' | 'その他'

export interface ReceiptProcessingMessage {
  lineUserId: string
  lineMessageId: string
  bucket: string
  key: string
  imageS3Uri: string
}

export interface AgentReceipt {
  lineMessageId: string
  receiptDate: string | null
  store: string | null
  category: ReceiptCategory
  total: number | null
  imageS3Uri: string
}

export interface AgentReceiptResult {
  success: boolean
  status: 'registered' | 'skipped' | 'failed'
  reason?: 'missing_required_fields' | 'configuration_error' | 'sheets_error' | 'ocr_error' | 'normalization_error' | 'failed'
  replyMessage: string
  errorDetail?: string
  receipt?: AgentReceipt
  sheet?: {
    sheetName: string
    updatedRange: string
    alreadyRegistered?: boolean
  }
}

export interface LineWebhookBody {
  events?: LineWebhookEvent[]
}

export interface LineWebhookEvent {
  type: string
  replyToken?: string
  source?: {
    type: string
    userId?: string
  }
  message?: {
    id: string
    type: string
  }
}
