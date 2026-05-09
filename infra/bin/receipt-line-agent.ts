#!/usr/bin/env node
import * as fs from 'node:fs'
import * as path from 'node:path'
import * as cdk from 'aws-cdk-lib'
import { ReceiptLineAgentStack } from '../lib/receipt-line-agent-stack'

loadDotEnv(path.join(__dirname, '..', '.env'))

const app = new cdk.App()

const envName = app.node.tryGetContext('envName') ?? 'prod'
const awsRegion = app.node.tryGetContext('awsRegion') ?? process.env.CDK_DEFAULT_REGION ?? 'ap-northeast-1'
const account = process.env.CDK_DEFAULT_ACCOUNT

new ReceiptLineAgentStack(app, `ReceiptLineAgentStack-${envName}`, {
  envName,
  bedrockModelId:
    process.env.BEDROCK_MODEL_ID ??
    app.node.tryGetContext('bedrockModelId') ??
    'global.anthropic.claude-haiku-4-5-20251001-v1:0',
  secretNames: {
    line: process.env.LINE_SECRET_NAME,
    google: process.env.GOOGLE_SECRET_NAME,
  },
  env: {
    account,
    region: awsRegion,
  },
})

function loadDotEnv(filePath: string): void {
  if (!fs.existsSync(filePath)) {
    return
  }

  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/)
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) {
      continue
    }

    const separatorIndex = trimmed.indexOf('=')
    if (separatorIndex === -1) {
      continue
    }

    const key = trimmed.slice(0, separatorIndex).trim()
    const rawValue = trimmed.slice(separatorIndex + 1).trim()
    const value = rawValue.replace(/^['"]|['"]$/g, '')
    process.env[key] ??= value
  }
}
