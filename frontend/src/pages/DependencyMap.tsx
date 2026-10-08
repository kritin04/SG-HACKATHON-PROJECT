/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import cytoscape from 'cytoscape'
import { Search, Zap, X, Route, Network, Boxes, Database, Info, ShieldCheck, Sparkles, Code2, Settings2, BookMarked, Lock } from 'lucide-react'
import { api, VERDICT } from '../api'
import { verdictBySystemNode } from '../components/ImpactMap'
import { buildElements, index, journeyOverlay, type View } from './mapLayout'
import { Badge, Button, Spinner, ErrorNote, cx } from '../components/ui'
import { useEvidence } from '../components/Evidence'

const STYLE: any[] = [
  { selector: 'node', style: {
    label: 'data(label)', 'font-family': 'Inter, Segoe UI, sans-serif', 'font-size': 13, 'text-wrap': 'wrap', 'text-max-width': 170,
    'text-valign': 'center', 'text-halign': 'center', color: '#1e293b', 'background-color': '#ffffff', 'border-width': 1.5, 'line-height': 1.35,
    'border-color': '#cbd5e1', shape: 'round-rectangle', width: 168, height: 50 } },
  { selector: 'node.user', style: { shape: 'ellipse', width: 120, height: 54, 'background-color': '#f1f5f9', 'border-color': '#64748b' } },
  { selector: 'node.service', style: { 'background-color': '#eef4ff', 'border-color': '#3b6ef5', 'font-weight': 600 } },
  { selector: 'node.database', style: { shape: 'barrel', 'background-color': '#fffbeb', 'border-color': '#f59e0b', width: 150, height: 58 } },
  { selector: 'node.external', style: { shape: 'cut-rectangle', 'background-color': '#f5f3ff', 'border-color': '#7c3aed', 'border-style': 'dashed', width: 190 } },
  { selector: 'node.endpoint', style: { width: 210, height: 24, 'font-size': 11, 'text-wrap': 'none', 'border-color': '#93c5fd', 'font-weight': 500, color: '#1e3a8a' } },
  { selector: 'node.table', style: { width: 200, height: 26, 'font-size': 11, 'text-wrap': 'none', 'background-color': '#fff7ed', 'border-color': '#fb923c' } },
  { selector: 'node.bigtable', style: { height: 48, width: 220 } },
  { selector: 'node.table.sensitive', style: { 'background-color': '#fff1f2', 'border-color': '#e11d48' } },
  { selector: ':parent', style: { 'text-valign': 'top', 'text-halign': 'center', 'text-margin-y': -4, padding: 14, 'font-weight': 600,
    'background-opacity': 0.55, shape: 'round-rectangle' } },
  { selector: 'edge', style: {
    'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.9, width: 1.6, 'line-color': '#94a3b8',
    'target-arrow-color': '#94a3b8', label: 'data(label)', 'font-size': 10.5, color: '#475569', 'text-background-color': '#ffffff',
    'text-background-opacity': 1, 'text-background-padding': 2, 'text-wrap': 'wrap', 'text-max-width': 140 } },
  { selector: 'edge.calls_api', style: { 'line-color': '#3b6ef5', 'target-arrow-color': '#3b6ef5', width: 2 } },
  { selector: 'edge.reads', style: { 'line-color': '#10b981', 'target-arrow-color': '#10b981' } },
  { selector: 'edge.writes', style: { 'line-color': '#f97316', 'target-arrow-color': '#f97316' } },
  { selector: 'edge.readwrite', style: { 'line-color': '#0891b2', 'target-arrow-color': '#0891b2' } },
  { selector: 'edge.trusts_tokens_from', style: { 'line-style': 'dotted', 'line-color': '#cbd5e1', 'target-arrow-color': '#cbd5e1', 'font-size': 8, color: '#94a3b8' } },
  { selector: 'edge.consumes', style: { 'line-style': 'dashed', 'line-color': '#7c3aed', 'target-arrow-color': '#7c3aed' } },
  { selector: 'edge.origin-ai', style: { 'line-style': 'dashed' } },
  { selector: '.faded', style: { opacity: 0.12 } },
  { selector: 'node.hl', style: { 'border-width': 3, 'border-color': '#0f172a' } },
  { selector: 'edge.hl', style: { width: 3, 'z-index': 10 } },
  { selector: 'node.wi-src', style: { 'border-width': 4, 'border-color': '#0f172a', 'background-color': '#e2e8f0' } },
  { selector: 'node.wi-high', style: { 'background-color': '#fee2e2', 'border-color': '#ef4444', 'border-width': 2.5 } },
  { selector: 'node.wi-med', style: { 'background-color': '#ffedd5', 'border-color': '#f97316', 'border-width': 2.5 } },
  { selector: 'node.wi-low', style: { 'background-color': '#fef9c3', 'border-color': '#eab308', 'border-width': 2.5 } },
  { selector: 'edge.jstep', style: { width: 4, 'line-color': '#0f172a', 'target-arrow-color': '#0f172a', label: 'data(stepLabel)', 'font-size': 12,
    'font-weight': 700, color: '#ffffff', 'text-background-color': '#0f172a', 'text-background-shape': 'roundrectangle', 'text-background-padding': 3, 'z-index': 20 } },
  { selector: 'node.jnode', style: { 'border-width': 3, 'border-color': '#0f172a' } },
  ...Object.entries(VERDICT).map(([k, v]) => ({ selector: `node.v-${k}`, style: k === 'not_impacted'
    ? { opacity: 0.45 } : { 'background-color': v.color + '26', 'border-color': v.color, 'border-width': 3.5 } })),
  { selector: ':selected', style: { 'border-width': 3.5, 'border-color': '#1d4ed8', 'overlay-opacity': 0 } },
]

const VIEWS: { id: View; label: string; icon: any; hint: string }[] = [
  { id: 'system', label: 'System', icon: Network, hint: 'Services, databases and outside systems' },
  { id: 'apis', label: 'Services & APIs', icon: Boxes, hint: 'Which API each service calls, which tables it uses' },
  { id: 'data', label: 'Data', icon: Database, hint: 'Tables, sensitive data and who reads or writes it' },
  { id: 'journeys', label: 'Customer journeys', icon: Route, hint: 'What happens behind each customer action' },
]

const ORIGIN: Record<string, { label: string; tone: string }> = {
  code: { label: 'From code', tone: 'blue' }, config: { label: 'From config', tone: 'green' }, schema: { label: 'From schema', tone: 'amber' },
  catalog: { label: 'From catalog', tone: 'violet' }, ai: { label: 'AI-resolved · verified', tone: 'amber' }, human: { label: 'Human-confirmed', tone: 'green' },
}

export default function DependencyMap() {
  const [map, setMap] = useState<any>(null)
  const [error, setError] = useState('')
  const [view, setView] = useState<View>(() => (new URLSearchParams(window.location.search).get('view') as View) || 'system')
  const [opts, setOpts] = useState({ security: false, outside: true, ops: false })
  const [selected, setSelected] = useState<{ kind: 'node' | 'edge'; data: any } | null>(null)
  const [whatIf, setWhatIf] = useState<any>(null)
  const [journey, setJourney] = useState<any>(null)
  const [tip, setTip] = useState<{ x: number; y: number; title: string; body: string; badge?: string } | null>(null)
  const [query, setQuery] = useState('')
  const box = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const [params, setParams] = useSearchParams()
  const crKey = params.get('cr')
  const [overlay, setOverlay] = useState<any>(null)
  const [crList, setCrList] = useState<any[]>([])
  useEffect(() => { api.crs().then(cs => setCrList(cs.filter((c: any) => c.analysis))) }, [])
  useEffect(() => { if (crKey) api.cr(crKey).then(d => setOverlay(d.analysis)); else setOverlay(null) }, [crKey])
  const verdicts = useMemo(() => {
    if (!overlay || !map) return {} as Record<string, { verdict: string; how: string[] }>
    const v: Record<string, { verdict: string; how: string[] }> = { ...verdictBySystemNode(overlay, map) }
    for (const i of overlay.items) v[i.id] = { verdict: i.verdict, how: [i.how] }
    return v
  }, [overlay, map])

  useEffect(() => { api.map().then(setMap).catch(e => setError(e.message)) }, [])
  const nodes = useMemo(() => (map ? index(map) : {}), [map])
  const journeys = map?.report?.journeys ?? []

  // (re)draw the graph when view/options change
  useEffect(() => {
    if (!map || !box.current) return
    const { els, pos } = buildElements(map, view, opts)
    cyRef.current?.destroy()
    const cy = cytoscape({ container: box.current, elements: els, style: STYLE, minZoom: 0.25, maxZoom: 2.5, wheelSensitivity: 0.25,
      layout: { name: 'preset', positions: (n: any) => pos[n.id()] ?? { x: 0, y: 0 }, fit: true, padding: 40 } as any })
    cyRef.current = cy
    cy.on('mouseover', 'node, edge', evt => {
      const el = evt.target
      const p = evt.renderedPosition ?? el.renderedMidpoint?.()
      if (el.isNode()) {
        const n = el.data('raw')
        if (!(cy.$('.wi-src').length || cy.$('.jstep').length)) {
          cy.elements().addClass('faded'); el.closedNeighborhood().removeClass('faded'); el.closedNeighborhood().addClass('hl')
          if (el.isParent()) el.children().removeClass('faded')
          if (el.isChild()) el.parent().removeClass('faded')
        }
        const vv = verdictsRef.current[n.id]
        setTip({ x: p.x, y: p.y, title: n.label, badge: vv ? VERDICT[vv.verdict].label : n.type,
          body: vv && vv.verdict !== 'not_impacted' ? vv.how.slice(0, 3).join(' · ') : describeNode(n) })
      } else {
        const raw = el.data('raw')?.[0]
        setTip({ x: p.x, y: p.y, title: edgeTitle(el, nodes), badge: raw ? ORIGIN[raw.origin]?.label : '',
          body: raw?.props?.business_label ? `Why: ${raw.props.business_label}` : (raw?.details?.length ? raw.details.join(', ') : '') })
      }
    })
    cy.on('mouseout', 'node, edge', () => { cy.elements().removeClass('faded hl'); setTip(null) })
    cy.on('tap', 'node', evt => { setSelected({ kind: 'node', data: evt.target.data('raw') }); setWhatIf(null) })
    cy.on('tap', 'edge', evt => setSelected({ kind: 'edge', data: { ...evt.target.data(), title: edgeTitle(evt.target, nodes) } }))
    cy.on('dbltap', 'node.service', evt => { setView('apis'); setSelected({ kind: 'node', data: evt.target.data('raw') }) })
    cy.on('tap', evt => { if (evt.target === cy) { setSelected(null) } })
    return () => { cy.destroy(); cyRef.current = null }
  }, [map, view, opts, nodes])

  // journeys view: pre-select the first journey so the numbered steps show immediately
  useEffect(() => { if (view === 'journeys' && !journey && journeys.length) setJourney(journeys.find((j: any) => /payment/i.test(j.entry)) ?? journeys[0]) }, [view, journeys, journey])

  // change-request impact overlay
  const verdictsRef = useRef<Record<string, any>>({})
  verdictsRef.current = verdicts
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.nodes().removeClass(Object.keys(VERDICT).map(k => `v-${k}`).join(' '))
    if (!overlay) return
    cy.nodes().forEach(n => {
      if (n.data('type') === 'user') return
      n.addClass(`v-${verdicts[n.id()]?.verdict ?? 'not_impacted'}`)
    })
  }, [verdicts, overlay, view, opts, map])

  // what-if colouring
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().removeClass('wi-src wi-high wi-med wi-low faded')
    if (!whatIf) return
    cy.elements().addClass('faded')
    const mark = (id: string, cls: string) => {
      const target = cy.getElementById(id).length ? id : nodes[id]?.parent
      if (!target) return
      const el = cy.getElementById(target)
      if (el.length) { el.removeClass('faded').addClass(cls); el.parent().removeClass('faded') }
    }
    mark(whatIf.source, 'wi-src')
    for (const a of whatIf.affected) mark(a.id, a.score >= 0.6 ? 'wi-high' : a.score >= 0.4 ? 'wi-med' : 'wi-low')
  }, [whatIf, view, nodes, opts])

  // journey highlighting
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.edges().removeClass('jstep').data('stepLabel', '')
    cy.nodes().removeClass('jnode')
    if (view !== 'journeys' || !journey) { cy.elements().removeClass('faded'); return }
    cy.elements().addClass('faded')
    const labels: Record<string, string[]> = {}
    for (const s of journeyOverlay(journey)) {
      (labels[s.edge] ??= []).push(String(s.n))
      s.nodes.forEach(n => cy.getElementById(n).removeClass('faded').addClass('jnode'))
    }
    for (const [id, ns] of Object.entries(labels)) {
      const e = cy.getElementById(id)
      if (e.length) e.removeClass('faded').addClass('jstep').data('stepLabel', ns.join(' · '))
    }
  }, [journey, view, map])

  const runWhatIf = async (id: string) => { setWhatIf(await api.whatIf(id)) }
  const doSearch = () => {
    const cy = cyRef.current
    if (!cy || !query.trim()) return
    const hit = cy.nodes().filter(n => String(n.data('label')).toLowerCase().includes(query.toLowerCase()))
    if (hit.length) { cy.animate({ fit: { eles: hit, padding: 120 } } as any, { duration: 400 }); hit.select(); setSelected({ kind: 'node', data: hit[0].data('raw') }) }
  }

  if (error) return <div className="p-8"><ErrorNote error={error} /></div>
  if (!map) return <div className="p-8"><Spinner label="Building the dependency map from the code…" /></div>
  const counts = map.report.counts

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-5 py-2.5">
        <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
          {VIEWS.map(v => (
            <button key={v.id} title={v.hint} onClick={() => { setView(v.id); setWhatIf(null); if (v.id !== 'journeys') setJourney(null) }}
              className={cx('flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition', view === v.id ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-600 hover:text-slate-900')}>
              <v.icon size={15} />{v.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-slate-600"><input type="checkbox" checked={opts.outside} onChange={e => setOpts({ ...opts, outside: e.target.checked })} />Outside systems</label>
        <label className="flex items-center gap-1.5 text-xs text-slate-600"><input type="checkbox" checked={opts.security} onChange={e => setOpts({ ...opts, security: e.target.checked })} />Login-token links</label>
        {view === 'apis' && <label className="flex items-center gap-1.5 text-xs text-slate-600"><input type="checkbox" checked={opts.ops} onChange={e => setOpts({ ...opts, ops: e.target.checked })} />Health endpoints</label>}
        <select value={crKey ?? ''} onChange={e => { const v = e.target.value; if (v) setParams({ cr: v }); else setParams({}) }}
          className={cx('max-w-[260px] truncate rounded-lg border px-2 py-1.5 text-sm', crKey ? 'border-brand-500 bg-brand-50 text-brand-800' : 'border-slate-300 text-slate-600')}>
          <option value="">Show impact of a change request…</option>
          {crList.map(c => <option key={c.key} value={c.key}>{c.key}: {c.summary}</option>)}
        </select>
        <div className="ml-auto flex items-center gap-2">
          <div className="flex items-center rounded-lg border border-slate-300 bg-white px-2">
            <Search size={14} className="text-slate-400" />
            <input value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && doSearch()} placeholder="Find a service, API, table…"
              className="w-44 px-2 py-1.5 text-sm focus:outline-none" />
          </div>
          <span className="hidden text-xs text-slate-500 2xl:inline">{counts.service} services · {counts.endpoint} APIs · {counts.table} tables · {counts.function} functions · {counts.edges} links</span>
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1 bg-[radial-gradient(#e2e8f0_1px,transparent_1px)] [background-size:18px_18px]">
          <div ref={box} className={cx('absolute inset-y-0 right-0', view === 'journeys' ? 'left-[300px]' : 'left-0')} />
          {tip && (
            <div className="pointer-events-none absolute z-20 max-w-xs rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg"
              style={{ left: tip.x + 16, top: tip.y + 12 }}>
              <div className="flex items-center gap-2 font-semibold text-slate-900">{tip.title}{tip.badge && <span className="rounded bg-slate-100 px-1.5 py-0.5 font-normal text-slate-500">{tip.badge}</span>}</div>
              {tip.body && <div className="mt-1 leading-5 text-slate-600">{tip.body}</div>}
            </div>
          )}
          <Legend view={view} />
          {overlay && (
            <div className="absolute right-4 top-4 z-10 rounded-xl border border-slate-200 bg-white/95 px-3 py-2 text-xs shadow-sm">
              <div className="mb-1 font-semibold text-slate-800">{overlay.key} impact</div>
              {Object.entries(VERDICT).map(([k, v]) => <div key={k} className="flex items-center gap-1.5 text-slate-600"><span className={cx('h-2.5 w-2.5 rounded-sm', v.dot)} />{v.label}</div>)}
            </div>
          )}
          {view === 'journeys' && <JourneyList journeys={journeys} selected={journey} onSelect={setJourney} />}
        </div>
        {(selected || whatIf) && (
          <aside className="scroll-thin w-[400px] shrink-0 overflow-y-auto border-l border-slate-200 bg-white">
            {whatIf ? <WhatIfPanel data={whatIf} nodes={nodes} onClose={() => setWhatIf(null)} /> :
              selected?.kind === 'node' ? <NodePanel node={selected.data} onClose={() => setSelected(null)} onWhatIf={runWhatIf} /> :
              selected ? <EdgePanel edge={selected.data} onClose={() => setSelected(null)} /> : null}
          </aside>
        )}
      </div>
    </div>
  )
}

function describeNode(n: any) {
  if (n.props?.description) return n.props.description
  if (n.type === 'service') return `${n.props.language} service · owned by ${n.props.owner} · ${n.props.endpoints ?? ''}`.replace(/ · $/, '')
  if (n.type === 'database') return `PostgreSQL database · owned by ${n.props.owner}`
  if (n.type === 'external') return n.props.description
  if (n.type === 'table') return `Columns: ${(n.props.columns ?? []).join(', ')}`
  if (n.type === 'endpoint') return `Handled by ${n.props.handler}()`
  return ''
}

function edgeTitle(el: any, nodes: Record<string, any>) {
  const s = nodes[el.data('source')]?.label ?? el.data('source')
  const t = nodes[el.data('target')]?.label ?? el.data('target')
  const raw = el.data('raw')?.[0]
  const verb = el.data('kind') === 'data' ? el.data('mode') : raw?.verb ?? ''
  return `${s} ${verb} ${t}`
}

function Legend({ view }: { view: View }) {
  const [open, setOpen] = useState(true)
  if (!open) return <button onClick={() => setOpen(true)} className="absolute bottom-4 left-4 z-10 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs shadow-sm"><Info size={13} className="mr-1 inline" />Legend</button>
  const Sw = ({ c, dashed }: { c: string; dashed?: boolean }) => <span className="inline-block w-6 border-t-2 align-middle" style={{ borderColor: c, borderStyle: dashed ? 'dashed' : 'solid' }} />
  return (
    <div className="absolute bottom-4 left-4 z-10 w-64 rounded-xl border border-slate-200 bg-white/95 p-3 text-[11px] text-slate-600 shadow-sm">
      <div className="mb-2 flex items-center justify-between font-semibold text-slate-800">How to read this map<button onClick={() => setOpen(false)}><X size={13} /></button></div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        <span><span className="mr-1 inline-block h-3 w-4 rounded border border-brand-500 bg-brand-50 align-middle" />Service</span>
        <span><span className="mr-1 inline-block h-3 w-4 rounded-full border border-amber-500 bg-amber-50 align-middle" />Database</span>
        <span><span className="mr-1 inline-block h-3 w-4 border border-dashed border-violet-600 bg-violet-50 align-middle" />Outside system</span>
        <span><span className="mr-1 inline-block h-3 w-4 rounded border border-rose-600 bg-rose-50 align-middle" />Sensitive data</span>
        <span><Sw c="#3b6ef5" /> calls API</span>
        <span><Sw c="#0891b2" /> reads & writes</span>
        <span><Sw c="#10b981" /> reads</span>
        <span><Sw c="#f97316" /> writes</span>
        <span><Sw c="#7c3aed" dashed /> outside reads</span>
        <span><Sw c="#94a3b8" dashed /> AI-resolved</span>
      </div>
      <div className="mt-2 border-t border-slate-100 pt-2 text-slate-500">{view === 'journeys' ? 'Pick a journey to see its numbered steps.' : 'Hover to focus · click for details & proof · double-click a service to see its APIs.'}</div>
    </div>
  )
}

function JourneyList({ journeys, selected, onSelect }: { journeys: any[]; selected: any; onSelect: (j: any) => void }) {
  return (
    <div className="absolute left-4 top-4 z-10 w-72 rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Customer journeys</div>
      <div className="space-y-1">
        {journeys.map(j => (
          <button key={j.id} onClick={() => onSelect(selected?.id === j.id ? null : j)}
            className={cx('w-full rounded-lg px-3 py-2 text-left text-sm transition', selected?.id === j.id ? 'bg-slate-900 text-white' : 'hover:bg-slate-100')}>
            <div className="font-medium">{j.name}</div>
            <div className={cx('text-xs', selected?.id === j.id ? 'text-slate-300' : 'text-slate-500')}>{j.steps.length} steps · starts at {j.entry.split(':').slice(2).join(':')}</div>
          </button>
        ))}
      </div>
      {selected && (
        <div className="mt-3 border-t border-slate-100 pt-3">
          {selected.summary && <p className="mb-2 text-xs text-slate-600">{selected.summary}</p>}
          <ol className="space-y-1.5">
            {selected.steps.map((s: any, i: number) => (
              <li key={i} className="flex gap-2 text-xs text-slate-700">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-900 text-[10px] font-semibold text-white">{i + 1}</span>
                <span>{s.text ?? `${s.from.split(':').pop()} → ${s.to.split(':').pop()}: ${s.detail}`}{s.background && <em className="text-slate-400"> (background)</em>}</span>
              </li>
            ))}
          </ol>
          {selected.narrated_by === 'ai' && <div className="mt-2 flex items-center gap-1 text-[11px] text-slate-400"><Sparkles size={11} />Wording by local AI; steps computed from verified code links.</div>}
        </div>
      )}
    </div>
  )
}

function PanelHead({ title, sub, onClose, badges }: { title: string; sub?: string; onClose: () => void; badges?: any }) {
  return (
    <div className="sticky top-0 z-10 flex items-start justify-between border-b border-slate-100 bg-white px-5 py-4">
      <div><div className="text-base font-semibold text-slate-900">{title}</div>{sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}{badges && <div className="mt-2 flex flex-wrap gap-1.5">{badges}</div>}</div>
      <button onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100"><X size={16} /></button>
    </div>
  )
}

function Section({ title, icon, children }: { title: string; icon?: any; children: any }) {
  return <div className="border-b border-slate-100 px-5 py-4"><h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">{icon}{title}</h4>{children}</div>
}

function NodePanel({ node, onClose, onWhatIf }: { node: any; onClose: () => void; onWhatIf: (id: string) => void }) {
  const [d, setD] = useState<any>(null)
  const open = useEvidence()
  useEffect(() => { setD(null); api.node(node.id).then(setD) }, [node.id])
  const p = node.props ?? {}
  const group = (list: any[], type: string) => list.filter(e => e.type === type)
  return (
    <div>
      <PanelHead title={node.label} sub={node.type === 'service' ? `${p.language} service · ${p.path ?? ''}` : node.type} onClose={onClose}
        badges={<>{p.owner && <Badge>{p.owner}</Badge>}{p.capability && <Badge tone="blue">{p.capability}</Badge>}{p.criticality && <Badge tone={p.criticality === 'high' ? 'red' : 'slate'}>{p.criticality} criticality</Badge>}
          {p.classification && <Badge tone="red"><Lock size={11} />{p.classification}</Badge>}</>} />
      <div className="border-b border-slate-100 px-5 py-4">
        {p.description ? (
          <><p className="text-sm leading-6 text-slate-700">{p.description}</p>
            {p.description_by === 'ai' && <div className="mt-1.5 flex items-center gap-1 text-[11px] text-slate-400"><Sparkles size={11} />Written by local AI from the code</div>}</>
        ) : <p className="text-sm text-slate-500">{describeNode(node) || 'No description yet.'}</p>}
        {p.suggested_classification && <div className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">AI suggests this may be <b>{p.suggested_classification}</b> data: {p.suggestion_reason}. Not yet confirmed in the data register.</div>}
        <div className="mt-3 flex gap-2">
          <Button size="sm" onClick={() => open({ title: node.label, ids: node.evidence ?? [], reason: 'Where this comes from' })} icon={<Code2 size={13} />}>Show proof</Button>
          {node.type !== 'user' && <Button size="sm" variant="primary" onClick={() => onWhatIf(node.id)} icon={<Zap size={13} />}>What if this changes?</Button>}
        </div>
      </div>
      {!d ? <div className="p-5"><Spinner /></div> : (
        <>
          {d.children.filter((c: any) => c.type === 'endpoint' && !c.props.ops).length > 0 && (
            <Section title="APIs it offers" icon={<Boxes size={13} />}>
              <ul className="space-y-1.5">{d.children.filter((c: any) => c.type === 'endpoint' && !c.props.ops).map((c: any) => (
                <li key={c.id} className="text-sm"><code className="text-xs text-slate-800">{c.label}</code>{c.props.description && <div className="text-xs text-slate-500">{c.props.description}</div>}</li>))}</ul>
            </Section>
          )}
          {node.type === 'table' && <ColumnsSection tableId={node.id} />}
          <EdgeList title="Calls" items={group(d.outgoing, 'calls_api').filter((e: any) => e.other.type === 'endpoint')} render={(e: any) => <><b>{e.other.parent?.split(':')[1]}</b> <code className="text-xs">{e.other.label}</code></>} open={open} />
          <EdgeList title="Called by" items={group(d.incoming, 'calls_api').filter((e: any) => e.other.type === 'service')} render={(e: any) => <><b>{e.other.label}</b> <span className="text-xs text-slate-500">{e.details.join(', ')}</span></>} open={open} />
          <EdgeList title="Data" items={[...group(d.outgoing, 'reads'), ...group(d.outgoing, 'writes')].filter((e: any) => e.other.type === 'table')} render={(e: any) => <><span className={e.type === 'writes' ? 'text-orange-600' : 'text-emerald-600'}>{e.verb}</span> <b>{e.other.label}</b></>} open={open} />
          <EdgeList title="Used by" items={[...group(d.incoming, 'reads'), ...group(d.incoming, 'writes'), ...group(d.incoming, 'consumes')].filter((e: any) => ['service', 'external'].includes(e.other.type))} render={(e: any) => <><b>{e.other.label}</b> <span className="text-xs text-slate-500">{e.verb}{e.details.length ? `: ${e.details.slice(0, 3).join(', ')}` : ''}</span></>} open={open} />
          <EdgeList title="Settings it needs" icon={<Settings2 size={13} />} items={group(d.outgoing, 'needs_config')} render={(e: any) => <><code className="text-xs">{e.other.label}</code></>} open={open} />
          <EdgeList title="Trusts login tokens from" icon={<ShieldCheck size={13} />} items={group(d.outgoing, 'trusts_tokens_from')} render={(e: any) => <b>{e.other.label}</b>} open={open} />
          {node.type === 'service' && <Section title="Code & tests" icon={<Code2 size={13} />}><p className="text-sm text-slate-600">{p.files} files · {p.functions} functions · {p.tests} automated tests</p></Section>}
        </>
      )}
    </div>
  )
}

function ColumnsSection({ tableId }: { tableId: string }) {
  const [cols, setCols] = useState<any[]>([])
  useEffect(() => { api.node(tableId).then(d => setCols(d.children.filter((c: any) => c.type === 'column'))) }, [tableId])
  return (
    <Section title="Columns" icon={<Database size={13} />}>
      <ul className="grid grid-cols-1 gap-1">
        {cols.map(c => (
          <li key={c.id} className="flex items-center justify-between text-sm">
            <code className="text-xs text-slate-800">{c.label} <span className="text-slate-400">{c.props.sql_type}</span></code>
            {c.props.classification ? <Badge tone="red"><BookMarked size={10} />{c.props.classification}</Badge> :
              c.props.suggested_classification ? <span title={c.props.suggestion_reason}><Badge tone="amber"><Sparkles size={10} />AI suggests {c.props.suggested_classification}</Badge></span> : null}
          </li>
        ))}
      </ul>
    </Section>
  )
}

function EdgeList({ title, items, render, open, icon }: { title: string; items: any[]; render: (e: any) => any; open: any; icon?: any }) {
  if (!items.length) return null
  return (
    <Section title={`${title} (${items.length})`} icon={icon}>
      <ul className="space-y-1.5">
        {items.map((e: any) => (
          <li key={e.id} className="flex items-start justify-between gap-2 text-sm text-slate-700">
            <div>{render(e)}{e.props?.business_label && <div className="text-xs text-slate-500">{e.props.business_label}</div>}</div>
            <button onClick={() => open({ title: `${e.source.split(':').pop()} ${e.verb} ${e.target.split(':').pop()}`, ids: e.evidence, reason: e.props?.how })}
              className="shrink-0 rounded px-1.5 py-0.5 text-[11px] text-brand-700 hover:bg-brand-50" title={ORIGIN[e.origin]?.label}>proof</button>
          </li>
        ))}
      </ul>
    </Section>
  )
}

function EdgePanel({ edge, onClose }: { edge: any; onClose: () => void }) {
  const open = useEvidence()
  const raws: any[] = edge.raw ?? []
  return (
    <div>
      <PanelHead title={edge.title} onClose={onClose} badges={[...new Set(raws.map(r => r.origin))].map(o => <Badge key={o} tone={ORIGIN[o]?.tone}>{ORIGIN[o]?.label}</Badge>)} />
      {raws.map((r: any) => (
        <Section key={r.id} title={r.verb}>
          {r.props?.business_label && <p className="mb-1 text-sm text-slate-800">{r.props.business_label}</p>}
          {r.details.length > 0 && <div className="mb-1 flex flex-wrap gap-1">{r.details.map((d: string) => <code key={d} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{d}</code>)}</div>}
          {r.props?.how && <p className="text-xs text-slate-500">How we know: {r.props.how}</p>}
          <p className="mt-1 text-xs text-slate-500">Confidence {Math.round(r.confidence * 100)}%</p>
          <Button size="sm" onClick={() => open({ title: edge.title, ids: r.evidence, reason: r.props?.how })} icon={<Code2 size={13} />}>Show proof ({r.evidence.length})</Button>
        </Section>
      ))}
    </div>
  )
}

function WhatIfPanel({ data, nodes, onClose }: { data: any; nodes: Record<string, any>; onClose: () => void }) {
  const open = useEvidence()
  const groups = [['service', 'Services'], ['endpoint', 'APIs'], ['table', 'Tables'], ['external', 'Outside systems'], ['test', 'Tests to re-run'], ['user', 'Customers']]
  return (
    <div>
      <PanelHead title={`If ${nodes[data.source]?.label} changes…`} sub={`${data.affected.length} things could be affected`} onClose={onClose}
        badges={<><Badge tone="red">strong</Badge><Badge tone="amber">medium</Badge><Badge tone="slate">weak</Badge></>} />
      {groups.map(([t, label]) => {
        const items = data.affected.filter((a: any) => a.type === t)
        if (!items.length) return null
        return (
          <Section key={t} title={`${label} (${items.length})`}>
            <ul className="space-y-1.5">
              {items.slice(0, 12).map((a: any) => (
                <li key={a.id} className="flex items-start justify-between gap-2 text-sm">
                  <div>
                    <span className={cx('mr-1.5 inline-block h-2 w-2 rounded-full', a.score >= 0.6 ? 'bg-red-500' : a.score >= 0.4 ? 'bg-orange-500' : 'bg-yellow-400')} />
                    <b className="font-medium">{a.label}</b>
                    <div className="text-xs text-slate-500">{a.why.slice(-1).map((w: any) => `${w.from} ${w.relation} ${w.to}`).join('')}</div>
                  </div>
                  <button onClick={() => open({ title: a.label, ids: a.why.flatMap((w: any) => w.evidence).slice(0, 6), why: a.why })} className="shrink-0 text-[11px] text-brand-700">why?</button>
                </li>
              ))}
              {items.length > 12 && <li className="text-xs text-slate-400">+{items.length - 12} more</li>}
            </ul>
          </Section>
        )
      })}
    </div>
  )
}
