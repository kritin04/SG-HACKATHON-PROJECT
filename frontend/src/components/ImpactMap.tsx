/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef } from 'react'
import cytoscape from 'cytoscape'
import { buildElements } from '../pages/mapLayout'
import { VERDICT } from '../api'

const RANK: Record<string, number> = { must_change: 0, likely_affected: 1, retest_only: 2, not_impacted: 3 }

/** Map each analysed item onto the system-level node it belongs to (endpoint -> service, table -> database). */
export function verdictBySystemNode(analysis: any, map: any) {
  const nodes: Record<string, any> = {}
  for (const n of map.nodes) nodes[n.id] = n
  const out: Record<string, { verdict: string; how: string[] }> = {}
  for (const i of analysis.items) {
    let id = i.id
    if (nodes[id]?.type === 'endpoint') id = nodes[id].parent
    if (nodes[id]?.type === 'table') id = nodes[id].parent
    const cur = out[id]
    if (!cur || RANK[i.verdict] < RANK[cur.verdict]) out[id] = { verdict: i.verdict, how: [...(cur?.how ?? [])] }
    if (i.verdict !== 'not_impacted') out[id].how.push(`${i.label}: ${i.how}`)
  }
  for (const x of analysis.externals ?? []) if (!out[x.id]) out[x.id] = { verdict: x.verdict, how: [x.how] }
  return out
}

export const IMPACT_STYLE = (v: Record<string, any>) => Object.entries(VERDICT).flatMap(([k, s]) => [
  { selector: `node.v-${k}`, style: { 'background-color': k === 'not_impacted' ? '#f8fafc' : s.color + '22', 'border-color': s.color,
    'border-width': k === 'not_impacted' ? 1 : 3, color: k === 'not_impacted' ? '#94a3b8' : '#0f172a' } },
]).concat(Object.keys(v).length ? [] : [])

export default function ImpactMap({ map, analysis, height = 320, onSelect }: { map: any; analysis: any; height?: number; onSelect?: (id: string) => void }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!box.current || !map || !analysis) return
    const { els, pos } = buildElements(map, 'system', { security: false, outside: true, ops: false })
    const v = verdictBySystemNode(analysis, map)
    // keep only the impacted parts (plus the customer) so the small map stays readable
    const keep = new Set(els.filter((el: any) => !el.data.source && (el.data.type === 'user' || (v[el.data.id] && v[el.data.id].verdict !== 'not_impacted'))).map((el: any) => el.data.id))
    const shown = els.filter((el: any) => el.data.source ? keep.has(el.data.source) && keep.has(el.data.target) : keep.has(el.data.id))
    els.length = 0
    els.push(...shown)
    for (const el of els) {
      if (el.data.source) continue
      const verdict = v[el.data.id]?.verdict ?? 'not_impacted'
      el.classes = `${el.classes} v-${el.data.type === 'user' ? 'none' : verdict}`
    }
    const cy = cytoscape({
      container: box.current, elements: els, userZoomingEnabled: true, boxSelectionEnabled: false,
      layout: { name: 'preset', positions: (n: any) => pos[n.id()], fit: true, padding: 16 } as any,
      style: [
        { selector: 'node', style: { label: 'data(label)', 'font-size': 12, 'text-wrap': 'wrap', 'text-max-width': '150px', 'text-valign': 'center',
          'text-halign': 'center', 'background-color': '#fff', 'border-width': 1, 'border-color': '#cbd5e1', shape: 'round-rectangle', width: 160, height: 46, color: '#334155' } },
        { selector: 'node.database', style: { shape: 'barrel' } },
        { selector: 'node.external', style: { shape: 'cut-rectangle', 'border-style': 'dashed', width: 180 } },
        { selector: 'node.user', style: { shape: 'ellipse', width: 110 } },
        { selector: 'edge', style: { width: 1.2, 'line-color': '#e2e8f0', 'target-arrow-color': '#e2e8f0', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier' } },
        ...IMPACT_STYLE(v),
      ] as any,
    })
    // highlight links between impacted parts
    cy.edges().forEach(e => {
      const a = v[e.source().id()]?.verdict, b = v[e.target().id()]?.verdict
      if (a && b && a !== 'not_impacted' && b !== 'not_impacted') e.style({ 'line-color': '#475569', 'target-arrow-color': '#475569', width: 2 })
    })
    cy.on('tap', 'node', evt => onSelect?.(evt.target.id()))
    return () => cy.destroy()
  }, [map, analysis, onSelect])
  return <div ref={box} style={{ height }} className="w-full" />
}
