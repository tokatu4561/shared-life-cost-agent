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

  test('fetches group member profile display name', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ displayName: 'ゆきほ' }),
    })
    global.fetch = fetchMock as unknown as typeof fetch

    await expect(new LineClient('token').getGroupMemberProfile('G001', 'U123')).resolves.toEqual({
      displayName: 'ゆきほ',
    })
    expect(fetchMock).toHaveBeenCalledWith('https://api.line.me/v2/bot/group/G001/member/U123', {
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

  test('throws when group member profile request fails', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
    }) as unknown as typeof fetch

    await expect(new LineClient('token').getGroupMemberProfile('G001', 'U123')).rejects.toThrow(
      'Failed to fetch LINE group member profile: 404',
    )
  })
})
