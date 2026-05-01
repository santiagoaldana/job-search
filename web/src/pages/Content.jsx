import { useEffect, useState } from 'react'
import { RefreshCw, Check, X, ExternalLink, Pencil, PenLine, Link2, Clock, Send, ChevronDown, ChevronUp } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Badge from '../components/Badge'
import Spinner from '../components/Spinner'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtScheduled(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
  })
}

// ── LinkedIn Status Bar ───────────────────────────────────────────────────────

function LinkedInStatusBar() {
  const [status, setStatus] = useState(null)
  const [connecting, setConnecting] = useState(false)

  useEffect(() => {
    api.getLinkedInStatus().then(setStatus).catch(() => setStatus({ connected: false }))
  }, [])

  const handleConnect = async () => {
    setConnecting(true)
    try {
      const { auth_url } = await api.connectLinkedIn()
      window.open(auth_url, '_blank', 'width=600,height=700')
      // Poll for status after user completes OAuth
      const poll = setInterval(async () => {
        const s = await api.getLinkedInStatus()
        if (s.connected) {
          setStatus(s)
          clearInterval(poll)
        }
      }, 3000)
      setTimeout(() => clearInterval(poll), 120000)
    } catch (e) {
      alert(e.message)
    } finally {
      setConnecting(false)
    }
  }

  if (!status) return null

  return (
    <div className={`mx-4 mb-3 px-3 py-2 rounded-xl flex items-center justify-between text-xs
      ${status.connected ? 'bg-green-500/10 border border-green-500/20' : 'bg-amber-500/10 border border-amber-500/20'}`}>
      <div className="flex items-center gap-2">
        <Link2 size={13} className={status.connected ? 'text-green-400' : 'text-amber-400'} />
        {status.connected
          ? <span className="text-green-400">Connected as <span className="font-medium">{status.person_name}</span> · expires {status.expires_at}</span>
          : <span className="text-amber-400">LinkedIn not connected — posts won't auto-publish</span>}
      </div>
      {!status.connected && (
        <button
          onClick={handleConnect}
          disabled={connecting}
          className="text-amber-400 font-medium hover:text-amber-300 disabled:opacity-50"
        >
          {connecting ? 'Opening…' : 'Connect'}
        </button>
      )}
    </div>
  )
}

// ── Schedule Modal ────────────────────────────────────────────────────────────

function ScheduleModal({ draft, onClose, onScheduled, onApprovedOnly }) {
  const [scheduledAt, setScheduledAt] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getNextSlot()
      .then(({ scheduled_at }) => {
        // Convert to datetime-local format (YYYY-MM-DDTHH:mm)
        const d = new Date(scheduled_at)
        const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
        setScheduledAt(local.toISOString().slice(0, 16))
      })
      .catch(() => {
        // Fallback: next Thursday 4pm local
        const d = new Date()
        d.setDate(d.getDate() + ((4 - d.getDay() + 7) % 7 || 7))
        d.setHours(16, 0, 0, 0)
        const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
        setScheduledAt(local.toISOString().slice(0, 16))
      })
      .finally(() => setLoading(false))
  }, [])

  const handleSchedule = async () => {
    if (!scheduledAt) return
    setSaving(true)
    try {
      const iso = new Date(scheduledAt).toISOString()
      await api.schedulePost(draft.id, iso)
      onScheduled(draft.id, iso)
    } catch (e) {
      alert(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleApproveOnly = async () => {
    setSaving(true)
    try {
      await api.approveDraft(draft.id)
      onApprovedOnly(draft.id)
    } catch (e) {
      alert(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-end justify-center" onClick={onClose}>
      <div
        className="bg-card w-full max-w-lg rounded-t-2xl p-5 space-y-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div className="font-semibold text-body flex items-center gap-2">
            <Clock size={16} className="text-blue-400" />
            Schedule Post
          </div>
          <button onClick={onClose}><X size={18} className="text-muted" /></button>
        </div>

        <div className="text-xs text-muted line-clamp-2 bg-bg rounded-lg px-3 py-2">
          {draft.body?.slice(0, 120)}…
        </div>

        <div>
          <label className="text-xs text-muted mb-1.5 block">Publish date & time (suggested: Wed/Thu 3–5 PM ET)</label>
          {loading ? (
            <div className="flex items-center gap-2 text-xs text-muted"><Spinner size={4} /> Finding optimal slot…</div>
          ) : (
            <input
              type="datetime-local"
              value={scheduledAt}
              onChange={e => setScheduledAt(e.target.value)}
              className="w-full bg-bg border border-theme rounded-lg px-3 py-2 text-sm text-body focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          )}
        </div>

        <div className="flex gap-2">
          <button
            onClick={handleSchedule}
            disabled={saving || loading || !scheduledAt}
            className="flex items-center justify-center gap-1.5 flex-1 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-3 text-sm font-medium"
          >
            <Clock size={14} />
            {saving ? 'Scheduling…' : 'Confirm Schedule'}
          </button>
          <button
            onClick={handleApproveOnly}
            disabled={saving}
            className="px-4 border border-theme rounded-xl text-sm text-muted hover:text-body disabled:opacity-50"
          >
            Approve only
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Compose Modal ─────────────────────────────────────────────────────────────

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
        className="bg-card w-full max-w-lg rounded-t-2xl p-4 space-y-3 overflow-y-auto max-h-[55vh]"
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
            rows={3}
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

// ── Draft Card ────────────────────────────────────────────────────────────────

function DraftCard({ draft, onScheduled, onApprovedOnly, onDiscard, onRegenerate, onPublishNow }) {
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
  const [instructions, setInstructions] = useState('')
  const [regenerating, setRegenerating] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [showSchedule, setShowSchedule] = useState(false)

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

  const handlePublishNow = async () => {
    if (!confirm('Publish this post to LinkedIn now?')) return
    setPublishing(true)
    try {
      await onPublishNow(draft.id)
    } catch (e) {
      alert(e.message)
    } finally {
      setPublishing(false)
    }
  }

  const isScheduled = draft.status === 'scheduled'
  const isApproved = draft.status === 'approved'

  return (
    <>
      <div className="bg-card border border-theme rounded-xl p-4">
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge color={draft.net_score >= 7 ? 'green' : draft.net_score >= 5 ? 'yellow' : 'slate'}>
              Score {draft.net_score?.toFixed(1)}
            </Badge>
            {draft.status === 'approved' && <Badge color="green">Approved</Badge>}
            {draft.status === 'scheduled' && <Badge color="blue">Scheduled</Badge>}
          </div>
          <div className="text-xs text-faint">{draft.controversy_score}C / {draft.risk_score}R</div>
        </div>

        {draft.source_title && (
          <div className="text-xs text-muted mb-2 flex items-center gap-1">
            <ExternalLink size={10} />
            {draft.source_title.slice(0, 60)}{draft.source_title.length > 60 ? '…' : ''}
          </div>
        )}

        {isScheduled && draft.scheduled_at && (
          <div className="flex items-center gap-1 text-xs text-blue-400 mb-2">
            <Clock size={10} />
            {fmtScheduled(draft.scheduled_at)}
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

        {/* Edit / regenerate */}
        {!isScheduled && (
          editing ? (
            <div className="mt-3 space-y-2">
              <textarea
                autoFocus
                rows={3}
                value={instructions}
                onChange={e => setInstructions(e.target.value)}
                placeholder="Describe what to change… e.g. 'Make the opening more provocative'"
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
          )
        )}

        {/* Action buttons */}
        {draft.status === 'pending' && !editing && (
          <div className="flex gap-2 mt-3">
            <button onClick={() => setShowSchedule(true)}
              className="flex items-center gap-1.5 flex-1 justify-center bg-blue-500 hover:bg-blue-600 text-white rounded-lg py-2 text-xs font-medium">
              <Clock size={12} /> Schedule
            </button>
            <button onClick={() => onDiscard(draft.id)}
              className="flex items-center gap-1.5 flex-1 justify-center bg-card2 hover:border-theme2 border border-theme text-body rounded-lg py-2 text-xs font-medium">
              <X size={12} /> Discard
            </button>
          </div>
        )}

        {(isApproved || isScheduled) && !editing && (
          <div className="flex gap-2 mt-3">
            <button
              onClick={handlePublishNow}
              disabled={publishing}
              className="flex items-center gap-1.5 flex-1 justify-center bg-green-500 hover:bg-green-600 disabled:opacity-50 text-white rounded-lg py-2 text-xs font-medium"
            >
              <Send size={12} /> {publishing ? 'Publishing…' : 'Publish Now'}
            </button>
            {isApproved && (
              <button onClick={() => setShowSchedule(true)}
                className="flex items-center gap-1.5 flex-1 justify-center border border-blue-500/40 text-blue-400 rounded-lg py-2 text-xs font-medium hover:bg-blue-500/10">
                <Clock size={12} /> Schedule
              </button>
            )}
            <button onClick={() => onDiscard(draft.id)}
              className="px-3 border border-theme text-muted rounded-lg py-2 text-xs hover:text-body">
              <X size={12} />
            </button>
          </div>
        )}
      </div>

      {showSchedule && (
        <ScheduleModal
          draft={draft}
          onClose={() => setShowSchedule(false)}
          onScheduled={(id, iso) => { setShowSchedule(false); onScheduled(id, iso) }}
          onApprovedOnly={(id) => { setShowSchedule(false); onApprovedOnly(id) }}
        />
      )}
    </>
  )
}

// ── Published Card ────────────────────────────────────────────────────────────

function PublishedCard({ draft }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="bg-card border border-theme rounded-xl p-4 opacity-75">
      <div className="flex items-center justify-between mb-2">
        <Badge color="slate">Published</Badge>
        <div className="text-xs text-faint">{draft.published_at?.slice(0, 10)}</div>
      </div>
      <div
        className={`text-sm text-body leading-relaxed cursor-pointer ${expanded ? '' : 'line-clamp-3'}`}
        onClick={() => setExpanded(v => !v)}
      >
        {draft.body}
      </div>
      {!expanded && (
        <button onClick={() => setExpanded(true)} className="text-xs text-blue-500 mt-1">Show more</button>
      )}
    </div>
  )
}

// ── Substack Tab ──────────────────────────────────────────────────────────────

function SubstackDraftCard({ draft, onApprove, onDiscard }) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const wordCount = draft.body ? draft.body.split(/\s+/).length : 0

  const handleCopy = () => {
    navigator.clipboard.writeText(draft.body || '').then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="bg-card border border-theme rounded-xl p-4">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm text-body truncate">{draft.source_title || 'Untitled'}</div>
          <div className="text-xs text-muted mt-0.5">{wordCount} words · {draft.created_at?.slice(0, 10)}</div>
        </div>
        <Badge color={draft.status === 'approved' ? 'green' : 'yellow'}>{draft.status}</Badge>
      </div>

      <div className={`text-sm text-body leading-relaxed whitespace-pre-wrap ${expanded ? '' : 'line-clamp-4'}`}>
        {draft.body}
      </div>
      <button onClick={() => setExpanded(v => !v)} className="text-xs text-blue-500 mt-1 flex items-center gap-1">
        {expanded ? <><ChevronUp size={11} /> Show less</> : <><ChevronDown size={11} /> Show more</>}
      </button>

      <div className="flex gap-2 mt-3 flex-wrap">
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-theme rounded-lg text-body"
        >
          {copied ? <><Check size={11} className="text-green-500" /> Copied!</> : 'Copy to clipboard'}
        </button>
        {draft.status !== 'approved' && (
          <button onClick={() => onApprove(draft.id)}
            className="text-xs px-3 py-1.5 border border-green-300 rounded-lg text-green-600">
            Approve
          </button>
        )}
        <button onClick={() => onDiscard(draft.id)}
          className="text-xs px-3 py-1.5 border border-theme rounded-lg text-muted">
          Discard
        </button>
      </div>
    </div>
  )
}

function SubstackTab() {
  const [drafts, setDrafts] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [topic, setTopic] = useState('')
  const [showTopicInput, setShowTopicInput] = useState(false)

  const load = async () => {
    setLoading(true)
    try { setDrafts(await api.getSubstackDrafts()) } catch (e) { console.error(e) } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleGenerate = async () => {
    if (!topic.trim()) return
    setGenerating(true)
    try {
      await api.generateSubstackDraft(topic.trim())
      setTopic('')
      setShowTopicInput(false)
      await load()
    } catch (e) { alert(e.message) } finally { setGenerating(false) }
  }

  const handleApprove = async (id) => {
    await api.approveDraft(id)
    setDrafts(ds => ds.map(d => d.id === id ? { ...d, status: 'approved' } : d))
  }

  const handleDiscard = async (id) => {
    await api.discardDraft(id)
    setDrafts(ds => ds.filter(d => d.id !== id))
  }

  return (
    <div className="px-4 pb-4 space-y-3">
      <div className="flex items-center justify-between pt-3">
        <div className="text-xs text-muted">{drafts.length} draft{drafts.length !== 1 ? 's' : ''} · paste to Substack manually</div>
        <button
          onClick={() => setShowTopicInput(v => !v)}
          className="flex items-center gap-1.5 text-sm text-blue-500"
        >
          <PenLine size={14} /> Generate
        </button>
      </div>

      {showTopicInput && (
        <div className="bg-card border border-theme rounded-xl p-4 space-y-3">
          <div className="text-sm font-medium text-body">Newsletter topic</div>
          <textarea
            value={topic}
            onChange={e => setTopic(e.target.value)}
            placeholder="e.g. How AI is reshaping executive hiring in FinTech"
            className="w-full h-20 text-sm bg-app border border-theme rounded-lg p-3 resize-none text-body placeholder:text-muted"
          />
          <div className="flex gap-2">
            <button
              onClick={handleGenerate}
              disabled={generating || !topic.trim()}
              className="bg-blue-500 text-white text-sm px-4 py-2 rounded-lg disabled:opacity-50"
            >{generating ? 'Generating…' : 'Generate'}</button>
            <button onClick={() => setShowTopicInput(false)} className="text-sm text-muted px-4 py-2">Cancel</button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12"><Spinner size={6} /></div>
      ) : drafts.length === 0 ? (
        <div className="py-12 text-center text-muted text-sm">No Substack drafts yet — tap Generate to create one</div>
      ) : (
        drafts.map(d => (
          <SubstackDraftCard key={d.id} draft={d} onApprove={handleApprove} onDiscard={handleDiscard} />
        ))
      )}
    </div>
  )
}


// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Content() {
  const [drafts, setDrafts] = useState([])
  const [published, setPublished] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [showCompose, setShowCompose] = useState(false)
  const [showPublished, setShowPublished] = useState(false)
  const [contentTab, setContentTab] = useState('linkedin')

  const load = async () => {
    setLoading(true)
    try {
      const [d, p] = await Promise.all([api.getDrafts(), api.getPublished()])
      setDrafts(d)
      setPublished(p)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleGenerate = async () => {
    setGenerating(true)
    try { await api.generateDrafts(7, 5); await load() }
    catch (e) { alert(e.message) }
    finally { setGenerating(false) }
  }

  const handleScheduled = (id, iso) => {
    setDrafts(ds => ds.map(d => d.id === id ? { ...d, status: 'scheduled', scheduled_at: iso } : d))
  }

  const handleApprovedOnly = (id) => {
    setDrafts(ds => ds.map(d => d.id === id ? { ...d, status: 'approved' } : d))
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

  const handlePublishNow = async (id) => {
    const result = await api.publishNow(id)
    setDrafts(ds => ds.filter(d => d.id !== id))
    setPublished(prev => [result.draft, ...prev].slice(0, 10))
  }

  const pending = drafts.filter(d => d.status === 'pending')
  const approved = drafts.filter(d => d.status === 'approved')
  const scheduled = drafts.filter(d => d.status === 'scheduled')
    .sort((a, b) => (a.scheduled_at || '').localeCompare(b.scheduled_at || ''))

  const cardProps = {
    onScheduled: handleScheduled,
    onApprovedOnly: handleApprovedOnly,
    onDiscard: handleDiscard,
    onRegenerate: handleRegenerate,
    onPublishNow: handlePublishNow,
  }

  return (
    <div className="flex flex-col">
      <PageHeader
        title="Content"
        subtitle={contentTab === 'linkedin'
          ? `${pending.length} pending · ${approved.length} approved · ${scheduled.length} scheduled`
          : 'Substack drafts'}
        action={contentTab === 'linkedin' ? (
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
        ) : null}
      />

      {/* Tab bar */}
      <div className="flex border-b border-theme px-4">
        {[
          { key: 'linkedin', label: 'LinkedIn' },
          { key: 'substack', label: 'Substack' },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setContentTab(key)}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              contentTab === key ? 'border-blue-500 text-blue-500' : 'border-transparent text-muted'
            }`}
          >{label}</button>
        ))}
      </div>

      {contentTab === 'substack' ? <SubstackTab /> : null}

      {contentTab === 'linkedin' && <LinkedInStatusBar />}

      {contentTab === 'linkedin' && loading ? (
        <div className="flex justify-center py-16"><Spinner size={8} /></div>
      ) : contentTab === 'linkedin' ? (
        <div className="px-4 space-y-3 pb-4">
          {drafts.length === 0 && scheduled.length === 0 && (
            <div className="py-12 text-center">
              <div className="text-muted text-sm mb-4">No drafts yet</div>
              <button onClick={handleGenerate} disabled={generating}
                className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-2.5 rounded-xl text-sm font-medium disabled:opacity-50">
                {generating ? 'Generating…' : 'Generate from latest FinTech news'}
              </button>
            </div>
          )}

          {/* Scheduled */}
          {scheduled.length > 0 && (
            <>
              <div className="text-xs text-blue-400 font-medium uppercase tracking-wide flex items-center gap-1.5">
                <Clock size={11} /> Scheduled ({scheduled.length})
              </div>
              {scheduled.map(d => <DraftCard key={d.id} draft={d} {...cardProps} />)}
            </>
          )}

          {/* Approved */}
          {approved.length > 0 && (
            <>
              <div className="text-xs text-muted font-medium uppercase tracking-wide pt-2">Approved ({approved.length})</div>
              {approved.map(d => <DraftCard key={d.id} draft={d} {...cardProps} />)}
            </>
          )}

          {/* Pending review */}
          {pending.length > 0 && (
            <>
              <div className="text-xs text-muted font-medium uppercase tracking-wide pt-2">Pending Review ({pending.length})</div>
              {pending.map(d => <DraftCard key={d.id} draft={d} {...cardProps} />)}
            </>
          )}

          {/* Published history */}
          {published.length > 0 && (
            <>
              <button
                onClick={() => setShowPublished(v => !v)}
                className="flex items-center gap-1.5 text-xs text-faint pt-2 hover:text-muted w-full"
              >
                {showPublished ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                Published history ({published.length})
              </button>
              {showPublished && published.map(d => <PublishedCard key={d.id} draft={d} />)}
            </>
          )}
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
