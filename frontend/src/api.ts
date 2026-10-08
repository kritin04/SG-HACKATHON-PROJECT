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

export const CURRENT_USER = { login: 'priya.nair', name: 'Priya Nair', role: 'Payments Lead' }

export const api = {
  health: () => req('/api/health'),
  crs: () => req('/api/crs'),
  impact: (key: string) => req(`/api/crs/${key}/impact`),
  impactAI: (key: string, force: boolean) => req(`/api/crs/${key}/ai?force=${force}`, { method: 'POST' }),
  confirmBaseline: (key: string, included: string[], excluded: string[]) =>
    req(`/api/crs/${key}/baseline`, { method: 'POST', body: JSON.stringify({ included, excluded, added: [], user: CURRENT_USER.login }) }),
  prs: () => req('/api/prs'),
  reconcile: (n: number) => req(`/api/prs/${n}/reconcile`),
  reviewAI: (n: number, force: boolean) => req(`/api/prs/${n}/ai?force=${force}`, { method: 'POST' }),
  findings: () => req('/api/docs/findings'),
  docStats: () => req('/api/docs/stats'),
  docAI: (id: string, force: boolean) => req(`/api/docs/findings/${id}/ai?force=${force}`, { method: 'POST' }),
  decide: (id: string, action: 'approve' | 'reject', text?: string, reason?: string) =>
    req(`/api/docs/findings/${id}/decision`, { method: 'POST', body: JSON.stringify({ action, text, reason, user: CURRENT_USER.login }) }),
  evidence: (ids: string[]) => req(`/api/evidence?ids=${encodeURIComponent(ids.join(','))}`),
  audit: () => req('/api/audit'),
}
