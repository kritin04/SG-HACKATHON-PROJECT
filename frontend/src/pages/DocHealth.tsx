/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState } from 'react'
import { FileWarning, FilePlus2, CheckCircle2, XCircle, Sparkles, RefreshCw, Pencil, GitBranch, Ticket, HeartPulse, Cpu } from 'lucide-react'
import { api } from '../api'
import { PageHeader } from '../components/Shell'
import { DiffView } from '../components/DiffView'
import { AIStatus, Badge, Button, Card, Empty, ErrorNote, Spinner, Stat, VerifiedBadge, cx } from '../components/ui'
import { Cite, useEvidence } from '../components/Evidence'

export default function DocHealth() {
  const [findings, setFindings] = useState<any[] | null>(null)
  const [stats, setStats] = useState<any>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [f, s] = await Promise.all([api.findings(), api.docStats()])
      setFindings(f); setStats(s)
      setSelected(sel => sel ?? f.find((x: any) => x.status === 'open')?.id ?? f[0]?.id ?? null)
    } catch (e: any) { setError(e.message) }
  }, [])
  useEffect(() => { load() }, [load])

  const replace = (f: any) => { setFindings(fs => fs!.map(x => x.id === f.id ? f : x)); api.docStats().then(setStats) }
  const current = findings?.find(f => f.id === selected)

  return (
    <div className="mx-auto max-w-7xl px-8 py-7">
      <PageHeader eyebrow="After shipping" title="Self-Healing Documentation"
        subtitle="Finds documentation made stale by completed Jira stories and merged code, explains the evidence, and drafts a minimal fix for a human to approve." />
      {error && <ErrorNote error={error} />}
      {stats && (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="Doc health" value={`${stats.health}%`} icon={<HeartPulse size={13} />} tone={stats.health >= 90 ? 'text-emerald-600' : stats.health >= 70 ? 'text-amber-600' : 'text-rose-600'}
            hint={`Sections without open findings: ${stats.sections - stats.affected_sections} of ${stats.sections}. It was ${stats.health_before}% before any fixes.`} />
          <Stat label="Stale sections" value={stats.stale} icon={<FileWarning size={13} />} tone={stats.stale ? 'text-rose-600' : undefined} />
          <Stat label="Missing docs" value={stats.missing} icon={<FilePlus2 size={13} />} tone={stats.missing ? 'text-amber-600' : undefined} />
          <Stat label="Fixes approved" value={stats.approved} icon={<CheckCircle2 size={13} />} tone="text-emerald-600" />
          <Stat label="Stories done without doc updates" value={stats.stories_without_doc_updates.length} icon={<Ticket size={13} />}
            hint={stats.stories_without_doc_updates.join(', ')} />
        </div>
      )}
      {!findings && !error && <Spinner label="Scanning completed work against the documentation…" />}
      {findings && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[360px_1fr]">
          <div className="space-y-2">
            {findings.map(f => (
              <button key={f.id} onClick={() => setSelected(f.id)}
                className={cx('w-full rounded-xl border bg-white px-4 py-3 text-left shadow-sm transition',
                  f.id === selected ? 'border-brand-500 ring-2 ring-brand-100' : 'border-slate-200 hover:border-slate-300',
                  f.status !== 'open' && 'opacity-70')}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <Badge tone={f.kind === 'stale' ? 'red' : 'amber'}>{f.kind === 'stale' ? 'Stale' : 'Missing'}</Badge>
                    <Badge tone={f.severity === 'high' ? 'red' : 'slate'}>{f.severity}</Badge>
                  </div>
                  <StatusBadge status={f.status} />
                </div>
                <div className="mt-2 text-sm font-medium text-slate-900">{f.title.replace(/`/g, '')}</div>
                <div className="mt-1 font-mono text-xs text-slate-500">{f.doc_path} § {f.section_heading}</div>
                <div className="mt-1.5 text-xs text-slate-500">{f.story} · {f.story_summary}</div>
              </button>
            ))}
            {!findings.length && <Empty>All documentation is in sync with completed work.</Empty>}
          </div>
          {current ? <FindingDetail f={current} onChange={replace} /> : <Empty>Select a finding</Empty>}
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'approved') return <Badge tone="green"><CheckCircle2 size={11} />Approved</Badge>
  if (status === 'rejected') return <Badge tone="slate"><XCircle size={11} />Rejected</Badge>
  return <Badge tone="blue">Open</Badge>
}

function FindingDetail({ f, onChange }: { f: any; onChange: (f: any) => void }) {
  const open = useEvidence()
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(f.proposed)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [reason, setReason] = useState('')
  useEffect(() => { setText(f.proposed); setEditing(false); setError(''); setReason('') }, [f.id, f.proposed])

  const act = async (fn: () => Promise<any>, label: string) => {
    setBusy(label); setError('')
    try { onChange(await fn()) } catch (e: any) { setError(e.message) } finally { setBusy(null) }
  }
  const ai = f.ai
  const decided = f.status !== 'open'

  return (
    <div className="space-y-5">
      <Card title={f.title.replace(/`/g, '')} subtitle={`${f.doc_path} § ${f.section_heading} · ${f.id}`}
        action={<Button size="sm" variant="ghost" onClick={() => open({ title: f.title.replace(/`/g, ''), ids: f.evidence, reason: f.explanation })}>View all evidence</Button>}>
        <p className="text-sm leading-6 text-slate-700">{f.explanation}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <Badge tone="blue"><Ticket size={11} />{f.story}: {f.story_summary}</Badge>
          {f.pr && <Badge>PR #{f.pr} merged</Badge>}
          {!f.docs_touched_in_pr && <Badge tone="amber">Story closed with no documentation change</Badge>}
          <Badge tone="blue"><Cpu size={11} />Detected by rule: {f.detector.replace(/_/g, ' ')}</Badge>
        </div>
      </Card>

      <Card title="Proposed update"
        subtitle={f.proposed_source === 'ai' ? 'Drafted by the local AI, verified against the code, limited to this section.' : 'Rule-based draft (deterministic). Use local AI to polish the wording.'}
        action={<div className="flex items-center gap-2">
          {f.proposed_source === 'ai' ? <VerifiedBadge verified /> : <Badge>Rule-based</Badge>}
          <AIStatus ai={ai} />
          {!decided && <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => act(() => api.docAI(f.id, ai?.status === 'cached' || ai?.status === 'generated'), 'ai')}
            icon={busy === 'ai' ? <RefreshCw size={13} className="animate-spin" /> : <Sparkles size={13} />}>
            {busy === 'ai' ? 'Drafting locally…' : ai?.updated_section ? 'Re-draft with AI' : 'Draft with local AI'}</Button>}
        </div>}>
        {busy === 'ai' && <div className="mb-3"><Spinner label="The local model is rewriting the section (about 30–60 s on CPU)…" /></div>}
        {ai?.updated_section && !ai.verified && (
          <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            The AI draft failed verification ({ai.issues.join('; ')}), so the rule-based draft is shown instead.
          </div>
        )}
        {ai?.change_summary && f.proposed_source === 'ai' && <p className="mb-3 text-sm text-slate-600">{ai.change_summary}<Cite ids={ai.evidence_ids} /></p>}
        {editing && !decided
          ? <textarea value={text} onChange={e => setText(e.target.value)} rows={Math.max(8, text.split('\n').length + 2)}
              className="w-full rounded-lg border border-slate-300 p-3 font-mono text-[13px] leading-6 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100" />
          : <DiffView lines={decided && f.decision?.final_text ? diffLocal(f.section_text, f.decision.final_text) : editing ? diffLocal(f.section_text, text) : f.diff} />}

        {error && <div className="mt-3"><ErrorNote error={error} /></div>}
        {decided ? (
          <div className={cx('mt-4 flex items-center gap-2 rounded-lg px-4 py-3 text-sm', f.status === 'approved' ? 'bg-emerald-50 text-emerald-800' : 'bg-slate-100 text-slate-700')}>
            {f.status === 'approved' ? <><GitBranch size={16} />Approved by {f.decision.decided_by} and committed to branch <code>docs/auto-heal</code> as <code>{f.decision.commit_sha?.slice(0, 7)}</code>, ready for a normal doc review.</>
              : <><XCircle size={16} />Rejected by {f.decision.decided_by}{f.decision.reason ? `: ${f.decision.reason}` : ''}</>}
          </div>
        ) : (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Button variant="ghost" onClick={() => setEditing(e => !e)} icon={<Pencil size={14} />}>{editing ? 'Preview diff' : 'Edit'}</Button>
              <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason (required to reject)"
                className="w-56 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
              <Button variant="danger" disabled={!!busy || !reason.trim()} onClick={() => act(() => api.decide(f.id, 'reject', undefined, reason), 'reject')} icon={<XCircle size={14} />}>Reject</Button>
            </div>
            <Button variant="success" disabled={!!busy} onClick={() => act(() => api.decide(f.id, 'approve', text, editing ? 'Edited by reviewer' : undefined), 'approve')}
              icon={busy === 'approve' ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}>
              Approve & commit to doc branch
            </Button>
          </div>
        )}
      </Card>
    </div>
  )
}

function diffLocal(a: string, b: string) {
  // simple line diff for live edits (server diff is used otherwise)
  const A = a.split('\n'), B = b.split('\n')
  const setA = new Set(A), setB = new Set(B)
  const out: { type: 'same' | 'add' | 'del'; text: string }[] = []
  let i = 0, j = 0
  while (i < A.length || j < B.length) {
    if (i < A.length && j < B.length && A[i] === B[j]) { out.push({ type: 'same', text: A[i] }); i++; j++ }
    else if (i < A.length && !setB.has(A[i])) { out.push({ type: 'del', text: A[i] }); i++ }
    else if (j < B.length && !setA.has(B[j])) { out.push({ type: 'add', text: B[j] }); j++ }
    else if (i < A.length) { out.push({ type: 'del', text: A[i] }); i++ }
    else { out.push({ type: 'add', text: B[j] }); j++ }
  }
  return out
}
