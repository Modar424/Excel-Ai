import { useEffect, useRef, useState } from 'react'
import { AlertCircle, BarChart3, CheckCircle2, BrainCircuit, CalendarCheck, Check, ChevronLeft, ChevronRight, Download, Eraser, Globe, GraduationCap, ListChecks, Loader2, Moon, Package, ShieldCheck, Sparkles, Star, Sun, Table2, Wallet, Wand2, Zap, ArrowLeft, ArrowRight } from 'lucide-react'
import Logo, { SheetIcon } from './components/Logo'
import HeroArtwork from './components/HeroArtwork'
import PreviewTable from './components/PreviewTable'
import { EXAMPLES, TAB_EXAMPLE, T, type Lang, type TabId } from './i18n'
import { ApiError, DEFAULT_ROWS, MAX_PROMPT, MAX_ROWS, generateWorkbook, saveBlob, type GenerateResult } from './services/api'

type Status = 'idle' | 'loading' | 'done' | 'error'
const FEAT_ICONS = [Star, BrainCircuit, Zap, ShieldCheck]
const IND_ICONS = [Table2, Download, Globe]
const EX_ICONS: Record<string, [typeof Wallet, string]> = {
  expenses: [Wallet, 'bg-emerald-100 text-emerald-600'], inventory: [Package, 'bg-emerald-100 text-emerald-600'], attendance: [CalendarCheck, 'bg-blue-100 text-blue-600'],
  grades: [GraduationCap, 'bg-violet-100 text-violet-600'], sales: [BarChart3, 'bg-amber-100 text-amber-600'], tasks: [ListChecks, 'bg-rose-100 text-rose-600'] }
const ROW_OPTIONS = [100, 500, 1000, 3000, 5000]

export default function App() {
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem('sc-lang') as Lang) || 'ar')
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const [prompt, setPrompt] = useState('')
  const [tab, setTab] = useState<TabId>('quick')
  const [rows, setRows] = useState(DEFAULT_ROWS)
  const [status, setStatus] = useState<Status>('idle')
  const [res, setRes] = useState<GenerateResult | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  const [sheetIdx, setSheetIdx] = useState(0)
  const abortRef = useRef<AbortController | null>(null)
  const t = T[lang]; const rtl = lang === 'ar'
  const Back = rtl ? ArrowLeft : ArrowRight, Chev = rtl ? ChevronLeft : ChevronRight

  useEffect(() => { document.documentElement.lang = lang; document.documentElement.dir = rtl ? 'rtl' : 'ltr'; try { localStorage.setItem('sc-lang', lang) } catch { /* ignore */ } }, [lang, rtl])
  useEffect(() => { document.documentElement.classList.toggle('dark', dark); try { localStorage.setItem('sc-theme', dark ? 'dark' : 'light') } catch { /* ignore */ } }, [dark])

  const rowOpts = ROW_OPTIONS.filter(n => n <= MAX_ROWS)
  const promptErr = prompt.length > MAX_PROMPT ? t.tooLong(MAX_PROMPT) : prompt.length > 0 && prompt.trim().length < 3 ? t.tooShort : ''
  const canSubmit = prompt.trim().length >= 3 && !promptErr && status !== 'loading'
  const go = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
  const fill = (id: string) => { const e = EXAMPLES[lang].find(x => x.id === id); if (e) setPrompt(e.prompt) }
  const pickTab = (id: TabId) => { setTab(id); fill(TAB_EXAMPLE[id]) }
  const pickExample = (id: string) => { fill(id); go('create') }

  async function submit(e?: React.FormEvent) {
    e?.preventDefault(); if (!canSubmit) return
    const ctrl = new AbortController(); abortRef.current = ctrl
    setStatus('loading'); setErr(null)
    try {
      const r = await generateWorkbook({ prompt: prompt.trim(), language: lang, max_rows: rows }, { signal: ctrl.signal, mockLabels: { cols: t.cols, ph: t.ph } })
      setRes(r); setSheetIdx(0); setStatus('done'); setTimeout(() => go('result'), 50)
    } catch (ex) {
      const ae = ex instanceof ApiError ? ex : new ApiError('unknown')
      if (ae.code === 'aborted') { setStatus('idle'); return }
      setErr(ae); setStatus('error')
    } finally { abortRef.current = null }
  }
  useEffect(() => () => abortRef.current?.abort(), [])

  const card = 'rounded-2xl border border-slate-200/80 bg-white/90 shadow-xl shadow-indigo-900/5 dark:border-white/10 dark:bg-deep/90'
  const field = 'w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 dark:border-white/15 dark:bg-navy'

  return (
    <div id="home" className="min-h-screen overflow-x-hidden">
      <header className="relative isolate overflow-hidden bg-navy text-white">
        <HeroArtwork />
        <nav className="relative z-10 border-b border-white/10 bg-navy/60 backdrop-blur-sm" aria-label="main">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-3 py-3 sm:px-4">
            <a href="#home" className="flex items-center gap-3"><Logo /><span className="leading-tight"><span className="block whitespace-nowrap text-xl font-bold">SheetCraft AI</span><span className="hidden text-[11px] text-slate-300 sm:block">{t.tagline}</span></span></a>
            <div className="hidden items-center gap-8 text-sm md:flex">
              {t.nav.map((n, i) => <button key={n} onClick={() => go(['home', 'features', 'examples', 'about'][i])} className={`relative py-2 transition hover:text-white ${i === 0 ? 'text-white after:absolute after:inset-x-0 after:-bottom-[13px] after:h-0.5 after:bg-violet' : 'text-slate-300'}`}>{n}</button>)}
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => setLang(rtl ? 'en' : 'ar')} aria-label={t.toggleLang} className="glass inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm transition hover:bg-white/15"><Globe size={15} /><span className="hidden sm:inline">{t.toggleLang}</span></button>
              <button onClick={() => setDark(d => !d)} role="switch" aria-checked={dark} aria-label={t.theme} className="glass relative flex h-9 w-[68px] items-center justify-between rounded-full px-2.5">
                <Sun size={15} className="text-gold" /><Moon size={15} />
                <span className={`absolute top-1 h-7 w-7 rounded-full bg-white/90 shadow-sm transition-all ${dark ? 'start-[34px]' : 'start-1'}`} />
                {dark ? <Moon size={15} className="absolute start-[38px] text-navy" /> : <Sun size={15} className="absolute start-[8px] text-amber-500" />}
              </button>
            </div>
          </div>
        </nav>
        <div className="relative z-10 mx-auto max-w-6xl px-4 pb-36 pt-[300px] md:min-h-[600px] md:pb-44 md:pt-14 lg:min-h-[640px]">
          <div className="max-w-xl md:max-w-[54%] md:min-w-[420px] md:rounded-3xl md:bg-navy/60 md:p-7 md:backdrop-blur-sm ltr:md:ms-auto">
            <p className="animate-rise inline-flex items-center gap-2 rounded-full border border-gold/50 bg-navy/50 px-4 py-1.5 text-sm text-gold"><Sparkles size={14} />{t.badge}</p>
            <h1 className="animate-rise mt-5 text-4xl font-extrabold leading-[1.25] [animation-delay:.1s] sm:text-5xl md:text-[2.3rem] lg:text-[2.6rem] xl:text-[2.9rem]">{t.h1a}<br /><span className="bg-linear-to-r from-gold to-amber-200 bg-clip-text text-transparent">{t.h1b}</span></h1>
            <p className="animate-rise mt-5 text-base leading-8 text-slate-200 [animation-delay:.2s] sm:text-lg">{t.sub}</p>
            <ul className="animate-rise mt-7 flex flex-wrap gap-x-7 gap-y-4 [animation-delay:.3s]">
              {t.inds.map(([a, b], i) => { const I = IND_ICONS[i]; return (
                <li key={a} className="flex items-center gap-3"><span className="glass rounded-lg p-2.5"><I size={20} /></span><span className="text-sm leading-5"><span className="block">{a}</span><span className="block text-slate-300">{b}</span></span></li>) })}
            </ul>
          </div>
        </div>
        <div aria-hidden className="absolute inset-x-0 bottom-0 z-[1] h-44 bg-linear-to-b from-transparent via-pale/60 to-pale dark:via-navy/60 dark:to-navy" />
      </header>

      <main>
        <section id="create" className="relative z-10 mx-auto -mt-28 max-w-6xl scroll-mt-4 px-4">
          <form onSubmit={submit} className={`${card} p-4 sm:p-6 `}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div role="group" aria-label={t.tabs[0][1]} className="flex flex-wrap gap-2">
                {t.tabs.map(([id, label]) => (
                  <button key={id} type="button" aria-pressed={tab === id} onClick={() => pickTab(id)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-sm transition ${tab === id ? 'border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-violet/50 dark:bg-violet/20 dark:text-indigo-200' : 'border-slate-200 text-slate-600 hover:border-violet/50 dark:border-white/15 dark:text-slate-300'}`}>
                    {id === 'quick' && <Sparkles size={14} />}{label}</button>))}
              </div>
              <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-600 dark:border-white/15 dark:text-slate-300"><Sparkles size={13} className="text-violet" />{t.aiChip}</span>
            </div>
            <div className="relative mt-4">
              <label htmlFor="prompt" className="sr-only">{t.placeholder}</label>
              <textarea id="prompt" value={prompt} onChange={e => setPrompt(e.target.value)} rows={4} placeholder={t.placeholder} aria-invalid={!!promptErr}
                className="w-full resize-y rounded-xl border border-slate-200 bg-white p-4 pb-9 text-base placeholder:text-slate-500 focus:border-violet focus:outline-hidden focus:ring-2 focus:ring-violet/25 dark:border-white/15 dark:bg-navy" />
              <button type="button" onClick={() => setPrompt('')} disabled={!prompt} aria-label={t.clear} title={t.clear} className="absolute end-3 top-3 rounded-lg p-1.5 text-slate-500 dark:text-slate-400 transition enabled:hover:text-violet disabled:opacity-0"><Eraser size={18} /></button>
              <span className={`num absolute bottom-2 start-4 text-xs ${prompt.length > MAX_PROMPT ? 'text-red-500' : 'text-slate-500 dark:text-slate-400'}`}>{prompt.length}/{MAX_PROMPT}</span>
              <span role="alert" className="absolute bottom-2 end-4 text-xs text-red-500">{promptErr}</span>
            </div>
            <div className="mt-4 grid gap-2 md:grid-cols-[minmax(200px,auto)_1fr_1fr] md:items-start">
              <button type="submit" disabled={!canSubmit} className="order-last flex items-center justify-center gap-2 rounded-xl bg-linear-to-r from-electric to-violet px-8 py-3.5 text-lg font-bold text-white shadow-lg shadow-violet/30 transition enabled:hover:-translate-y-0.5 enabled:active:scale-[.98] disabled:opacity-50 md:order-first mt-5">
                {status === 'loading' ? <><Loader2 className="animate-spin" size={20} />{t.creating}</> : <>{t.create}<Back size={20} /></>}</button>
              <div><label htmlFor="rows" className="mb-1 block text-sm text-slate-500 dark:text-slate-400 dark:text-slate-300">{t.rows}</label>
                <select id="rows" value={rows} onChange={e => setRows(Number(e.target.value))} className={`${field} num`}>{rowOpts.map(n => <option key={n} value={n}>{n.toLocaleString('en-US')}</option>)}</select>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{t.rowsHint(MAX_ROWS)}</p></div>
              <div><label htmlFor="lang" className="mb-1 flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400 dark:text-slate-300"><Globe size={14} />{t.language}</label>
                <select id="lang" value={lang} onChange={e => setLang(e.target.value as Lang)} className={field}><option value="ar">العربية</option><option value="en">English</option></select></div>
            </div>
            {status === 'loading' && <button type="button" onClick={() => abortRef.current?.abort()} className="mt-3 w-full rounded-lg border border-slate-300 py-2 text-sm text-slate-600 transition hover:bg-slate-50 dark:border-white/20 dark:text-slate-300 dark:hover:bg-white/5">{t.cancel}</button>}
            {status === 'error' && err && <div role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              <div className="flex items-start justify-between gap-3"><span className="flex items-start gap-2"><AlertCircle size={16} className="mt-0.5 shrink-0" /><span>{t.errors[err.code] ?? t.errors.unknown}{err.retryAfter ? ` ${t.retryIn(err.retryAfter)}` : ''}</span></span>
                <button type="button" onClick={() => submit()} className="shrink-0 font-semibold underline">{t.retry}</button></div>
              {err.requestId && <p className="num mt-1 text-xs opacity-70">{t.refId}: {err.requestId}</p>}</div>}
          </form>
        </section>

        <section id="features" className="mx-auto max-w-6xl scroll-mt-4 px-4 pt-12">
          <h2 className="sr-only">{t.nav[1]}</h2>
          <div className="grid gap-x-5 gap-y-10 pt-4 sm:grid-cols-2 lg:grid-cols-4">
            {t.feats.map(([h, d], i) => { const I = FEAT_ICONS[i]; return (
              <article key={h} className={`${card} relative px-5 pb-6 pt-10 text-center transition hover:-translate-y-1 hover:shadow-2xl`}>
                <span className="absolute -top-6 start-1/2 -translate-x-1/2 rtl:translate-x-1/2 inline-flex h-12 w-12 items-center justify-center rounded-full border border-slate-100 bg-white text-electric shadow-lg dark:border-white/10 dark:bg-deep dark:text-indigo-300"><I size={22} /></span>
                <h3 className="font-bold">{h}</h3><p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{d}</p></article>) })}
          </div>
        </section>

        <section id="examples" className="mx-auto grid max-w-6xl scroll-mt-4 gap-5 px-4 pt-10 lg:grid-cols-3">
          <aside className={`${card} p-5`}>
            <h2 className="mb-3 font-bold">{t.suggested}</h2>
            <ul className="space-y-2">
              {EXAMPLES[lang].map(x => { const [I, c] = EX_ICONS[x.id]; return (
                <li key={x.id}><button onClick={() => pickExample(x.id)} className="flex w-full items-center gap-3 rounded-xl border border-slate-100 p-2.5 text-start transition hover:border-violet/40 hover:bg-violet/5 dark:border-white/10">
                  <span className={`rounded-lg p-2 ${c}`}><I size={18} /></span>
                  <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{x.label}</span><span className="block truncate text-xs text-slate-500 dark:text-slate-400">{x.sub}</span></span>
                  <Chev size={16} className="shrink-0 text-slate-500 dark:text-slate-400" /></button></li>) })}
            </ul>
          </aside>
          <article className={`${card} relative overflow-hidden p-5 sm:p-7 lg:col-span-2`}>
            <div className="flex flex-col-reverse items-center gap-6 md:flex-row">
              <div className="w-full flex-1">
                <div className="relative rounded-xl border border-slate-200 bg-white p-3 shadow-lg dark:border-white/10 dark:bg-navy">
                  <div className="mb-2 flex items-center gap-2"><SheetIcon className="h-7 w-7" /><span className="h-2 flex-1 rounded-sm bg-slate-100 dark:bg-white/10" /></div>
                  <div className="overflow-x-auto"><table className="w-full min-w-[300px] text-xs"><thead><tr className="bg-slate-100 dark:bg-white/10">{t.exCols.map((c, i) => <th key={c} className={`px-2 py-1.5 font-semibold ${i === 3 ? 'text-end' : 'text-start'}`}>{c}</th>)}</tr></thead>
                    <tbody>{t.exRows.map((r, i) => <tr key={i} className="border-t border-slate-100 dark:border-white/10">{r.map((v, c) => <td key={c} className={`px-2 py-1.5 ${c === 3 ? 'num text-end' : c === 0 ? 'num' : ''}`}>{c === 3 ? `$${Number(v).toLocaleString('en-US')}` : v}</td>)}</tr>)}</tbody>
                    <tfoot><tr className="border-t border-slate-200 bg-gold/15 font-bold dark:border-white/20"><td className="px-2 py-1.5" colSpan={3}>{t.exTotal}</td><td className="num px-2 py-1.5 text-end">${t.exRows.reduce((s, r) => s + Number(r[3]), 0).toLocaleString('en-US')}</td></tr></tfoot></table></div>
                </div>
                <span className="mt-3 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-indigo-700 shadow-sm dark:border-white/15 dark:bg-deep dark:text-indigo-200"><Download size={13} />{t.exFile}</span>
              </div>
              <div className="w-full md:w-[42%]">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-100 bg-indigo-50 px-3 py-1 text-xs text-indigo-700 dark:border-violet/40 dark:bg-violet/20 dark:text-indigo-200"><Sparkles size={12} />{t.resultTag}</span>
                <h2 className="mt-3 text-2xl font-extrabold">{t.exTitle}</h2>
                <ul className="mt-4 space-y-3">{t.exChecks.map(c => <li key={c} className="flex items-center gap-2"><span className="rounded-full bg-emerald-500 p-0.5 text-white"><Check size={14} /></span>{c}</li>)}</ul>
              </div>
            </div>
          </article>
        </section>

        {res && (
          <section id="result" className="mx-auto max-w-5xl scroll-mt-4 px-4 pt-12">
            <h2 className="mb-3 text-2xl font-extrabold">{t.resultTitle}</h2>
            {res.mock && <p role="status" className="mb-3 rounded-lg border border-gold/40 bg-gold/10 p-3 text-sm">{t.demoBanner}</p>}
            <div className={`${card} mb-4 flex flex-wrap items-center justify-between gap-3 p-4 sm:p-5`}>
              <div><p className="flex items-center gap-2 font-bold"><CheckCircle2 size={20} className="text-emerald-500" />{t.done}</p>
                <p className="mt-1 text-sm text-muted dark:text-slate-400"><bdi>{res.filename}</bdi> · {t.rowsOf(res.rows)}</p></div>
              <button type="button" disabled={!res.blob} onClick={() => res.blob && saveBlob(res.blob, res.filename)}
                className="inline-flex items-center gap-2 rounded-xl bg-linear-to-r from-electric to-violet px-6 py-3 font-bold text-white shadow-lg shadow-violet/30 transition enabled:hover:-translate-y-0.5 disabled:opacity-50"><Download size={18} />{res.blob ? t.downloadBtn : t.download}</button>
            </div>
            {res.warnings > 0 && <p role="status" className="mb-3 rounded-lg border border-gold/40 bg-gold/10 p-3 text-sm">{t.warnings(res.warnings)}</p>}
            {res.sheets.length > 0 && (() => { const sh = res.sheets[Math.min(sheetIdx, res.sheets.length - 1)]; return <>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                {res.sheets.length > 1 && res.sheets.map((x, i) => <button key={i} type="button" onClick={() => setSheetIdx(i)} aria-pressed={i === sheetIdx} className={`rounded-full border px-3 py-1 text-sm ${i === sheetIdx ? 'border-violet bg-violet/10' : 'border-slate-300 dark:border-white/20'}`}>{x.name}</button>)}
                {sh.synthetic && <span className="rounded-full bg-gold/20 px-3 py-1 text-xs font-semibold text-amber-700 dark:text-gold">{t.syntheticTag}</span>}
              </div>
              <PreviewTable key={sh.name + lang} sheet={sh} lang={lang} />
              {sh.calcs.length > 0 && <div className={`${card} mt-4 p-4`}><h3 className="mb-2 font-bold">{t.calcsTitle}</h3>
                <ul className="flex flex-wrap gap-2">{sh.calcs.map(c => <li key={c} className="rounded-full bg-violet/10 px-3 py-1 text-sm">{c}</li>)}</ul>
                <p className="mt-2 text-xs text-muted dark:text-slate-400">{t.calcNote}</p></div>}</> })()}
          </section>)}
      </main>

      <footer id="about" className="relative mt-16 bg-navy text-slate-200">
        <div aria-hidden className="absolute inset-x-0 -top-px h-px bg-linear-to-r from-transparent via-gold to-transparent" />
        <p className="flex items-center justify-center gap-2 px-4 py-5 text-center text-sm"><Sparkles size={16} className="shrink-0 text-violet" />{t.footerBar}</p>
        <p className="pb-4 text-center text-xs text-slate-400">SheetCraft AI · {t.footer}</p>
      </footer>
    </div>
  )
}
