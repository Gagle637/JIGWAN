const DEFAULT_API_BASE = 'http://localhost:8000'

function apiBase(): string {
  return import.meta.env.VITE_API_BASE ?? DEFAULT_API_BASE
}

/** 에러 응답(docs/spec.md 6-3: {"error":{"code","message"}})을 던질 때 쓰는 타입. */
export class ApiError extends Error {
  code: string
  status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  const text = await response.text()
  try {
    const body = JSON.parse(text) as { error?: { code?: string; message?: string } }
    if (body.error?.code && body.error?.message) {
      return new ApiError(body.error.code, body.error.message, response.status)
    }
  } catch {
    // JSON이 아닌 응답(예: 502 HTML 에러 페이지) — 아래 fallback으로 내려간다.
  }
  return new ApiError('UNKNOWN', text || response.statusText, response.status)
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })

  if (!response.ok) {
    throw await toApiError(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
