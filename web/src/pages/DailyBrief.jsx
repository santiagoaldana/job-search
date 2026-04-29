import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Flame, Calendar, Mail, BookOpen, Send, Lightbulb, RefreshCw, Briefcase, ChevronDown, ChevronUp, X } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Spinner from '../components/Spinner'

const SECTION_ICONS = {
  positions: Briefcase,
  outreach: Mail,
  events: Calendar,
}

const ACTION_ICONS = {
  follow_up_3: AlertCircle,
  follow_up_7: AlertCircle,
  warm_path: Mail,
  hot_lead: Flame,
  start_outreach: Mail,
  interview_prep: BookOpen,
  publish_content: Send,
  review_suggestions: Lightbulb,
  linkedin_import_reminder: Lightbulb,
  event: Calendar,
}

const ACTION_COLORS = {
  follow_up_3: 'border-red-300 bg-red-50 dark:border-red-700 dark:bg-red-950/40',
  follow_up_7: 'border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-950/40',
  warm_path: 'border-green-300 bg-green-50 dark:border-green-700 dark:bg-green-950/40',
  hot_lead: 'border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-950/40',
  start_outreach: 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/40',
  interview_prep: 'border-purple-300 bg-purple-50 dark:border-purple-700 dark:bg-purple-950/40',
  event: 'border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30',
}

const ACTION_ICON_COLORS = {
  follow_up_3: 'text-red-500',
  follow_up_7: 'text-orange-500',
  warm_path: 'text-green-500',
  hot_lead: 'text-orange-500',
  start_outreach: 'text-blue-500',
  interview_prep: 'text-purple-500',
  event: 'text-blue-400',
}

function FollowUpModal({ action, onClose, onSent }) {
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [drafting, setDrafting] = useState(true)
  const [sending, setSending] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.draftFollowup(action.payload_id, action.followup_day)
      .then(d => {
        setSubject(d.subject || '')
        setBody(d.body || '')
        setDrafting(false)
      })
      .catch(e => {
        setError(e.message)
        setDrafting(false)
      })
  }, [action.payload_id, action.followup_day])

  const handleSend = async () => {
    setSending(true)
    try {
      const result = await api.sendFollowup(action.payload_id, {
        subject,
        body,
        followup_day: action.followup_day,
      })
      setDone(true)
      if (result.mailto_url) {
        window.open(result.mailto_url, '_blank')
      }
      onSent && onSent(action.payload_id, action.followup_day)
    } catch (e) {
      setError(e.message)
    } finally {
      setSending(false)
    }
  }

  const title = action.followup_day === 3 ? 'Day 3 Bump' : 'Day 7 Close'
  const companyName = action.label?.replace(/Day \d+ (?:follow-up|close) — /, '') || ''

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 px-0 sm:px-4">
      <div className="bg-white dark:bg-slate-900 w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl shadow-xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 pt-4 pb-3 border-b border-theme flex-shrink-0">
          <div>
            <div className="font-semibold text-body text-sm">{title} — {companyName}</div>
            <div className="text-xs text-muted mt-0.5">{action.detail}</div>
          </div>
          <button onClick={onClose} className="p-1 text-muted hover:text-body">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {error && (
            <div className="mb-3 text-xs text-red-500 bg-red-50 dark:bg-red-950/40 rounded-lg p-2">{error}</div>
          )}
          {drafting ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <Spinner size={6} />
              <div className="text-xs text-muted">Drafting with AI…</div>
            </div>
          ) : done ? (
            <div className="flex flex-col items-center py-8 gap-2 text-green-600 dark:text-green-400">
              <div className="text-3xl">✓</div>
              <div className="text-sm font-medium">Draft logged</div>
              <div className="text-xs text-muted text-center">Your email client should have opened with the pre-filled message.</div>
            </div>
          ) : (
            <>
              <div className="mb-2">
                <label className="text-xs text-muted mb-1 block">Subject</label>
                <input
                  value={subject}
                  onChange={e => setSubject(e.target.value)}
                  className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body"
                  placeholder="Subject"
                />
              </div>
              <div>
                <label className="text-xs text-muted mb-1 block">Body</label>
                <textarea
                  value={body}
                  onChange={e => setBody(e.target.value)}
                  rows={9}
                  className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body resize-none"
                />
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        {!drafting && !done && (
          <div className="px-4 pb-4 pt-2 border-t border-theme flex-shrink-0">
            <button
              onClick={handleSend}
              disabled={sending || !subject || !body}
              className="w-full bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-3 text-sm font-semibold transition-colors"
            >
              {sending ? 'Opening Gmail…' : 'Send via Gmail →'}
            </button>
            <div className="text-xs text-muted text-center mt-2">Opens your email client with this message pre-filled</div>
          </div>
        )}
        {done && (
          <div className="px-4 pb-4 pt-2 flex-shrink-0">
            <button onClick={onClose} className="w-full border border-theme text-body rounded-xl py-3 text-sm font-medium">
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function Section({ title, icon: Icon, items, onAction, badge, badgeColor = 'blue', defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="mb-1">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5"
      >
        <div className="flex items-center gap-2">
          <Icon size={15} className="text-muted" />
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</span>
          {items.length > 0 && (
            <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium text-white ${
              badgeColor === 'red' ? 'bg-red-500' :
              badgeColor === 'orange' ? 'bg-orange-500' :
              badgeColor === 'green' ? 'bg-green-500' :
              'bg-blue-500'
            }`}>
              {items.length}
            </span>
          )}
        </div>
        {open ? <ChevronUp size={14} className="text-muted" /> : <ChevronDown size={14} className="text-muted" />}
      </button>

      {open && (
        <div className="px-4 space-y-2 pb-2">
          {items.length === 0 ? (
            <div className="py-4 text-center text-muted text-xs">Nothing to do here ✓</div>
          ) : (
            items.map((action, i) => {
              const Icon = ACTION_ICONS[action.action_type] || AlertCircle
              const cardColor = ACTION_COLORS[action.action_type] || 'border-theme bg-card'
              const iconColor = ACTION_ICON_COLORS[action.action_type] || 'text-muted'
              const isFollowUp = action.action_type === 'follow_up_3' || action.action_type === 'follow_up_7'

              return (
                <button
                  key={i}
                  onClick={() => onAction(action)}
                  className={`w-full text-left p-4 rounded-xl border ${cardColor} transition-all active:scale-[0.99]`}
                >
                  <div className="flex items-start gap-3">
                    <Icon size={16} className={`mt-0.5 flex-shrink-0 ${iconColor}`} />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-body text-sm leading-snug">{action.label}</div>
                      {action.detail && (
                        <div className="text-xs text-muted mt-0.5 leading-relaxed">{action.detail}</div>
                      )}
                      <div className="mt-2">
                        <span className={`text-xs font-semibold ${isFollowUp ? 'text-red-500' : 'text-blue-500'}`}>
                          {action.cta} →
                        </span>
                      </div>
                    </div>
                  </div>
                </button>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}

export default function DailyBrief() {
  const [brief, setBrief] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [followUpModal, setFollowUpModal] = useState(null)
  const navigate = useNavigate()

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setBrief(await api.getDailyBrief())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleAction = (action) => {
    if (action.action_type === 'follow_up_3' || action.action_type === 'follow_up_7') {
      setFollowUpModal(action)
      return
    }
    if (action.action_type === 'start_outreach') {
      navigate(`/company/${action.company_id || action.payload_id}`)
    } else if (action.action_type === 'hot_lead') {
      if (action.company_id) {
        navigate(`/leads?company_id=${action.company_id}`)
      } else {
        navigate('/leads')
      }
    } else if (action.payload_type === 'event' || action.action_type === 'event') {
      if (action.event_id) {
        navigate(`/events?highlight=${action.event_id}`)
      } else {
        navigate('/events')
      }
    } else if (action.payload_type === 'company') {
      navigate(`/company/${action.company_id || action.payload_id}`)
    } else if (action.payload_type === 'content') {
      navigate('/content')
    } else if (action.payload_type === 'suggestions') {
      navigate('/settings')
    } else if (action.payload_type === 'settings') {
      navigate('/settings')
    } else if (action.payload_type === 'contact' || action.action_type === 'warm_path') {
      if (action.company_id) {
        navigate(`/company/${action.company_id}`)
      }
    } else if (action.payload_type === 'outreach' && action.company_id) {
      navigate(`/company/${action.company_id}`)
    }
  }

  const handleFollowUpSent = (recordId, followupDay) => {
    // Refresh brief so the sent item disappears
    setTimeout(() => {
      load()
      setFollowUpModal(null)
    }, 1500)
  }

  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
  const overdueCount = brief ? (brief.overdue_count || 0) : 0

  return (
    <div className="flex flex-col">
      <PageHeader
        title="Daily Brief"
        subtitle={today}
        action={
          <button onClick={load} className="p-2 text-muted hover:text-body transition-colors">
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>
        }
      />

      {loading && !brief && (
        <div className="flex justify-center py-16"><Spinner size={8} /></div>
      )}

      {error && (
        <div className="mx-4 p-4 bg-red-50 border border-red-200 dark:bg-red-950/50 dark:border-red-700 rounded-xl text-red-600 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      {brief && (
        <>
          {/* Summary bar */}
          <div className="flex gap-3 px-4 pb-3">
            <div className="flex-1 bg-card border border-theme rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-body">{brief.total_actions}</div>
              <div className="text-xs text-muted mt-0.5">actions</div>
            </div>
            <div className={`flex-1 rounded-xl p-3 text-center border ${overdueCount > 0 ? 'bg-red-50 border-red-200 dark:bg-red-950/60 dark:border-red-800' : 'bg-card border-theme'}`}>
              <div className={`text-2xl font-bold ${overdueCount > 0 ? 'text-red-500 dark:text-red-400' : 'text-muted'}`}>
                {overdueCount}
              </div>
              <div className="text-xs text-muted mt-0.5">overdue</div>
            </div>
          </div>

          {brief.total_actions === 0 && (
            <div className="mx-4 p-8 text-center text-muted">
              <div className="text-4xl mb-3">✓</div>
              <div className="font-medium text-body">All clear for today</div>
              <div className="text-sm mt-1">No pending actions</div>
            </div>
          )}

          <div className="pb-4">
            <Section
              title="Outreach"
              icon={Mail}
              items={brief.outreach || []}
              onAction={handleAction}
              badgeColor="red"
            />
            <div className="mx-4 border-t border-theme my-1" />
            <Section
              title="Positions"
              icon={Briefcase}
              items={brief.positions || []}
              onAction={handleAction}
              badgeColor="orange"
            />
            <div className="mx-4 border-t border-theme my-1" />
            <Section
              title="Events"
              icon={Calendar}
              items={brief.events || []}
              onAction={handleAction}
              badgeColor="blue"
            />
          </div>
        </>
      )}

      {followUpModal && (
        <FollowUpModal
          action={followUpModal}
          onClose={() => setFollowUpModal(null)}
          onSent={handleFollowUpSent}
        />
      )}
    </div>
  )
}
