import * as cdk from 'aws-cdk-lib'
import { Template, Match } from 'aws-cdk-lib/assertions'
import { ReceiptLineAgentStack } from '../lib/receipt-line-agent-stack'

function synthTemplate(): Template {
  const app = new cdk.App()
  const stack = new ReceiptLineAgentStack(app, 'TestReceiptLineAgentStack', {
    envName: 'prod',
    bedrockModelId: 'global.anthropic.claude-haiku-4-5-20251001-v1:0',
    env: { account: '123456789012', region: 'ap-northeast-1' },
  })
  return Template.fromStack(stack)
}

function synthTemplateWithImportedSecrets(): Template {
  const app = new cdk.App()
  const stack = new ReceiptLineAgentStack(app, 'TestReceiptLineAgentStackWithImportedSecrets', {
    envName: 'prod',
    bedrockModelId: 'global.anthropic.claude-haiku-4-5-20251001-v1:0',
    secretNames: {
      line: 'existing/line',
      google: 'existing/google',
    },
    env: { account: '123456789012', region: 'ap-northeast-1' },
  })
  return Template.fromStack(stack)
}

describe('ReceiptLineAgentStack', () => {
  test('creates public HTTP API and webhook route', () => {
    const template = synthTemplate()
    template.resourceCountIs('AWS::ApiGatewayV2::Api', 1)
    template.hasResourceProperties('AWS::ApiGatewayV2::Route', {
      RouteKey: 'POST /line/webhook',
    })
  })

  test('creates queues with a DLQ', () => {
    const template = synthTemplate()
    template.resourceCountIs('AWS::SQS::Queue', 2)
    template.hasResourceProperties('AWS::SQS::Queue', {
      RedrivePolicy: Match.objectLike({
        maxReceiveCount: 3,
      }),
    })
  })

  test('creates public-readable receipt bucket with 90 day expiration', () => {
    const template = synthTemplate()
    template.hasResourceProperties('AWS::S3::Bucket', {
      LifecycleConfiguration: {
        Rules: Match.arrayWith([
          Match.objectLike({
            ExpirationInDays: 90,
            Status: 'Enabled',
          }),
        ]),
      },
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: false,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: false,
      },
    })
    template.hasResourceProperties('AWS::S3::BucketPolicy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Sid: 'AllowPublicReadReceiptImages',
            Action: 's3:GetObject',
            Effect: 'Allow',
            Principal: {
              AWS: '*',
            },
            Resource: {
              'Fn::Join': Match.arrayWith([
                Match.arrayWith([
                  Match.objectLike({
                    'Fn::GetAtt': [Match.stringLikeRegexp('ReceiptImagesBucket'), 'Arn'],
                  }),
                  '/receipts/*',
                ]),
              ]),
            },
          }),
        ]),
      }),
    })
  })

  test('creates idempotency table keyed by lineMessageId', () => {
    const template = synthTemplate()
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      KeySchema: [{ AttributeName: 'lineMessageId', KeyType: 'HASH' }],
      AttributeDefinitions: [{ AttributeName: 'lineMessageId', AttributeType: 'S' }],
      BillingMode: 'PAY_PER_REQUEST',
    })
  })

  test('sets Lambda log retention to 30 days', () => {
    const template = synthTemplate()
    template.resourceCountIs('Custom::LogRetention', 2)
    template.hasResourceProperties('Custom::LogRetention', {
      RetentionInDays: 30,
    })
  })

  test('creates secrets and AgentCore runtime', () => {
    const template = synthTemplate()
    template.resourceCountIs('AWS::SecretsManager::Secret', 2)
    template.resourceCountIs('AWS::BedrockAgentCore::Runtime', 1)
  })

  test('can import existing secrets instead of creating new ones', () => {
    const template = synthTemplateWithImportedSecrets()
    template.resourceCountIs('AWS::SecretsManager::Secret', 0)
    template.resourceCountIs('AWS::BedrockAgentCore::Runtime', 1)
  })

  test('grants AgentCore invocation permission to worker', () => {
    const template = synthTemplate()
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: 'bedrock-agentcore:InvokeAgentRuntime',
            Effect: 'Allow',
            Resource: Match.arrayWith([
              {
                'Fn::GetAtt': [Match.stringLikeRegexp('ReceiptAgentRuntime'), 'AgentRuntimeArn'],
              },
              {
                'Fn::Join': [
                  '',
                  [
                    {
                      'Fn::GetAtt': [Match.stringLikeRegexp('ReceiptAgentRuntime'), 'AgentRuntimeArn'],
                    },
                    '/runtime-endpoint/*',
                  ],
                ],
              },
            ]),
          }),
        ]),
      }),
    })
  })

  test('allows webhook to invoke AgentCore for text queries', () => {
    const template = synthTemplate()
    template.hasResourceProperties('AWS::Lambda::Function', {
      Environment: {
        Variables: Match.objectLike({
          AGENT_CORE_RUNTIME_ARN: {
            'Fn::GetAtt': [Match.stringLikeRegexp('ReceiptAgentRuntime'), 'AgentRuntimeArn'],
          },
        }),
      },
    })
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: 'bedrock-agentcore:InvokeAgentRuntime',
            Effect: 'Allow',
            Resource: Match.arrayWith([
              {
                'Fn::GetAtt': [Match.stringLikeRegexp('ReceiptAgentRuntime'), 'AgentRuntimeArn'],
              },
              {
                'Fn::Join': [
                  '',
                  [
                    {
                      'Fn::GetAtt': [Match.stringLikeRegexp('ReceiptAgentRuntime'), 'AgentRuntimeArn'],
                    },
                    '/runtime-endpoint/*',
                  ],
                ],
              },
            ]),
          }),
        ]),
      }),
    })
  })

  test('scopes Bedrock model invocation to configured inference profile', () => {
    const template = synthTemplate()
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
            Effect: 'Allow',
            Resource: {
              'Fn::Join': [
                '',
                [
                  'arn:',
                  { Ref: 'AWS::Partition' },
                  ':bedrock:ap-northeast-1:123456789012:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0',
                ],
              ],
            },
          }),
          Match.objectLike({
            Action: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
            Effect: 'Allow',
            Resource: {
              'Fn::Join': [
                '',
                [
                  'arn:',
                  { Ref: 'AWS::Partition' },
                  ':bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0',
                ],
              ],
            },
            Condition: Match.objectLike({
              StringLike: Match.objectLike({
                'bedrock:InferenceProfileArn': {
                  'Fn::Join': [
                    '',
                    [
                      'arn:',
                      { Ref: 'AWS::Partition' },
                      ':bedrock:ap-northeast-1:123456789012:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0',
                    ],
                  ],
                },
              }),
            }),
          }),
        ]),
      }),
    })
  })

  test('grants Google secret read permission to AgentCore runtime', () => {
    const template = synthTemplateWithImportedSecrets()
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: 'secretsmanager:GetSecretValue',
            Effect: 'Allow',
            Resource: Match.arrayWith([
              {
                'Fn::Join': [
                  '',
                  [
                    'arn:',
                    { Ref: 'AWS::Partition' },
                    ':secretsmanager:ap-northeast-1:123456789012:secret:existing/google',
                  ],
                ],
              },
            ]),
          }),
        ]),
      }),
    })
  })
})
