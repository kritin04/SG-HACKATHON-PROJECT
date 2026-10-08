/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { KanbanSquare, Network, ShieldCheck, Cpu, GitCommitHorizontal, Lock, BadgeCheck } from 'lucide-react'
import { api, CURRENT_USER } from '../api'
import { cx } from './ui'

const NAV = [
  { to: '/board', label: 'Change Requests', hint: 'Jira board + impact', icon: KanbanSquare },
  { to: '/map', label: 'Dependency Map', hint: 'How everything connects', icon: Network },
]

export function Shell({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<any>(null)
  useEffect(() => {
    const load = () => api.health().then(setHealth).catch(() => setHealth({ error: true }))
    load()
    const t = setInterval(load, 20000)
    return () => clearInterval(t)
  }, [])
  const ai = health?.ollama
  const acc = health?.accuracy
  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col bg-brand-900 text-slate-200">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-500 text-white"><ShieldCheck size={20} /></div>
          <div>
            <div className="text-sm font-semibold leading-tight text-white">Change Impact</div>
            <div className="text-xs text-brand-100/70">Copilot</div>
          </div>
        </div>
        <nav className="mt-2 flex-1 space-y-1 px-3">
          {NAV.map(n => (
            <NavLink key={n.to} to={n.to}
              className={({ isActive }) => cx('flex items-center gap-3 rounded-lg px-3 py-2.5 transition',
                isActive ? 'bg-white/10 text-white' : 'text-slate-300 hover:bg-white/5 hover:text-white')}>
              <n.icon size={18} />
              <div>
                <div className="text-sm font-medium">{n.label}</div>
                <div className="text-[11px] text-slate-400">{n.hint}</div>
              </div>
            </NavLink>
          ))}
        </nav>
        <div className="space-y-2 border-t border-white/10 px-5 py-4 text-xs text-slate-400">
          <div className="flex items-center gap-2"><Lock size={13} />AI runs locally. No data leaves this machine.</div>
          {health?.project && <div>Analysing <span className="text-slate-200">{health.project.name}</span> (open-source)</div>}
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
          <div className="flex items-center gap-5 text-xs text-slate-600">
            <span className="flex items-center gap-1.5">
              <span className={cx('h-2 w-2 rounded-full', ai?.up ? 'bg-emerald-500' : 'bg-rose-500')} />
              <Cpu size={14} />Local AI {ai?.up ? 'ready' : 'offline (rule-based mode)'}
            </span>
            {health?.project && (
              <span className="flex items-center gap-1.5"><GitCommitHorizontal size={14} />{health.project.name} @ <code>{health.project.short}</code> ({health.project.pinned_label})</span>
            )}
            {acc?.expected && (
              <span className="flex items-center gap-1.5" title="Map links checked against a hand-verified answer key">
                <BadgeCheck size={14} className="text-emerald-600" />Map accuracy {acc.found}/{acc.expected} · {Math.round(acc.precision * 100)}% precise
              </span>
            )}
          </div>
          <div className="flex items-center gap-2.5">
            <div className="text-right">
              <div className="text-sm font-medium text-slate-800">{CURRENT_USER.name}</div>
              <div className="text-[11px] text-slate-500">{CURRENT_USER.role}</div>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">{CURRENT_USER.name.split(" ").map(w => w[0]).join("")}</div>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  )
}
