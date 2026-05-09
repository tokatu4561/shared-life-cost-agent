export class LineClient {
  constructor(private readonly channelAccessToken: string) {}

  async pushText(to: string, text: string): Promise<void> {
    const response = await fetch('https://api.line.me/v2/bot/message/push', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.channelAccessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        to,
        messages: [{ type: 'text', text }],
      }),
    })

    if (!response.ok) {
      throw new Error(`LINE push message failed: ${response.status}`)
    }
  }
}
