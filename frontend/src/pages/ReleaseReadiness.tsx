/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, XCircle, AlertOctagon, HelpCircle, Sparkles, RefreshCw, GitPullRequest, FlaskConical, FileWarning,
  ShieldCheck, Network, ArrowRight, Lock, GitCommitHorizontal } from 'lucide-react'
import { api } from '../api'
import { PageHeader } from '../components/Shell'
import { AIStatus, Badge, Button, Card, Empty, ErrorNote, Spinner, cx } from '../components/ui'
import { Cite, WhyButton } from '../components/Evidence'

export default function ReleaseReadiness() {
  const { pr } = useParams()
  const nav = useNavigate()
  const [prs, setPrs] = useState<any[]>([])
  const [rec, setRec] = useState<any>(null)
  const [error, setError] = useState('')
  const [aiBusy, setAiBusy] = useState(false)
  const n = pr ? Number(pr) : null

  useEffect(() => { api.prs().then(setPrs).catch(e => setError(e.message)) }, [])
  useEffect(() => { if (!pr && prs.length) nav(`/release/${prs[0].number}`, { replace: true }) }, [pr, prs, nav])
  useEffect(() => {
    if (!n) return
    setRec(null); setError('')
    api.reconcile(n).then(setRec).catch(e => setError(e.message))
  }, [n])

  const runAI = async (force: boolean) => {
    if (!n) return
    setAiBusy(true)
    try { const ai = await api.reviewAI(n, force); setRec((r: any) => ({ ...r, ai })) } catch (e: any) { setError(e.message) } finally { setAiBusy(false) }
  }

  return (
    <div className="mx-auto max-w-7xl px-8 py-7">
      <PageHeader eyebrow="Before merging" title="Release Readiness"
        subtitle="Compares the confirmed impact baseline with what the pull request actually changed: what matched, what was missed, what was unplanned, and whether required controls have evidence." />

      <div className="mb-6 flex flex-wrap gap-2">
        {prs.map(p => (
          <button key={p.number} onClick={() => nav(`/release/${p.number}`)}
            className={cx('flex items-center gap-2 rounded-lg border bg-white px-3 py-2 text-left text-sm shadow-sm transition',
              p.number === n ? 'border-brand-500 ring-2 ring-brand-100' : 'border-slate-200 hover:border-slate-300')}>
            <GitPullRequest size={15} className={p.state === 'open' ? 'text-emerald-600' : 'text-violet-600'} />
            <span className="font-mono text-xs text-slate-500">#{p.number}</span>
            <span className="max-w-xs truncate font-medium text-slate-800">{p.title}</span>
            <Badge tone={p.state === 'open' ? 'green' : 'violet'}>{p.state}</Badge>
          </button>
        ))}
      </div>

      {error && <ErrorNote error={error} />}
      {!rec && !error && <div className="py-16"><Spinner label="Comparing the plan with the code changes…" /></div>}
      {rec && (
        <div className="space-y-6">
          <Verdict rec={rec} />

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2" title={<span className="flex items-center gap-2"><Sparkles size={16} className="text-brand-600" />AI review summary</span>}
              subtitle="Written by the local model from the comparison results and cited evidence."
              action={<div className="flex items-center gap-3"><AIStatus ai={rec.ai} />
                <Button size="sm" variant={rec.ai?.summary ? 'ghost' : 'primary'} disabled={aiBusy} onClick={() => runAI(!!rec.ai?.summary)}
                  icon={aiBusy ? <RefreshCw size={13} className="animate-spin" /> : <Sparkles size={13} />}>
                  {aiBusy ? 'Generating locally…' : rec.ai?.summary ? 'Re-run' : 'Generate with local AI'}
                </Button></div>}>
              {rec.ai?.summary
                ? <p className="text-[15px] leading-7 text-slate-800">{rec.ai.summary}<Cite ids={rec.ai.evidence_ids} /></p>
                : <p className="text-sm text-slate-500">{aiBusy ? 'The local model is summarising. This takes about a minute on a laptop CPU.' : 'Generate a plain-English release summary for the change board.'}</p>}
            </Card>
            <Card title="Pull request" action={<Cite ids={[rec.pr.evidence]} label="PR" />}>
              <div className="space-y-2 text-sm">
                <div className="font-medium text-slate-900">#{rec.pr.number} {rec.pr.title}</div>
                <div className="text-slate-500">by {rec.pr.author} · <code className="text-xs">{rec.pr.head_ref}</code></div>
                <div className="text-slate-500">Approved by: {rec.pr.approvers.join(', ') || 'nobody yet'}</div>
                <ul className="mt-2 space-y-1 border-t border-slate-100 pt-2">
                  {rec.pr.commits.map((c: any) => <li key={c.sha} className="flex gap-2 text-xs text-slate-600"><GitCommitHorizontal size={14} className="shrink-0 text-slate-400" /><code>{c.short}</code>{c.subject}</li>)}
                </ul>
                <div className="flex items-center gap-2 border-t border-slate-100 pt-2 text-xs text-slate-500">
                  {rec.compared_against === 'baseline'
                    ? <><Lock size={13} className="text-emerald-600" />Compared with the baseline confirmed by {rec.baseline_confirmed_by}</>
                    : <><HelpCircle size={13} />No confirmed baseline yet, so compared with the automatic prediction. <Link className="text-brand-700 underline" to={`/impact/${rec.pr.jira_key}`}>Confirm it</Link></>}
                </div>
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Column title="Matched the plan" tone="green" icon={<CheckCircle2 size={16} />} items={rec.code.confirmed}
              render={(i: any) => <><div className="font-mono text-sm text-slate-900">{i.label}</div><div className="text-xs text-slate-500">{i.symbols.map((s: any) => `${s.label.split('.').pop()} (${s.change})`).join(', ')}</div></>} />
            <Column title="Unplanned changes" tone="amber" icon={<AlertOctagon size={16} />} items={rec.code.surprise}
              render={(i: any) => <><div className="flex items-center gap-2 font-mono text-sm text-slate-900">{i.label}{i.severity === 'high' && <Badge tone="red">High</Badge>}</div>
                <ul className="mt-1 text-xs text-slate-600">{i.reasons.map((r: string) => <li key={r}>• {r}</li>)}</ul></>} />
            <Column title="Planned but not changed" tone="red" icon={<XCircle size={16} />} items={rec.code.missed}
              render={(i: any) => <><div className="flex items-center gap-2 font-mono text-sm text-slate-900">{i.label}<Badge tone={i.severity === 'likely_miss' ? 'red' : 'slate'}>{i.severity === 'likely_miss' ? 'Likely miss' : 'Review'}</Badge></div>
                <ul className="mt-1 text-xs text-slate-600">{i.reasons.map((r: string) => <li key={r}>• {r}</li>)}</ul></>} />
          </div>

          <Card title={<span className="flex items-center gap-2"><ShieldCheck size={16} className="text-violet-600" />Control evidence checklist</span>}
            subtitle="Controls triggered by the actual changes, checked against evidence in the pull request.">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {rec.controls.map((c: any) => (
                <div key={c.id} className={cx('rounded-lg border p-4', c.satisfied ? 'border-emerald-200 bg-emerald-50/40' : 'border-rose-200 bg-rose-50/40')}>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2"><span className="font-mono text-xs font-semibold text-violet-700">{c.id}</span>
                        {!c.predicted && <Badge tone="amber">Not predicted</Badge>}</div>
                      <div className="text-sm font-semibold text-slate-900">{c.name}</div>
                      <div className="mt-0.5 text-xs text-slate-500">{c.reasons.join(' · ')}</div>
                    </div>
                    {c.satisfied ? <CheckCircle2 className="shrink-0 text-emerald-600" size={20} /> : <XCircle className="shrink-0 text-rose-600" size={20} />}
                  </div>
                  <ul className="mt-3 space-y-1.5">
                    {c.checks.map((ch: any, i: number) => (
                      <li key={i} className="flex items-start gap-2 text-sm">
                        {ch.satisfied ? <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600" /> : <XCircle size={15} className="mt-0.5 shrink-0 text-rose-500" />}
                        <span><span className="text-slate-800">{ch.requirement}</span><span className="text-slate-500">: {ch.detail}</span></span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              {!rec.controls.length && <Empty>No controls triggered.</Empty>}
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card title={<span className="flex items-center gap-2"><FlaskConical size={16} />Testing</span>}>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Test files changed</div>
              <div className="mt-1 space-y-1">{rec.tests.changed.length ? rec.tests.changed.map((t: string) => <div key={t} className="font-mono text-sm text-slate-700">{t}</div>) : <span className="text-sm text-slate-500">None</span>}</div>
              <div className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">Changed code with no test</div>
              <ul className="mt-1 space-y-1">{rec.tests.untested.map((u: any) => (
                <li key={u.id} className="flex items-center justify-between font-mono text-sm text-rose-700">{u.label.split('.').slice(-2).join('.')}<Cite ids={u.evidence} label="diff" /></li>))}</ul>
            </Card>
            <Card title={<span className="flex items-center gap-2"><Network size={16} />Data & downstream</span>}>
              <ul className="space-y-2">
                {rec.data.map((d: any) => (
                  <li key={d.id} className="flex flex-wrap items-center gap-2 text-sm">
                    <code className="text-slate-800">{d.label}</code>
                    <Badge tone={d.status === 'confirmed' ? 'green' : d.status === 'surprise' ? 'amber' : 'red'}>{d.status === 'surprise' ? 'unplanned' : d.status}</Badge>
                    {d.classifications.map((c: string) => <Badge key={c} tone={c === 'PII' ? 'red' : 'slate'}>{c}</Badge>)}
                  </li>
                ))}
              </ul>
              <div className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">Downstream systems affected</div>
              <ul className="mt-1 space-y-1">{rec.external.map((x: any) => (
                <li key={x.id} className="text-sm text-slate-700">{x.label} <span className="text-xs text-slate-500">via {x.via.map((v: string) => v.split(':')[1]).join(', ')}</span></li>))}</ul>
            </Card>
            <Card title={<span className="flex items-center gap-2"><FileWarning size={16} />Documentation follow-ups</span>}
              action={<Link to="/docs" className="flex items-center gap-1 text-xs font-medium text-brand-700">Open Doc Health<ArrowRight size={12} /></Link>}>
              {rec.doc_findings.length ? (
                <ul className="space-y-2">{rec.doc_findings.map((f: any) => (
                  <li key={f.id} className="text-sm"><div className="text-slate-800">{f.title.replace(/`/g, '')}</div><div className="font-mono text-xs text-slate-500">{f.doc_path}</div></li>))}</ul>
              ) : <Empty>Docs are in sync with this change.</Empty>}
            </Card>
          </div>

          <div className="flex items-center gap-6 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm shadow-sm">
            <span className="font-semibold text-slate-900">Prediction accuracy for this change</span>
            <span className="text-slate-600">Precision <b>{Math.round((rec.accuracy.precision ?? 0) * 100)}%</b> <span className="text-xs text-slate-400">(predicted modules that really changed)</span></span>
            <span className="text-slate-600">Recall <b>{Math.round((rec.accuracy.recall ?? 0) * 100)}%</b> <span className="text-xs text-slate-400">(changed modules that were predicted)</span></span>
          </div>
        </div>
      )}
    </div>
  )
}

function Verdict({ rec }: { rec: any }) {
  const v = rec.verdict
  return (
    <section className={cx('rounded-xl border p-5 shadow-sm', v.ready ? 'border-emerald-200 bg-emerald-50' : 'border-rose-200 bg-rose-50')}>
      <div className="flex items-center gap-3">
        {v.ready ? <CheckCircle2 size={28} className="text-emerald-600" /> : <AlertOctagon size={28} className="text-rose-600" />}
        <div>
          <div className={cx('text-lg font-semibold', v.ready ? 'text-emerald-900' : 'text-rose-900')}>
            {v.ready ? 'Ready to release' : `Not ready to release: ${v.high} blocking action${v.high === 1 ? '' : 's'}`}
          </div>
          <div className="text-sm text-slate-600">PR #{rec.pr.number} for {rec.pr.jira_key} · {v.actions.length} action(s) in total</div>
        </div>
      </div>
      {v.actions.length > 0 && (
        <ol className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2">
          {v.actions.map((a: any, i: number) => (
            <li key={i} className="flex items-start gap-2 rounded-lg bg-white/70 px-3 py-2 text-sm">
              <span className={cx('mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white', a.severity === 'high' ? 'bg-rose-500' : 'bg-amber-500')}>{i + 1}</span>
              <span className="text-slate-800">{a.text}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function Column({ title, tone, icon, items, render }: { title: string; tone: string; icon: ReactNode; items: any[]; render: (i: any) => ReactNode }) {
  const head = { green: 'text-emerald-700 bg-emerald-50 border-emerald-200', amber: 'text-amber-800 bg-amber-50 border-amber-200', red: 'text-rose-700 bg-rose-50 border-rose-200' }[tone]
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className={cx('flex items-center justify-between border-b px-4 py-2.5 text-sm font-semibold', head)}>
        <span className="flex items-center gap-2">{icon}{title}</span><span>{items.length}</span>
      </header>
      <ul className="divide-y divide-slate-100">
        {items.length ? items.map(i => (
          <li key={i.id} className="flex items-start justify-between gap-2 px-4 py-3">
            <div className="min-w-0">{render(i)}</div>
            <WhyButton title={i.label} ids={i.evidence ?? []} reason={i.reasons?.join('; ')} />
          </li>
        )) : <li className="px-4 py-6 text-center text-sm text-slate-400">None</li>}
      </ul>
    </section>
  )
}
