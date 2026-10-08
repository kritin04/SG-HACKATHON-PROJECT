/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Sparkles, Loader2, User, AlertTriangle, ShieldAlert, Network, HelpCircle } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, RiskBadge, Spinner, cx } from '../components/ui'

const COLUMNS = [
  { id: 'todo', title: 'To analyse', hint: 'New change requests' },
  { id: 'running', title: 'Analysing', hint: 'Local AI at work' },
  { id: 'done', title: 'Analysed', hint: 'Impact ready to review' },
]

export default function Board() {
  const [crs, setCrs] = useState<any[] | null>(null)
  const [creating, setCreating] = useState(false)
  const nav = useNavigate()
  const load = useCallback(() => api.crs().then(setCrs), [])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!crs?.some(c => c.job?.status === 'running')) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [crs, load])

  const column = (c: any) => c.job?.status === 'running' ? 'running' : c.analysis ? 'done' : 'todo'
  const start = async (e: any, key: string) => { e.stopPropagation(); await api.analyze(key); load() }

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-[1400px] px-8 py-6">
        <div className="mb-5 flex items-end justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-brand-600">Jira · Bank of Anthos</div>
            <h1 className="mt-1 text-2xl font-semibold text-slate-900">Change requests</h1>
            <p className="mt-1 text-sm text-slate-500">Open a change request to see what it will affect, how, and who needs to be involved, before any code is written.</p>
          </div>
          <Button variant="primary" onClick={() => setCreating(true)} icon={<Plus size={15} />}>New change request</Button>
        </div>
        {!crs ? <Spinner label="Loading change requests…" /> : (
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            {COLUMNS.map(col => {
              const items = crs.filter(c => column(c) === col.id)
              return (
                <section key={col.id} className="rounded-xl bg-slate-100/80 p-3">
                  <header className="mb-3 flex items-center justify-between px-1">
                    <div><span className="text-sm font-semibold text-slate-800">{col.title}</span><span className="ml-2 text-xs text-slate-500">{col.hint}</span></div>
                    <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-slate-600">{items.length}</span>
                  </header>
                  <div className="space-y-2.5">
                    {items.map(c => (
                      <article key={c.key} onClick={() => nav(`/cr/${c.key}`)}
                        className="cursor-pointer rounded-lg border border-slate-200 bg-white p-3.5 shadow-sm transition hover:border-brand-500 hover:shadow">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs font-semibold text-brand-700">{c.key}</span>
                          <div className="flex items-center gap-1.5">
                            {c.analysis && <RiskBadge level={c.analysis.risk} />}
                            <Badge tone={c.priority === 'High' ? 'red' : c.priority === 'Low' ? 'slate' : 'amber'}>{c.priority}</Badge>
                          </div>
                        </div>
                        <div className="mt-1.5 text-sm font-medium leading-snug text-slate-900">{c.summary}</div>
                        {c.analysis && (
                          <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600">
                            <span className="flex items-center gap-1"><AlertTriangle size={12} className="text-red-500" />{c.analysis.must_change} must change</span>
                            {c.analysis.externals > 0 && <span className="flex items-center gap-1"><Network size={12} className="text-violet-600" />{c.analysis.externals} outside system(s)</span>}
                            {c.analysis.controls > 0 && <span className="flex items-center gap-1"><ShieldAlert size={12} className="text-violet-600" />{c.analysis.controls} approval(s)</span>}
                            {c.analysis.open_questions > 0 && <span className="flex items-center gap-1"><HelpCircle size={12} className="text-amber-600" />{c.analysis.open_questions} open question(s)</span>}
                            {c.analysis.size && <span>Size {c.analysis.size}</span>}
                          </div>
                        )}
                        {c.job?.status === 'running' && (
                          <div className="mt-2.5 flex items-center gap-2 text-xs text-brand-700"><Loader2 size={13} className="animate-spin" />Step {c.job.stage}/6 · {c.job.stage_name}</div>
                        )}
                        {c.job?.status === 'error' && <div className="mt-2 text-xs text-rose-600">Analysis failed: {c.job.error}</div>}
                        <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-2.5">
                          <span className="flex items-center gap-1 text-xs text-slate-500"><User size={12} />{c.assignee}</span>
                          {col.id === 'todo' && <span onClick={e => start(e, c.key)}><Button size="sm" variant="primary" icon={<Sparkles size={12} />}>Analyse impact</Button></span>}
                          {col.id === 'done' && <span className="text-xs font-medium text-brand-700">Open analysis →</span>}
                        </div>
                      </article>
                    ))}
                    {!items.length && <div className="rounded-lg border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-400">Nothing here</div>}
                  </div>
                </section>
              )
            })}
          </div>
        )}
      </div>
      {creating && <NewCrDialog onClose={() => setCreating(false)} onCreated={k => { setCreating(false); nav(`/cr/${k}`) }} />}
    </div>
  )
}

function NewCrDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (key: string) => void }) {
  const [summary, setSummary] = useState('')
  const [description, setDescription] = useState('')
  const [ac, setAc] = useState('')
  const [priority, setPriority] = useState('Medium')
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    const r = await api.createCr({ summary, description, acceptance_criteria: ac.split('\n').map(s => s.trim()).filter(Boolean), priority })
    await api.analyze(r.key)
    onCreated(r.key)
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40" onClick={onClose}>
      <div className="w-full max-w-xl rounded-xl bg-white p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-slate-900">New change request</h2>
        <p className="mt-1 text-sm text-slate-500">Write it the way a business analyst would. The impact analysis starts as soon as you create it.</p>
        <div className="mt-4 space-y-3">
          <input value={summary} onChange={e => setSummary(e.target.value)} placeholder="Title, e.g. Show the transaction date in the SMS"
            className={cx('w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none')} />
          <textarea value={description} onChange={e => setDescription(e.target.value)} rows={4} placeholder="What should change and why?"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
          <textarea value={ac} onChange={e => setAc(e.target.value)} rows={3} placeholder="Acceptance criteria (one per line)"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
          <select value={priority} onChange={e => setPriority(e.target.value)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option>High</option><option>Medium</option><option>Low</option>
          </select>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!summary.trim() || busy} onClick={submit} icon={<Sparkles size={14} />}>{busy ? 'Creating…' : 'Create and analyse'}</Button>
        </div>
      </div>
    </div>
  )
}
