// Single API layer. All backend access goes through here. Base URL only from VITE_API_BASE_URL.
import type { Lang } from '../i18n'

export const API_BASE: string = String(import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
export const MAX_ROWS = Number(import.meta.env.VITE_MAX_ROWS ?? 5000)
export const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_REQUEST_TIMEOUT_MS ?? 90000)
export const MAX_PROMPT = 1000
export const DEFAULT_ROWS = 100
const MOCK = import.meta.env.VITE_MOCK_API === '1'

export type ApiErrorCode = 'invalid_request' | 'payload_too_large' | 'length_required' | 'invalid_spec' | 'rate_limited' | 'ai_quota'
  | 'ai_unavailable' | 'busy' | 'timeout' | 'internal_error' | 'network' | 'aborted' | 'unknown'
const KNOWN: ApiErrorCode[] = ['invalid_request', 'payload_too_large', 'length_required', 'invalid_spec', 'rate_limited', 'ai_quota', 'ai_unavailable', 'busy', 'timeout', 'internal_error']
const BY_STATUS: Record<number, ApiErrorCode> = { 400: 'invalid_request', 411: 'length_required', 413: 'payload_too_large', 422: 'invalid_spec', 429: 'rate_limited', 500: 'internal_error', 503: 'ai_unavailable', 504: 'timeout' }

export class ApiError extends Error {
  constructor(public code: ApiErrorCode, public status?: number, public retryAfter?: number, public requestId?: string) { super(code) }
}

export interface GenerateRequest { prompt: string; language: Lang; max_rows?: number }
export interface PreviewSheet { name: string; columns: string[]; rows: (string | number)[][]; totalRows: number; totalCols: number; synthetic: boolean; calcs: string[] }
export interface GenerateResult { blob: Blob | null; filename: string; rows: number; warnings: number; sheets: PreviewSheet[]; requestId?: string; mock: boolean }

export function parseFilename(cd: string | null): string {
  if (!cd) return 'workbook.xlsx'
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd)
  if (star) { try { return decodeURIComponent(star[1].trim()) } catch { /* fall through */ } }
  const plain = /filename="?([^";]+)"?/i.exec(cd)
  return plain ? plain[1].trim() : 'workbook.xlsx'
}

export function decodePreview(h: string | null): PreviewSheet[] {
  if (!h) return []
  try {
    const bin = atob(h)
    const j = JSON.parse(new TextDecoder().decode(Uint8Array.from(bin, c => c.charCodeAt(0))))
    if (j?.v !== 1 || !Array.isArray(j.sheets)) return []
    return j.sheets.map((s: Record<string, unknown>) => ({
      name: String(s.name ?? ''), columns: (Array.isArray(s.columns) ? s.columns : []).map(String),
      rows: (Array.isArray(s.rows) ? s.rows : []).map((r: unknown) => (Array.isArray(r) ? r : []).map(v => (typeof v === 'number' ? v : String(v ?? '')))),
      totalRows: Number(s.total_rows) || 0, totalCols: Number(s.total_cols) || 0, synthetic: !!s.synthetic,
      calcs: (Array.isArray(s.calcs) ? s.calcs : []).map(String)
    }))
  } catch { return [] }
}

async function toApiError(res: Response): Promise<ApiError> {
  let code: ApiErrorCode = BY_STATUS[res.status] ?? 'unknown'
  let retry: number | undefined, rid: string | undefined
  try {
    const e = (await res.json())?.error
    if (e && KNOWN.includes(e.code)) code = e.code
    else if (e?.code === 'method_not_allowed' || e?.code === 'not_found') code = 'unknown'
    if (typeof e?.retry_after === 'number') retry = e.retry_after
    if (typeof e?.request_id === 'string') rid = e.request_id
  } catch { /* non-JSON body (e.g. proxy error page): keep status-based code */ }
  const ra = Number(res.headers.get('retry-after'))
  if (retry === undefined && Number.isFinite(ra) && ra > 0) retry = ra
  return new ApiError(code, res.status, retry, rid)
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.style.display = 'none'
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 15000)
}

interface Opts { signal?: AbortSignal; timeoutMs?: number; fetchImpl?: typeof fetch; mockLabels?: { cols: readonly string[]; ph: string } }

export async function generateWorkbook(req: GenerateRequest, opts: Opts = {}): Promise<GenerateResult> {
  if (MOCK) return mockResult(req, opts.mockLabels)
  const doFetch = opts.fetchImpl ?? fetch
  const ctrl = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => { timedOut = true; ctrl.abort() }, opts.timeoutMs ?? REQUEST_TIMEOUT_MS)
  const onAbort = () => ctrl.abort()
  opts.signal?.addEventListener('abort', onAbort)
  try {
    const res = await doFetch(`${API_BASE}/api/v1/spreadsheets/generate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req), signal: ctrl.signal })
    if (!res.ok) throw await toApiError(res)
    if (!(res.headers.get('content-type') ?? '').includes('spreadsheetml')) throw new ApiError('unknown', res.status)
    const blob = await res.blob()
    return { blob, filename: parseFilename(res.headers.get('content-disposition')), rows: Number(res.headers.get('x-rows-generated')) || 0,
      warnings: Number(res.headers.get('x-warnings')) || 0, sheets: decodePreview(res.headers.get('x-preview')),
      requestId: res.headers.get('x-request-id') ?? undefined, mock: false }
  } catch (e) {
    if (e instanceof ApiError) throw e
    if (timedOut) throw new ApiError('timeout')
    if (opts.signal?.aborted) throw new ApiError('aborted')
    throw new ApiError('network')
  } finally {
    clearTimeout(timer)
    opts.signal?.removeEventListener('abort', onAbort)
  }
}

// UI-only development mode (VITE_MOCK_API=1): no file is produced.
async function mockResult(req: GenerateRequest, l?: Opts['mockLabels']): Promise<GenerateResult> {
  await new Promise(r => setTimeout(r, 800))
  const n = req.max_rows ?? DEFAULT_ROWS
  const cols = [...(l?.cols ?? ['A', 'B', 'C', 'D'])]
  const rows = Array.from({ length: 8 }, (_, i) => cols.map((_, j) => (j === 2 ? 4000 + i * 100 : `${l?.ph ?? 'Item'} ${i + 1}`)))
  return { blob: null, filename: 'demo.xlsx', rows: n, warnings: 0, mock: true, sheets: [{ name: 'Demo', columns: cols, rows, totalRows: n, totalCols: cols.length, synthetic: true, calcs: [] }] }
}
