import type { PreviewSheet } from '../services/api'
import { T, type Lang } from '../i18n'

/** Small real sample (header-capped by the server). Never renders the full dataset. */
export default function PreviewTable({ sheet, lang }: { sheet: PreviewSheet; lang: Lang }) {
  const t = T[lang]
  const numeric = (c: number) => sheet.rows.some(r => typeof r[c] === 'number') && sheet.rows.every(r => typeof r[c] === 'number' || r[c] === '')
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs dark:border-white/10 dark:bg-deep">
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={sheet.name}>
        <table className="w-full min-w-120 text-sm">
          <thead><tr className="bg-electric text-white">
            <th className="w-12 px-3 py-2 text-center font-medium opacity-70">#</th>
            {sheet.columns.map((c, i) => <th key={i} className={`px-4 py-2 font-semibold ${numeric(i) ? 'text-end' : 'text-start'}`}>{c}</th>)}
          </tr></thead>
          <tbody>
            {sheet.rows.map((r, i) => (
              <tr key={i} className="odd:bg-white even:bg-pale dark:odd:bg-deep dark:even:bg-navy/60">
                <td className="num px-3 py-2 text-center text-xs text-muted dark:text-slate-400">{i + 1}</td>
                {sheet.columns.map((_, c) => <td key={c} className={`h-9 px-4 py-2 ${numeric(c) ? 'num text-end' : ''}`}>{r[c] ?? ''}</td>)}
              </tr>))}
          </tbody>
        </table>
      </div>
      <p className="border-t border-slate-200 px-4 py-2 text-xs text-muted dark:text-slate-400 dark:border-white/10">
        {t.previewNote(sheet.rows.length, sheet.totalRows)} {sheet.totalCols > sheet.columns.length && t.colsNote(sheet.columns.length, sheet.totalCols)}
      </p>
    </div>
  )
}
