const defaultApiBase = 'http://localhost:8000'

function apiBase(): string {
  return import.meta.env.VITE_API_BASE ?? defaultApiBase
}

export function resolveApiUrl(path: string): string {
  if (!path || path.startsWith('http')) return path
  return `${apiBase()}${path}`
}

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

function parseErrorBody(text: string): { code?: string; message?: string } | null {
  try {
    const body = JSON.parse(text) as { error?: { code?: string; message?: string } }
    return body.error ?? null
  } catch {
    return null
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  const text = await response.text()
  const error = parseErrorBody(text)
  if (error?.code && error?.message) {
    return new ApiError(error.code, error.message, response.status)
  }
  return new ApiError('UNKNOWN', text || response.statusText, response.status)
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(resolveApiUrl(path), { ...init, headers })

  if (!response.ok) {
    throw await toApiError(response)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}
