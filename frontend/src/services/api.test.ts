import { describe, expect, it } from 'vitest'
import { API_BASE, ApiError, decodePreview, generateWorkbook, parseFilename } from './api'

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
const REQ = { prompt: 'أنشئ جدولًا للموظفين', language: 'ar' as const, max_rows: 3000 }
const b64 = (o: unknown) => btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(o))))
const PV = { v: 1, sheets: [{ name: 'الموظفين', columns: ['الرقم', 'الاسم'], rows: [[1, '']], total_rows: 3000, total_cols: 5, synthetic: false, calcs: ['إجمالي'] }] }
const ok = (extra: Record<string, string> = {}) => async () => new Response(new Uint8Array([80, 75, 3, 4]), { status: 200, headers: {
  'content-type': XLSX, 'content-disposition': `attachment; filename="x.xlsx"; filename*=UTF-8''${encodeURIComponent('جدول الموظفين.xlsx')}`,
  'x-rows-generated': '3000', 'x-warnings': '2', 'x-preview': b64(PV), 'x-request-id': 'abc123', ...extra } })
const fail = (status: number, body: unknown, headers: Record<string, string> = {}) => async () =>
  new Response(typeof body === 'string' ? body : JSON.stringify(body), { status, headers })
const code = async (p: Promise<unknown>) => { try { await p } catch (e) { return e as ApiError } throw new Error('did not throw') }

describe('generateWorkbook', () => {
  it('returns blob, Arabic filename, counts and decoded preview', async () => {
    const r = await generateWorkbook(REQ, { fetchImpl: ok() })
    expect(r.blob?.size).toBe(4); expect(r.filename).toBe('جدول الموظفين.xlsx'); expect(r.rows).toBe(3000); expect(r.warnings).toBe(2)
    expect(r.sheets[0]).toMatchObject({ name: 'الموظفين', totalRows: 3000, totalCols: 5, calcs: ['إجمالي'] }); expect(r.requestId).toBe('abc123')
  })
  it('posts JSON to the configured base URL without secrets', async () => {
    let seen: { url: string; init: RequestInit } | undefined
    await generateWorkbook(REQ, { fetchImpl: async (u, i) => { seen = { url: String(u), init: i! }; return ok()() } })
    expect(seen!.url).toBe(`${API_BASE}/api/v1/spreadsheets/generate`); expect(seen!.init.method).toBe('POST')
    expect(JSON.parse(String(seen!.init.body))).toEqual(REQ); expect(JSON.stringify(seen!.init.headers)).not.toMatch(/key|authorization/i)
  })
  it('maps quota error with retry-after from the body', async () => {
    const e = await code(generateWorkbook(REQ, { fetchImpl: fail(429, { error: { code: 'ai_quota', message: 'm', request_id: 'r1', retry_after: 42 } }, { 'retry-after': '42' }) }))
    expect(e).toMatchObject({ code: 'ai_quota', status: 429, retryAfter: 42, requestId: 'r1' })
  })
  it('uses the Retry-After header for rate limits and status for non-JSON proxy errors', async () => {
    expect(await code(generateWorkbook(REQ, { fetchImpl: fail(429, { error: { code: 'rate_limited' } }, { 'retry-after': '9' }) }))).toMatchObject({ code: 'rate_limited', retryAfter: 9 })
    expect((await code(generateWorkbook(REQ, { fetchImpl: fail(504, '<html>Gateway Timeout</html>') }))).code).toBe('timeout')
    expect((await code(generateWorkbook(REQ, { fetchImpl: fail(502, '<html>Bad gateway</html>') }))).code).toBe('unknown')
  })
  it('maps the server-busy 503 separately from AI-unavailable', async () => {
    const e = await code(generateWorkbook(REQ, { fetchImpl: fail(503, { error: { code: 'busy', message: 'x', retry_after: 5 } }, { 'retry-after': '5' }) }))
    expect(e).toMatchObject({ code: 'busy', status: 503, retryAfter: 5 })
  })
  it.each([[400, 'invalid_request'], [413, 'payload_too_large'], [422, 'invalid_spec'], [503, 'ai_unavailable'], [500, 'internal_error']])('maps %i', async (s, c) => {
    expect((await code(generateWorkbook(REQ, { fetchImpl: fail(s, { error: { code: c, message: 'x' } }) }))).code).toBe(c)
  })
  it('treats a 200 that is not an xlsx (captive portal/proxy page) as an error', async () => {
    const e = await code(generateWorkbook(REQ, { fetchImpl: async () => new Response('<html>login</html>', { status: 200, headers: { 'content-type': 'text/html' } }) }))
    expect(e.code).toBe('unknown')
  })
  it('network failure', async () => {
    expect((await code(generateWorkbook(REQ, { fetchImpl: async () => { throw new TypeError('Failed to fetch') } }))).code).toBe('network')
  })
  const hang: typeof fetch = (_u, init) => new Promise((_res, rej) => init!.signal!.addEventListener('abort', () => rej(new DOMException('aborted', 'AbortError'))))
  it('client-side timeout', async () => {
    expect((await code(generateWorkbook(REQ, { fetchImpl: hang, timeoutMs: 30 }))).code).toBe('timeout')
  })
  it('user cancel', async () => {
    const c = new AbortController(); setTimeout(() => c.abort(), 20)
    expect((await code(generateWorkbook(REQ, { fetchImpl: hang, signal: c.signal, timeoutMs: 5000 }))).code).toBe('aborted')
  })
})

describe('helpers', () => {
  it('parseFilename', () => {
    expect(parseFilename(null)).toBe('workbook.xlsx'); expect(parseFilename('attachment; filename="a b.xlsx"')).toBe('a b.xlsx')
    expect(parseFilename("attachment; filename=\"x.xlsx\"; filename*=UTF-8''%D8%A7.xlsx")).toBe('ا.xlsx'); expect(parseFilename("attachment; filename*=UTF-8''%E0%A4%A")).toBe('workbook.xlsx')
  })
  it('decodePreview tolerates garbage', () => {
    for (const bad of [null, '', '!!!', btoa('not json'), btoa('{"v":2,"sheets":[]}'), btoa('{"v":1}')]) expect(decodePreview(bad)).toEqual([])
    expect(decodePreview(b64({ v: 1, sheets: [{ name: 'S', rows: [[1, null]] }] }))[0].rows[0]).toEqual([1, ''])
  })
})
