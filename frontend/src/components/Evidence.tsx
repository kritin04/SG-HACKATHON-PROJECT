/* eslint-disable @typescript-eslint/no-explicit-any */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { X, FileCode2, FileText, GitCompare, BookMarked, Ticket, GitPullRequest, ArrowRight, Search } from 'lucide-react'
import { api } from '../api'
import { Badge, Spinner, TierBadge, cx } from './ui'

type Req = { title: string; ids: string[]; why?: any[]; reason?: string; tier?: string }
const Ctx = createContext<(r: Req) => void>(() => {})
export const useEvidence = () => useContext(Ctx)

const KIND: Record<string, { label: string; icon: ReactNode; tone: string }> = {
  code: { label: 'Code', icon: <FileCode2 size={13} />, tone: 'blue' },
  doc: { label: 'Documentation', icon: <FileText size={13} />, tone: 'slate' },
  diff: { label: 'Code change', icon: <GitCompare size={13} />, tone: 'amber' },
  catalog: { label: 'Curated catalog', icon: <BookMarked size={13} />, tone: 'violet' },
  jira: { label: 'Jira', icon: <Ticket size={13} />, tone: 'blue' },
  pr: { label: 'Pull request', icon: <GitPullRequest size={13} />, tone: 'green' },
}

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [req, setReq] = useState<Req | null>(null)
  const [items, setItems] = useState<any[] | null>(null)
  useEffect(() => {
    if (!req) return
    setItems(null)
    const ids = [...new Set(req.ids.filter(Boolean))]
    if (!ids.length) { setItems([]); return }
    api.evidence(ids).then(setItems).catch(() => setItems([]))
  }, [req])
  return (
    <Ctx.Provider value={setReq}>
      {children}
      {req && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/30 backdrop-blur-[1px]" onClick={() => setReq(null)}>
          <aside className="flex h-full w-full max-w-2xl flex-col bg-white shadow-2xl" onClick={e => e.stopPropagation()}>
            <header className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
              <div>
                <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500"><Search size={13} />Why is this here?</div>
                <h2 className="mt-1 text-lg font-semibold text-slate-900">{req.title}</h2>
                {req.tier && <div className="mt-2"><TierBadge tier={req.tier} /></div>}
              </div>
              <button onClick={() => setReq(null)} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"><X size={18} /></button>
            </header>
            <div className="scroll-thin flex-1 space-y-5 overflow-y-auto px-6 py-5">
              {req.reason && <p className="rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-900">{req.reason}</p>}
              {req.why && req.why.length > 0 && <WhyChain steps={req.why} />}
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Evidence ({items?.length ?? '…'})</h4>
                {items === null ? <Spinner label="Loading evidence" /> : (
                  <div className="space-y-3">
                    {items.map(e => {
                      const k = KIND[e.kind] ?? KIND.code
                      return (
                        <div key={e.id} className="overflow-hidden rounded-lg border border-slate-200">
                          <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2">
                            <div className="flex min-w-0 items-center gap-2">
                              <Badge tone={k.tone}>{k.icon}{k.label}</Badge>
                              <span className="truncate font-mono text-xs text-slate-600">{e.location}</span>
                            </div>
                            <span className="font-mono text-[11px] text-slate-400">{e.id}</span>
                          </div>
                          <EvidenceBody e={e} />
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>
          </aside>
        </div>
      )}
    </Ctx.Provider>
  )
}

function EvidenceBody({ e }: { e: any }) {
  if (e.kind === 'diff') {
    return (
      <pre className="scroll-thin max-h-80 overflow-auto bg-white p-3 text-xs leading-5">
        {e.text.split('\n').map((l: string, i: number) => (
          <div key={i} className={cx(l.startsWith('+') && !l.startsWith('+++') && 'bg-emerald-50 text-emerald-800',
            l.startsWith('-') && !l.startsWith('---') && 'bg-rose-50 text-rose-800', l.startsWith('@@') && 'text-brand-600')}>{l || ' '}</div>
        ))}
      </pre>
    )
  }
  const start = e.kind === 'code' && e.start ? e.start : null
  return (
    <pre className={cx('scroll-thin max-h-80 overflow-auto p-3 text-xs leading-5', e.kind === 'code' ? 'bg-slate-900 text-slate-100' : 'whitespace-pre-wrap bg-white text-slate-700')}>
      {start ? e.text.split('\n').map((l: string, i: number) => (
        <div key={i}><span className="mr-3 inline-block w-6 select-none text-right text-slate-500">{start + i}</span>{l}</div>
      )) : e.text}
    </pre>
  )
}

export function WhyChain({ steps }: { steps: any[] }) {
  return (
    <div>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Dependency path</h4>
      <ol className="space-y-1.5">
        {steps.map((s, i) => (
          <li key={i} className="flex flex-wrap items-center gap-1.5 text-sm">
            <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-800">{s.from}</code>
            <span className="flex items-center gap-1 text-xs text-slate-500"><ArrowRight size={12} />{s.relation}<ArrowRight size={12} /></span>
            <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-800">{s.to}</code>
            {s.tier === 'curated' && <Badge tone="violet">catalog</Badge>}
            {s.confidence < 0.8 && <Badge tone="amber">medium confidence</Badge>}
          </li>
        ))}
      </ol>
    </div>
  )
}

export function WhyButton({ title, ids, why, reason, tier }: Req) {
  const open = useEvidence()
  return (
    <button onClick={() => open({ title, ids, why, reason, tier })}
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-brand-700 hover:bg-brand-50">
      <Search size={12} />Why?
    </button>
  )
}

export function Cite({ ids, label = 'evidence' }: { ids: string[]; label?: string }) {
  const open = useEvidence()
  if (!ids?.length) return null
  return (
    <button onClick={() => open({ title: 'Cited evidence', ids })}
      className="ml-1 inline-flex items-center rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600 hover:bg-brand-50 hover:text-brand-700">
      {ids.length} {label}
    </button>
  )
}
