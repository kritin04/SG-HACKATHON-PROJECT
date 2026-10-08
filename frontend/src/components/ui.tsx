/* eslint-disable @typescript-eslint/no-explicit-any */
import type { ReactNode } from 'react'
import { Loader2, Cpu, BookMarked, UserCheck, ShieldCheck, ShieldAlert, AlertTriangle } from 'lucide-react'

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(' ')
}

export function Card({ children, className, title, action, subtitle }: {
  children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode; subtitle?: ReactNode
}) {
  return (
    <section className={cx('rounded-xl border border-slate-200 bg-white shadow-sm', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-3.5">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

export function Button({ children, onClick, variant = 'secondary', disabled, size = 'md', icon }: {
  children: ReactNode; onClick?: () => void; variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'
  disabled?: boolean; size?: 'sm' | 'md'; icon?: ReactNode
}) {
  const styles = {
    primary: 'bg-brand-600 text-white hover:bg-brand-700 shadow-sm',
    secondary: 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shadow-sm',
    ghost: 'text-slate-600 hover:bg-slate-100',
    danger: 'bg-white text-rose-700 border border-rose-200 hover:bg-rose-50',
    success: 'bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm',
  }[variant]
  return (
    <button onClick={onClick} disabled={disabled}
      className={cx('inline-flex items-center gap-1.5 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-2 text-sm', styles)}>
      {icon}{children}
    </button>
  )
}

export function Badge({ children, tone = 'slate', className }: { children: ReactNode; tone?: string; className?: string }) {
  const tones: Record<string, string> = {
    slate: 'bg-slate-100 text-slate-700 ring-slate-200',
    blue: 'bg-brand-50 text-brand-700 ring-brand-100',
    green: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    amber: 'bg-amber-50 text-amber-800 ring-amber-200',
    red: 'bg-rose-50 text-rose-700 ring-rose-200',
    violet: 'bg-violet-50 text-violet-700 ring-violet-200',
  }
  return <span className={cx('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset', tones[tone], className)}>{children}</span>
}

export function RiskBadge({ level, large }: { level: string; large?: boolean }) {
  const tone = level === 'High' ? 'red' : level === 'Medium' ? 'amber' : 'green'
  return <Badge tone={tone} className={large ? 'px-3 py-1 text-sm' : ''}>{level} risk</Badge>
}

export function ConfidencePill({ level, score }: { level: string; score?: number }) {
  const tone = level === 'High' ? 'bg-brand-600' : level === 'Medium' ? 'bg-brand-400' : 'bg-slate-300'
  const width = Math.round((score ?? 0) * 100)
  return (
    <div className="flex w-28 items-center gap-2" title={`Impact score ${score}`}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className={cx('h-full rounded-full', tone)} style={{ width: `${Math.max(width, 6)}%` }} />
      </div>
      <span className="w-12 text-xs text-slate-500">{level}</span>
    </div>
  )
}

export function TierBadge({ tier }: { tier: string }) {
  if (tier === 'curated') return <Badge tone="violet"><BookMarked size={12} />From catalog</Badge>
  if (tier === 'confirmed') return <Badge tone="green"><UserCheck size={12} />Human-confirmed</Badge>
  return <Badge tone="blue"><Cpu size={12} />Auto-detected</Badge>
}

export function VerifiedBadge({ verified, issues }: { verified: boolean; issues?: string[] }) {
  return verified
    ? <Badge tone="green"><ShieldCheck size={12} />Verified against evidence</Badge>
    : <span title={(issues || []).join('\n')}><Badge tone="amber"><ShieldAlert size={12} />Unverified</Badge></span>
}

export function Spinner({ label }: { label?: string }) {
  return <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="animate-spin" size={16} />{label}</div>
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">{children}</div>
}

export function ErrorNote({ error }: { error: string }) {
  return <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"><AlertTriangle size={16} />{error}</div>
}

export function Stat({ label, value, tone, icon, hint }: { label: string; value: ReactNode; tone?: string; icon?: ReactNode; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm" title={hint}>
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">{icon}{label}</div>
      <div className={cx('mt-1 text-2xl font-semibold tracking-tight', tone ?? 'text-slate-900')}>{value}</div>
    </div>
  )
}

export function Tabs({ tabs, active, onChange }: { tabs: { id: string; label: string; count?: number }[]; active: string; onChange: (id: string) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-200">
      {tabs.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={cx('-mb-px whitespace-nowrap border-b-2 px-3.5 py-2.5 text-sm font-medium transition',
            active === t.id ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500 hover:text-slate-800')}>
          {t.label}
          {t.count !== undefined && <span className={cx('ml-1.5 rounded-full px-1.5 py-0.5 text-xs', active === t.id ? 'bg-brand-50 text-brand-700' : 'bg-slate-100 text-slate-500')}>{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function AIStatus({ ai }: { ai: any }) {
  if (!ai) return null
  if (ai.status === 'cached' || ai.status === 'generated')
    return <span className="text-xs text-slate-500">Local model {ai.model}{ai.seconds ? ` · ${Math.round(ai.seconds)}s` : ''}{ai.status === 'cached' ? ' · cached' : ''}</span>
  if (ai.status === 'unavailable') return <span className="text-xs text-amber-700">Local AI unavailable. Showing rule-based results.</span>
  return <span className="text-xs text-slate-500">Not generated yet</span>
}
