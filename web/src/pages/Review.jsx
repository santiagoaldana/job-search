import { useEffect, useState } from 'react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Spinner from '../components/Spinner'

function DiffView({ aiBody, sentBody }) {
  if (!aiBody || !sentBody) return null
  // Word-level diff: highlight words present in AI but not sent (removed) and vice versa
  const aiWords = aiBody.split(/\s+/)
  const sentWords = sentBody.split(/\s+/)
  const aiSet = new Set(aiWords)
  const sentSet = new Set(sentWords)

  return (
    <div className="grid grid-cols-2 gap-3 mt-2">
      <div>
        <div className="text-xs font-semibold text-muted mb-1">AI draft</div>
        <pre className="text-xs bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg p-3 whitespace-pre-wrap break-words leading-relaxed text-body">
          {aiWords.map((w, i) => (
            <span key={i} className={!sentSet.has(w) ? 'bg-red-200 dark:bg-red-800/60 rounded px-0.5' : ''}>
              {w}{' '}
            </span>
          ))}
        </pre>
      </div>
      <div>
        <div className="text-xs font-semibold text-muted mb-1">Sent version</div>
        <pre className="text-xs bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-lg p-3 whitespace-pre-wrap break-words leading-relaxed text-body">
          {sentWords.map((w, i) => (
            <span key={i} className={!aiSet.has(w) ? 'bg-green-200 dark:bg-green-800/60 rounded px-0.5' : ''}>
              {w}{' '}
            </span>
          ))}
        </pre>
      </div>
    </div>
  )
}

function ExampleRow({ ex }) {
  const [expanded, setExpanded] = useState(false)
  const statusColor = {
    positive: 'text-green-600 dark:text-green-400',
    ghosted: 'text-red-500',
    pending: 'text-amber-500',
    negative: 'text-slate-500',
  }[ex.response_status] || 'text-muted'

  return (
    <div className="border border-theme rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800/40"
      >
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-muted">#{ex.id}</span>
          <span className="text-xs text-body truncate max-w-48">{ex.sent_subject || ex.ai_draft_subject || '(no subject)'}</span>
          <span className="text-xs font-semibold text-orange-500">ed: {ex.edit_distance}</span>
          <span className={`text-xs font-medium ${statusColor}`}>{ex.response_status}</span>
        </div>
        <span className="text-xs text-muted">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <div className="px-3 pb-3">
          {ex.ai_draft_subject !== ex.sent_subject && (
            <div className="flex gap-2 mb-2 text-xs">
              <span className="text-muted line-through">{ex.ai_draft_subject}</span>
              <span className="text-body">→ {ex.sent_subject}</span>
            </div>
          )}
          <DiffView aiBody={ex.ai_draft_body} sentBody={ex.sent_body} />
          {ex.prompt_version && (
            <div className="mt-2 text-xs text-muted">Prompt version: {ex.prompt_version}</div>
          )}
        </div>
      )}
    </div>
  )
}

function CodeRow({ row }) {
  const [open, setOpen] = useState(false)
  const fmtPct = v => v != null ? `${Math.round(v * 100)}%` : '—'

  return (
    <div className="bg-card border border-theme rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800/30"
      >
        <div className="flex items-center gap-4">
          <span className="text-sm font-semibold text-body font-mono">{row.message_code}</span>
          <span className="text-xs text-muted">{row.drafts} draft{row.drafts !== 1 ? 's' : ''}</span>
          <span className="text-xs text-muted">avg edit: {row.avg_edit_distance ?? '—'}</span>
          <span className="text-xs text-muted">reply: {fmtPct(row.reply_rate)}</span>
        </div>
        <span className="text-xs text-muted">{open ? '▲' : '▼'}</span>
      </button>
      {open && row.examples.length > 0 && (
        <div className="px-4 pb-4 flex flex-col gap-2">
          <div className="text-xs text-muted mb-1">Top {row.examples.length} highest-edit examples</div>
          {row.examples.map(ex => <ExampleRow key={ex.id} ex={ex} />)}
        </div>
      )}
      {open && row.examples.length === 0 && (
        <div className="px-4 pb-4 text-xs text-muted">No diff data yet for this message code.</div>
      )}
    </div>
  )
}

export default function ReviewPage() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getReviewSummary()
      .then(setRows)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="min-h-screen bg-background">
      <PageHeader title="Prompt Review" />
      <div className="max-w-3xl mx-auto px-4 py-6 flex flex-col gap-3">
        {loading && (
          <div className="flex justify-center py-12"><Spinner size={6} /></div>
        )}
        {error && (
          <div className="text-sm text-red-500 bg-red-50 dark:bg-red-950/20 rounded-xl px-4 py-3">{error}</div>
        )}
        {!loading && !error && rows.length === 0 && (
          <div className="text-sm text-muted text-center py-12">No outreach data in the last 30 days.</div>
        )}
        {rows.map(row => <CodeRow key={row.message_code} row={row} />)}
      </div>
    </div>
  )
}
