/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Sparkles, RefreshCw, Boxes, Server, FlaskConical, FileText, Users, ShieldAlert, CheckCircle2,
  ArrowRight, AlertTriangle, Network, Lock } from 'lucide-react'
import { api } from '../api'
import { PageHeader } from '../components/Shell'
import { AIStatus, Badge, Button, Card, ConfidencePill, Empty, ErrorNote, RiskBadge, Spinner, Stat, Tabs, TierBadge, VerifiedBadge, cx } from '../components/ui'
import { Cite, WhyButton } from '../components/Evidence'

export default function ImpactAnalyzer() {
  const { key } = useParams()
  const nav = useNavigate()
  const [crs, setCrs] = useState<any[]>([])
  const [report, setReport] = useState<any>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('code')
  const [excluded, setExcluded] = useState<Set<string>>(new Set())
  const [aiBusy, setAiBusy] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => { api.crs().then(setCrs).catch(e => setError(e.message)) }, [])
  useEffect(() => {
    if (!key && crs.length) nav(`/impact/${crs.find(c => c.type === 'Change Request')?.key ?? crs[0].key}`, { replace: true })
  }, [key, crs, nav])
  useEffect(() => {
    if (!key) return
    setReport(null); setError('')
    api.impact(key).then(r => {
      setReport(r)
      setExcluded(new Set(r.baseline?.excluded ?? []))
    }).catch(e => setError(e.message))
  }, [key])

  const runAI = async (force: boolean) => {
    if (!key) return
    setAiBusy(true)
    try { const ai = await api.impactAI(key, force); setReport((r: any) => ({ ...r, ai })) }
    catch (e: any) { setError(e.message) }
    finally { setAiBusy(false) }
  }

  const selectable = useMemo(() => report ? [...report.code, ...report.interfaces, ...report.external, ...report.data] : [], [report])
  const toggle = (id: string) => setExcluded(s => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const confirm = async () => {
    if (!key) return
    setSaving(true)
    try {
      const included = selectable.map((i: any) => i.id).filter((id: string) => !excluded.has(id))
      const baseline = await api.confirmBaseline(key, included, [...excluded])
      setReport((r: any) => ({ ...r, baseline }))
    } catch (e: any) { setError(e.message) } finally { setSaving(false) }
  }

  const changeRequests = crs.filter(c => c.type === 'Change Request')
  return (
    <div className="mx-auto max-w-7xl px-8 py-7">
      <PageHeader eyebrow="Before coding" title="Change Impact Analyzer"
        subtitle="Predicts what a change request will affect (code, downstream systems, data, tests, documentation, owners and controls) and shows the evidence behind every item." />

      <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-2">
        {changeRequests.map(c => (
          <button key={c.key} onClick={() => nav(`/impact/${c.key}`)}
            className={cx('rounded-xl border bg-white px-4 py-3 text-left shadow-sm transition',
              c.key === key ? 'border-brand-500 ring-2 ring-brand-100' : 'border-slate-200 hover:border-slate-300')}>
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-semibold text-brand-700">{c.key}</span>
              <div className="flex items-center gap-1.5">
                {c.baseline && <Badge tone="green"><Lock size={11} />Baseline</Badge>}
                <Badge tone={c.priority === 'High' ? 'red' : c.priority === 'Low' ? 'slate' : 'amber'}>{c.priority}</Badge>
              </div>
            </div>
            <div className="mt-1 text-sm font-medium text-slate-900">{c.summary}</div>
            <div className="mt-1 text-xs text-slate-500">{c.status} · {c.components.join(', ')}</div>
          </button>
        ))}
      </div>

      {error && <ErrorNote error={error} />}
      {!report && !error && <div className="py-16"><Spinner label="Analysing dependencies…" /></div>}
      {report && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2" title={<span className="flex items-center gap-2"><span className="font-mono text-brand-700">{report.cr.key}</span>{report.cr.summary}</span>}
              subtitle={`${report.cr.status} · Assignee ${report.cr.assignee} · Components: ${report.cr.components.join(', ')} · analysed at main @ ${report.sha}`}
              action={<Cite ids={[report.cr.evidence]} label="Jira" />}>
              <p className="text-sm leading-6 text-slate-700">{report.cr.description}</p>
              <ul className="mt-3 space-y-1">
                {report.cr.acceptance_criteria.map((a: string) => (
                  <li key={a} className="flex gap-2 text-sm text-slate-600"><CheckCircle2 size={15} className="mt-0.5 shrink-0 text-slate-400" />{a}</li>
                ))}
              </ul>
            </Card>
            <RiskCard risk={report.risk} />
          </div>

          <AIBrief ai={report.ai} busy={aiBusy} onRun={runAI} />

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
            <Stat label="Code modules" value={report.stats.modules} icon={<Boxes size={13} />} />
            <Stat label="Systems" value={report.stats.systems} icon={<Server size={13} />} />
            <Stat label="Downstream" value={report.stats.external} icon={<Network size={13} />} tone={report.stats.external ? 'text-amber-600' : undefined} />
            <Stat label="Tests to run" value={report.stats.tests} icon={<FlaskConical size={13} />} />
            <Stat label="Test gaps" value={report.stats.test_gaps} icon={<AlertTriangle size={13} />} tone={report.stats.test_gaps ? 'text-rose-600' : undefined} />
            <Stat label="Docs to review" value={report.stats.docs} icon={<FileText size={13} />} />
            <Stat label="Controls" value={report.stats.controls} icon={<ShieldAlert size={13} />} tone={report.stats.controls ? 'text-violet-700' : undefined} />
          </div>

          <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="px-5 pt-2">
              <Tabs active={tab} onChange={setTab} tabs={[
                { id: 'code', label: 'Code', count: report.code.length },
                { id: 'systems', label: 'Systems & Downstream', count: report.systems.length + report.external.length + report.interfaces.length },
                { id: 'data', label: 'Data', count: report.data.length },
                { id: 'tests', label: 'Tests', count: report.tests.to_run.length + report.tests.gaps.length },
                { id: 'docs', label: 'Docs', count: report.docs.length },
                { id: 'owners', label: 'Owners', count: report.owners.length },
                { id: 'controls', label: 'Controls', count: report.controls.length },
              ]} />
            </div>
            <div className="p-5">
              {tab === 'code' && <ItemList items={report.code} excluded={excluded} onToggle={toggle} render={(i: any) => (
                <>
                  <div className="font-mono text-sm font-medium text-slate-900">{i.label}</div>
                  <div className="mt-0.5 text-xs text-slate-500">{i.path} · {i.symbols.length} function(s): {i.symbols.slice(0, 3).map((s: any) => s.label.split('.').pop()).join(', ')}{i.symbols.length > 3 ? '…' : ''}</div>
                </>)} />}
              {tab === 'systems' && (
                <div className="space-y-6">
                  <Group title="Downstream systems outside this codebase" icon={<Network size={15} />}>
                    <ItemList items={report.external} excluded={excluded} onToggle={toggle} render={(i: any) => (
                      <><div className="text-sm font-medium text-slate-900">{i.label}</div><div className="text-xs text-slate-500">{i.description} · Owner {i.owners.join(', ')}</div></>)} />
                  </Group>
                  <Group title="Internal systems" icon={<Server size={15} />}>
                    <ItemList items={report.systems} render={(i: any) => (
                      <><div className="text-sm font-medium text-slate-900">{i.label} <Badge tone={i.criticality === 'high' ? 'red' : 'slate'}>{i.criticality} criticality</Badge></div><div className="text-xs text-slate-500">{i.reason} · Owner {i.owners.join(', ')}</div></>)} />
                  </Group>
                  <Group title="APIs" icon={<Boxes size={15} />}>
                    <ItemList items={report.interfaces} excluded={excluded} onToggle={toggle} render={(i: any) => (
                      <div className="font-mono text-sm text-slate-900">{i.label}</div>)} />
                  </Group>
                </div>
              )}
              {tab === 'data' && <ItemList items={report.data} excluded={excluded} onToggle={toggle} render={(i: any) => (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm font-medium text-slate-900">{i.label}</span>
                    <Badge>{i.kind === 'table' ? 'Table' : i.kind === 'topic' ? 'Event topic' : 'Config key'}</Badge>
                    {i.new && <Badge tone="blue">New</Badge>}
                    {(i.classifications || []).map((c: string) => <Badge key={c} tone={c === 'PII' ? 'red' : 'amber'}>{c}</Badge>)}
                  </div>
                  {i.columns?.length > 0 && <div className="mt-0.5 text-xs text-slate-500">Columns: {i.columns.map((c: string) => c.split('.')[1]).join(', ')}</div>}
                </>)} />}
              {tab === 'tests' && (
                <div className="space-y-6">
                  <Group title="Existing tests to run" icon={<FlaskConical size={15} />}>
                    <ItemList items={report.tests.to_run} render={(i: any) => (
                      <><div className="font-mono text-sm text-slate-900">{i.label}</div><div className="text-xs text-slate-500">{i.tests.map((t: any) => t.label).join(', ')}</div></>)} />
                  </Group>
                  <Group title="Test gaps: impacted code with no automated test" icon={<AlertTriangle size={15} className="text-rose-500" />}>
                    <ItemList items={report.tests.gaps.map((g: any) => ({ ...g, tier: 'inferred', why: [], seed: { reason: 'No test covers these impacted functions' } }))} render={(i: any) => (
                      <><div className="font-mono text-sm text-slate-900">{i.label}</div><div className="text-xs text-rose-600">{i.symbols.map((s: string) => s.split('.').pop()).join(', ')}</div></>)} />
                  </Group>
                  <SuggestedTests ai={report.ai} />
                </div>
              )}
              {tab === 'docs' && <ItemList items={report.docs.map((d: any) => ({ ...d, why: d.sections[0]?.why ?? [], seed: { reason: d.reason ?? d.sections[0]?.seed?.reason } }))} render={(i: any) => (
                <><div className="font-mono text-sm text-slate-900">{i.label}</div><div className="text-xs text-slate-500">{i.sections.length ? 'Sections: ' + i.sections.map((s: any) => s.label.split('§ ')[1]).join(', ') : i.reason}</div></>)} />}
              {tab === 'owners' && (
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {report.owners.map((o: any) => (
                    <div key={o.id} className="flex items-start gap-3 rounded-lg border border-slate-200 p-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-600"><Users size={16} /></div>
                      <div>
                        <div className="text-sm font-medium text-slate-900">{o.label} {o.kind === 'person' && <Badge tone="violet">Approver</Badge>}</div>
                        <ul className="mt-0.5 text-xs text-slate-500">{o.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {tab === 'controls' && (report.controls.length ? (
                <div className="space-y-3">
                  {report.controls.map((c: any) => (
                    <div key={c.id} className="rounded-lg border border-violet-200 bg-violet-50/40 p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="flex items-center gap-2"><span className="font-mono text-xs font-semibold text-violet-700">{c.id}</span><span className="text-sm font-semibold text-slate-900">{c.name}</span></div>
                          <p className="mt-1 text-sm text-slate-600">{c.description}</p>
                        </div>
                        <WhyButton title={`${c.id} ${c.name}`} ids={c.evidence} reason={'Triggered because: ' + c.reasons.join('; ')} tier="curated" />
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs">
                        {c.reasons.map((r: string) => <Badge key={r} tone="violet">{r}</Badge>)}
                      </div>
                      <div className="mt-2 text-xs text-slate-500">Evidence required: {c.required_evidence.map((r: any) => r.type === 'approver_role' ? `approval by ${r.role}` : r.type === 'test_change' ? 'test changes' : 'documentation update').join(' · ')}</div>
                    </div>
                  ))}
                  <p className="text-xs text-slate-500">Controls are synthetic examples from the curated catalog. The tool says when a rule is triggered. It does not decide compliance.</p>
                </div>
              ) : <Empty>No configured controls are triggered by this change.</Empty>)}
            </div>
          </section>

          <BaselineBar report={report} count={selectable.length - excluded.size} excluded={excluded.size} saving={saving} onConfirm={confirm}
            onNext={() => report.cr && nav('/release')} />
        </div>
      )}
    </div>
  )
}

function RiskCard({ risk }: { risk: any }) {
  const tone = risk.level === 'High' ? 'from-rose-50 border-rose-200' : risk.level === 'Medium' ? 'from-amber-50 border-amber-200' : 'from-emerald-50 border-emerald-200'
  return (
    <section className={cx('rounded-xl border bg-gradient-to-b to-white p-5 shadow-sm', tone)}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">Change risk</h3>
        <RiskBadge level={risk.level} large />
      </div>
      <ul className="mt-4 space-y-2">
        {risk.reasons.map((r: string) => (
          <li key={r} className="flex gap-2 text-sm text-slate-700"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />{r}</li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-slate-500">Rule-based score: {risk.points} points (personal data, downstream systems, controls, test gaps, criticality).</p>
    </section>
  )
}

function AIBrief({ ai, busy, onRun }: { ai: any; busy: boolean; onRun: (force: boolean) => void }) {
  const has = ai?.summary
  return (
    <Card title={<span className="flex items-center gap-2"><Sparkles size={16} className="text-brand-600" />AI impact brief</span>}
      subtitle="Written by a local model from the evidence below. Every claim is checked against cited evidence."
      action={<div className="flex items-center gap-3"><AIStatus ai={ai} />
        <Button size="sm" variant={has ? 'ghost' : 'primary'} disabled={busy} onClick={() => onRun(!!has)} icon={busy ? <RefreshCw size={13} className="animate-spin" /> : <Sparkles size={13} />}>
          {busy ? 'Generating locally…' : has ? 'Re-run' : 'Generate with local AI'}
        </Button></div>}>
      {busy && !has && <Spinner label="The local model is reading the evidence. On a laptop CPU this takes 1–3 minutes." />}
      {!busy && !has && <p className="text-sm text-slate-500">{ai?.status === 'unavailable' ? 'Local AI is offline. All findings below come from deterministic analysis and are still valid.' : 'Generate a plain-English brief of the impact, key risks and suggested tests.'}</p>}
      {has && (
        <div className="space-y-4">
          <p className="text-[15px] leading-7 text-slate-800">{ai.summary}</p>
          {ai.key_risks?.length > 0 && (
            <div>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Key risks</h4>
              <ul className="space-y-2">
                {ai.key_risks.map((r: any, i: number) => (
                  <li key={i} className={cx('rounded-lg border px-3 py-2 text-sm', r.verified ? 'border-slate-200' : 'border-amber-200 bg-amber-50/50 text-slate-500')}>
                    <div className="flex items-start justify-between gap-3">
                      <span>{r.text}</span>
                      <span className="flex shrink-0 items-center gap-1"><VerifiedBadge verified={r.verified} issues={r.issues} /><Cite ids={r.evidence_ids} /></span>
                    </div>
                    {r.quote && <div className="mt-1 font-mono text-xs text-slate-500">“{r.quote}”</div>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {ai.total_count > 0 && <p className="text-xs text-slate-500">{ai.verified_count} of {ai.total_count} AI claims passed verification. Unverified claims are greyed out and are not used in the baseline.</p>}
        </div>
      )}
    </Card>
  )
}

function SuggestedTests({ ai }: { ai: any }) {
  if (!ai?.suggested_tests?.length) return null
  return (
    <Group title="AI-suggested new test cases" icon={<Sparkles size={15} className="text-brand-600" />}>
      <ul className="space-y-2">
        {ai.suggested_tests.map((t: any, i: number) => (
          <li key={i} className={cx('flex items-start justify-between gap-3 rounded-lg border px-3 py-2 text-sm', t.verified ? 'border-slate-200' : 'border-amber-200 bg-amber-50/50 text-slate-500')}>
            <div><div className="font-medium text-slate-800">{t.title}</div><div className="font-mono text-xs text-slate-500">target: {t.target}</div></div>
            <span className="flex shrink-0 items-center gap-1"><VerifiedBadge verified={t.verified} issues={t.issues} /><Cite ids={t.evidence_ids} /></span>
          </li>
        ))}
      </ul>
    </Group>
  )
}

function Group({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <div>
      <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800">{icon}{title}</h4>
      {children}
    </div>
  )
}

function ItemList({ items, render, excluded, onToggle }: { items: any[]; render: (i: any) => ReactNode; excluded?: Set<string>; onToggle?: (id: string) => void }) {
  if (!items.length) return <Empty>Nothing impacted in this category.</Empty>
  return (
    <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
      {items.map(i => {
        const off = excluded?.has(i.id)
        return (
          <li key={i.id} className={cx('flex items-center gap-4 px-4 py-3', off && 'bg-slate-50 opacity-50')}>
            {onToggle && <input type="checkbox" checked={!off} onChange={() => onToggle(i.id)} className="h-4 w-4 rounded border-slate-300 text-brand-600" title="Include in baseline" />}
            <div className="min-w-0 flex-1">
              {render(i)}
              {i.seed?.reason && <div className="mt-1 text-xs text-slate-500">↳ {i.seed.reason}{i.why?.length ? ` · ${i.why.length}-step dependency path` : ''}</div>}
            </div>
            {i.confidence && <ConfidencePill level={i.confidence} score={i.score} />}
            {i.tier && <TierBadge tier={i.tier} />}
            <WhyButton title={i.label} ids={i.evidence ?? []} why={i.why} reason={i.seed?.reason || i.reason} tier={i.tier} />
          </li>
        )
      })}
    </ul>
  )
}

function BaselineBar({ report, count, excluded, saving, onConfirm, onNext }: any) {
  const b = report.baseline
  return (
    <div className="sticky bottom-4 z-10 flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white/95 px-5 py-3.5 shadow-lg backdrop-blur">
      {b ? (
        <div className="flex items-center gap-3 text-sm">
          <CheckCircle2 size={20} className="text-emerald-600" />
          <div><span className="font-semibold text-slate-900">Baseline confirmed</span> by {b.confirmed_by} · {new Date(b.confirmed_at).toLocaleString()} · {b.included.length} items locked{b.excluded.length ? `, ${b.excluded.length} excluded` : ''}</div>
          <TierBadge tier="confirmed" />
        </div>
      ) : (
        <div className="text-sm text-slate-600"><span className="font-semibold text-slate-900">Review the prediction.</span> Untick anything that is out of scope, then lock it as the baseline that the pull request will be checked against.</div>
      )}
      <div className="flex shrink-0 items-center gap-2">
        <Button variant={b ? 'secondary' : 'primary'} onClick={onConfirm} disabled={saving} icon={<Lock size={14} />}>
          {saving ? 'Saving…' : b ? 'Update baseline' : `Confirm baseline (${count} items${excluded ? `, ${excluded} excluded` : ''})`}
        </Button>
        {b && <Button variant="primary" onClick={onNext} icon={<ArrowRight size={14} />}>Check the pull request</Button>}
      </div>
    </div>
  )
}
