export default function FitBar({ score, showLabel = true }) {
  const color = score >= 80 ? 'bg-green-500' : score >= 65 ? 'bg-blue-500' : score >= 50 ? 'bg-yellow-500' : 'bg-slate-600'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      {showLabel && <span className="text-xs text-slate-400 w-8 text-right">{score}%</span>}
    </div>
  )
}
