import type { SQSHandler } from 'aws-lambda'
import { DynamoDBClient } from '@aws-sdk/client-dynamodb'
import { DynamoDBDocumentClient, UpdateCommand } from '@aws-sdk/lib-dynamodb'
import { requiredEnv } from '../shared/env'
import { logger } from '../shared/logger'
import { getJsonSecret, requireSecretValue, type LineSecret } from '../shared/secrets'
import type { AgentReceiptResult, ReceiptProcessingMessage } from '../shared/types'
import { AgentCoreClient } from './agentCoreClient'
import { LineClient } from './lineClient'

const dynamoClient = DynamoDBDocumentClient.from(new DynamoDBClient({}))

const lineSecretArn = requiredEnv('LINE_SECRET_ARN')
const receiptEventsTable = requiredEnv('RECEIPT_EVENTS_TABLE')
const agentCoreRuntimeArn = requiredEnv('AGENT_CORE_RUNTIME_ARN')

const agentCoreClient = new AgentCoreClient(agentCoreRuntimeArn)
let cachedLineSecret: LineSecret | undefined

export const handler: SQSHandler = async (event) => {
  const lineClient = new LineClient(await getLineChannelAccessToken())

  for (const record of event.Records) {
    const message = JSON.parse(record.body) as ReceiptProcessingMessage
    await processReceipt(message, lineClient)
  }
}

async function processReceipt(message: ReceiptProcessingMessage, lineClient: LineClient): Promise<void> {
  await updateReceiptEvent(message.lineMessageId, {
    status: 'PROCESSING',
    updatedAt: new Date().toISOString(),
  })

  try {
    const agentResult = await agentCoreClient.invokeReceiptAgent(message)
    await handleAgentResult(message, agentResult, lineClient)
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Unexpected worker failure', {
      lineMessageId: message.lineMessageId,
      error: errorMessage,
    })
    await updateReceiptEvent(message.lineMessageId, {
      status: 'FAILED',
      errorMessage,
      updatedAt: new Date().toISOString(),
    })
    throw error
  }
}

async function handleAgentResult(
  message: ReceiptProcessingMessage,
  result: AgentReceiptResult,
  lineClient: LineClient,
): Promise<void> {
  const status = result.success ? 'SUCCEEDED' : result.reason === 'missing_required_fields' ? 'SKIPPED' : 'FAILED'
  const updateValues: Record<string, string | number | undefined> = {
    status,
    agentStatus: result.status,
    reason: result.reason,
    errorMessage: result.errorDetail,
    updatedAt: new Date().toISOString(),
    receiptDate: result.receipt?.receiptDate ?? undefined,
    lineUserIdFromAgent: result.receipt?.lineUserId,
    lineDisplayNameFromAgent: result.receipt?.lineDisplayName,
    lineMessageIdFromAgent: result.receipt?.lineMessageId,
    store: result.receipt?.store ?? undefined,
    category: result.receipt?.category,
    total: result.receipt?.total ?? undefined,
    sheetName: result.sheet?.sheetName,
    updatedRange: result.sheet?.updatedRange,
    alreadyRegistered:
      result.sheet?.alreadyRegistered === undefined ? undefined : String(result.sheet.alreadyRegistered),
  }

  await updateReceiptEvent(message.lineMessageId, updateValues)
  try {
    await lineClient.pushText(message.lineUserId, result.replyMessage)
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Failed to push LINE result message', {
      lineMessageId: message.lineMessageId,
      error: errorMessage,
    })
    try {
      await updateReceiptEvent(message.lineMessageId, {
        pushStatus: 'FAILED',
        pushErrorMessage: errorMessage,
        updatedAt: new Date().toISOString(),
      })
    } catch (updateError) {
      logger.error('Failed to record LINE push failure', {
        lineMessageId: message.lineMessageId,
        error: updateError instanceof Error ? updateError.message : String(updateError),
      })
    }
  }
}

async function updateReceiptEvent(
  lineMessageId: string,
  values: Record<string, string | number | undefined>,
): Promise<void> {
  const entries = Object.entries(values).filter((entry): entry is [string, string | number] => entry[1] !== undefined)
  const names: Record<string, string> = {}
  const expressionValues: Record<string, string | number> = {}
  const assignments: string[] = []

  for (const [key, value] of entries) {
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

async function getLineChannelAccessToken(): Promise<string> {
  const secret = await getLineSecret()
  return requireSecretValue(secret.channelAccessToken, 'channelAccessToken', lineSecretArn)
}

async function getLineSecret(): Promise<LineSecret> {
  cachedLineSecret ??= await getJsonSecret<LineSecret>(lineSecretArn)
  return cachedLineSecret
}
