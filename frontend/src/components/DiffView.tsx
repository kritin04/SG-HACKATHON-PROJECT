import { cx } from './ui'

export function DiffView({ lines }: { lines: { type: 'same' | 'add' | 'del'; text: string }[] }) {
  return (
    <div className="scroll-thin overflow-auto rounded-lg border border-slate-200 bg-white font-mono text-[13px] leading-6">
      {lines.map((l, i) => (
        <div key={i} className={cx('flex', l.type === 'add' && 'bg-emerald-50', l.type === 'del' && 'bg-rose-50')}>
          <span className={cx('w-8 shrink-0 select-none text-center', l.type === 'add' ? 'text-emerald-600' : l.type === 'del' ? 'text-rose-600' : 'text-slate-300')}>
            {l.type === 'add' ? '+' : l.type === 'del' ? '−' : ' '}
          </span>
          <span className={cx('whitespace-pre-wrap break-words pr-4', l.type === 'add' && 'text-emerald-900', l.type === 'del' && 'text-rose-900 line-through decoration-rose-300')}>
            {l.text || ' '}
          </span>
        </div>
      ))}
    </div>
  )
}
