/* eslint-disable @typescript-eslint/no-explicit-any */
// Turns the API's dependency map into Cytoscape elements + fixed positions for each view.
// Layout is deterministic and reads left -> right like a story: Customer -> website -> services -> databases -> outside systems.

export type View = 'system' | 'apis' | 'data' | 'journeys'
export type Opts = { security: boolean; outside: boolean; ops: boolean }

const COL = 290

export function index(map: any) {
  const nodes: Record<string, any> = {}
  for (const n of map.nodes) nodes[n.id] = n
  return nodes
}

function shortList(items: string[], max = 2) {
  if (items.length <= max) return items.join(', ')
  return `${items.slice(0, max).join(', ')} +${items.length - max}`
}

/** Column (x) and order (y) for level-1 nodes. */
function systemColumns(map: any, nodes: Record<string, any>) {
  const services = map.nodes.filter((n: any) => n.type === 'service')
  const entry = map.edges.filter((e: any) => e.type === 'uses').map((e: any) => e.target)
  const depth: Record<string, number> = {}
  for (const s of services) depth[s.id] = entry.includes(s.id) ? 0 : 1
  // longest call chain from the entry service (bounded)
  for (let i = 0; i < 4; i++) {
    for (const e of map.edges) {
      if (e.type === 'calls_api' && e.source.startsWith('svc:') && e.target.startsWith('svc:')) {
        depth[e.target] = Math.max(depth[e.target] ?? 1, (depth[e.source] ?? 0) + 1)
      }
    }
  }
  const dbOf = (sid: string) => {
    const e = map.edges.find((x: any) => x.source === sid && (x.type === 'reads' || x.type === 'writes') && x.target.startsWith('db:'))
    return e ? e.target : 'zz'
  }
  const maxDepth = Math.max(...Object.values(depth))
  const cols: Record<number, string[]> = {}
  for (const s of services) (cols[1 + depth[s.id]] ??= []).push(s.id)
  for (const c of Object.values(cols)) c.sort((a, b) => (dbOf(a) + a).localeCompare(dbOf(b) + b))
  const dbCol = 2 + maxDepth
  const dbs = map.nodes.filter((n: any) => n.type === 'database').map((n: any) => n.id).sort()
  cols[dbCol] = dbs
  const exts = map.nodes.filter((n: any) => n.type === 'external')
    .sort((a: any, b: any) => {
      const da = map.edges.find((e: any) => e.source === a.id && e.target.startsWith('db:'))?.target ?? 'zz'
      const db = map.edges.find((e: any) => e.source === b.id && e.target.startsWith('db:'))?.target ?? 'zz'
      return (da + a.label).localeCompare(db + b.label)
    }).map((n: any) => n.id)
  cols[dbCol + 1] = exts
  cols[0] = ['user:customer']
  return { cols, nodes }
}

function place(cols: Record<number, string[]>, heights: Record<string, number> = {}, gap = 34) {
  const pos: Record<string, { x: number; y: number }> = {}
  for (const [c, ids] of Object.entries(cols)) {
    const hs = ids.map(id => heights[id] ?? 70)
    const total = hs.reduce((a, b) => a + b, 0) + gap * (ids.length - 1)
    let y = -total / 2
    ids.forEach((id, i) => {
      pos[id] = { x: Number(c) * COL, y: y + hs[i] / 2 }
      y += hs[i] + gap
    })
  }
  return pos
}

function dataEdges(map: any, level: 'db' | 'table') {
  // merge reads + writes between the same pair into one visual edge
  const pairs: Record<string, any> = {}
  for (const e of map.edges) {
    if ((e.type === 'reads' || e.type === 'writes') && e.source.startsWith('svc:') && e.target.startsWith(level === 'db' ? 'db:' : 'table:')) {
      const k = `data:${e.source}|${e.target}`
      const p = (pairs[k] ??= { id: k, source: e.source, target: e.target, modes: new Set<string>(), evidence: [], details: [], raw: [] })
      p.modes.add(e.type)
      p.evidence.push(...e.evidence)
      p.details.push(...e.details)
      p.raw.push(e)
    }
  }
  return Object.values(pairs).map((p: any) => {
    const mode = p.modes.size === 2 ? 'reads & writes' : [...p.modes][0]
    return { data: { id: p.id, source: p.source, target: p.target, label: mode, kind: 'data', mode, raw: p.raw,
      evidence: [...new Set(p.evidence)] }, classes: `data ${mode === 'reads' ? 'reads' : mode === 'writes' ? 'writes' : 'readwrite'}` }
  })
}

function edgeEl(e: any, label?: string) {
  const biz = e.props?.business_label
  return { data: { id: e.id, source: e.source, target: e.target, label: label ?? biz ?? shortList(e.details), raw: [e], kind: e.type,
    evidence: e.evidence }, classes: `${e.type} origin-${e.origin}` }
}

function nodeEl(n: any, label?: string, parent?: string, extra = '') {
  const sensitive = n.type === 'table' && n.sensitive
  return { data: { id: n.id, label: label ?? n.label, type: n.type, raw: n, parent }, classes: `${n.type} ${sensitive ? 'sensitive' : ''} ${extra}` }
}

export function buildElements(map: any, view: View, opts: Opts) {
  const nodes = index(map)
  const { cols } = systemColumns(map, nodes)
  if (!opts.outside) delete cols[Math.max(...Object.keys(cols).map(Number))]
  const els: any[] = []
  let pos: Record<string, { x: number; y: number }> = {}
  const tablesOf = (db: string) => map.nodes.filter((n: any) => n.type === 'table' && n.parent === db)
  const colsOf = (t: string) => map.nodes.filter((n: any) => n.type === 'column' && n.parent === t)
  for (const t of map.nodes.filter((n: any) => n.type === 'table')) {
    const cs = colsOf(t.id)
    t.personal = cs.filter((c: any) => /Personal|Secret/.test(c.props.classification ?? '')).length
    t.suggested = cs.filter((c: any) => c.props.suggested_classification && !c.props.classification).length
    t.sensitive = t.personal > 0
    t.ncols = cs.length
  }
  const visible = new Set(Object.values(cols).flat())

  if (view === 'system' || view === 'journeys') {
    pos = place(cols, {}, 40)
    for (const id of visible) {
      const n = nodes[id]
      const sub = n.type === 'service' ? n.props.capability : n.type === 'database' ? `${tablesOf(id).length} table(s)` :
        n.type === 'external' ? 'outside system' : 'web browser'
      els.push(nodeEl(n, `${n.label}\n${sub ?? ''}`))
    }
    for (const e of map.edges) {
      if (!visible.has(e.source) || !visible.has(e.target)) continue
      if (e.type === 'uses' || (e.type === 'calls_api' && e.source.startsWith('svc:') && e.target.startsWith('svc:'))) els.push(edgeEl(e))
      if (e.type === 'trusts_tokens_from' && opts.security) els.push(edgeEl(e, 'trusts login'))
      if (e.type === 'consumes' && e.target.startsWith('db:')) els.push(edgeEl(e, `reads ${shortList(e.details)}`))
    }
    els.push(...dataEdges(map, 'db'))
  }

  if (view === 'apis') {
    const heights: Record<string, number> = {}
    const kids: Record<string, any[]> = {}
    for (const id of visible) {
      const n = nodes[id]
      if (n.type === 'service') kids[id] = map.nodes.filter((x: any) => x.type === 'endpoint' && x.parent === id && (opts.ops || !x.props.ops))
      if (n.type === 'database') kids[id] = tablesOf(id)
      heights[id] = kids[id] ? Math.max(70, kids[id].length * 34 + 46) : 60
    }
    pos = place(cols, heights, 46)
    for (const id of visible) {
      const n = nodes[id]
      els.push(nodeEl(n, n.type === 'service' ? `${n.label}  ·  ${n.props.language}` : n.label, undefined, kids[id]?.length ? 'group' : ''))
      const list = kids[id] ?? []
      list.forEach((k: any, i: number) => {
        els.push(nodeEl(k, k.type === 'table' ? `${k.label} (${k.ncols} cols)` : k.label, id))
        pos[k.id] = { x: pos[id].x, y: pos[id].y - ((list.length - 1) * 34) / 2 + i * 34 + 8 }
      })
    }
    const shown = new Set(els.map(e => e.data.id))
    for (const e of map.edges) {
      if (!shown.has(e.source) || !shown.has(e.target)) continue
      if (e.type === 'calls_api' && e.source.startsWith('svc:') && e.target.startsWith('ep:')) els.push(edgeEl(e, ''))
      if (e.type === 'uses') els.push(edgeEl(e))
      if (e.type === 'consumes' && e.target.startsWith('table:')) els.push(edgeEl(e, 'reads'))
      if (e.type === 'trusts_tokens_from' && opts.security) els.push(edgeEl(e, 'trusts login'))
    }
    els.push(...dataEdges(map, 'table').map(d => ({ ...d, data: { ...d.data, label: '' } })))
  }

  if (view === 'data') {
    const svcs = map.nodes.filter((n: any) => n.type === 'service' && map.edges.some((e: any) => e.source === n.id && e.target.startsWith('table:')))
    const dbs = map.nodes.filter((n: any) => n.type === 'database')
    const exts = opts.outside ? map.nodes.filter((n: any) => n.type === 'external') : []
    const heights: Record<string, number> = {}
    for (const d of dbs) heights[d.id] = tablesOf(d.id).length * 64 + 50
    pos = place({ 0: svcs.map((s: any) => s.id).sort((a: string, b: string) => {
      const ta = map.edges.find((e: any) => e.source === a && e.target.startsWith('table:'))?.target ?? ''
      const tb = map.edges.find((e: any) => e.source === b && e.target.startsWith('table:'))?.target ?? ''
      return (ta + a).localeCompare(tb + b)
    }), 1: dbs.map((d: any) => d.id), 2: exts.map((x: any) => x.id) }, heights, 60)
    for (const s of svcs) els.push(nodeEl(s, `${s.label}\n${s.props.capability}`))
    for (const x of exts) els.push(nodeEl(x, `${x.label}\noutside system`))
    for (const d of dbs) {
      els.push(nodeEl(d, d.label, undefined, 'group'))
      tablesOf(d.id).forEach((t: any, i: number, arr: any[]) => {
        const flag = t.personal ? `\n🔒 ${t.personal} personal / secret` : t.suggested ? `\n⚠ ${t.suggested} suggested sensitive` : ''
        els.push(nodeEl(t, `${t.label}  (${t.ncols} columns)${flag}`, d.id, 'bigtable'))
        pos[t.id] = { x: pos[d.id].x, y: pos[d.id].y - ((arr.length - 1) * 64) / 2 + i * 64 + 10 }
      })
    }
    els.push(...dataEdges(map, 'table'))
    for (const e of map.edges) if (e.type === 'consumes' && e.target.startsWith('table:') && opts.outside) els.push(edgeEl(e, 'reads'))
  }
  return { els, pos }
}

export function journeyOverlay(journey: any) {
  // map each journey step to the element ids used in the system view
  const steps: { edge: string; nodes: string[]; n: number }[] = []
  journey.steps.forEach((s: any, i: number) => {
    let edge = s.edge
    const target = s.to.startsWith('table:') ? `db:${s.to.split(':')[1].split('.')[0]}` : s.to
    if (s.kind === 'reads' || s.kind === 'writes') edge = `data:${s.from}|${target}`
    else if (s.kind === 'api') edge = `${s.from}|calls_api|${s.to}`
    steps.push({ edge, nodes: [s.from, target], n: i + 1 })
  })
  return steps
}
