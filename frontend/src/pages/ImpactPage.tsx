/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Sparkles, RefreshCw, Briefcase, Cpu, Database, Network, FlaskConical, ShieldCheck, Users, HelpCircle,
  ChevronDown, ChevronRight, Check, Loader2, Plus, Search, Map as MapIcon, Lock, Info, X } from 'lucide-react'
import { api, VERDICT } from '../api'
import { Badge, Button, RiskBadge, Spinner, ErrorNote, cx } from '../components/ui'
import { useEvidence } from '../components/Evidence'
import ImpactMap from '../components/ImpactMap'

const STAGES = ['Understand the request', 'Find where it starts', 'Follow the dependency map', 'Judge what must change', 'Check data, systems, rules & tests', 'Write the summary']
const CARDS: { id: string; title: string; icon: any }[] = [
  { id: 'business', title: 'Business', icon: Briefcase }, { id: 'technical', title: 'Technical', icon: Cpu },
  { id: 'data', title: 'Data', icon: Database }, { id: 'integrations', title: 'Outside systems', icon: Network },
  { id: 'testing', title: 'Testing', icon: FlaskConical }, { id: 'compliance', title: 'Approvals', icon: ShieldCheck },
]
const STATUS: Record<string, string> = { red: 'border-red-200 bg-red-50', amber: 'border-amber-200 bg-amber-50', green: 'border-emerald-200 bg-emerald-50' }
const DOT: Record<string, string> = { red: 'bg-red-500', amber: 'bg-amber-500', green: 'bg-emerald-500' }

export default function ImpactPage() {
  const { key } = useParams()
  const nav = useNavigate()
  const [data, setData] = useState<any>(null)
  const [map, setMap] = useState<any>(null)
  const [error, setError] = useState('')
  const load = useCallback(() => key && api.cr(key).then(setData).catch(e => setError(e.message)), [key])
  useEffect(() => { load(); api.map().then(setMap) }, [load])
  useEffect(() => {
    if (data?.job?.status !== 'running') return
    const t = setInterval(load, 2500)
    return () => clearInterval(t)
  }, [data, load])

  if (error) return <div className="p-8"><ErrorNote error={error} /></div>
  if (!data) return <div className="p-8"><Spinner label="Loading…" /></div>
  const f = data.issue.fields
  const a = data.analysis
  const running = data.job?.status === 'running'
  const run = async (force = false) => { await api.analyze(data.key, force); load() }

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-[1400px] px-8 py-6">
        <Link to="/board" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={15} />Change requests</Link>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2"><span className="font-mono text-sm font-semibold text-brand-700">{data.key}</span>
              <Badge tone={f.priority.name === 'High' ? 'red' : f.priority.name === 'Low' ? 'slate' : 'amber'}>{f.priority.name} priority</Badge>
              {f.labels.map((l: string) => <Badge key={l}>{l}</Badge>)}</div>
            <h1 className="mt-1 text-2xl font-semibold text-slate-900">{f.summary}</h1>
            <p className="mt-1 text-sm text-slate-600">{f.description}</p>
          </div>
          <div className="flex items-center gap-2">
            {a && <RiskBadge level={a.risk.level} large />}
            {a?.assessment?.size && <Badge tone="blue" className="px-3 py-1 text-sm">Size {a.assessment.size}</Badge>}
            {a && <Button onClick={() => nav(`/map?cr=${data.key}`)} icon={<MapIcon size={14} />}>Show on map</Button>}
            {a && !running && <Button variant="ghost" onClick={() => run(true)} icon={<RefreshCw size={14} />}>Re-run</Button>}
          </div>
        </div>

        {(running || !a) && <RunPanel job={data.job} running={running} onRun={() => run(false)} />}

        {a && (
          <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[1fr_400px]">
            <div className="space-y-5">
              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-2 flex items-center justify-between">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Impact at a glance</h2>
                  <span className="flex items-center gap-1 text-xs text-slate-400"><Sparkles size={12} />{a.assessment.by === 'ai' ? 'Written by local AI from verified facts' : 'Rule-based summary (AI unavailable)'}</span>
                </div>
                <p className="text-[15px] leading-7 text-slate-800">{a.assessment.summary}</p>
                <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3">
                  {CARDS.map(c => {
                    const card = a.cards[c.id]
                    return (
                      <a key={c.id} href={`#sec-${c.id}`} className={cx('rounded-lg border p-3 transition hover:shadow-sm', STATUS[card.status])}>
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-800"><span className={cx('h-2.5 w-2.5 rounded-full', DOT[card.status])} /><c.icon size={15} />{c.title}</div>
                        <div className="mt-1 text-xs leading-5 text-slate-700">{card.line}</div>
                      </a>
                    )
                  })}
                </div>
              </section>

              <Understanding u={a.understanding} />

              <Accordion id="technical" title="What changes, and how" icon={Cpu} open count={a.items.filter((i: any) => i.verdict !== 'not_impacted').length}>
                <TechnicalSection a={a} crKey={data.key} onChange={setData} />
              </Accordion>
              <Accordion id="data" title="Data" icon={Database} count={a.data.length}>
                {a.data.length ? <ul className="space-y-3">{a.data.map((d: any) => (
                  <li key={d.id} className="rounded-lg border border-slate-200 p-3">
                    <div className="flex flex-wrap items-center gap-2"><b className="text-slate-900">{d.label}</b><span className="text-xs text-slate-500">table in {d.id.split(':')[1].split('.')[0]}</span>
                      <VerdictBadge v={d.verdict} />{d.classifications.map((c: string) => <Badge key={c} tone={c.startsWith('Personal') || c === 'Secret' ? 'red' : 'amber'}><Lock size={10} />{c}</Badge>)}</div>
                    <div className="mt-1 text-xs text-slate-600">Written by {d.writers.join(', ') || '-'} · read by {d.readers.join(', ') || '-'}</div>
                    {d.new_fields.map((nf: any) => <div key={nf.field} className="mt-1.5 rounded bg-brand-50 px-2 py-1 text-xs text-brand-900">New field <b>{nf.field}</b>{nf.sensitivity !== 'None' && <> · {nf.sensitivity} data</>}</div>)}
                  </li>))}</ul> : <Empty>No database changes.</Empty>}
              </Accordion>
              <Accordion id="integrations" title="Outside systems (we can't change them, so we must coordinate)" icon={Network} count={a.externals.length}>
                {a.externals.length ? <ul className="space-y-3">{a.externals.map((x: any) => (
                  <li key={x.id} className="rounded-lg border border-violet-200 bg-violet-50/40 p-3">
                    <div className="flex items-center justify-between"><b className="text-slate-900">{x.label}</b><span className="text-xs text-slate-500">Owner: {x.owner}</span></div>
                    <p className="mt-0.5 text-xs text-slate-600">{x.description}</p>
                    <p className="mt-1 text-sm text-slate-700">{x.how}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">{x.actions.map((ac: string) => <Badge key={ac} tone="violet"><Check size={10} />{ac}</Badge>)}</div>
                  </li>))}</ul> : <Empty>No outside systems are affected.</Empty>}
              </Accordion>
              <Accordion id="testing" title="Testing" icon={FlaskConical} count={a.tests.gaps.length + a.assessment.test_scenarios.length}>
                <TestingSection a={a} />
              </Accordion>
              <Accordion id="compliance" title="Approvals needed (bank rules)" icon={ShieldCheck} count={a.controls.length}>
                {a.controls.length ? <ul className="space-y-3">{a.controls.map((c: any) => (
                  <li key={c.id} className="rounded-lg border border-slate-200 p-3">
                    <div className="flex items-center gap-2"><span className="font-mono text-xs font-semibold text-violet-700">{c.id}</span><b className="text-slate-900">{c.name}</b></div>
                    <ul className="mt-1 text-xs text-slate-600">{c.reasons.map((r: string) => <li key={r}>• {r}</li>)}</ul>
                    <div className="mt-2 flex flex-wrap gap-1.5">{c.requires.map((r: string) => <Badge key={r} tone="violet">{r}</Badge>)}</div>
                  </li>))}</ul> : <Empty>No approval rules are triggered.</Empty>}
                <p className="mt-3 text-xs text-slate-400">Rules come from the bank's change policy (synthetic examples here). The tool says when a rule applies; people decide.</p>
              </Accordion>
              <Accordion id="people" title="People to involve" icon={Users} count={a.people.length}>
                <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">{a.people.map((p: any) => (
                  <li key={p.who} className="rounded-lg border border-slate-200 p-3"><b className="text-sm text-slate-900">{p.who}</b>
                    <ul className="mt-0.5 text-xs text-slate-600">{p.why.map((w: string) => <li key={w}>{w}</li>)}</ul></li>))}</ul>
              </Accordion>
              <Accordion id="how" title="How this analysis was worked out" icon={Info}>
                <HowSection a={a} />
              </Accordion>
            </div>

            <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start">
              <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                  <h3 className="text-sm font-semibold text-slate-800">Impact on the system</h3>
                  <button onClick={() => nav(`/map?cr=${data.key}`)} className="text-xs font-medium text-brand-700">Open full map →</button>
                </div>
                {map ? <ImpactMap map={map} analysis={a} height={340} /> : <div className="p-4"><Spinner /></div>}
                <div className="flex flex-wrap gap-3 border-t border-slate-100 px-4 py-2.5 text-[11px] text-slate-600">
                  {Object.entries(VERDICT).map(([k, v]) => <span key={k} className="flex items-center gap-1"><span className={cx('h-2.5 w-2.5 rounded-sm', v.dot)} />{v.label}</span>)}
                </div>
              </section>
              <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="text-sm font-semibold text-slate-800">Why this risk level</h3>
                <ul className="mt-2 space-y-1.5">{a.risk.reasons.map((r: string) => <li key={r} className="flex gap-2 text-xs text-slate-700"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />{r}</li>)}</ul>
                {a.assessment.size && <p className="mt-3 text-xs text-slate-600"><b>Size {a.assessment.size}:</b> {a.assessment.size_reason}</p>}
                <p className="mt-3 text-[11px] text-slate-400">Analysed {a.generated_at} at commit {a.sha.slice(0, 7)} · {a.model ?? 'rules only (AI unavailable)'}{a.ai_seconds ? ` · local AI time ${Math.round(a.ai_seconds / 60)} min` : ''}</p>
              </section>
            </aside>
          </div>
        )}
      </div>
    </div>
  )
}

function RunPanel({ job, running, onRun }: { job: any; running: boolean; onRun: () => void }) {
  return (
    <section className="mt-6 rounded-xl border border-brand-100 bg-brand-50/60 p-5">
      {!running ? (
        <div className="flex items-center justify-between gap-4">
          <div><div className="font-semibold text-slate-900">No impact analysis yet</div><p className="text-sm text-slate-600">The local AI will read the request, follow the dependency map and judge what changes. Takes 2-6 minutes on this laptop.</p>
            {job?.status === 'error' && <p className="mt-1 text-sm text-rose-600">Last run failed: {job.error}</p>}</div>
          <Button variant="primary" onClick={onRun} icon={<Sparkles size={15} />}>Run impact analysis</Button>
        </div>
      ) : (
        <div>
          <div className="mb-3 flex items-center gap-2 font-semibold text-slate-900"><Loader2 size={16} className="animate-spin text-brand-600" />Analysing… {Math.round(job.elapsed ?? 0)}s</div>
          <ol className="grid grid-cols-1 gap-2 md:grid-cols-3">
            {STAGES.map((s, i) => {
              const n = i + 1
              const state = job.stage > n ? 'done' : job.stage === n ? 'now' : 'todo'
              return (
                <li key={s} className={cx('flex items-center gap-2 rounded-lg px-3 py-2 text-sm', state === 'done' ? 'bg-white text-slate-700' : state === 'now' ? 'bg-white font-medium text-brand-700 shadow-sm' : 'text-slate-400')}>
                  {state === 'done' ? <Check size={15} className="text-emerald-600" /> : state === 'now' ? <Loader2 size={15} className="animate-spin" /> : <span className="flex h-4 w-4 items-center justify-center text-[10px]">{n}</span>}{s}
                </li>
              )
            })}
          </ol>
        </div>
      )}
    </section>
  )
}

function Understanding({ u }: { u: any }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">What the request means</h2>
      <p className="mt-2 text-sm text-slate-800"><b>{u.change_type ? `${u.change_type[0].toUpperCase()}${u.change_type.slice(1)}:` : ''}</b> {u.intent}</p>
      {u.business_terms?.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{u.business_terms.map((t: string) => <Badge key={t}>{t}</Badge>)}</div>}
      {u.open_questions?.length > 0 && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-amber-900"><HelpCircle size={15} />Questions to answer before development</div>
          <ol className="mt-1.5 list-decimal space-y-1 pl-5 text-sm text-amber-900">{u.open_questions.map((q: string) => <li key={q}>{q}</li>)}</ol>
        </div>
      )}
      {u.assumptions?.length > 0 && <div className="mt-3 text-xs text-slate-500"><b>Assumptions made:</b> {u.assumptions.join(' · ')}</div>}
    </section>
  )
}

function Accordion({ id, title, icon: Icon, children, open: initial = false, count }: { id: string; title: string; icon: any; children: ReactNode; open?: boolean; count?: number }) {
  const [open, setOpen] = useState(initial)
  return (
    <section id={`sec-${id}`} className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <button onClick={() => setOpen(o => !o)} className="flex w-full items-center justify-between px-5 py-3.5 text-left">
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-900"><Icon size={16} className="text-slate-500" />{title}{count !== undefined && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">{count}</span>}</span>
        {open ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
      </button>
      {open && <div className="border-t border-slate-100 px-5 py-4">{children}</div>}
    </section>
  )
}

function VerdictBadge({ v }: { v: string }) {
  return <Badge tone={VERDICT[v].tone}><span className={cx('h-1.5 w-1.5 rounded-full', VERDICT[v].dot)} />{VERDICT[v].label}</Badge>
}

function SourceBadge({ by }: { by: string }) {
  if (by === 'human') return <Badge tone="green">Reviewer</Badge>
  if (by === 'ai') return <span title="Decided by the local AI from map evidence"><Badge tone="blue"><Sparkles size={10} />AI</Badge></span>
  return <span title="AI answer unavailable or invalid: rule-based fallback"><Badge>Rules</Badge></span>
}

function TechnicalSection({ a, crKey, onChange }: { a: any; crKey: string; onChange: (d: any) => void }) {
  const open = useEvidence()
  const [showNone, setShowNone] = useState(false)
  const [adding, setAdding] = useState(false)
  const update = async (node_id: string, action: 'remove' | 'override', verdict?: string) => {
    const analysis = await api.scope(crKey, { node_id, action, verdict })
    onChange((d: any) => ({ ...d, analysis }))
  }
  const groups = ['must_change', 'likely_affected', 'retest_only', ...(showNone ? ['not_impacted'] : [])]
  const icon = (t: string) => t === 'service' ? '⬢' : t === 'endpoint' ? '⇄' : t === 'table' ? '▤' : '◇'
  return (
    <div className="space-y-4">
      {groups.map(g => {
        const items = a.items.filter((i: any) => i.verdict === g)
        if (!items.length) return null
        return (
          <div key={g}>
            <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500"><span className={cx('h-2 w-2 rounded-full', VERDICT[g].dot)} />{VERDICT[g].label} ({items.length})</div>
            <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
              {items.map((i: any) => (
                <li key={i.id} className="flex items-start gap-3 px-3 py-2.5">
                  <span className="mt-0.5 w-4 text-center text-slate-400" title={i.type}>{icon(i.type)}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5 text-sm"><b className="text-slate-900">{i.label}</b>
                      {i.service && <span className="text-xs text-slate-500">in {i.service}</span>}<span className="text-xs text-slate-400">{i.type === 'endpoint' ? 'API' : i.type}</span>
                      <SourceBadge by={i.by} />{i.ai_verdict && i.ai_verdict !== i.verdict && <span className="text-[11px] text-slate-400">(AI said: {VERDICT[i.ai_verdict]?.label})</span>}</div>
                    <p className="mt-0.5 text-sm text-slate-700">{i.how}</p>
                    {i.why?.length > 0 && i.why.join('; ') !== i.how && <p className="mt-0.5 text-xs text-slate-400">Found because: {i.why.join('; ')}</p>}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <select value={i.verdict} onChange={e => update(i.id, 'override', e.target.value)} className="rounded border border-slate-200 bg-white px-1 py-0.5 text-xs text-slate-600" title="Change the verdict">
                      {Object.entries(VERDICT).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                    </select>
                    <button onClick={() => open({ title: i.label, ids: i.evidence ?? [], why: i.path, reason: i.how })} className="rounded px-1.5 py-0.5 text-xs text-brand-700 hover:bg-brand-50">Why?</button>
                    {i.verdict !== 'not_impacted' && <button onClick={() => update(i.id, 'remove')} title="Remove from scope" className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><X size={13} /></button>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
      <div className="flex items-center gap-3">
        <Button size="sm" onClick={() => setAdding(true)} icon={<Plus size={13} />}>Add to scope</Button>
        <button onClick={() => setShowNone(s => !s)} className="text-xs text-slate-500 hover:text-slate-800">{showNone ? 'Hide' : 'Show'} checked but not impacted ({a.items.filter((i: any) => i.verdict === 'not_impacted').length})</button>
        {a.contract_changes?.length > 0 && <span className="text-xs text-amber-700">⚠ API contract change: {a.contract_changes.map((c: any) => `${c.api} (used by ${c.callers.join(', ')})`).join('; ')}</span>}
      </div>
      {adding && <AddToScope crKey={crKey} onClose={() => setAdding(false)} onDone={an => { onChange((d: any) => ({ ...d, analysis: an })); setAdding(false) }} />}
    </div>
  )
}

function AddToScope({ crKey, onClose, onDone }: { crKey: string; onClose: () => void; onDone: (a: any) => void }) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<any[]>([])
  const [note, setNote] = useState('')
  const [verdict, setVerdict] = useState('must_change')
  useEffect(() => { api.searchNodes(q).then(setHits) }, [q])
  return (
    <div className="rounded-lg border border-brand-200 bg-brand-50/40 p-3">
      <div className="flex items-center gap-2">
        <div className="flex flex-1 items-center rounded-lg border border-slate-300 bg-white px-2"><Search size={14} className="text-slate-400" />
          <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Search a service, API, table or outside system" className="w-full px-2 py-1.5 text-sm focus:outline-none" /></div>
        <select value={verdict} onChange={e => setVerdict(e.target.value)} className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm">
          {Object.entries(VERDICT).slice(0, 3).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <button onClick={onClose} className="p-1 text-slate-400"><X size={15} /></button>
      </div>
      <input value={note} onChange={e => setNote(e.target.value)} placeholder="Why? (e.g. finance asked to include this)" className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm focus:outline-none" />
      <ul className="mt-2 max-h-48 overflow-y-auto">
        {hits.map(h => (
          <li key={h.id}><button onClick={async () => onDone(await api.scope(crKey, { node_id: h.id, action: 'add', verdict, note }))}
            className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm hover:bg-white">
            <span><b>{h.label}</b> <span className="text-xs text-slate-500">{h.type}{h.parent ? ` in ${h.parent.split(':')[1]}` : ''}</span></span><Plus size={13} className="text-brand-600" /></button></li>
        ))}
      </ul>
    </div>
  )
}

function TestingSection({ a }: { a: any }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Existing automated tests to re-run</div>
        {a.tests.to_run.length ? <ul className="space-y-1.5">{a.tests.to_run.map((t: any) => (
          <li key={t.for}><details><summary className="cursor-pointer text-sm text-slate-800"><b>{t.service}</b>: {t.count} tests</summary>
            <ul className="mt-1 pl-4 font-mono text-xs text-slate-500">{t.tests.map((x: string) => <li key={x}>{x}</li>)}</ul></details></li>))}</ul> : <Empty>No existing tests found for the impacted parts.</Empty>}
      </div>
      {a.tests.gaps.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-red-600">Test gaps: parts that change but have no automated test</div>
          <ul className="space-y-1">{a.tests.gaps.map((g: any) => <li key={g.for} className="text-sm text-slate-700">• <b>{g.for}</b> ({g.service})</li>)}</ul>
        </div>
      )}
      {a.assessment.test_scenarios.length > 0 && (
        <div>
          <div className="mb-1.5 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-slate-500"><Sparkles size={12} />Suggested new test scenarios</div>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-700">{a.assessment.test_scenarios.map((s: string) => <li key={s}>{s}</li>)}</ol>
        </div>
      )}
    </div>
  )
}

function HowSection({ a }: { a: any }) {
  const st = a.stages
  const row = (name: string, m: any) => m && <li className="flex justify-between text-xs"><span>{name}</span><span className="text-slate-500">{m.status}{m.model ? ` · ${m.model}` : ''}{m.seconds ? ` · ${Math.round(m.seconds)}s` : ''}</span></li>
  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
      <div>
        <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Where the change starts (entry points)</div>
        <ul className="space-y-1">{a.entry_points.map((e: any) => (
          <li key={e.id} className="text-xs text-slate-700"><b>{e.label}</b> <span className="text-slate-400">({e.type})</span> · {e.reasons.join('; ')}</li>))}</ul>
      </div>
      <div>
        <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Pipeline steps</div>
        <ul className="space-y-1 text-slate-700">
          {row('1 · AI understands the request', st.understand)}
          {row('2 · Meaning-based search', st.semantic)}
          {row('4 · AI judges each candidate', st.judge)}
          {row('5 · AI writes the assessment', st.assess)}
        </ul>
        <p className="mt-2 text-xs text-slate-500">Git history: {st.cochange?.commits_with_code_changes ?? 0} recent commits changed source code, so there was {st.cochange?.pairs ? '' : 'not '}enough history to learn which services change together.</p>
        <p className="mt-2 text-xs text-slate-500">Candidates come only from the verified dependency map. The AI can only judge them, not invent new ones. Anything the AI could not answer falls back to rules and is marked "Rules".</p>
      </div>
    </div>
  )
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-slate-500">{children}</p>
}
