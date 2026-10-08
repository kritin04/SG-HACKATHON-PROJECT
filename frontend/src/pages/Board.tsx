/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Sparkles, Loader2, User, AlertTriangle, ShieldAlert, Network, HelpCircle, RefreshCw, Link2, ExternalLink } from 'lucide-react'
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
    const t = setInterval(load, 1000)
    return () => clearInterval(t)
  }, [crs, load])

  const column = (c: any) => c.job?.status === 'running' ? 'running' : c.analysis ? 'done' : 'todo'
  const start = async (e: any, key: string) => { e.stopPropagation(); await api.analyze(key); load() }

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-[1400px] px-8 py-6">
        <div className="mb-5 flex items-end justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-brand-600">Jira · Payments Platform</div>
            <h1 className="mt-1 text-2xl font-semibold text-slate-900">Change requests</h1>
            <p className="mt-1 text-sm text-slate-500">Open a change request to see what it will affect, how, and who needs to be involved, before any code is written.</p>
          </div>
          <Button variant="primary" onClick={() => setCreating(true)} icon={<Plus size={15} />}>New change request</Button>
        </div>
        <JiraBar onSynced={load} />
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
                          <span className="flex items-center gap-2 text-xs text-slate-500"><span className="flex items-center gap-1"><User size={12} />{c.assignee}</span>
                            {c.url && <a href={c.url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} className="flex items-center gap-0.5 text-brand-700 hover:underline"><ExternalLink size={11} />Jira</a>}</span>
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

function JiraBar({ onSynced }: { onSynced: () => void }) {
  const [st, setSt] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const load = () => api.jiraStatus().then(setSt).catch(() => setSt(null))
  useEffect(() => { load() }, [])
  if (!st) return null
  const sync = async () => {
    setBusy(true); setMsg('')
    try { const r = await api.jiraSync(); setMsg(`Synced ${r.count} issue(s) from Jira`); await load(); onSynced() }
    catch (e: any) { setMsg(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="flex items-center gap-3 text-sm">
        <span className={cx('flex h-8 w-8 items-center justify-center rounded-lg', st.connected && st.reachable ? 'bg-blue-50 text-blue-700' : 'bg-slate-100 text-slate-500')}><Link2 size={16} /></span>
        {st.connected ? (
          <div>
            <div className="font-medium text-slate-900">Connected to Jira <span className={cx('ml-1 inline-block h-2 w-2 rounded-full', st.reachable ? 'bg-emerald-500' : 'bg-rose-500')} /></div>
            <div className="text-xs text-slate-500">{st.base_url} · <code>{st.jql}</code> · {st.issues} issue(s) · last sync {st.last_sync ?? 'never'}{st.user ? ` · as ${st.user}` : ''}{st.error ? ` · ${st.error}` : ''}</div>
          </div>
        ) : (
          <div><div className="font-medium text-slate-900">Using demo change requests</div><div className="text-xs text-slate-500">Set JIRA_BASE_URL in .env to read change requests from a real Jira (or the local demo tracker).</div></div>
        )}
      </div>
      <div className="flex items-center gap-3">
        {msg && <span className="text-xs text-slate-600">{msg}</span>}
        {st.connected && <a href={st.base_url} target="_blank" rel="noreferrer" className="text-xs font-medium text-brand-700 hover:underline">Open Jira ↗</a>}
        {st.connected && <Button variant="primary" size="sm" disabled={busy} onClick={sync} icon={<RefreshCw size={13} className={busy ? 'animate-spin' : ''} />}>{busy ? 'Syncing…' : 'Sync from Jira'}</Button>}
      </div>
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
