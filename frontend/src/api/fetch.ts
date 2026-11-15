interface ApiErrorBody {
  code?: string;
  message?: string;
}

interface ApiFetchOptions {
  method?: string;
  json?: unknown;
  params?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
}

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

const defaultApiBase = 'http://localhost:8000';

function apiBase(): string {
  return import.meta.env.VITE_API_BASE ?? defaultApiBase;
}

function parseErrorBody(text: string): ApiErrorBody | null {
  try {
    const body = JSON.parse(text) as { error?: ApiErrorBody };
    return body.error ?? null;
  } catch {
    return null;
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  const text = await response.text();
  const error = parseErrorBody(text);
  if (error?.code && error?.message) {
    return new ApiError(error.code, error.message, response.status);
  }
  return new ApiError('UNKNOWN', '서버 오류가 발생했습니다.', response.status);
}

function buildUrl(path: string, params?: ApiFetchOptions['params']): string {
  const url = resolveApiUrl(path);
  if (!params) return url;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const queryString = query.toString();
  return queryString ? `${url}?${queryString}` : url;
}

export function resolveApiUrl(path: string): string {
  if (!path || path.startsWith('http')) return path;
  return `${apiBase()}${path}`;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { method, json, params, signal } = options;
  const headers = new Headers();
  const body = json !== undefined ? JSON.stringify(json) : undefined;
  if (body !== undefined) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, params), { method, headers, body, signal });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError('NETWORK', '서버에 연결할 수 없습니다.', 0);
  }

  if (!response.ok) {
    throw await toApiError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
