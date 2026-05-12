import { LineClient } from '../../core-app/lambda/webhook/lineClient'

describe('LineClient', () => {
  const originalFetch = global.fetch

  afterEach(() => {
    global.fetch = originalFetch
    jest.restoreAllMocks()
  })

  test('fetches profile display name', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ displayName: '太郎' }),
    })
    global.fetch = fetchMock as unknown as typeof fetch

    await expect(new LineClient('token').getProfile('U123')).resolves.toEqual({ displayName: '太郎' })
    expect(fetchMock).toHaveBeenCalledWith('https://api.line.me/v2/bot/profile/U123', {
      method: 'GET',
      headers: {
        Authorization: 'Bearer token',
      },
    })
  })

  test('throws when profile request fails', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
    }) as unknown as typeof fetch

    await expect(new LineClient('token').getProfile('U123')).rejects.toThrow('Failed to fetch LINE profile: 404')
  })
})
