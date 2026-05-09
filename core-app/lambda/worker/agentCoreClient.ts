import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from '@aws-sdk/client-bedrock-agentcore'
import { randomUUID } from 'node:crypto'
import type { AgentReceiptResult, ReceiptProcessingMessage } from '../shared/types'

export class AgentCoreClient {
  private readonly client = new BedrockAgentCoreClient({})

  constructor(private readonly agentRuntimeArn: string) {}

  async invokeReceiptAgent(message: ReceiptProcessingMessage): Promise<AgentReceiptResult> {
    const response = await this.client.send(
      new InvokeAgentRuntimeCommand({
        agentRuntimeArn: this.agentRuntimeArn,
        runtimeSessionId: randomUUID(),
        payload: JSON.stringify(message),
        contentType: 'application/json',
        qualifier: 'DEFAULT',
      }),
    )

    const responseText = await decodeResponsePayload(response.response)
    return JSON.parse(responseText) as AgentReceiptResult
  }
}

async function decodeResponsePayload(payload: unknown): Promise<string> {
  if (!payload) {
    throw new Error('AgentCore response did not include payload')
  }

  if (payload instanceof Uint8Array) {
    return new TextDecoder().decode(payload)
  }

  if (typeof payload === 'string') {
    return payload
  }

  if (typeof (payload as { transformToString?: () => Promise<string> }).transformToString === 'function') {
    return await (payload as { transformToString: () => Promise<string> }).transformToString()
  }

  if (Symbol.asyncIterator in Object(payload)) {
    const chunks: Uint8Array[] = []
    for await (const chunk of payload as AsyncIterable<Uint8Array>) {
      chunks.push(chunk)
    }
    return new TextDecoder().decode(Buffer.concat(chunks))
  }

  throw new Error('Unsupported AgentCore response payload type')
}
