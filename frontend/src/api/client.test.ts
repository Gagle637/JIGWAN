import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch } from './client'

function mockFetchOnce(response: Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(response)),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiFetch', () => {
  it('성공 응답은 JSON을 그대로 반환한다', async () => {
    mockFetchOnce(
      new Response(JSON.stringify({ status: 'ready' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    const result = await apiFetch<{ status: string }>('/api/health')

    expect(result).toEqual({ status: 'ready' })
  })

  it('{"error":{"code","message"}} 응답은 ApiError(code, message, status)로 던진다', async () => {
    mockFetchOnce(
      new Response(
        JSON.stringify({ error: { code: 'BUILDING_NOT_FOUND', message: '건물을 찾을 수 없습니다.' } }),
        { status: 404, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    await expect(apiFetch('/api/buildings/999')).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError)
      const apiError = err as ApiError
      expect(apiError.code).toBe('BUILDING_NOT_FOUND')
      expect(apiError.message).toBe('건물을 찾을 수 없습니다.')
      expect(apiError.status).toBe(404)
      return true
    })
  })

  it('JSON이 아닌 오류 응답(예: 502)도 죽지 않고 ApiError가 된다', async () => {
    mockFetchOnce(
      new Response('<html>Bad Gateway</html>', {
        status: 502,
        statusText: 'Bad Gateway',
        headers: { 'Content-Type': 'text/html' },
      }),
    )

    await expect(apiFetch('/api/health')).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError)
      const apiError = err as ApiError
      expect(apiError.status).toBe(502)
      expect(apiError.code).toBe('UNKNOWN')
      return true
    })
  })
})
