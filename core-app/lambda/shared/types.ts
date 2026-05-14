export type ReceiptCategory = '食費' | '日用品' | 'その他'
export type AgentTask = 'receipt' | 'expense_query'

export interface ReceiptProcessingMessage {
  task?: 'receipt'
  lineUserId: string
  lineDisplayName: string
  lineMessageId: string
  lineReplyToId: string
  lineReplySourceType: string
  bucket: string
  key: string
  imageUrl: string
}

export interface ExpenseQueryMessage {
  task: 'expense_query'
  lineUserId: string
  lineDisplayName: string
  lineMessageId: string
  text: string
}

export interface AgentReceipt {
  lineUserId: string
  lineDisplayName: string
  lineMessageId: string
  receiptDate: string | null
  store: string | null
  category: ReceiptCategory
  total: number | null
  imageUrl: string
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

export interface AgentExpenseQueryResult {
  success: boolean
  status: 'answered' | 'unsupported' | 'failed'
  reason?: 'unsupported_query' | 'configuration_error' | 'sheets_error' | 'classification_error' | 'failed'
  replyMessage: string
  errorDetail?: string
}

export type AgentCoreMessage = ReceiptProcessingMessage | ExpenseQueryMessage
export type AgentCoreResult = AgentReceiptResult | AgentExpenseQueryResult

export interface LineWebhookBody {
  events?: LineWebhookEvent[]
}

export interface LineWebhookEvent {
  type: string
  replyToken?: string
  source?: {
    type: string
    userId?: string
    groupId?: string
    roomId?: string
  }
  message?: {
    id: string
    type: string
    text?: string
  }
}
