export class LineClient {
  constructor(private readonly channelAccessToken: string) {}

  async getProfile(userId: string): Promise<{ displayName: string }> {
    const response = await fetch(`https://api.line.me/v2/bot/profile/${encodeURIComponent(userId)}`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${this.channelAccessToken}`,
      },
    })

    if (!response.ok) {
      throw new Error(`Failed to fetch LINE profile: ${response.status}`)
    }

    const profile = (await response.json()) as { displayName?: string }
    return { displayName: profile.displayName ?? '' }
  }

  async getGroupMemberProfile(groupId: string, userId: string): Promise<{ displayName: string }> {
    const response = await fetch(
      `https://api.line.me/v2/bot/group/${encodeURIComponent(groupId)}/member/${encodeURIComponent(userId)}`,
      {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${this.channelAccessToken}`,
        },
      },
    )

    if (!response.ok) {
      throw new Error(`Failed to fetch LINE group member profile: ${response.status}`)
    }

    const profile = (await response.json()) as { displayName?: string }
    return { displayName: profile.displayName ?? '' }
  }

  async replyText(replyToken: string, text: string): Promise<void> {
    await this.postJson('https://api.line.me/v2/bot/message/reply', {
      replyToken,
      messages: [{ type: 'text', text }],
    })
  }

  async getMessageContent(messageId: string): Promise<Uint8Array> {
    const response = await fetch(`https://api-data.line.me/v2/bot/message/${messageId}/content`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${this.channelAccessToken}`,
      },
    })

    if (!response.ok) {
      throw new Error(`Failed to fetch LINE message content: ${response.status}`)
    }

    return new Uint8Array(await response.arrayBuffer())
  }

  private async postJson(url: string, body: unknown): Promise<void> {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.channelAccessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      throw new Error(`LINE API request failed: ${response.status}`)
    }
  }
}
