import { createHmac } from 'node:crypto'
import { verifyLineSignature } from '../../core-app/lambda/webhook/signature'

describe('verifyLineSignature', () => {
  test('accepts a valid LINE signature', () => {
    const body = JSON.stringify({ events: [] })
    const secret = 'channel-secret'
    const signature = createHmac('sha256', secret).update(body).digest('base64')

    expect(verifyLineSignature(body, secret, signature)).toBe(true)
  })

  test('rejects an invalid LINE signature', () => {
    const body = JSON.stringify({ events: [] })

    expect(verifyLineSignature(body, 'channel-secret', 'invalid')).toBe(false)
  })
})
