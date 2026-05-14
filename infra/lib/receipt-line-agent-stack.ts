import * as path from 'node:path'
import * as cdk from 'aws-cdk-lib'
import { Duration, RemovalPolicy } from 'aws-cdk-lib'
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2'
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations'
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb'
import * as iam from 'aws-cdk-lib/aws-iam'
import * as lambda from 'aws-cdk-lib/aws-lambda'
import * as lambdaNodejs from 'aws-cdk-lib/aws-lambda-nodejs'
import * as logs from 'aws-cdk-lib/aws-logs'
import * as s3 from 'aws-cdk-lib/aws-s3'
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager'
import * as sqs from 'aws-cdk-lib/aws-sqs'
import { Construct } from 'constructs'
import * as agentcore from '@aws-cdk/aws-bedrock-agentcore-alpha'

export interface ReceiptLineAgentStackProps extends cdk.StackProps {
  readonly envName: string
  readonly bedrockModelId: string
  readonly secretNames?: {
    readonly line?: string
    readonly google?: string
  }
}

export class ReceiptLineAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ReceiptLineAgentStackProps) {
    super(scope, id, props)

    const resourcePrefix = `receipt-line-agent-${props.envName}`
    const secretPrefix = `receipt-line-agent/${props.envName}`
    const appRoot = path.join(__dirname, '../..', 'core-app')

    const lineSecret = this.resolveSecret(
      'LineSecret',
      props.secretNames?.line,
      `${secretPrefix}/line`,
      'LINE Messaging API settings as JSON: channelSecret, channelAccessToken, optional channelId and allowedExpenseQuerySourceIds.',
    )

    const googleSecret = this.resolveSecret(
      'GoogleSecret',
      props.secretNames?.google,
      `${secretPrefix}/google`,
      'Google Sheets settings as JSON: spreadsheetId and serviceAccount.',
    )

    const receiptImagesBucket = new s3.Bucket(this, 'ReceiptImagesBucket', {
      blockPublicAccess: new s3.BlockPublicAccess({
        blockPublicAcls: true,
        blockPublicPolicy: false,
        ignorePublicAcls: true,
        restrictPublicBuckets: false,
      }),
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      lifecycleRules: [
        {
          id: 'ExpireReceiptImagesAfter90Days',
          expiration: Duration.days(90),
        },
      ],
      removalPolicy: RemovalPolicy.RETAIN,
    })
    receiptImagesBucket.addToResourcePolicy(
      new iam.PolicyStatement({
        sid: 'AllowPublicReadReceiptImages',
        actions: ['s3:GetObject'],
        principals: [new iam.AnyPrincipal()],
        resources: [receiptImagesBucket.arnForObjects('receipts/*')],
      }),
    )

    const receiptEventsTable = new dynamodb.Table(this, 'ReceiptEventsTable', {
      tableName: `${resourcePrefix}-events`,
      partitionKey: { name: 'lineMessageId', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.RETAIN,
      pointInTimeRecoverySpecification: {
        pointInTimeRecoveryEnabled: true,
      },
    })

    const deadLetterQueue = new sqs.Queue(this, 'ReceiptProcessingDeadLetterQueue', {
      queueName: `${resourcePrefix}-processing-dlq`,
      retentionPeriod: Duration.days(14),
    })

    const processingQueue = new sqs.Queue(this, 'ReceiptProcessingQueue', {
      queueName: `${resourcePrefix}-processing`,
      visibilityTimeout: Duration.minutes(5),
      retentionPeriod: Duration.days(4),
      deadLetterQueue: {
        queue: deadLetterQueue,
        maxReceiveCount: 3,
      },
    })
    const bedrockInvokePolicyStatements = this.bedrockInvokePolicyStatements(props.bedrockModelId)

    const agentRuntime = new agentcore.Runtime(this, 'ReceiptAgentRuntime', {
      runtimeName: `receiptAgent_${props.envName}`,
      agentRuntimeArtifact: agentcore.AgentRuntimeArtifact.fromAsset(path.join(appRoot, 'agent')),
      environmentVariables: {
        AWS_REGION: this.region,
        AWS_DEFAULT_REGION: this.region,
        BEDROCK_MODEL_ID: props.bedrockModelId,
        GOOGLE_SECRET_ARN: googleSecret.secretArn,
      },
    })

    agentRuntime.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['s3:GetObject'],
        resources: [receiptImagesBucket.arnForObjects('*')],
      }),
    )
    agentRuntime.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['secretsmanager:GetSecretValue'],
        resources: this.secretReadArns(googleSecret),
      }),
    )
    agentRuntime.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
        resources: bedrockInvokePolicyStatements.inferenceProfileResources,
      }),
    )
    if (bedrockInvokePolicyStatements.foundationModelResources.length > 0) {
      agentRuntime.addToRolePolicy(
        new iam.PolicyStatement({
          actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
          resources: bedrockInvokePolicyStatements.foundationModelResources,
          conditions: bedrockInvokePolicyStatements.inferenceProfileArn
            ? {
                StringLike: {
                  'bedrock:InferenceProfileArn': bedrockInvokePolicyStatements.inferenceProfileArn,
                },
              }
            : undefined,
        }),
      )
    }

    const commonLambdaProps = {
      runtime: lambda.Runtime.NODEJS_22_X,
      architecture: lambda.Architecture.ARM_64,
      memorySize: 256,
      logRetention: logs.RetentionDays.ONE_MONTH,
      bundling: {
        minify: true,
        sourceMap: true,
        target: 'node22',
      },
    } satisfies Pick<
      lambdaNodejs.NodejsFunctionProps,
      'runtime' | 'architecture' | 'memorySize' | 'logRetention' | 'bundling'
    >

    const webhookFunction = new lambdaNodejs.NodejsFunction(this, 'WebhookFunction', {
      ...commonLambdaProps,
      functionName: `${resourcePrefix}-webhook`,
      entry: path.join(appRoot, 'lambda/webhook/handler.ts'),
      handler: 'handler',
      timeout: Duration.seconds(30),
      environment: {
        LINE_SECRET_ARN: lineSecret.secretArn,
        RECEIPT_IMAGE_BUCKET: receiptImagesBucket.bucketName,
        RECEIPT_EVENTS_TABLE: receiptEventsTable.tableName,
        RECEIPT_PROCESSING_QUEUE_URL: processingQueue.queueUrl,
        AGENT_CORE_RUNTIME_ARN: agentRuntime.agentRuntimeArn,
      },
    })

    const workerFunction = new lambdaNodejs.NodejsFunction(this, 'WorkerFunction', {
      ...commonLambdaProps,
      functionName: `${resourcePrefix}-worker`,
      entry: path.join(appRoot, 'lambda/worker/handler.ts'),
      handler: 'handler',
      timeout: Duration.minutes(2),
      environment: {
        LINE_SECRET_ARN: lineSecret.secretArn,
        RECEIPT_EVENTS_TABLE: receiptEventsTable.tableName,
        AGENT_CORE_RUNTIME_ARN: agentRuntime.agentRuntimeArn,
      },
    })

    lineSecret.grantRead(webhookFunction)
    receiptImagesBucket.grantWrite(webhookFunction)
    receiptEventsTable.grantReadWriteData(webhookFunction)
    processingQueue.grantSendMessages(webhookFunction)
    webhookFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['bedrock-agentcore:InvokeAgentRuntime'],
        resources: [
          agentRuntime.agentRuntimeArn,
          `${agentRuntime.agentRuntimeArn}/runtime-endpoint/*`,
        ],
      }),
    )

    lineSecret.grantRead(workerFunction)
    receiptEventsTable.grantReadWriteData(workerFunction)
    workerFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['bedrock-agentcore:InvokeAgentRuntime'],
        resources: [
          agentRuntime.agentRuntimeArn,
          `${agentRuntime.agentRuntimeArn}/runtime-endpoint/*`,
        ],
      }),
    )
    workerFunction.addEventSourceMapping('ReceiptProcessingEventSource', {
      eventSourceArn: processingQueue.queueArn,
      batchSize: 1,
    })
    processingQueue.grantConsumeMessages(workerFunction)

    const api = new apigwv2.HttpApi(this, 'ReceiptLineAgentApi', {
      apiName: `${resourcePrefix}-api`,
      corsPreflight: {
        allowMethods: [apigwv2.CorsHttpMethod.POST],
        allowOrigins: ['*'],
      },
    })
    api.addRoutes({
      path: '/line/webhook',
      methods: [apigwv2.HttpMethod.POST],
      integration: new integrations.HttpLambdaIntegration('WebhookIntegration', webhookFunction),
    })

    new cdk.CfnOutput(this, 'WebhookUrl', {
      value: `${api.apiEndpoint}/line/webhook`,
    })
    new cdk.CfnOutput(this, 'ReceiptImagesBucketName', {
      value: receiptImagesBucket.bucketName,
    })
    new cdk.CfnOutput(this, 'ReceiptEventsTableName', {
      value: receiptEventsTable.tableName,
    })
    new cdk.CfnOutput(this, 'ReceiptProcessingQueueUrl', {
      value: processingQueue.queueUrl,
    })
    new cdk.CfnOutput(this, 'ReceiptAgentRuntimeArn', {
      value: agentRuntime.agentRuntimeArn,
    })
  }

  private resolveSecret(
    id: string,
    providedSecretName: string | undefined,
    defaultSecretName: string,
    description: string,
  ): secretsmanager.ISecret {
    if (providedSecretName?.trim()) {
      return secretsmanager.Secret.fromSecretNameV2(this, id, providedSecretName.trim())
    }

    return new secretsmanager.Secret(this, id, {
      secretName: defaultSecretName,
      description,
    })
  }

  private secretReadArns(secret: secretsmanager.ISecret): string[] {
    return [
      secret.secretArn,
      `${secret.secretArn}*`,
      cdk.Stack.of(this).formatArn({
        service: 'secretsmanager',
        resource: 'secret',
        resourceName: `${secret.secretName}-*`,
      }),
    ]
  }

  private bedrockInvokePolicyStatements(bedrockModelId: string): {
    inferenceProfileResources: string[]
    foundationModelResources: string[]
    inferenceProfileArn?: string
  } {
    if (bedrockModelId.startsWith('arn:')) {
      return {
        inferenceProfileResources: [bedrockModelId],
        foundationModelResources: [],
      }
    }

    if (!this.isInferenceProfileId(bedrockModelId)) {
      return {
        inferenceProfileResources: [
          cdk.Stack.of(this).formatArn({
            service: 'bedrock',
            resource: 'foundation-model',
            resourceName: bedrockModelId,
            region: this.region,
            account: '',
          }),
        ],
        foundationModelResources: [],
      }
    }

    const inferenceProfileArn = cdk.Stack.of(this).formatArn({
      service: 'bedrock',
      resource: 'inference-profile',
      resourceName: bedrockModelId,
    })

    return {
      inferenceProfileResources: [inferenceProfileArn],
      foundationModelResources: [
        cdk.Stack.of(this).formatArn({
          service: 'bedrock',
          resource: 'foundation-model',
          resourceName: this.foundationModelIdFromInferenceProfileId(bedrockModelId),
          region: '*',
          account: '',
        }),
      ],
      inferenceProfileArn,
    }
  }

  private isInferenceProfileId(bedrockModelId: string): boolean {
    return /^(global|us|eu|au)\./.test(bedrockModelId)
  }

  private foundationModelIdFromInferenceProfileId(inferenceProfileId: string): string {
    return inferenceProfileId.replace(/^(global|us|eu|au)\./, '')
  }
}
