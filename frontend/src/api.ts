/* eslint-disable @typescript-eslint/no-explicit-any */
export type Json = any

async function req<T = Json>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail ?? detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  return r.json()
}

export const CURRENT_USER = { login: 'kritin', name: 'Kritin Goyal', role: 'Lead Engineer' }

export const api = {
  health: () => req('/api/health'),
  map: () => req('/api/map'),
  node: (id: string) => req(`/api/map/node/${encodeURIComponent(id)}`),
  whatIf: (id: string) => req(`/api/map/whatif/${encodeURIComponent(id)}`),
  evidence: (ids: string[]) => req(`/api/evidence?ids=${encodeURIComponent(ids.join(','))}`),
  crs: () => req('/api/crs'),
  cr: (key: string) => req(`/api/crs/${key}`),
  analyze: (key: string, force = false) => req(`/api/crs/${key}/analyze?force=${force}`, { method: 'POST' }),
  scope: (key: string, body: { node_id: string; action: 'add' | 'remove' | 'override'; verdict?: string; note?: string }) =>
    req(`/api/crs/${key}/scope`, { method: 'POST', body: JSON.stringify({ ...body, user: CURRENT_USER.name }) }),
  searchNodes: (q: string) => req(`/api/nodes/search?q=${encodeURIComponent(q)}`),
  jiraStatus: () => req('/api/jira/status'),
  jiraSync: () => req('/api/jira/sync', { method: 'POST' }),
  publish: (key: string) => req(`/api/crs/${key}/publish`, { method: 'POST' }),
  createCr: (body: { summary: string; description: string; acceptance_criteria: string[]; priority: string }) =>
    req('/api/crs', { method: 'POST', body: JSON.stringify(body) }),
}

export const VERDICT: Record<string, { label: string; tone: string; color: string; dot: string }> = {
  must_change: { label: 'Must change', tone: 'red', color: '#ef4444', dot: 'bg-red-500' },
  likely_affected: { label: 'Likely affected', tone: 'amber', color: '#f97316', dot: 'bg-orange-500' },
  retest_only: { label: 'Re-test only', tone: 'blue', color: '#eab308', dot: 'bg-yellow-400' },
  not_impacted: { label: 'Not impacted', tone: 'slate', color: '#cbd5e1', dot: 'bg-slate-300' },
}
