/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { Radar, GitPullRequestArrow, FileHeart, ShieldCheck, Cpu, GitCommitHorizontal, Lock } from 'lucide-react'
import { api, CURRENT_USER } from '../api'
import { cx } from './ui'

const NAV = [
  { to: '/impact', label: 'Impact Analyzer', hint: 'Before coding', icon: Radar },
  { to: '/release', label: 'Release Readiness', hint: 'Before merging', icon: GitPullRequestArrow },
  { to: '/docs', label: 'Self-Healing Docs', hint: 'After shipping', icon: FileHeart },
]

export function Shell({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<any>(null)
  useEffect(() => {
    const load = () => api.health().then(setHealth).catch(() => setHealth({ error: true }))
    load()
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [])
  const ai = health?.ollama
  return (
    <div className="flex h-full">
      <aside className="flex w-64 shrink-0 flex-col bg-brand-900 text-slate-200">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-500 text-white"><ShieldCheck size={20} /></div>
          <div>
            <div className="text-sm font-semibold leading-tight text-white">Change Assurance</div>
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
          <div className="flex items-center gap-2"><Lock size={13} />Runs 100% locally. No data leaves this machine.</div>
          <div>Synthetic demo data · NovaBank</div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
          <div className="flex items-center gap-4 text-xs text-slate-600">
            <span className="flex items-center gap-1.5">
              <span className={cx('h-2 w-2 rounded-full', ai?.up ? (ai.live_model_ready ? 'bg-emerald-500' : 'bg-amber-500') : 'bg-rose-500')} />
              <Cpu size={14} />Local AI: {ai?.up ? (ai.live_model_ready ? `${ai.live_model} ready` : 'model loading') : 'offline (rule-based mode)'}
            </span>
            {health?.repo && (
              <span className="flex items-center gap-1.5"><GitCommitHorizontal size={14} />main @ <code>{health.repo.main.short}</code> · {health.graph.nodes} nodes / {health.graph.edges} dependencies indexed</span>
            )}
          </div>
          <div className="flex items-center gap-2.5">
            <div className="text-right">
              <div className="text-sm font-medium text-slate-800">{CURRENT_USER.name}</div>
              <div className="text-[11px] text-slate-500">{CURRENT_USER.role}</div>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">PN</div>
          </div>
        </header>
        <main className="scroll-thin flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}

export function PageHeader({ eyebrow, title, subtitle, right }: { eyebrow: string; title: string; subtitle: string; right?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-6 pb-5">
      <div>
        <div className="text-xs font-semibold uppercase tracking-wider text-brand-600">{eyebrow}</div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">{subtitle}</p>
      </div>
      {right}
    </div>
  )
}
