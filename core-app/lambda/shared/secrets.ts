import { GetSecretValueCommand, SecretsManagerClient } from '@aws-sdk/client-secrets-manager'

export interface LineSecret {
  channelSecret: string
  channelAccessToken: string
  channelId?: string
  allowedExpenseQuerySourceIds?: string[]
}

const secretsClient = new SecretsManagerClient({})

export async function getJsonSecret<T>(secretId: string): Promise<T> {
  const result = await secretsClient.send(new GetSecretValueCommand({ SecretId: secretId }))
  if (!result.SecretString) {
    throw new Error(`Secret ${secretId} does not contain SecretString`)
  }
  return JSON.parse(result.SecretString) as T
}

export function requireSecretValue(value: string | undefined, key: string, secretId: string): string {
  if (!value) {
    throw new Error(`Secret ${secretId} is missing required key: ${key}`)
  }
  return value
}
