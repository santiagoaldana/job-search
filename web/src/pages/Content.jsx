import { useEffect, useState } from 'react'
import { RefreshCw, Check, X, ExternalLink, Pencil, PenLine } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Badge from '../components/Badge'
import Spinner from '../components/Spinner'

function ComposeModal({ onClose, onSaved }) {
  const [context, setContext] = useState('')
  const [composing, setComposing] = useState(false)

  async function handleCompose() {
    if (!context.trim()) return
    setComposing(true)
    try {
      await api.composePost(context.trim())
      onSaved()
    } catch (e) {
      alert(e.message)
    } finally {
      setComposing(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-end justify-center" onClick={onClose}>
      <div
        className="bg-card w-full max-w-lg rounded-t-2xl p-6 space-y-4 overflow-y-auto max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div className="font-semibold text-body">New Post from Scratch</div>
          <button onClick={onClose}><X size={18} className="text-muted" /></button>
        </div>

        <div>
          <label className="text-xs text-muted mb-1 block">What do you want to write about?</label>
          <textarea
            autoFocus
            rows={5}
            value={context}
            onChange={e => setContext(e.target.value)}
            className="w-full bg-bg border border-theme rounded-lg px-3 py-2 text-sm text-body resize-none focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
        </div>

        <button
          onClick={handleCompose}
          disabled={composing || !context.trim()}
          className="w-full bg-blue-500 text-white rounded-xl py-3 text-sm font-medium disabled:opacity-50"
        >
          {composing ? 'Generating…' : 'Generate Post'}
        </button>
      </div>
    </div>
  )
}

export default function Content() {
  const [drafts, setDrafts] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [showCompose, setShowCompose] = useState(false)

  const load = async () => {
    setLoading(true)
    try { setDrafts(await api.getDrafts()) }
    catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleGenerate = async () => {
    setGenerating(true)
    try { await api.generateDrafts(7, 3); await load() }
    catch (e) { alert(e.message) }
    finally { setGenerating(false) }
  }

  const handleApprove = async (id) => {
    try {
      await api.approveDraft(id)
      setDrafts(ds => ds.map(d => d.id === id ? { ...d, status: 'approved' } : d))
    } catch (e) { alert(e.message) }
  }

  const handleDiscard = async (id) => {
    try {
      await api.discardDraft(id)
      setDrafts(ds => ds.filter(d => d.id !== id))
    } catch (e) { alert(e.message) }
  }

  const handleRegenerate = async (id, instructions) => {
    try {
      const updated = await api.regenerateDraft(id, instructions)
      setDrafts(ds => ds.map(d => d.id === id ? updated : d))
    } catch (e) { alert(e.message) }
  }

  const pending = drafts.filter(d => d.status === 'pending')
  const approved = drafts.filter(d => d.status === 'approved')

  return (
    <div className="flex flex-col">
      <PageHeader
        title="LinkedIn Queue"
        subtitle={`${pending.length} pending · ${approved.length} approved`}
        action={
          <div className="flex items-center gap-3">
            <button onClick={() => setShowCompose(true)}
              className="flex items-center gap-1.5 text-sm text-blue-500">
              <PenLine size={14} />
              New Post
            </button>
            <button onClick={handleGenerate} disabled={generating}
              className="flex items-center gap-1.5 text-sm text-muted disabled:opacity-50">
              <RefreshCw size={14} className={generating ? 'animate-spin' : ''} />
              Generate
            </button>
          </div>
        }
      />

      {loading ? (
        <div className="flex justify-center py-16"><Spinner size={8} /></div>
      ) : (
        <div className="px-4 space-y-3 pb-4">
          {drafts.length === 0 && (
            <div className="py-12 text-center">
              <div className="text-muted text-sm mb-4">No drafts yet</div>
              <button onClick={handleGenerate} disabled={generating}
                className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-2.5 rounded-xl text-sm font-medium disabled:opacity-50">
                {generating ? 'Generating…' : 'Generate from latest FinTech news'}
              </button>
            </div>
          )}

          {pending.length > 0 && (
            <div className="text-xs text-muted font-medium uppercase tracking-wide">Pending Review</div>
          )}
          {pending.map(d => <DraftCard key={d.id} draft={d} onApprove={handleApprove} onDiscard={handleDiscard} onRegenerate={handleRegenerate} />)}

          {approved.length > 0 && (
            <div className="text-xs text-muted font-medium uppercase tracking-wide pt-2">Approved</div>
          )}
          {approved.map(d => <DraftCard key={d.id} draft={d} onApprove={handleApprove} onDiscard={handleDiscard} onRegenerate={handleRegenerate} />)}
        </div>
      )}

      {showCompose && (
        <ComposeModal
          onClose={() => setShowCompose(false)}
          onSaved={() => { setShowCompose(false); load() }}
        />
      )}
    </div>
  )
}

function DraftCard({ draft, onApprove, onDiscard, onRegenerate }) {
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
  const [instructions, setInstructions] = useState('')
  const [regenerating, setRegenerating] = useState(false)

  const handleRegenerate = async () => {
    if (!instructions.trim()) return
    setRegenerating(true)
    try {
      await onRegenerate(draft.id, instructions)
      setEditing(false)
      setInstructions('')
    } finally {
      setRegenerating(false)
    }
  }

  return (
    <div className="bg-card border border-theme rounded-xl p-4">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge color={draft.net_score >= 7 ? 'green' : draft.net_score >= 5 ? 'yellow' : 'slate'}>
            Score {draft.net_score?.toFixed(1)}
          </Badge>
          {draft.status === 'approved' && <Badge color="green">Approved</Badge>}
        </div>
        <div className="text-xs text-faint">{draft.controversy_score}C / {draft.risk_score}R</div>
      </div>

      {draft.source_title && (
        <div className="text-xs text-muted mb-2 flex items-center gap-1">
          <ExternalLink size={10} />
          {draft.source_title.slice(0, 60)}{draft.source_title.length > 60 ? '…' : ''}
        </div>
      )}

      <div
        className={`text-sm text-body leading-relaxed cursor-pointer ${expanded ? '' : 'line-clamp-4'}`}
        onClick={() => setExpanded(v => !v)}
      >
        {draft.body}
      </div>
      {!expanded && (
        <button onClick={() => setExpanded(true)} className="text-xs text-blue-500 mt-1">Show more</button>
      )}

      {/* Edit / regenerate section */}
      {editing ? (
        <div className="mt-3 space-y-2">
          <textarea
            autoFocus
            rows={3}
            value={instructions}
            onChange={e => setInstructions(e.target.value)}
            placeholder="Describe what to change… e.g. 'Make the opening more provocative' or 'Add a reference to LATAM fintech'"
            className="w-full text-sm bg-input border border-theme rounded-lg px-3 py-2 text-body placeholder:text-faint resize-none focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
          <div className="flex gap-2">
            <button
              onClick={handleRegenerate}
              disabled={regenerating || !instructions.trim()}
              className="flex-1 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-lg py-2 text-xs font-medium"
            >
              {regenerating ? 'Regenerating…' : 'Regenerate'}
            </button>
            <button
              onClick={() => { setEditing(false); setInstructions('') }}
              className="px-4 border border-theme rounded-lg text-xs text-muted"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setEditing(true)}
          className="flex items-center gap-1 text-xs text-muted mt-2 hover:text-body"
        >
          <Pencil size={11} /> Edit with instructions
        </button>
      )}

      {draft.status === 'pending' && !editing && (
        <div className="flex gap-2 mt-3">
          <button onClick={() => onApprove(draft.id)}
            className="flex items-center gap-1.5 flex-1 justify-center bg-green-500 hover:bg-green-600 text-white rounded-lg py-2 text-xs font-medium">
            <Check size={14} /> Approve
          </button>
          <button onClick={() => onDiscard(draft.id)}
            className="flex items-center gap-1.5 flex-1 justify-center bg-card2 hover:border-theme2 border border-theme text-body rounded-lg py-2 text-xs font-medium">
            <X size={14} /> Discard
          </button>
        </div>
      )}
    </div>
  )
}
