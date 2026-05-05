import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Flame, Calendar, Mail, BookOpen, Send, Lightbulb, RefreshCw, Briefcase, ChevronDown, ChevronUp, X, UserPlus } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Spinner from '../components/Spinner'
import AICostBadge from '../components/AICostBadge'

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
  contact_gap: UserPlus,
  email_bounce_retry: AlertCircle,
  try_linkedin_dm: Mail,
  linkedin_reimport: Lightbulb,
  event: Calendar,
  check_linkedin_acceptance: UserPlus,
  email_escalation: Mail,
}

const ACTION_COLORS = {
  follow_up_3: 'border-red-300 bg-red-50 dark:border-red-700 dark:bg-red-950/40',
  follow_up_7: 'border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-950/40',
  warm_path: 'border-green-300 bg-green-50 dark:border-green-700 dark:bg-green-950/40',
  hot_lead: 'border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-950/40',
  start_outreach: 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/40',
  interview_prep: 'border-purple-300 bg-purple-50 dark:border-purple-700 dark:bg-purple-950/40',
  event: 'border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30',
  contact_gap: 'border-slate-300 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/40',
  email_bounce_retry: 'border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-950/40',
  try_linkedin_dm: 'border-purple-300 bg-purple-50 dark:border-purple-700 dark:bg-purple-950/40',
  linkedin_reimport: 'border-yellow-300 bg-yellow-50 dark:border-yellow-700 dark:bg-yellow-950/40',
  check_linkedin_acceptance: 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/40',
  email_escalation: 'border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-950/40',
}

const ACTION_ICON_COLORS = {
  follow_up_3: 'text-red-500',
  follow_up_7: 'text-orange-500',
  warm_path: 'text-green-500',
  hot_lead: 'text-orange-500',
  start_outreach: 'text-blue-500',
  interview_prep: 'text-purple-500',
  event: 'text-blue-400',
  contact_gap: 'text-slate-500',
  email_bounce_retry: 'text-orange-500',
  try_linkedin_dm: 'text-purple-500',
  linkedin_reimport: 'text-yellow-500',
  check_linkedin_acceptance: 'text-blue-500',
  email_escalation: 'text-orange-500',
}

function FollowUpModal({ action, onClose, onSent }) {
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [conversation, setConversation] = useState('')
  const [drafting, setDrafting] = useState(true)
  const [sending, setSending] = useState(false)
  const [awaitingConfirm, setAwaitingConfirm] = useState(false)
  const [maitoUrl, setMailtoUrl] = useState(null)
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)
  const [language, setLanguage] = useState('en')
  const [snoozing, setSnoozing] = useState(false)
  const [snoozeDays, setSnoozeDays] = useState(3)

  useEffect(() => {
    setDrafting(true)
    setError(null)
    api.draftFollowup(action.payload_id, action.followup_day, language)
      .then(d => {
        console.log('[FollowUpModal] API response:', { conversation_text_length: d.conversation_text?.length, has_conversation_context: d.has_conversation_context, conversation_history_count: d.conversation_history?.length })
        setSubject(d.subject || '')
        setBody(d.body || '')
        setConversation(d.conversation_text || '')
        setDrafting(false)
      })
      .catch(e => {
        setError(e.message)
        setDrafting(false)
      })
  }, [action.payload_id, action.followup_day, language])

  const handleOpenGmail = async () => {
    setSending(true)
    try {
      const result = await api.buildMailto(action.payload_id, { subject, body, followup_day: action.followup_day })
      const url = result.mailto_url
      setMailtoUrl(url)
      if (url) window.open(url, '_blank')
      setAwaitingConfirm(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setSending(false)
    }
  }

  const handleConfirmSent = async () => {
    setSending(true)
    try {
      await api.markFollowupSent(action.payload_id, { followup_day: action.followup_day })
      setDone(true)
      onSent && onSent(action.payload_id, action.followup_day)
    } catch (e) {
      setError(e.message)
    } finally {
      setSending(false)
    }
  }

  const handleDidNotSend = () => {
    setAwaitingConfirm(false)
    setMailtoUrl(null)
  }

  const handleSnooze = async () => {
    setSending(true)
    try {
      const today = new Date()
      today.setDate(today.getDate() + snoozeDays)
      const newDate = today.toISOString().split('T')[0]
      const patch = action.followup_day === 3
        ? { follow_up_3_due: newDate }
        : { follow_up_7_due: newDate }
      await api.patchOutreach(action.payload_id, patch)
      setDone(true)
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
    <div className="fixed inset-0 z-[60] bg-black/50" onClick={onClose}>
      <div
        className="absolute inset-x-0 bottom-16 mx-auto max-w-lg bg-white dark:bg-slate-900 rounded-2xl shadow-xl flex flex-col"
        style={{maxHeight: 'calc(100dvh - 5rem)'}}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 pt-4 pb-3 border-b border-theme flex-shrink-0">
          <div>
            <div className="font-semibold text-body text-sm">{title} — {companyName}</div>
            <div className="text-xs text-muted mt-0.5">{action.detail}</div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-theme overflow-hidden text-xs font-medium">
              <button
                onClick={() => setLanguage('en')}
                className={`px-2 py-1 transition-colors ${language === 'en' ? 'bg-blue-500 text-white' : 'text-muted hover:text-body'}`}
              >EN</button>
              <button
                onClick={() => setLanguage('es')}
                className={`px-2 py-1 transition-colors ${language === 'es' ? 'bg-blue-500 text-white' : 'text-muted hover:text-body'}`}
              >ES</button>
            </div>
            <button onClick={onClose} className="p-1 text-muted hover:text-body">
              <X size={18} />
            </button>
          </div>
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
              {conversation && (
                <div className="mb-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-200 dark:border-slate-700">
                  <label className="text-xs font-semibold text-muted mb-2 block">📧 Previous Conversation</label>
                  <pre className="text-xs text-muted whitespace-pre-wrap break-words max-h-32 overflow-y-auto font-mono leading-relaxed">
                    {conversation}
                  </pre>
                </div>
              )}
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
                  rows={6}
                  className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body resize-none"
                />
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        {!drafting && !done && !awaitingConfirm && !snoozing && (
          <div className="px-4 pb-4 pt-2 border-t border-theme flex-shrink-0">
            <button
              onClick={handleOpenGmail}
              disabled={sending || !subject || !body}
              className="w-full bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-3 text-sm font-semibold transition-colors"
            >
              {sending ? 'Opening Gmail…' : 'Send via Gmail →'}
            </button>
            <div className="flex gap-3 mt-2 justify-center">
              <button onClick={handleConfirmSent} disabled={sending} className="text-xs text-muted py-1">
                Already sent? Mark as done
              </button>
              <span className="text-xs text-muted py-1">·</span>
              <button onClick={() => setSnoozing(true)} className="text-xs text-muted py-1">
                Snooze / reschedule
              </button>
            </div>
          </div>
        )}
        {!drafting && !done && snoozing && (
          <div className="px-4 pb-4 pt-2 border-t border-theme flex-shrink-0">
            <div className="text-sm font-medium text-body mb-3">Set new follow-up date</div>
            <div className="flex gap-2 mb-3">
              {[2, 3, 5, 7].map(d => (
                <button
                  key={d}
                  onClick={() => setSnoozeDays(d)}
                  className={`flex-1 rounded-lg py-2 text-xs font-medium border transition-colors ${snoozeDays === d ? 'bg-blue-500 text-white border-blue-500' : 'border-theme text-body'}`}
                >
                  +{d}d
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <button onClick={() => setSnoozing(false)} className="flex-1 border border-theme text-body rounded-xl py-2.5 text-sm font-medium">
                Back
              </button>
              <button
                onClick={handleSnooze}
                disabled={sending}
                className="flex-1 bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white rounded-xl py-2.5 text-sm font-semibold transition-colors"
              >
                {sending ? 'Saving…' : `Snooze ${snoozeDays} days`}
              </button>
            </div>
          </div>
        )}
        {!drafting && !done && awaitingConfirm && !snoozing && (
          <div className="px-4 pb-4 pt-2 border-t border-theme flex-shrink-0">
            <div className="text-sm font-medium text-body text-center mb-3">Did you send the email?</div>
            <div className="flex gap-2">
              <button
                onClick={handleDidNotSend}
                className="flex-1 border border-theme text-body rounded-xl py-3 text-sm font-medium"
              >
                No, go back
              </button>
              <button
                onClick={handleConfirmSent}
                disabled={sending}
                className="flex-1 bg-green-500 hover:bg-green-600 disabled:opacity-50 text-white rounded-xl py-3 text-sm font-semibold transition-colors"
              >
                {sending ? 'Saving…' : 'Yes, mark as sent'}
              </button>
            </div>
            {maitoUrl && (
              <button onClick={() => window.open(maitoUrl, '_blank')} className="w-full text-xs text-blue-500 text-center mt-2">
                Re-open Gmail draft
              </button>
            )}
            <button onClick={() => setSnoozing(true)} className="w-full text-xs text-muted text-center mt-2 py-1">
              Snooze / reschedule instead
            </button>
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

function LinkedInAcceptanceCard({ action, onRefresh }) {
  const [state, setState] = useState('prompt') // prompt | escalating | escalated | done
  const [nextStep, setNextStep] = useState(action.next_step || null)
  const [busy, setBusy] = useState(false)
  const [emailSent, setEmailSent] = useState(false)

  const handleAccepted = async () => {
    setBusy(true)
    try {
      await api.patchOutreach(action.payload_id, { linkedin_accepted: true, follow_up_3_sent: true })
    } catch (_) {}
    setBusy(false)
    setState('done')
    setTimeout(onRefresh, 800)
  }

  const handleNotAccepted = async () => {
    setBusy(true)
    try {
      await api.patchOutreach(action.payload_id, { linkedin_accepted: false })
      if (action.contact_id) {
        const res = await api.getContactNextStep(action.contact_id)
        setNextStep(res.next_step)
      }
    } catch (_) {}
    setBusy(false)
    setState('escalating')
  }

  const handleBounced = async () => {
    setBusy(true)
    try {
      const res = await api.markEmailBounced(action.contact_id)
      setNextStep(res.next_step)
      setEmailSent(false)
    } catch (_) {}
    setBusy(false)
  }

  const handleSendEmail = () => {
    if (!nextStep?.guessed_email) return
    const mailto = `mailto:${nextStep.guessed_email}?subject=${encodeURIComponent('Following up — ' + (action.contact_name || ''))}`
    window.open(mailto, '_blank')
    setEmailSent(true)
    setState('escalated')
  }

  return (
    <div className="p-4 rounded-xl border border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/40 space-y-3">
      <div className="flex items-start gap-3">
        <UserPlus size={16} className="mt-0.5 flex-shrink-0 text-blue-500" />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-body text-sm">{action.label}</div>
          <div className="text-xs text-muted mt-0.5">{action.detail}</div>
        </div>
      </div>

      {state === 'prompt' && (
        <div className="flex gap-2">
          <button
            onClick={handleNotAccepted}
            disabled={busy}
            className="flex-1 border border-theme text-body rounded-lg py-2 text-xs font-medium disabled:opacity-50"
          >
            Not yet
          </button>
          <button
            onClick={handleAccepted}
            disabled={busy}
            className="flex-1 bg-blue-500 hover:bg-blue-600 text-white rounded-lg py-2 text-xs font-semibold disabled:opacity-50"
          >
            {busy ? '...' : 'Yes, accepted'}
          </button>
        </div>
      )}

      {state === 'done' && (
        <div className="text-xs text-green-600 font-medium">Marked as connected. DM follow-up queued.</div>
      )}

      {(state === 'escalating' || state === 'escalated') && nextStep && (
        <div className="space-y-2">
          {nextStep.action === 'draft_email_guessed' && (
            <>
              <div className="text-xs text-muted">Guessed email: <span className="font-mono text-body">{nextStep.guessed_email}</span></div>
              {!emailSent ? (
                <button
                  onClick={handleSendEmail}
                  className="w-full bg-orange-500 hover:bg-orange-600 text-white rounded-lg py-2 text-xs font-semibold"
                >
                  Send via Gmail →
                </button>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={handleBounced}
                    disabled={busy}
                    className="flex-1 border border-red-300 text-red-600 rounded-lg py-2 text-xs font-medium disabled:opacity-50"
                  >
                    {busy ? '...' : 'Email bounced — try next'}
                  </button>
                  <button
                    onClick={() => { setState('done'); onRefresh() }}
                    className="flex-1 bg-green-500 text-white rounded-lg py-2 text-xs font-semibold"
                  >
                    Sent
                  </button>
                </div>
              )}
            </>
          )}
          {nextStep.action === 'exhausted' && (
            <div className="text-xs text-muted">All email patterns tried. Try a mutual connection intro or phone outreach.</div>
          )}
          {nextStep.action === 'prompt_manual_email' && (
            <div className="text-xs text-muted">No company domain found to guess email. Add their email manually in the Contacts tab.</div>
          )}
          {nextStep.action === 'draft_linkedin_dm' && (
            <div className="text-xs text-muted">They are already a 1st-degree connection — send a LinkedIn DM directly.</div>
          )}
        </div>
      )}
    </div>
  )
}

function FollowUpCardActions({ action, onMarkSent, onRescheduled }) {
  const [rescheduling, setRescheduling] = useState(false)
  const [newDate, setNewDate] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!newDate) return
    setSaving(true)
    try {
      const field = action.followup_day === 3 ? 'follow_up_3_due' : 'follow_up_7_due'
      await api.patchOutreach(action.payload_id, { [field]: newDate })
      setRescheduling(false)
      onRescheduled && onRescheduled()
    } catch (e) {
      alert(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-2 border-t border-theme/50 pt-2">
      {rescheduling ? (
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={newDate}
            onChange={e => setNewDate(e.target.value)}
            className="flex-1 border border-theme rounded-lg px-2 py-1 text-xs bg-card text-body"
            autoFocus
          />
          <button
            onClick={handleSave}
            disabled={saving || !newDate}
            className="text-xs font-medium text-blue-500 disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            onClick={() => setRescheduling(false)}
            className="text-xs text-muted"
          >
            Cancel
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3 justify-center">
          <button
            onClick={e => { e.stopPropagation(); onMarkSent(action) }}
            className="text-xs text-muted"
          >
            Already sent? Mark done
          </button>
          <span className="text-theme/30">·</span>
          <button
            onClick={e => { e.stopPropagation(); setRescheduling(true) }}
            className="text-xs text-muted"
          >
            Reschedule
          </button>
        </div>
      )}
    </div>
  )
}

function Section({ title, icon: Icon, items, onAction, onMarkSent, onRefresh, badge, badgeColor = 'blue', defaultOpen = true }) {
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
              if (action.action_type === 'check_linkedin_acceptance' || action.action_type === 'email_escalation') {
                return <LinkedInAcceptanceCard key={i} action={action} onRefresh={onRefresh} />
              }

              const Icon = ACTION_ICONS[action.action_type] || AlertCircle
              const cardColor = ACTION_COLORS[action.action_type] || 'border-theme bg-card'
              const iconColor = ACTION_ICON_COLORS[action.action_type] || 'text-muted'
              const isFollowUp = action.action_type === 'follow_up_3' || action.action_type === 'follow_up_7'

              return (
                <div
                  key={i}
                  className={`w-full text-left p-4 rounded-xl border ${cardColor}`}
                >
                  <button
                    onClick={() => onAction(action)}
                    className="w-full text-left transition-all active:scale-[0.99]"
                  >
                    <div className="flex items-start gap-3">
                      <Icon size={16} className={`mt-0.5 flex-shrink-0 ${iconColor}`} />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-body text-sm leading-snug">{action.label}</div>
                        {action.detail && (
                          <div className="text-xs text-muted mt-0.5 leading-relaxed">{action.detail}</div>
                        )}
                        <div className="mt-2 flex items-center gap-2">
                          <span className={`text-xs font-semibold ${isFollowUp ? 'text-red-500' : 'text-blue-500'}`}>
                            {action.cta} →
                          </span>
                          {isFollowUp && <AICostBadge model="haiku" cost="$0.003" />}
                        </div>
                      </div>
                    </div>
                  </button>
                  {isFollowUp && onMarkSent && (
                    <FollowUpCardActions action={action} onMarkSent={onMarkSent} onRescheduled={onRefresh} />
                  )}
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}

function WeeklyHealth() {
  const [open, setOpen] = useState(false)
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    if (report) { setOpen(o => !o); return }
    setOpen(true)
    setLoading(true)
    try {
      setReport(await api.getProgressReport())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const trend = (current, prior, higherIsBetter = true) => {
    if (!prior) return null
    const delta = current - prior
    if (delta === 0) return null
    const up = delta > 0
    const good = higherIsBetter ? up : !up
    return <span className={good ? 'text-green-500' : 'text-red-500'}>{up ? '↑' : '↓'}{Math.abs(delta)}</span>
  }

  return (
    <div className="mx-4 mb-4">
      <button
        onClick={load}
        className="w-full flex items-center justify-between bg-card border border-theme rounded-xl px-4 py-3"
      >
        <div className="text-sm font-medium text-body">Weekly Health</div>
        {open ? <ChevronUp size={16} className="text-muted" /> : <ChevronDown size={16} className="text-muted" />}
      </button>

      {open && (
        <div className="mt-2 bg-card border border-theme rounded-xl overflow-hidden divide-y divide-theme">
          {loading ? (
            <div className="flex justify-center py-8"><Spinner size={6} /></div>
          ) : report ? (
            <>
              {/* Pipeline */}
              <div className="px-4 py-3">
                <div className="text-xs font-semibold text-orange-500 uppercase tracking-wide mb-2">Pipeline</div>
                <div className="flex gap-3 flex-wrap text-xs text-muted mb-2">
                  {['pool','researched','outreach','response','meeting'].map((s, i, arr) => (
                    <span key={s}><strong className="text-body">{report.pipeline.stage_counts[s] || 0}</strong> {s}{i < arr.length-1 ? ' →' : ''}</span>
                  ))}
                </div>
                <div className="flex gap-4 text-sm">
                  <div><span className="font-semibold">{report.pipeline.moved_this_week}</span> <span className="text-xs text-muted">moved this week {trend(report.pipeline.moved_this_week, report.pipeline.moved_prior_week)}</span></div>
                  <div><span className={`font-semibold ${report.pipeline.stalled_count > 0 ? 'text-red-500' : ''}`}>{report.pipeline.stalled_count}</span> <span className="text-xs text-muted">stalled</span></div>
                </div>
              </div>
              {/* Outreach */}
              <div className="px-4 py-3">
                <div className="text-xs font-semibold text-orange-500 uppercase tracking-wide mb-2">Outreach</div>
                <div className="flex gap-4 flex-wrap text-sm">
                  <div><span className="font-semibold">{report.outreach.sent_this_week}</span> <span className="text-xs text-muted">this week {trend(report.outreach.sent_this_week, report.outreach.sent_prior_week)}</span></div>
                  <div><span className={`font-semibold ${report.outreach.response_rate_pct >= 20 ? 'text-green-500' : report.outreach.response_rate_pct < 10 ? 'text-red-500' : ''}`}>{report.outreach.response_rate_pct}%</span> <span className="text-xs text-muted">response rate</span></div>
                  <div><span className="font-semibold text-muted">{report.outreach.ghosted_count}</span> <span className="text-xs text-muted">ghosted</span></div>
                  {report.outreach.avg_reply_days && <div><span className="font-semibold">{report.outreach.avg_reply_days}d</span> <span className="text-xs text-muted">avg reply</span></div>}
                </div>
              </div>
              {/* Follow-ups */}
              <div className="px-4 py-3">
                <div className="text-xs font-semibold text-orange-500 uppercase tracking-wide mb-2">Follow-ups</div>
                <div className="flex gap-4 flex-wrap text-sm">
                  <div><span className={`font-semibold ${report.followups.total_overdue > 0 ? 'text-red-500' : 'text-green-500'}`}>{report.followups.total_overdue}</span> <span className="text-xs text-muted">overdue</span></div>
                  <div><span className="font-semibold text-purple-500">{report.followups.needs_linkedin_dm}</span> <span className="text-xs text-muted">need LinkedIn DM</span></div>
                </div>
              </div>
              {/* Gaps */}
              <div className="px-4 py-3">
                <div className="text-xs font-semibold text-orange-500 uppercase tracking-wide mb-2">Contact Gaps</div>
                <div className="flex gap-4 flex-wrap text-sm">
                  <div><span className={`font-semibold ${report.gaps.no_contact_count > 0 ? 'text-red-500' : 'text-green-500'}`}>{report.gaps.no_contact_count}</span> <span className="text-xs text-muted">no contact found</span></div>
                  <div><span className="font-semibold text-muted">{report.gaps.contact_no_outreach_count}</span> <span className="text-xs text-muted">contact, not reached</span></div>
                </div>
                {report.gaps.no_contact.slice(0, 3).map(c => (
                  <div key={c.id} className="text-xs text-muted mt-1">• {c.name}</div>
                ))}
              </div>
            </>
          ) : null}
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
    } else if (action.action_type === 'contact_gap') {
      navigate(`/company/${action.company_id}?tab=Contacts`)
    } else if (action.action_type === 'email_bounce_retry' || action.action_type === 'try_linkedin_dm') {
      if (action.company_id) navigate(`/company/${action.company_id}?tab=Contacts`)
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
        const contactParam = action.payload_id ? `&contact_id=${action.payload_id}` : ''
        navigate(`/company/${action.company_id}?tab=Outreach${contactParam}`)
      }
    } else if (action.payload_type === 'outreach' && action.company_id) {
      navigate(`/company/${action.company_id}`)
    }
  }

  const handleFollowUpSent = (recordId, followupDay) => {
    setTimeout(() => {
      load()
      setFollowUpModal(null)
    }, 1500)
  }

  const handleMarkSent = async (action) => {
    try {
      await api.markFollowupSent(action.payload_id, { followup_day: action.followup_day })
      load()
    } catch (e) {
      console.error('markFollowupSent error', e)
    }
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

          <WeeklyHealth />

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
              onMarkSent={handleMarkSent}
              onRefresh={load}
              badgeColor="red"
            />
            <div className="mx-4 border-t border-theme my-1" />
            <Section
              title="Companies"
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
