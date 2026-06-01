import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Flame, Calendar, Mail, BookOpen, Send, Lightbulb, RefreshCw, Briefcase, ChevronDown, ChevronUp, X, UserPlus, MessageSquare, Star } from 'lucide-react'
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
  prompt_review: BookOpen,
  call: MessageSquare,
  contact_gap: UserPlus,
  email_bounce_retry: AlertCircle,
  try_linkedin_dm: Mail,
  event: Calendar,
  check_linkedin_acceptance: UserPlus,
  email_escalation: Mail,
  new_reply: MessageSquare,
  linkedin_accepted: UserPlus,
  champion_checkin: Star,
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
  check_linkedin_acceptance: 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/40',
  email_escalation: 'border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-950/40',
  new_reply: 'border-green-400 bg-green-50 dark:border-green-600 dark:bg-green-950/50',
  linkedin_accepted: 'border-sky-300 bg-sky-50 dark:border-sky-700 dark:bg-sky-950/40',
  champion_checkin: 'border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/40',
  prompt_review: 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/40',
  call: 'border-violet-300 bg-violet-50 dark:border-violet-700 dark:bg-violet-950/40',
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
  check_linkedin_acceptance: 'text-blue-500',
  email_escalation: 'text-orange-500',
  new_reply: 'text-green-600',
  linkedin_accepted: 'text-sky-500',
  champion_checkin: 'text-amber-500',
  prompt_review: 'text-blue-500',
  call: 'text-violet-500',
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
  const [keepwarm, setKeepwarm] = useState(false)
  const [keepwarmDays, setKeepwarmDays] = useState(30)
  const [keepwarmDate, setKeepwarmDate] = useState('')
  const [keepwarmDone, setKeepwarmDone] = useState(false)
  const [postMeetingChoice, setPostMeetingChoice] = useState(null) // null | 'd3' | 'champion' | 'remind'
  const [championNotes, setChampionNotes] = useState('')
  const [championDate, setChampionDate] = useState('')
  const [newElement, setNewElement] = useState('')
  const [suggestingElement, setSuggestingElement] = useState(false)
  const [meetingNote, setMeetingNote] = useState('')
  const [meetingNoteSubmitted, setMeetingNoteSubmitted] = useState(false)
  const [personalEmail, setPersonalEmail] = useState('')
  const [personalEmailSaving, setPersonalEmailSaving] = useState(false)
  const [personalEmailDone, setPersonalEmailDone] = useState(false)

  useEffect(() => {
    setDrafting(true)
    setError(null)
    // For MSG-5 (followup_day=0), don't auto-draft — wait for meeting note
    if (action.followup_day === 0) {
      setDrafting(false)
      return
    }
    api.draftFollowup(action.payload_id, action.followup_day, language)
      .then(d => {
        const draftSubject = d.subject || ''
        const draftBody = d.body || ''
        setSubject(draftSubject)
        setBody(draftBody)
        setConversation(d.conversation_text || '')
        // Pre-fill meeting note for MSG-6 from record.notes
        if (action.followup_day === -1 && d.meeting_note) {
          setMeetingNote(d.meeting_note)
        }
        setDrafting(false)
        // For Day 3 bumps, fetch a suggested new element to pre-fill the input
        if (action.followup_day === 3) {
          setSuggestingElement(true)
          api.suggestBumpElement(action.payload_id)
            .then(r => { if (r.suggestion) setNewElement(r.suggestion) })
            .catch(() => {})
            .finally(() => setSuggestingElement(false))
        }
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
      if (!result.to_email) {
        setError('No email address on file for this contact. Add one in the company card first.')
        setSending(false)
        return
      }
      if (result.email_is_guessed) {
        setError(`Sending to guessed email: ${result.to_email} — verify in Gmail before sending.`)
      }
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
    setError(null)
    try {
      const payload = { followup_day: action.followup_day }
      if (action.followup_day === 0 && meetingNote.trim()) payload.meeting_note = meetingNote.trim()
      await api.markFollowupSent(action.payload_id, payload)
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



  const handleKeepwarm = async () => {
    setSending(true)
    try {
      let chosenDate = keepwarmDate
      if (!chosenDate) {
        const d = new Date()
        d.setDate(d.getDate() + keepwarmDays)
        chosenDate = d.toISOString().split('T')[0]
      }
      await api.patchOutreach(action.payload_id, { follow_up_7_sent: false, follow_up_7_due: chosenDate })
      setKeepwarmDone(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setSending(false)
    }
  }

  const title = action.followup_day === 0 ? 'Post-Meeting Follow-up' : action.followup_day === -1 ? 'Reach Back Out' : action.followup_day === 3 ? 'Day 3 follow-up' : 'Day 7 close-out'
  const companyName = action.label?.replace(/Day \d+ (?:follow-up|close) — /, '') || ''

  return (
    <div className="fixed inset-0 z-[60] bg-black/50" onClick={onClose}>
      <div
        className="absolute inset-x-0 bottom-16 mx-auto max-w-lg bg-white dark:bg-slate-900 rounded-2xl shadow-xl flex flex-col overflow-hidden"
        style={{maxHeight: 'calc(100dvh - 8rem)'}}
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
          {error && !body && (
            <div className="flex flex-col items-center py-8 gap-3">
              <div className="text-xs text-red-500 bg-red-50 dark:bg-red-950/40 rounded-lg p-3 text-center w-full">
                Could not load draft — the server may be waking up. Try again in a few seconds.
              </div>
              <button
                onClick={() => { setError(null); setDrafting(true); api.draftFollowup(action.payload_id, action.followup_day, language).then(d => { setSubject(d.subject || ''); setBody(d.body || ''); setConversation(d.conversation_text || ''); setDrafting(false); }).catch(e => { setError(e.message); setDrafting(false); }) }}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
              >
                Retry
              </button>
            </div>
          )}
          {error && body && (
            <div className="mb-3 text-xs text-red-500 bg-red-50 dark:bg-red-950/40 rounded-lg p-2">{error}</div>
          )}
          {drafting ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <Spinner size={6} />
              <div className="text-xs text-muted">Drafting with AI…</div>
            </div>
          ) : done ? (
            <div className="flex flex-col items-center py-6 gap-2 text-green-600 dark:text-green-400">
              <div className="text-3xl">✓</div>
              <div className="text-sm font-medium">Sent!</div>
              {action.followup_day === 0 ? (
                /* Post-meeting Email 1 sent — 3-option next step */
                keepwarmDone ? (
                  <div className="text-xs text-muted text-center mt-1">All set. See you then.</div>
                ) : postMeetingChoice === 'd3' ? (
                  <div className="text-xs text-muted text-center mt-1">D+3 follow-up scheduled. Card will surface in 3 business days.</div>
                ) : postMeetingChoice === 'champion' ? (
                  championDate ? (
                    <div className="w-full mt-3 text-body" onClick={e => e.stopPropagation()}>
                      <textarea rows={2} placeholder="How do you know them / what happened?" value={championNotes} onChange={e => setChampionNotes(e.target.value)}
                        className="w-full text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body placeholder:text-muted resize-none focus:outline-none focus:ring-1 focus:ring-amber-500 mb-2" />
                      <div className="flex gap-2">
                        <input type="date" value={championDate} onChange={e => setChampionDate(e.target.value)}
                          className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body focus:outline-none focus:ring-1 focus:ring-amber-500" />
                        <button disabled={!championDate || sending} onClick={async e => { e.stopPropagation(); setSending(true); try { await api.updateContact(action.contact_id, { is_champion: true, champion_notes: championNotes.trim() || null, next_checkin_date: championDate }); setKeepwarmDone(true); } catch(err) { setError(err.message); } finally { setSending(false); } }}
                          className="text-xs px-3 py-2 rounded-lg bg-amber-500 text-white font-medium disabled:opacity-40 hover:bg-amber-600">
                          {sending ? 'Saving…' : 'Confirm'}
                        </button>
                        <button onClick={e => { e.stopPropagation(); setPostMeetingChoice(null); }} className="text-xs px-3 py-2 rounded-lg border border-theme text-muted hover:text-body">Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <div className="w-full mt-3 text-body" onClick={e => e.stopPropagation()}>
                      <div className="text-xs text-muted mb-2 text-center">Set next check-in date</div>
                      <div className="flex gap-2">
                        <input type="date" value={championDate} onChange={e => setChampionDate(e.target.value)}
                          className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body focus:outline-none focus:ring-1 focus:ring-amber-500" />
                        <button onClick={e => { e.stopPropagation(); setPostMeetingChoice(null); }} className="text-xs px-3 py-2 rounded-lg border border-theme text-muted hover:text-body">Cancel</button>
                      </div>
                    </div>
                  )
                ) : postMeetingChoice === 'remind' ? (
                  <div className="w-full mt-3 text-body">
                    <div className="flex gap-2 mb-2">
                      {[14, 30, 60].map(d => (
                        <button key={d} onClick={() => { setKeepwarmDays(d); setKeepwarmDate(''); }}
                          className={`flex-1 rounded-lg py-2 text-xs font-medium border transition-colors ${keepwarmDays === d && !keepwarmDate ? 'bg-blue-500 text-white border-blue-500' : 'border-theme text-body'}`}>
                          +{d}d
                        </button>
                      ))}
                    </div>
                    <input type="date" value={keepwarmDate} onChange={e => { setKeepwarmDate(e.target.value); setKeepwarmDays(0); }}
                      className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body mb-3" />
                    <div className="flex gap-2">
                      <button onClick={() => setPostMeetingChoice(null)} className="flex-1 border border-theme text-body rounded-xl py-2.5 text-sm font-medium">Back</button>
                      <button onClick={handleKeepwarm} disabled={sending || (!keepwarmDate && !keepwarmDays)}
                        className="flex-1 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-2.5 text-sm font-semibold transition-colors">
                        {sending ? 'Saving…' : 'Set reminder'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="w-full mt-3 flex flex-col gap-2 text-body">
                    <button onClick={async e => { e.stopPropagation(); setSending(true); try { const d = new Date(); d.setDate(d.getDate() + 3); await api.patchOutreach(action.payload_id, { post_meeting_2_due: d.toISOString().slice(0,10) }); setPostMeetingChoice('d3'); } catch(err) { setError(err.message); } finally { setSending(false); } }}
                      disabled={sending}
                      className="w-full border border-theme text-body rounded-xl py-2.5 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40">
                      Schedule D+3 follow-up
                    </button>
                    <button onClick={e => { e.stopPropagation(); setPostMeetingChoice('champion'); }}
                      className="w-full border border-amber-300 text-amber-600 dark:text-amber-400 rounded-xl py-2.5 text-sm font-medium hover:bg-amber-50 dark:hover:bg-amber-950/30">
                      They were a great lead — mark as champion
                    </button>
                    <button onClick={e => { e.stopPropagation(); setPostMeetingChoice('remind'); }}
                      className="w-full text-xs text-muted hover:underline py-1">
                      Remind me later
                    </button>
                  </div>
                )
              ) : (
                /* Non-post-meeting — original keepwarm flow */
                keepwarmDone ? (
                  <div className="text-xs text-muted text-center mt-1">Keepwarm reminder set. See you then.</div>
                ) : keepwarm ? (
                  <div className="w-full mt-3 text-body">
                    <div className="text-sm font-medium mb-3 text-center text-body">Schedule a keepwarm reminder?</div>
                    <div className="flex gap-2 mb-2">
                      {[14, 30, 60].map(d => (
                        <button key={d} onClick={() => { setKeepwarmDays(d); setKeepwarmDate(''); }}
                          className={`flex-1 rounded-lg py-2 text-xs font-medium border transition-colors ${keepwarmDays === d && !keepwarmDate ? 'bg-blue-500 text-white border-blue-500' : 'border-theme text-body'}`}>
                          +{d}d
                        </button>
                      ))}
                    </div>
                    <input type="date" value={keepwarmDate} onChange={e => { setKeepwarmDate(e.target.value); setKeepwarmDays(0); }}
                      className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body mb-3" />
                    <div className="flex gap-2">
                      <button onClick={() => setKeepwarm(false)} className="flex-1 border border-theme text-body rounded-xl py-2.5 text-sm font-medium">Skip</button>
                      <button onClick={handleKeepwarm} disabled={sending || (!keepwarmDate && !keepwarmDays)}
                        className="flex-1 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-2.5 text-sm font-semibold transition-colors">
                        {sending ? 'Saving…' : 'Set reminder'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <button onClick={() => setKeepwarm(true)} className="mt-1 text-xs text-blue-500 hover:underline">
                    Schedule a keepwarm reminder?
                  </button>
                )
              )}
              {action.followup_day === 7 && action.linkedin_accepted && !personalEmailDone && (
                <div className="w-full mt-3 px-1" onClick={e => e.stopPropagation()}>
                  <div className="text-xs text-muted mb-2 text-center">This contact is connected on LinkedIn. Check their profile for a personal email before closing out.</div>
                  <div className="flex gap-2">
                    <input
                      type="email"
                      placeholder="personal@email.com"
                      value={personalEmail}
                      onChange={e => setPersonalEmail(e.target.value)}
                      className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    <button
                      disabled={!personalEmail.trim() || personalEmailSaving}
                      onClick={async e => {
                        e.stopPropagation()
                        setPersonalEmailSaving(true)
                        try {
                          if (action.contact_id) {
                            await api.updateContact(action.contact_id, { email: personalEmail.trim(), email_guessed: false })
                          }
                          setPersonalEmailDone(true)
                        } catch (err) {
                          console.error(err)
                        } finally {
                          setPersonalEmailSaving(false)
                        }
                      }}
                      className="text-xs px-3 py-2 rounded-lg bg-blue-500 text-white font-medium disabled:opacity-40 hover:bg-blue-600"
                    >{personalEmailSaving ? 'Saving…' : 'Save'}</button>
                  </div>
                </div>
              )}
              {action.followup_day === 7 && action.linkedin_accepted && personalEmailDone && (
                <div className="text-xs text-muted text-center mt-2">Personal email saved. Fresh outreach cadence will start automatically.</div>
              )}
            </div>
          ) : !error || body ? (
            <>
              {/* MSG-5: meeting note gate — show before draft for followup_day=0 */}
              {action.followup_day === 0 && !meetingNoteSubmitted ? (
                <div className="flex flex-col gap-3">
                  <div>
                    <label className="text-xs font-medium text-body mb-1 block">
                      Meeting notes <span className="text-orange-500">*</span>
                    </label>
                    <p className="text-xs text-muted mb-2">What did you discuss? What did they say that stood out? The AI will anchor the thank-you on a specific thing they raised.</p>
                    <textarea
                      value={meetingNote}
                      onChange={e => setMeetingNote(e.target.value)}
                      rows={4}
                      placeholder="e.g. They raised the challenge of onboarding fintech partners quickly. Asked about my experience with API integrations at Avianca…"
                      className={`w-full rounded-lg px-3 py-2 text-sm bg-card text-body resize-none placeholder-faint focus:outline-none focus:ring-1 border ${meetingNote.trim() ? 'border-theme focus:ring-blue-500' : 'border-orange-400 focus:ring-orange-500'}`}
                    />
                    {!meetingNote.trim() && (
                      <p className="text-xs text-orange-500 mt-1">Add meeting notes to draft the thank-you</p>
                    )}
                  </div>
                  <button
                    disabled={!meetingNote.trim() || drafting}
                    onClick={async () => {
                      setDrafting(true)
                      setError(null)
                      try {
                        const d = await api.draftFollowup(action.payload_id, action.followup_day, language, meetingNote.trim())
                        setSubject(d.subject || '')
                        setBody(d.body || '')
                        setConversation(d.conversation_text || '')
                        setMeetingNoteSubmitted(true)
                      } catch (e) { setError(e.message) }
                      finally { setDrafting(false) }
                    }}
                    className="w-full bg-blue-500 hover:bg-blue-600 disabled:opacity-40 text-white rounded-xl py-2.5 text-sm font-semibold transition-colors"
                  >
                    {drafting ? 'Drafting…' : 'Draft thank-you'}
                  </button>
                </div>
              ) : (
              <>
              {conversation && (
                <div className="mb-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-200 dark:border-slate-700">
                  <label className="text-xs font-semibold text-muted mb-2 block">📧 Previous Conversation</label>
                  <pre className="text-xs text-muted whitespace-pre-wrap break-words max-h-20 overflow-y-auto font-mono leading-relaxed">
                    {conversation}
                  </pre>
                </div>
              )}
              {/* MSG-6: editable meeting note pre-filled from record.notes */}
              {action.followup_day === -1 && (
                <div className="mb-2">
                  <label className="text-xs text-muted mb-1 block">
                    Meeting notes {meetingNote ? <span className="text-green-500">(pre-filled from your thank-you)</span> : <span className="text-orange-400">(not found — add to improve the draft)</span>}
                  </label>
                  <textarea
                    value={meetingNote}
                    onChange={e => setMeetingNote(e.target.value)}
                    rows={3}
                    placeholder="What did you discuss? The AI will use this to frame the referral ask."
                    className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body resize-none placeholder-faint"
                  />
                  {meetingNote && (
                    <button
                      onClick={async () => {
                        setDrafting(true)
                        try {
                          const d = await api.draftFollowup(action.payload_id, action.followup_day, language, meetingNote.trim())
                          setSubject(d.subject || '')
                          setBody(d.body || '')
                        } catch (e) { setError(e.message) }
                        finally { setDrafting(false) }
                      }}
                      disabled={drafting}
                      className="mt-1.5 text-xs text-blue-500 hover:text-blue-600 disabled:opacity-40"
                    >
                      Regenerate with updated notes
                    </button>
                  )}
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
              {action.followup_day === 3 && (
                <div>
                  <label className="text-xs text-muted mb-1 block">
                    New element — what you noticed since you sent this
                    {suggestingElement && <span className="ml-1 text-blue-400">suggesting…</span>}
                  </label>
                  <textarea
                    value={newElement}
                    onChange={e => setNewElement(e.target.value)}
                    rows={2}
                    placeholder="A question that occurred to you, a data point, or a reframe of the original ask…"
                    className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body resize-none placeholder-faint"
                  />
                  {newElement && (
                    <button
                      onClick={async () => {
                        setDrafting(true)
                        try {
                          const d = await api.draftFollowup(action.payload_id, action.followup_day, language, newElement)
                          setBody(d.body || '')
                        } catch (e) { setError(e.message) }
                        finally { setDrafting(false) }
                      }}
                      disabled={drafting}
                      className="mt-1.5 text-xs text-blue-500 hover:text-blue-600 disabled:opacity-40"
                    >
                      Regenerate with this element
                    </button>
                  )}
                </div>
              )}
              <div>
                <label className="text-xs text-muted mb-1 block">Body</label>
                <textarea
                  value={body}
                  onChange={e => setBody(e.target.value)}
                  rows={4}
                  className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body resize-none"
                />
              </div>
              {/* Snooze — always visible in scroll area */}
              {!snoozing && (
                <div className="mt-3 pt-3 border-t border-theme flex gap-3 justify-center">
                  <button onClick={handleConfirmSent} disabled={sending} className="text-xs text-muted py-1">
                    Already sent? Mark as done
                  </button>
                  <span className="text-xs text-muted py-1">·</span>
                  <button onClick={() => setSnoozing(true)} className="text-xs text-muted py-1">
                    Snooze / reschedule
                  </button>
                </div>
              )}
              {snoozing && (
                <div className="mt-3 pt-3 border-t border-theme">
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
                      Cancel
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
            </>
            )}
            </>
          ) : null}
        </div>

        {/* Footer */}
        {!drafting && !done && !awaitingConfirm && !(action.followup_day === 0 && !meetingNoteSubmitted) && (
          <div className="px-4 pb-4 pt-2 border-t border-theme flex-shrink-0">
            <button
              onClick={handleOpenGmail}
              disabled={sending || !subject || !body}
              className="w-full bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-3 text-sm font-semibold transition-colors"
            >
              {sending ? 'Opening Gmail…' : 'Send via Gmail →'}
            </button>
          </div>
        )}
        {!drafting && !done && awaitingConfirm && (
          <div className="px-4 pb-4 pt-2 border-t border-theme flex-shrink-0">
            <div className="text-sm font-medium text-body text-center mb-3">Did you send the email?</div>
            {error && (
              <div className="mb-3 text-xs text-red-500 bg-red-50 dark:bg-red-950/40 rounded-lg p-2 text-center">{error}</div>
            )}
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

function InlineFollowUpCard({ action, onSent, onDismiss, onRefresh }) {
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [conversation, setConversation] = useState('')
  const [drafting, setDrafting] = useState(false)
  const [sending, setSending] = useState(false)
  const [awaitingConfirm, setAwaitingConfirm] = useState(false)
  const [mailtoUrl, setMailtoUrl] = useState(null)
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)
  const [language, setLanguage] = useState('en')
  const [rescheduling, setRescheduling] = useState(false)
  const [rescheduleDate, setRescheduleDate] = useState('')
  const [keepwarm, setKeepwarm] = useState(false)
  const [keepwarmDate, setKeepwarmDate] = useState('')
  const [keepwarmDone, setKeepwarmDone] = useState(false)
  const [postMeetingChoice, setPostMeetingChoice] = useState(null)
  const [championNotes, setChampionNotes] = useState('')
  const [championDate, setChampionDate] = useState('')
  const [newElement, setNewElement] = useState('')
  const [suggestingElement, setSuggestingElement] = useState(false)
  const [meetingNote, setMeetingNote] = useState('')
  const [meetingNoteSubmitted, setMeetingNoteSubmitted] = useState(false)
  const [personalEmail, setPersonalEmail] = useState('')
  const [personalEmailSaving, setPersonalEmailSaving] = useState(false)
  const [personalEmailDone, setPersonalEmailDone] = useState(false)
  const [closing, setClosing] = useState(false)

  const cardColor = ACTION_COLORS[action.action_type] || 'border-theme bg-card'
  const ActionIcon = ACTION_ICONS[action.action_type] || AlertCircle
  const iconColor = ACTION_ICON_COLORS[action.action_type] || 'text-muted'
  const isPriority = false
  const title = action.followup_day === 0 ? 'Post-Meeting Follow-up' : action.followup_day === -1 ? 'Reach Back Out' : action.followup_day === 3 ? 'Day 3 follow-up' : 'Day 7 close-out'

  const handleDraft = async () => {
    setDrafting(true)
    setError(null)
    try {
      const d = await api.draftFollowup(action.payload_id, action.followup_day, language, newElement || undefined)
      setSubject(d.subject || '')
      setBody(d.body || '')
      setConversation(d.conversation_text || '')
      if (action.followup_day === -1 && d.meeting_note) setMeetingNote(d.meeting_note)
      if (action.followup_day === 3) {
        setSuggestingElement(true)
        api.suggestBumpElement(action.payload_id)
          .then(r => { if (r.suggestion) setNewElement(r.suggestion) })
          .catch(() => {})
          .finally(() => setSuggestingElement(false))
      }
    } catch (e) { setError(e.message) }
    finally { setDrafting(false) }
  }

  const handleRefine = async () => {
    if (!subject && !body) return
    setDrafting(true)
    setError(null)
    try {
      const d = await api.refineDraft(action.payload_id, subject, body, language)
      setSubject(d.subject || subject)
      setBody(d.body || body)
    } catch (e) { setError(e.message) }
    finally { setDrafting(false) }
  }

  const handleOpenGmail = async () => {
    setSending(true)
    try {
      const result = await api.buildMailto(action.payload_id, { subject, body, followup_day: action.followup_day })
      const url = result.mailto_url
      setMailtoUrl(url)
      if (!result.to_email) { setError('No email address on file. Add one in the company card first.'); setSending(false); return }
      if (result.email_is_guessed) setError(`Sending to guessed email: ${result.to_email} — verify before sending.`)
      if (url) window.open(url, '_blank')
      setAwaitingConfirm(true)
    } catch (e) { setError(e.message) }
    finally { setSending(false) }
  }

  const handleConfirmSent = async () => {
    setSending(true)
    setError(null)
    try {
      const payload = { followup_day: action.followup_day }
      if (action.followup_day === 0 && meetingNote.trim()) payload.meeting_note = meetingNote.trim()
      await api.markFollowupSent(action.payload_id, payload)
      setDone(true)
      onSent && onSent(action.payload_id, action.followup_day)
    } catch (e) { setError(e.message) }
    finally { setSending(false) }
  }

  const handleReschedule = async () => {
    if (!rescheduleDate) return
    setSending(true)
    try {
      const patch = action.followup_day === 3 ? { follow_up_3_due: rescheduleDate } : { follow_up_7_due: rescheduleDate }
      await api.patchOutreach(action.payload_id, patch)
      onRefresh && onRefresh()
    } catch (e) { setError(e.message) }
    finally { setSending(false) }
  }

  const handleCloseOut = async () => {
    setClosing(true)
    try {
      await api.updateOutreachResponse(action.payload_id, 'negative')
      onRefresh && onRefresh()
    } catch (e) { setError(e.message) }
    finally { setClosing(false) }
  }

  const handleKeepwarm = async () => {
    if (!keepwarmDate) return
    setSending(true)
    try {
      await api.patchOutreach(action.payload_id, { follow_up_7_sent: false, follow_up_7_due: keepwarmDate })
      setKeepwarmDone(true)
    } catch (e) { setError(e.message) }
    finally { setSending(false) }
  }

  const hasDraft = subject || body

  return (
    <div className={`rounded-xl border ${cardColor} p-4 flex flex-col gap-3`} onClick={e => e.stopPropagation()}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 flex-1 min-w-0">
          <ActionIcon size={15} className={`mt-0.5 flex-shrink-0 ${iconColor}`} />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-body leading-snug">{title} — {action.contact_name || action.label}</div>
            {(action.contact_title || action.company_name) && (
              <div className="text-xs text-muted mt-0.5">
                {[action.contact_title, action.company_name].filter(Boolean).join(' · ')}
              </div>
            )}
            {action.detail && <div className="text-xs text-muted mt-0.5">{action.detail}</div>}
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <div className="flex rounded-lg border border-theme overflow-hidden text-xs font-medium">
            <button onClick={() => setLanguage('en')} className={`px-1.5 py-0.5 transition-colors ${language === 'en' ? 'bg-blue-500 text-white' : 'text-muted'}`}>EN</button>
            <button onClick={() => setLanguage('es')} className={`px-1.5 py-0.5 transition-colors ${language === 'es' ? 'bg-blue-500 text-white' : 'text-muted'}`}>ES</button>
          </div>
          {onDismiss && (
            <button onClick={() => onDismiss(action)} className="p-1 text-muted hover:text-body"><X size={14} /></button>
          )}
        </div>
      </div>

      {/* Last message — shown immediately from payload, full conversation after draft loads */}
      {(conversation || action.last_message) && (
        <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-200 dark:border-slate-700 p-3">
          <div className="text-xs font-semibold text-muted mb-1">📧 {conversation ? 'Previous Conversation' : 'Last message sent'}</div>
          <pre className="text-xs text-muted whitespace-pre-wrap break-words max-h-32 overflow-y-auto font-mono leading-relaxed">{conversation || action.last_message}</pre>
        </div>
      )}

      {done ? (
        /* Done state */
        <div className="flex flex-col items-center py-3 gap-2 text-green-600 dark:text-green-400">
          <div className="text-2xl">✓</div>
          <div className="text-sm font-medium">Sent!</div>
          {action.followup_day === 0 ? (
            keepwarmDone ? (
              <div className="text-xs text-muted text-center">All set. See you then.</div>
            ) : postMeetingChoice === 'd3' ? (
              <div className="text-xs text-muted text-center">D+3 follow-up scheduled.</div>
            ) : postMeetingChoice === 'champion' ? (
              championDate ? (
                <div className="w-full flex flex-col gap-2" onClick={e => e.stopPropagation()}>
                  <textarea rows={2} placeholder="How do you know them / what happened?" value={championNotes} onChange={e => setChampionNotes(e.target.value)} className="w-full text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body placeholder:text-muted resize-none" />
                  <div className="flex gap-2">
                    <input type="date" value={championDate} onChange={e => setChampionDate(e.target.value)} className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body" />
                    <button disabled={!championDate || sending} onClick={async e => { e.stopPropagation(); setSending(true); try { await api.updateContact(action.contact_id, { is_champion: true, champion_notes: championNotes.trim() || null, next_checkin_date: championDate }); setKeepwarmDone(true); } catch(err) { setError(err.message); } finally { setSending(false); } }} className="text-xs px-3 py-2 rounded-lg bg-amber-500 text-white font-medium disabled:opacity-40">{sending ? 'Saving…' : 'Confirm'}</button>
                    <button onClick={e => { e.stopPropagation(); setPostMeetingChoice(null) }} className="text-xs px-3 py-2 rounded-lg border border-theme text-muted">Cancel</button>
                  </div>
                </div>
              ) : (
                <div className="w-full flex gap-2" onClick={e => e.stopPropagation()}>
                  <input type="date" value={championDate} onChange={e => setChampionDate(e.target.value)} className="flex-1 text-xs rounded-lg border border-amber-400 bg-transparent px-3 py-2 text-body" />
                  <button onClick={e => { e.stopPropagation(); setPostMeetingChoice(null) }} className="text-xs px-3 py-2 rounded-lg border border-theme text-muted">Cancel</button>
                </div>
              )
            ) : postMeetingChoice === 'remind' ? (
              <div className="w-full flex flex-col gap-2">
                <input type="date" value={keepwarmDate} onChange={e => setKeepwarmDate(e.target.value)} className="w-full text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body" />
                <div className="flex gap-2">
                  <button onClick={() => setPostMeetingChoice(null)} className="flex-1 border border-theme text-body rounded-xl py-2 text-xs font-medium">Back</button>
                  <button onClick={handleKeepwarm} disabled={sending || !keepwarmDate} className="flex-1 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-2 text-xs font-semibold">{sending ? 'Saving…' : 'Set reminder'}</button>
                </div>
              </div>
            ) : (
              <div className="w-full flex flex-col gap-2">
                <button onClick={async e => { e.stopPropagation(); setSending(true); try { const d = new Date(); d.setDate(d.getDate() + 3); await api.patchOutreach(action.payload_id, { post_meeting_2_due: d.toISOString().slice(0,10) }); setPostMeetingChoice('d3'); } catch(err) { setError(err.message); } finally { setSending(false); } }} disabled={sending} className="w-full border border-theme text-body rounded-xl py-2 text-xs font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40">Schedule D+3 follow-up</button>
                <button onClick={e => { e.stopPropagation(); setPostMeetingChoice('champion'); }} className="w-full border border-amber-300 text-amber-600 dark:text-amber-400 rounded-xl py-2 text-xs font-medium hover:bg-amber-50">They were a great lead — mark as champion</button>
                <button onClick={e => { e.stopPropagation(); setPostMeetingChoice('remind'); }} className="w-full text-xs text-muted hover:underline py-1">Remind me later</button>
              </div>
            )
          ) : (
            keepwarmDone ? (
              <div className="text-xs text-muted text-center">Reminder set.</div>
            ) : keepwarm ? (
              <div className="w-full flex flex-col gap-2">
                <input type="date" value={keepwarmDate} onChange={e => setKeepwarmDate(e.target.value)} className="w-full text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body" />
                <div className="flex gap-2">
                  <button onClick={() => setKeepwarm(false)} className="flex-1 border border-theme text-body rounded-xl py-2 text-xs font-medium">Skip</button>
                  <button onClick={handleKeepwarm} disabled={sending || !keepwarmDate} className="flex-1 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-2 text-xs font-semibold">{sending ? 'Saving…' : 'Set reminder'}</button>
                </div>
              </div>
            ) : (
              <button onClick={() => setKeepwarm(true)} className="text-xs text-blue-500 hover:underline">Schedule a keepwarm reminder?</button>
            )
          )}
          {action.followup_day === 7 && action.linkedin_accepted && !personalEmailDone && (
            <div className="w-full mt-1" onClick={e => e.stopPropagation()}>
              <div className="text-xs text-muted mb-1 text-center">Connected on LinkedIn — check their profile for a personal email before closing out.</div>
              <div className="flex gap-2">
                <input type="email" placeholder="personal@email.com" value={personalEmail} onChange={e => setPersonalEmail(e.target.value)} className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body" />
                <button disabled={!personalEmail.trim() || personalEmailSaving} onClick={async e => { e.stopPropagation(); setPersonalEmailSaving(true); try { if (action.contact_id) await api.updateContact(action.contact_id, { email: personalEmail.trim(), email_guessed: false }); setPersonalEmailDone(true); } catch (err) { console.error(err) } finally { setPersonalEmailSaving(false) } }} className="text-xs px-3 py-2 rounded-lg bg-blue-500 text-white font-medium disabled:opacity-40">{personalEmailSaving ? 'Saving…' : 'Save'}</button>
              </div>
            </div>
          )}
          {action.followup_day === 7 && action.linkedin_accepted && personalEmailDone && (
            <div className="text-xs text-muted text-center">Personal email saved. Fresh outreach cadence will start automatically.</div>
          )}
        </div>
      ) : (
        <>
          {/* MSG-5: meeting note gate */}
          {action.followup_day === 0 && !meetingNoteSubmitted ? (
            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium text-body">Meeting notes <span className="text-orange-500">*</span></label>
              <p className="text-xs text-muted">What did you discuss? The AI will anchor the thank-you on a specific thing they raised.</p>
              <textarea value={meetingNote} onChange={e => setMeetingNote(e.target.value)} rows={3} placeholder="e.g. They raised the challenge of onboarding fintech partners quickly..." className={`w-full rounded-lg px-3 py-2 text-sm bg-card text-body resize-none placeholder-faint focus:outline-none focus:ring-1 border ${meetingNote.trim() ? 'border-theme focus:ring-blue-500' : 'border-orange-400 focus:ring-orange-500'}`} />
              <button disabled={!meetingNote.trim() || drafting} onClick={async () => { setDrafting(true); setError(null); try { const d = await api.draftFollowup(action.payload_id, 0, language, meetingNote.trim()); setSubject(d.subject || ''); setBody(d.body || ''); setConversation(d.conversation_text || ''); setMeetingNoteSubmitted(true); } catch (e) { setError(e.message) } finally { setDrafting(false) } }} className="w-full bg-blue-500 hover:bg-blue-600 disabled:opacity-40 text-white rounded-xl py-2.5 text-sm font-semibold">{drafting ? 'Drafting…' : 'Draft thank-you'}</button>
            </div>
          ) : !hasDraft ? (
            /* No draft yet — show Draft button */
            <button
              onClick={handleDraft}
              disabled={drafting}
              className="w-full bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-2.5 text-sm font-semibold"
            >
              {drafting ? 'Drafting…' : 'Draft →'}
            </button>
          ) : (
            /* Draft loaded — show editable fields */
            <>
              {/* MSG-6: editable meeting note */}
              {action.followup_day === -1 && (
                <div>
                  <label className="text-xs text-muted mb-1 block">Meeting notes {meetingNote ? <span className="text-green-500">(pre-filled)</span> : <span className="text-orange-400">(not found — add to improve draft)</span>}</label>
                  <textarea value={meetingNote} onChange={e => setMeetingNote(e.target.value)} rows={2} placeholder="What did you discuss?" className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body resize-none" />
                </div>
              )}
              {action.followup_day === 3 && (
                <div>
                  <label className="text-xs text-muted mb-1 block">New element {suggestingElement && <span className="ml-1 text-blue-400">suggesting…</span>}</label>
                  <textarea value={newElement} onChange={e => setNewElement(e.target.value)} rows={2} placeholder="A question that occurred to you, a data point, or a reframe…" className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body resize-none" />
                </div>
              )}
              <div>
                <label className="text-xs text-muted mb-1 block">Subject</label>
                <input value={subject} onChange={e => setSubject(e.target.value)} className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body" placeholder="Subject" />
              </div>
              <div>
                <label className="text-xs text-muted mb-1 block">Body</label>
                <textarea value={body} onChange={e => setBody(e.target.value)} rows={4} className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body resize-none" />
              </div>
              {error && <div className="text-xs text-red-500 bg-red-50 dark:bg-red-950/40 rounded-lg p-2">{error}</div>}
              {!awaitingConfirm ? (
                <div className="flex gap-2">
                  <button onClick={handleRefine} disabled={drafting || (!subject && !body)} className="text-xs px-3 py-2 rounded-lg border border-theme text-muted hover:text-body disabled:opacity-40">{drafting ? 'Refining…' : 'Refine ↺'}</button>
                  <button onClick={handleOpenGmail} disabled={sending || !subject || !body} className="flex-1 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-2.5 text-sm font-semibold">{sending ? 'Opening Gmail…' : 'Send via Gmail →'}</button>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <div className="text-xs font-medium text-body text-center">Did you send the email?</div>
                  <div className="flex gap-2">
                    <button onClick={() => { setAwaitingConfirm(false); setMailtoUrl(null) }} className="flex-1 border border-theme text-body rounded-xl py-2.5 text-sm font-medium">No, go back</button>
                    <button onClick={handleConfirmSent} disabled={sending} className="flex-1 bg-green-500 hover:bg-green-600 disabled:opacity-50 text-white rounded-xl py-2.5 text-sm font-semibold">{sending ? 'Saving…' : 'Yes, sent ✓'}</button>
                  </div>
                  {mailtoUrl && <button onClick={() => window.open(mailtoUrl, '_blank')} className="text-xs text-blue-500 text-center">Re-open Gmail draft</button>}
                </div>
              )}
            </>
          )}

          {/* Footer actions */}
          <div className="pt-2 border-t border-theme flex flex-col gap-1.5">
            {!rescheduling ? (
              <div className="flex items-center gap-3 flex-wrap">
                <button onClick={handleConfirmSent} disabled={sending} className="text-xs text-muted hover:text-body">Already sent? Mark done</button>
                <span className="text-xs text-muted/40">·</span>
                <button onClick={() => setRescheduling(true)} className="text-xs text-muted hover:text-body">Reschedule</button>
                <span className="text-xs text-muted/40">·</span>
                <button onClick={handleCloseOut} disabled={closing} className="text-xs text-red-400 hover:text-red-500 disabled:opacity-40">{closing ? 'Closing…' : 'Close out'}</button>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <div className="text-xs text-body font-medium">Set new follow-up date</div>
                <div className="flex gap-2">
                  <input type="date" value={rescheduleDate} onChange={e => setRescheduleDate(e.target.value)} className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body" />
                  <button onClick={handleReschedule} disabled={sending || !rescheduleDate} className="text-xs px-3 py-2 rounded-lg bg-blue-500 text-white font-medium disabled:opacity-40">{sending ? 'Saving…' : 'Save'}</button>
                  <button onClick={() => setRescheduling(false)} className="text-xs px-3 py-2 rounded-lg border border-theme text-muted">Cancel</button>
                </div>
              </div>
            )}
            {/* We met */}
            {action.contact_id && !rescheduling && (
              <button onClick={() => onSent && onSent({ ...action, followup_day: 0 })} className="text-xs text-green-600 dark:text-green-400 hover:underline text-left">We met — draft post-meeting email instead →</button>
            )}
            {/* Champion toggle */}
            {action.contact_id && !action.is_champion && !rescheduling && onRefresh && (
              <WarmPathChampionToggle action={action} contactId={action.contact_id} onRefresh={onRefresh} />
            )}
          </div>
        </>
      )}
    </div>
  )
}

function NewReplyCard({ action, onDismiss, onRefresh, onMetDraft }) {
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [drafting, setDrafting] = useState(false)
  const [sending, setSending] = useState(false)
  const [awaitingConfirm, setAwaitingConfirm] = useState(false)
  const [mailtoUrl, setMailtoUrl] = useState(null)
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)

  const handleDraft = async () => {
    setDrafting(true)
    setError(null)
    try {
      const subjectLine = `Re: ${action.label.replace('Reply received — ', '')}`
      setSubject(subjectLine)
      setBody('')
    } catch (e) { setError(e.message) }
    finally { setDrafting(false) }
  }

  const handleOpenGmail = async () => {
    setSending(true)
    try {
      const subjectEnc = encodeURIComponent(subject)
      const bodyEnc = encodeURIComponent(body)
      const url = `https://mail.google.com/mail/?view=cm&su=${subjectEnc}&body=${bodyEnc}`
      setMailtoUrl(url)
      window.open(url, '_blank')
      setAwaitingConfirm(true)
    } catch (e) { setError(e.message) }
    finally { setSending(false) }
  }

  const hasDraft = subject || body

  return (
    <div className="p-4 rounded-xl border border-green-400 bg-green-50 dark:border-green-600 dark:bg-green-950/50 space-y-2">
      <div className="flex items-start gap-3">
        <MessageSquare size={16} className="mt-0.5 flex-shrink-0 text-green-600" />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-body text-sm">{action.label}</div>
          {(action.contact_title || action.company_name) && (
            <div className="text-xs text-muted mt-0.5">{[action.contact_title, action.company_name].filter(Boolean).join(' · ')}</div>
          )}
          {action.detail && (
            <div className="text-xs text-muted mt-0.5 leading-relaxed italic">{action.detail}</div>
          )}
        </div>
        {onDismiss && (
          <button onClick={() => onDismiss(action)} className="flex-shrink-0 p-1 text-muted hover:text-body">
            <X size={14} />
          </button>
        )}
      </div>
      {error && <div className="text-xs text-red-500">{error}</div>}
      {done ? (
        <div className="text-xs text-green-600 font-medium text-center">Response drafted ✓</div>
      ) : !hasDraft ? (
        <button onClick={handleDraft} disabled={drafting} className="w-full bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-lg py-2 text-xs font-semibold">
          {drafting ? 'Drafting…' : 'Draft response →'}
        </button>
      ) : !awaitingConfirm ? (
        <div className="space-y-2">
          <input value={subject} onChange={e => setSubject(e.target.value)} className="w-full border border-theme rounded-lg px-3 py-2 text-xs bg-card text-body" placeholder="Subject" />
          <textarea value={body} onChange={e => setBody(e.target.value)} rows={3} className="w-full border border-theme rounded-lg px-3 py-2 text-xs bg-card text-body resize-none" placeholder="Your reply…" />
          <div className="flex gap-2">
            <button onClick={handleDraft} disabled={drafting} className="text-xs px-3 py-2 border border-theme rounded-lg text-muted">Refine ↺</button>
            <button onClick={handleOpenGmail} disabled={sending} className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-lg py-2 text-xs font-semibold">{sending ? 'Opening…' : 'Send via Gmail →'}</button>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="text-xs text-muted text-center">Did you send the reply?</div>
          <div className="flex gap-2">
            <button onClick={() => { setAwaitingConfirm(false); setMailtoUrl(null) }} className="flex-1 border border-theme text-body rounded-lg py-2 text-xs">No, go back</button>
            <button onClick={() => setDone(true)} className="flex-1 bg-green-500 text-white rounded-lg py-2 text-xs font-semibold">Yes, sent ✓</button>
          </div>
          {mailtoUrl && <button onClick={() => window.open(mailtoUrl, '_blank')} className="w-full text-xs text-blue-500 text-center">Re-open Gmail draft</button>}
        </div>
      )}
      {onMetDraft && !done && (
        <button onClick={onMetDraft} className="text-xs text-green-700 dark:text-green-400 hover:underline text-left w-full">We met — draft post-meeting email instead →</button>
      )}
    </div>
  )
}

function LinkedInAcceptedSyncCard({ action, onDismiss, onRefresh }) {
  const [dm, setDm] = useState('')
  const [busy, setBusy] = useState(true)
  const [state, setState] = useState('loading') // loading | draft | copied | done
  const [error, setError] = useState(null)
  const [refining, setRefining] = useState(false)
  const [refineCopied, setRefineCopied] = useState(false)

  useEffect(() => {
    if (!action.payload_id) { setBusy(false); setState('draft'); return }
    api.draftTemplate(action.payload_id, 'linkedin_dm', action.contact_id)
      .then(res => {
        setDm(res.body || '')
        setState('draft')
      })
      .catch(e => {
        setError(e.message || 'Failed to draft DM')
        setState('draft')
      })
      .finally(() => setBusy(false))
  }, [action.payload_id, action.contact_id])

  const handleCopy = () => {
    const fallback = () => { const ta = document.createElement('textarea'); ta.value = dm; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta) }
    navigator.clipboard.writeText(dm).catch(fallback)
    // Open LinkedIn profile if URL available
    if (action.linkedin_url) {
      const slug = action.linkedin_url.replace(/\/$/, '').split('/').pop()
      window.open(`https://www.linkedin.com/in/${slug}`, '_blank')
    }
    setState('copied')
  }

  const handleConfirmSent = async () => {
    setBusy(true)
    try {
      await api.skipOutreach(action.payload_id)
      setState('done')
      setTimeout(() => onRefresh && onRefresh(), 800)
    } catch (e) {
      setError(e.message || 'Error confirming')
    } finally {
      setBusy(false)
    }
  }

  const handleRefine = async () => {
    setRefining(true)
    try {
      const ctx = await api.getConversationContext(action.payload_id, { subject: '', body: dm, stage: 'linkedin_dm' })
      const prompt = [
        '## Prior outreach message',
        ctx.conversation_history?.[0]?.body_preview || '(none)',
        '',
        '## My current DM draft',
        dm,
        '',
        '## Instructions',
        ctx.generation_instructions,
      ].join('\n')
      const fallback = () => { const ta = document.createElement('textarea'); ta.value = prompt; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta) }
      navigator.clipboard.writeText(prompt).catch(fallback)
      setRefineCopied(true)
      setTimeout(() => setRefineCopied(false), 2000)
    } catch (e) {
      console.error('refine error', e)
    } finally {
      setRefining(false)
    }
  }

  return (
    <div className="p-4 rounded-xl border border-sky-300 bg-sky-50 dark:border-sky-700 dark:bg-sky-950/40 space-y-3">
      <div className="flex items-start gap-3">
        <UserPlus size={16} className="mt-0.5 flex-shrink-0 text-sky-500" />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-body text-sm">{action.label}</div>
          {(action.contact_title || action.company_name) && (
            <div className="text-xs text-muted mt-0.5">{[action.contact_title, action.company_name].filter(Boolean).join(' · ')}</div>
          )}
          <div className="text-xs text-muted mt-0.5">{action.detail}</div>
        </div>
        {onDismiss && (
          <button onClick={() => onDismiss(action)} className="flex-shrink-0 p-1 text-muted hover:text-body">
            <X size={14} />
          </button>
        )}
      </div>

      {error && <div className="text-xs text-red-500">{error}</div>}

      {state === 'loading' && (
        <div className="text-xs text-muted">Drafting outreach DM...</div>
      )}

      {(state === 'draft' || state === 'copied') && (
        <div className="space-y-2">
          <textarea
            value={dm}
            onChange={e => setDm(e.target.value)}
            rows={5}
            className="w-full border border-theme rounded-lg px-3 py-2 text-xs bg-card text-body resize-none"
          />
          {state === 'draft' && (
            <div className="flex gap-2">
              <button
                onClick={handleCopy}
                className="flex-1 bg-sky-500 hover:bg-sky-600 text-white rounded-lg py-2 text-xs font-semibold"
              >
                {action.linkedin_url ? 'Open LinkedIn + Copy →' : 'Copy to clipboard →'}
              </button>
              <button
                onClick={handleRefine}
                disabled={refining}
                className="text-xs px-3 py-2 border border-purple-300 text-purple-600 dark:text-purple-400 rounded-lg hover:bg-purple-50 dark:hover:bg-purple-950/40 disabled:opacity-40"
              >
                {refining ? '...' : refineCopied ? 'Copied!' : '✨ Refine with AI'}
              </button>
            </div>
          )}
          {state === 'copied' && (
            <div className="space-y-2">
              <div className="text-xs text-muted">
                {action.linkedin_url ? 'LinkedIn opened + text copied. Paste the message and send it.' : 'Copied to clipboard. Paste into LinkedIn and send.'}
                {' '}Did you send it?
              </div>
              <div className="flex gap-2">
                <button onClick={handleCopy} className="text-xs text-sky-500 hover:underline">Re-copy text</button>
                <span className="text-xs text-muted/40">·</span>
                <button onClick={() => setState('draft')} className="text-xs text-muted hover:text-body">Edit draft</button>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setState('draft')} className="flex-1 border border-theme text-body rounded-lg py-2 text-xs font-medium">
                  No, go back
                </button>
                <button onClick={handleConfirmSent} disabled={busy} className="flex-1 bg-green-500 text-white rounded-lg py-2 text-xs font-semibold disabled:opacity-50">
                  {busy ? '...' : 'Yes, sent ✓'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {state === 'done' && (
        <div className="text-xs text-green-600 font-medium">DM sent and logged. Thread closed.</div>
      )}

      {state !== 'done' && (
        <EscalationControls action={action} onRefresh={onRefresh} />
      )}
      {action.contact_id && state !== 'done' && (
        <button
          onClick={() => onRefresh && onRefresh({ ...action, followup_day: 0 })}
          className="text-xs text-green-600 dark:text-green-400 hover:underline text-left w-full mt-1"
        >
          We met — draft post-meeting email instead →
        </button>
      )}
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
      await api.patchOutreach(action.payload_id, { linkedin_accepted: null, follow_up_3_sent: true })
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
    const mailto = `https://mail.google.com/mail/?view=cm&to=${encodeURIComponent(nextStep.guessed_email)}&su=${encodeURIComponent('Following up — ' + (action.contact_name || ''))}`
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
            <div className="text-xs text-muted">All email patterns tried. Check their LinkedIn profile — 1st-degree connections often share their email there.</div>
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

function EmailBounceRetryCard({ action, onRefresh }) {
  const [state, setState] = useState('loading') // loading | draft | sent | exhausted
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [guessedEmail, setGuessedEmail] = useState(action.guessed_email || null)
  const [contactTitle, setContactTitle] = useState('')
  const [intel, setIntel] = useState('')
  const [busy, setBusy] = useState(false)
  const [refineCopied, setRefineCopied] = useState(false)
  const [draftKey, setDraftKey] = useState(0)

  useEffect(() => {
    api.draftBounceRetry(action.payload_id)
      .then(res => {
        if (res.guessed_email) setGuessedEmail(res.guessed_email)
        if (res.contact_title) setContactTitle(res.contact_title)
        if (res.intel) setIntel(res.intel)
        setSubject(res.subject || '')
        setBody(res.body || '')
        setState(res.guessed_email || guessedEmail ? 'draft' : 'exhausted')
      })
      .catch(() => {
        setState(guessedEmail ? 'draft' : 'exhausted')
      })
  }, [draftKey])

  const handleSendViaGmail = () => {
    window.open(
      `https://mail.google.com/mail/?view=cm&to=${encodeURIComponent(guessedEmail || '')}&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`,
      '_blank'
    )
    setState('sent')
  }

  const handleBounced = async () => {
    setBusy(true)
    try {
      const res = await api.markEmailBounced(action.payload_id)
      const ns = res.next_step
      if (ns?.action === 'draft_email_guessed' && ns.guessed_email) {
        setGuessedEmail(ns.guessed_email)
        setState('loading')
        setDraftKey(k => k + 1)
      } else {
        setState('exhausted')
      }
    } catch (_) {}
    setBusy(false)
  }

  const handleConfirmSent = async () => {
    try {
      await api.confirmBounceRetrySent(action.payload_id, {
        guessed_email: guessedEmail,
        subject,
        body,
      })
    } catch (_) {}
    onRefresh()
  }

  const handleRefine = () => {
    const lines = [
      '## Who I am reaching out to',
      `${action.contact_name || 'this contact'}${contactTitle ? `, ${contactTitle}` : ''} at ${action.company_name || 'their company'}.`,
      'A previous email bounced. This is a retry with a different email address pattern.',
      '',
    ]
    if (intel) { lines.push('## Company context', intel, '') }
    if (news) { lines.push('## Recent news', news, '') }
    lines.push(
      '## My current draft',
      `Subject: ${subject}`,
      body,
      '',
      "## Santiago's background",
      'MIT Sloan MBA. 20+ years in FinTech, payments, digital identity, LATAM markets. Currently Chief Product Solutions Officer at SMCU (largest SBA credit union lender in Massachusetts). Seeking C-suite or SVP roles in payments infrastructure, BaaS, embedded banking, agentic AI.',
      '',
      '## Instructions',
      "Rewrite the email. Be specific to this person's role and company context above. Lead with something they genuinely care about. End with a soft, specific ask. 3 to 4 sentences max. No em dashes, no hyphens.",
    )
    const prompt = lines.join('\n')
    const fallback = () => { const ta = document.createElement('textarea'); ta.value = prompt; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta) }
    navigator.clipboard.writeText(prompt).catch(fallback)
    setRefineCopied(true)
    setTimeout(() => setRefineCopied(false), 2000)
  }

  return (
    <div className="p-4 rounded-xl border border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-950/40 space-y-3">
      <div className="flex items-start gap-3">
        <AlertCircle size={16} className="mt-0.5 flex-shrink-0 text-orange-500" />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-body text-sm">{action.label}</div>
          {action.detail && <div className="text-xs text-muted mt-0.5">{action.detail}</div>}
        </div>
      </div>

      {state === 'loading' && (
        <div className="text-xs text-muted">Preparing draft...</div>
      )}

      {state === 'draft' && (
        <div className="space-y-2">
          {guessedEmail && (
            <div className="text-xs text-muted">
              To: <span className="font-mono text-body">{guessedEmail}</span>{' '}
              <span className="text-orange-500">(unverified)</span>
            </div>
          )}
          <input
            value={subject}
            onChange={e => setSubject(e.target.value)}
            className="w-full text-xs border border-theme rounded-lg px-3 py-2 bg-card text-body"
            placeholder="Subject"
          />
          <textarea
            value={body}
            onChange={e => setBody(e.target.value)}
            rows={5}
            className="w-full text-xs border border-theme rounded-lg px-3 py-2 bg-card text-body resize-none"
          />
          <div className="flex gap-2">
            <button
              onClick={handleSendViaGmail}
              className="flex-1 bg-orange-500 hover:bg-orange-600 text-white rounded-lg py-2 text-xs font-semibold"
            >
              Send via Gmail →
            </button>
            <button
              onClick={handleRefine}
              className="text-xs px-3 py-2 border border-purple-300 text-purple-600 dark:text-purple-400 rounded-lg hover:bg-purple-50 dark:hover:bg-purple-950/40 disabled:opacity-40"
            >
              {refineCopied ? 'Copied!' : '✨ Refine with AI'}
            </button>
          </div>
        </div>
      )}

      {state === 'sent' && (
        <div className="space-y-2">
          <div className="text-xs text-muted">
            Gmail opened with <span className="font-mono">{guessedEmail}</span>. Did you send it?
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleBounced}
              disabled={busy}
              className="flex-1 border border-red-300 text-red-600 rounded-lg py-2 text-xs font-medium disabled:opacity-50"
            >
              {busy ? '...' : 'Email bounced — try next'}
            </button>
            <button
              onClick={handleConfirmSent}
              className="flex-1 bg-green-500 text-white rounded-lg py-2 text-xs font-semibold"
            >
              Sent ✓
            </button>
          </div>
        </div>
      )}

      {state === 'exhausted' && (
        <div className="text-xs text-muted">All email patterns tried. Reach out via LinkedIn instead.</div>
      )}
    </div>
  )
}

function LinkedInNotAcceptedCard({ action, onRefresh }) {
  const [state, setState] = useState('loading') // loading | draft | sent | exhausted | done
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [intel, setIntel] = useState('')
  const [guessedEmail, setGuessedEmail] = useState(action.next_step?.guessed_email || null)
  const [busy, setBusy] = useState(false)
  const [refineCopied, setRefineCopied] = useState(false)

  useEffect(() => {
    api.draftTemplate(action.payload_id, 'escalation', action.contact_id)
      .then(res => {
        setSubject(res.subject || '')
        setBody(res.body || '')
        if (res.intel) setIntel(res.intel)
        if (res.guessed_email) setGuessedEmail(res.guessed_email)
        setState(res.guessed_email ? 'draft' : 'exhausted')
      })
      .catch(e => {
        console.error('[LinkedInNotAcceptedCard] draftTemplate failed:', e)
        const name = action.contact_name ? action.contact_name.split(' ')[0] : 'there'
        const co = action.company_name || 'your company'
        setSubject(name !== 'there' ? `${name} - reaching out directly` : `Reaching out directly - ${co}`)
        setBody(`Hi ${name},\n\nI sent you a connection request on LinkedIn recently and thought reaching out directly might be easier. I would love to learn more about what you are building at ${co}.\n\nWorth a quick note back?`)
        setState('draft')
      })
  }, [])

  const handleSendViaGmail = () => {
    window.open(
      `https://mail.google.com/mail/?view=cm&to=${encodeURIComponent(guessedEmail || '')}&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`,
      '_blank'
    )
    setState('sent')
  }

  const handleConfirmSent = async () => {
    setBusy(true)
    try {
      await api.confirmEscalation(action.payload_id, {
        contact_id: action.contact_id,
        guessed_email: guessedEmail,
        subject,
        body,
      })
      setBusy(false)
      setState('done')
      setTimeout(onRefresh, 800)
    } catch (err) {
      setBusy(false)
      alert('Failed to confirm: ' + (err.message || 'unknown error'))
    }
  }

  const handleRefine = () => {
    const lines = [
      '## Who I am reaching out to',
      `${action.contact_name || 'this contact'}${action.contact_title ? `, ${action.contact_title}` : ''} at ${action.company_name || 'their company'}.`,
      'LinkedIn connection was not accepted. This is a direct email escalation.',
      '',
    ]
    if (intel) { lines.push('## Company context', intel, '') }
    lines.push(
      '## My current draft',
      `Subject: ${subject}`,
      body,
      '',
      "## Santiago's background",
      'MIT Sloan MBA. 20+ years in FinTech, payments, digital identity, LATAM markets. Currently Chief Product Solutions Officer at SMCU (largest SBA credit union lender in Massachusetts). Seeking C-suite or SVP roles in payments infrastructure, BaaS, embedded banking, agentic AI.',
      '',
      '## Instructions',
      "Rewrite the email. Be specific to this person's role and company context above. Lead with something they genuinely care about. End with a soft, specific ask. 3 to 4 sentences max. No em dashes, no hyphens.",
    )
    const prompt = lines.join('\n')
    const fallback = () => { const ta = document.createElement('textarea'); ta.value = prompt; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta) }
    navigator.clipboard.writeText(prompt).catch(fallback)
    setRefineCopied(true)
    setTimeout(() => setRefineCopied(false), 2000)
  }

  return (
    <div className="p-4 rounded-xl border border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-950/40 space-y-3">
      <div className="flex items-start gap-3">
        <UserPlus size={16} className="mt-0.5 flex-shrink-0 text-orange-500" />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-body text-sm">{action.label}</div>
          <div className="text-xs text-muted mt-0.5">
            {[action.contact_name, action.contact_title, action.company_name].filter(Boolean).join(' · ')}
          </div>
          <div className="text-xs text-muted mt-0.5">{action.detail}</div>
        </div>
      </div>

      <WarmPathIntel action={action} />

      {state === 'loading' && (
        <div className="text-xs text-muted">Preparing draft...</div>
      )}

      {state === 'draft' && (
        <div className="space-y-2">
          {guessedEmail && (
            <div className="text-xs text-muted">
              To: <span className="font-mono text-body">{guessedEmail}</span>{' '}
              <span className="text-orange-500">(unverified)</span>
            </div>
          )}
          <input
            value={subject}
            onChange={e => setSubject(e.target.value)}
            className="w-full text-xs border border-theme rounded-lg px-3 py-2 bg-card text-body"
            placeholder="Subject"
          />
          <textarea
            value={body}
            onChange={e => setBody(e.target.value)}
            rows={5}
            className="w-full text-xs border border-theme rounded-lg px-3 py-2 bg-card text-body resize-none"
          />
          <div className="flex gap-2">
            <button
              onClick={handleSendViaGmail}
              className="flex-1 bg-orange-500 hover:bg-orange-600 text-white rounded-lg py-2 text-xs font-semibold"
            >
              Send via Gmail →
            </button>
            <button
              onClick={handleRefine}
              className="text-xs px-3 py-2 border border-purple-300 text-purple-600 dark:text-purple-400 rounded-lg hover:bg-purple-50 dark:hover:bg-purple-950/40"
            >
              {refineCopied ? 'Copied!' : '✨ Refine with AI'}
            </button>
          </div>
        </div>
      )}

      {state === 'sent' && (
        <div className="space-y-2">
          <div className="text-xs text-muted">
            Gmail opened with <span className="font-mono">{guessedEmail}</span>. Did you send it?
          </div>
          <div className="text-xs text-muted">
            If it bounced, check Gmail tomorrow — the Brief will automatically suggest the next email pattern.
          </div>
          <div className="flex gap-2">
            <button onClick={() => setState('draft')} className="flex-1 border border-theme text-body rounded-lg py-2 text-xs font-medium">
              Back
            </button>
            <button onClick={handleConfirmSent} disabled={busy} className="flex-1 bg-green-500 text-white rounded-lg py-2 text-xs font-semibold disabled:opacity-50">
              {busy ? '...' : 'Yes, sent'}
            </button>
          </div>
        </div>
      )}

      {state === 'exhausted' && (
        <div className="text-xs text-muted">
          All email patterns tried. Add their email manually in the Contacts tab, or reach out via LinkedIn DM.
        </div>
      )}

      {state === 'done' && (
        <div className="text-xs text-green-600 font-medium">Email logged. Follow-up clock started.</div>
      )}

      {state !== 'done' && (
        <EscalationControls action={action} onRefresh={onRefresh} />
      )}
      {action.contact_id && state !== 'done' && (
        <button
          onClick={() => onRefresh && onRefresh({ ...action, followup_day: 0 })}
          className="text-xs text-green-600 dark:text-green-400 hover:underline text-left w-full mt-1"
        >
          We met — draft post-meeting email instead →
        </button>
      )}
    </div>
  )
}

function WarmPathIntel({ action }) {
  const [loading, setLoading] = useState(false)
  const [intel, setIntel] = useState(action.intel_summary || '')
  const [expanded, setExpanded] = useState(false)

  const generate = async (e) => {
    e.stopPropagation()
    if (!action.company_id) return
    setLoading(true)
    try {
      const res = await api.refreshIntel(action.company_id)
      setIntel(res.intel_summary || '')
    } catch (err) {
      console.error('intel error', err)
    } finally {
      setLoading(false)
    }
  }

  if (intel) {
    // Strip snapshot header and split into readable lines
    const cleaned = intel
      .replace(/^Intel snapshot as of \d{4}-\d{2}-\d{2}\s*/i, '')
      .replace(/\b(RECENT NEWS|CONTACTS|OUTREACH|FUNDING|NOTES):\s*/g, '\n$1: ')
      .replace(/\s*-\s+/g, '\n• ')
      .trim()
    const lines = cleaned.split('\n').filter(l => l.trim())

    return (
      <div className="mt-2">
        <div className={`text-xs text-muted leading-relaxed space-y-0.5 ${expanded ? '' : 'line-clamp-3'}`}>
          {lines.map((line, i) => (
            <div key={i} className={/^[A-Z ]+:/.test(line) ? 'font-semibold text-body mt-1' : ''}>
              {line}
            </div>
          ))}
        </div>
        <button
          onClick={e => { e.stopPropagation(); setExpanded(v => !v) }}
          className="flex items-center gap-1 mt-1 text-xs text-blue-500 hover:text-blue-400"
        >
          {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          {expanded ? 'Show less' : 'Show more'}
        </button>
      </div>
    )
  }

  return (
    <button
      onClick={generate}
      disabled={loading}
      className="mt-2 text-xs text-blue-500 hover:underline disabled:opacity-50"
    >
      {loading ? 'Generating intel…' : 'Generate company intel'}
    </button>
  )
}

function WarmPathSnooze({ action, onSnoozed }) {
  const [open, setOpen] = useState(false)
  const [date, setDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 7)
    return d.toISOString().slice(0, 10)
  })
  const [saving, setSaving] = useState(false)

  const confirm = async (e) => {
    e.stopPropagation()
    if (!date || !action.payload_id) return
    setSaving(true)
    try {
      await api.updateContact(action.payload_id, { snooze_until: date })
      onSnoozed()
    } catch (e) {
      console.error('snooze error', e)
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <div className="mt-3 pt-3 border-t border-theme">
        <button
          onClick={e => { e.stopPropagation(); setOpen(true) }}
          className="text-xs text-muted hover:text-body hover:underline"
        >
          Not ready? Set follow-up date →
        </button>
      </div>
    )
  }

  return (
    <div className="mt-3 pt-3 border-t border-theme flex items-center gap-2" onClick={e => e.stopPropagation()}>
      <input
        type="date"
        value={date}
        onChange={e => setDate(e.target.value)}
        className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      <button
        disabled={!date || saving}
        onClick={confirm}
        className="text-xs px-3 py-2 rounded-lg border border-theme text-muted hover:text-body disabled:opacity-40"
      >
        {saving ? 'Saving…' : 'Confirm'}
      </button>
      <button
        onClick={e => { e.stopPropagation(); setOpen(false) }}
        className="text-xs px-3 py-2 rounded-lg border border-theme text-muted hover:text-body"
      >
        Cancel
      </button>
    </div>
  )
}

function WarmPathChampionToggle({ action, onRefresh, contactId: contactIdProp }) {
  const contactId = contactIdProp ?? action.payload_id
  const [open, setOpen] = useState(false)
  const [notes, setNotes] = useState('')
  const [date, setDate] = useState('')
  const [saving, setSaving] = useState(false)

  const confirm = async (e) => {
    e.stopPropagation()
    if (!date || !contactId) return
    setSaving(true)
    try {
      await api.updateContact(contactId, {
        is_champion: true,
        champion_notes: notes.trim() || null,
        next_checkin_date: date,
      })
      onRefresh()
    } catch (err) {
      console.error('champion toggle error', err)
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <div className="mt-3 pt-3 border-t border-theme">
        <button
          onClick={e => { e.stopPropagation(); setOpen(true) }}
          className="text-xs text-amber-600 dark:text-amber-400 hover:underline"
        >
          Already a champion? Mark as such →
        </button>
      </div>
    )
  }

  return (
    <div className="mt-3 pt-3 border-t border-theme flex flex-col gap-2" onClick={e => e.stopPropagation()}>
      <textarea
        rows={2}
        placeholder="How do you know them / what happened?"
        value={notes}
        onChange={e => setNotes(e.target.value)}
        className="w-full text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body placeholder:text-muted resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      <div className="flex items-center gap-2">
        <input
          type="date"
          value={date}
          onChange={e => setDate(e.target.value)}
          className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <button
          disabled={!date || saving}
          onClick={confirm}
          className="text-xs px-3 py-2 rounded-lg bg-amber-500 text-white font-medium disabled:opacity-40 hover:bg-amber-600"
        >
          {saving ? 'Saving…' : 'Confirm'}
        </button>
        <button
          onClick={e => { e.stopPropagation(); setOpen(false) }}
          className="text-xs px-3 py-2 rounded-lg border border-theme text-muted hover:text-body"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

function PublishContentCard({ action, onRefresh }) {
  const [slot, setSlot] = useState(null)
  const [saving, setSaving] = useState(false)
  const [done, setDone] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getNextSlot()
      .then(({ scheduled_at, label }) => setSlot({ iso: scheduled_at, label }))
      .catch(() => {
        const d = new Date()
        d.setDate(d.getDate() + ((4 - d.getDay() + 7) % 7 || 7))
        d.setHours(16, 0, 0, 0)
        setSlot({ iso: d.toISOString(), label: d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) + ' 4pm' })
      })
  }, [])

  const handleSchedule = async (e) => {
    e.stopPropagation()
    if (!slot) return
    setSaving(true)
    setError(null)
    try {
      await api.schedulePost(action.payload_id, slot.iso)
      setDone('scheduled')
      setTimeout(() => onRefresh && onRefresh(), 1200)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handlePublishNow = async (e) => {
    e.stopPropagation()
    setSaving(true)
    setError(null)
    try {
      await api.publishNow(action.payload_id)
      setDone('published')
      setTimeout(() => onRefresh && onRefresh(), 1200)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (done) {
    return (
      <div className="mt-2 pt-2 border-t border-theme text-xs text-green-600 dark:text-green-400">
        {done === 'scheduled' ? `Scheduled for ${slot?.label} ✓` : 'Published ✓'}
      </div>
    )
  }

  return (
    <div className="mt-2 pt-2 border-t border-theme flex flex-col gap-2" onClick={e => e.stopPropagation()}>
      {error && <p className="text-xs text-red-500">{error}</p>}
      <div className="flex gap-2">
        <button
          disabled={!slot || saving}
          onClick={handleSchedule}
          className="flex-1 text-xs px-3 py-2 rounded-lg bg-blue-500 text-white font-medium disabled:opacity-40 hover:bg-blue-600"
        >
          {saving ? 'Scheduling…' : slot ? `Schedule for ${slot.label}` : 'Loading slot…'}
        </button>
        <button
          disabled={saving}
          onClick={handlePublishNow}
          className="text-xs px-3 py-2 rounded-lg border border-theme text-body hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40"
        >
          Post now
        </button>
      </div>
    </div>
  )
}


function ReferralPivotCard({ action }) {
  const [open, setOpen] = useState(false)
  const [replySummary, setReplySummary] = useState('')
  const [drafting, setDrafting] = useState(false)
  const [draft, setDraft] = useState(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState(null)

  const handleDraft = async (e) => {
    e.stopPropagation()
    if (!replySummary.trim()) return
    setDrafting(true)
    setError(null)
    try {
      const result = await api.draftReferralPivot(action.payload_id, { reply_summary: replySummary.trim() })
      setDraft(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setDrafting(false)
    }
  }

  if (!open) {
    return (
      <div className="mt-2 pt-2 border-t border-theme">
        <button
          onClick={e => { e.stopPropagation(); setOpen(true) }}
          className="text-xs text-blue-500 hover:underline"
        >
          Did they mention someone to connect you with? Draft referral ask →
        </button>
      </div>
    )
  }

  return (
    <div className="mt-2 pt-2 border-t border-theme flex flex-col gap-2" onClick={e => e.stopPropagation()}>
      <label className="text-xs font-medium text-body">What did they say they could do?</label>
      <textarea
        rows={2}
        placeholder="e.g. They mentioned their colleague at Sardine who runs partnerships…"
        value={replySummary}
        onChange={e => setReplySummary(e.target.value)}
        className="w-full text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body placeholder:text-muted resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      {error && <p className="text-xs text-red-500">{error}</p>}
      {draft ? (
        <div className="p-3 bg-blue-50 dark:bg-blue-950/30 rounded-lg border border-blue-200 dark:border-blue-800 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-blue-700 dark:text-blue-300">Referral pivot draft</span>
            <button
              onClick={() => {
                const text = `Subject: ${draft.subject}\n\n${draft.body}`
                navigator.clipboard?.writeText(text).catch(() => {})
                setCopied(true)
                setTimeout(() => setCopied(false), 2000)
              }}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >{copied ? 'Copied!' : 'Copy'}</button>
          </div>
          <div className="text-xs text-muted font-medium">{draft.subject}</div>
          <pre className="text-xs text-body whitespace-pre-wrap break-words leading-relaxed">{draft.body}</pre>
          <button onClick={handleDraft} disabled={drafting} className="text-xs text-blue-500 hover:underline disabled:opacity-40 text-left">
            Regenerate
          </button>
        </div>
      ) : (
        <button
          disabled={!replySummary.trim() || drafting}
          onClick={handleDraft}
          className="text-xs px-3 py-2 rounded-lg bg-blue-500 text-white font-medium disabled:opacity-40 hover:bg-blue-600"
        >
          {drafting ? 'Drafting…' : 'Draft referral ask'}
        </button>
      )}
      <button onClick={e => { e.stopPropagation(); setOpen(false) }} className="text-xs text-muted hover:underline text-left">
        Cancel
      </button>
    </div>
  )
}


function CallScriptCard({ action }) {
  const [open, setOpen] = useState(false)
  const first = (action.contact_name || 'them').split(' ')[0]
  const title = action.contact_title ? `, ${action.contact_title}` : ''
  const script = `Hi, may I speak with ${first}?\n\nHi ${first}, this is Santiago Aldana. I've been reaching out about a conversation on [agentic finance / payments / digital identity — pick one] — I think there's a genuine overlap with what you're building at ${action.contact_name?.split(' ').pop() || 'your company'}${title}.\n\nI'll keep it under two minutes: would you have 30 seconds to hear what I had in mind?`

  return (
    <div className="mt-3 pt-3 border-t border-theme" onClick={e => e.stopPropagation()}>
      <div className="flex items-center justify-between mb-2">
        <a
          href={`tel:${action.phone}`}
          className="text-xs px-3 py-2 rounded-lg bg-violet-500 text-white font-medium hover:bg-violet-600"
        >Call {action.phone} →</a>
        <button
          onClick={() => setOpen(v => !v)}
          className="text-xs text-muted hover:underline"
        >{open ? 'Hide script' : 'Show script'}</button>
      </div>
      {open && (
        <pre className="text-xs text-body whitespace-pre-wrap bg-violet-50 dark:bg-violet-950/20 border border-violet-200 dark:border-violet-800 rounded-lg p-3 leading-relaxed">{script}</pre>
      )}
    </div>
  )
}

function ChampionCheckinCard({ action, onRefresh }) {
  const pending = action.pending_outreach  // {id, subject, last_message, followup_day, days_overdue}

  // Draft state (shared between nudge and fresh check-in paths)
  const [language, setLanguage] = useState('en')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [drafting, setDrafting] = useState(false)
  const [sending, setSending] = useState(false)
  const [awaitingConfirm, setAwaitingConfirm] = useState(false)
  const [mailtoUrl, setMailtoUrl] = useState(null)
  const [draftError, setDraftError] = useState(null)
  const hasDraft = subject || body

  // Check-in state
  const [notes, setNotes] = useState('')
  const [date, setDate] = useState('')
  const [saving, setSaving] = useState(false)
  const [done, setDone] = useState(false)

  // Intro flow
  const [agreeIntro, setAgreeIntro] = useState(false)
  const [introTarget, setIntroTarget] = useState('')
  const [introCompany, setIntroCompany] = useState('')
  const [introCompanyType, setIntroCompanyType] = useState('')
  const [introDrafting, setIntroDrafting] = useState(false)
  const [introDraft, setIntroDraft] = useState(null)
  const [introCopied, setIntroCopied] = useState(false)

  // Close flow
  const [closingPrompt, setClosingPrompt] = useState(false)
  const [snoozeDate, setSnoozeDate] = useState('')

  const handleDraftNudge = async () => {
    if (!pending) return
    setDrafting(true)
    setDraftError(null)
    try {
      const d = await api.draftFollowup(pending.id, pending.followup_day, language)
      setSubject(d.subject || '')
      setBody(d.body || '')
    } catch (e) { setDraftError(e.message) }
    finally { setDrafting(false) }
  }

  const handleDraftFresh = async () => {
    setDrafting(true)
    setDraftError(null)
    try {
      const result = await api.draftChampionCheckin(action.payload_id, notes.trim())
      setSubject(result.subject || '')
      setBody(result.body || '')
    } catch (e) { setDraftError(e.message) }
    finally { setDrafting(false) }
  }

  const handleRefineChampion = async () => {
    if (!subject && !body) return
    setDrafting(true)
    setDraftError(null)
    try {
      const recordId = pending ? pending.id : action.payload_id
      const d = await api.refineDraft(recordId, subject, body, language)
      setSubject(d.subject || subject)
      setBody(d.body || body)
    } catch (e) { setDraftError(e.message) }
    finally { setDrafting(false) }
  }

  const handleOpenGmail = async () => {
    setSending(true)
    try {
      const to = encodeURIComponent(action.contact_email || '')
      const su = encodeURIComponent(subject)
      const bd = encodeURIComponent(body)
      const url = `https://mail.google.com/mail/?view=cm&to=${to}&su=${su}&body=${bd}`
      setMailtoUrl(url)
      window.open(url, '_blank')
      setAwaitingConfirm(true)
    } catch (e) { setDraftError(e.message) }
    finally { setSending(false) }
  }

  const handleConfirmSent = async () => {
    if (pending) {
      // Mark the pending follow-up as sent
      setSending(true)
      try {
        await api.markFollowupSent(pending.id, { followup_day: pending.followup_day })
      } catch (e) { console.error(e) }
      finally { setSending(false) }
    }
    setAwaitingConfirm(false)
    setMailtoUrl(null)
    setSubject('')
    setBody('')
  }

  const handleDraftIntro = async (e) => {
    e.stopPropagation()
    setIntroDrafting(true)
    try {
      const result = await api.draftChampionIntro(action.payload_id, {
        target_person_name: introTarget.trim(),
        target_company_name: introCompany.trim(),
        target_company_type: introCompanyType.trim(),
        champion_notes: notes.trim() || action.champion_notes || '',
      })
      setIntroDraft(result)
    } catch (err) { setDraftError(err.message) }
    finally { setIntroDrafting(false) }
  }

  const save = async (e) => {
    e.stopPropagation()
    if (!date || !action.payload_id) return
    setSaving(true)
    try {
      const newNotes = action.champion_notes
        ? `${action.champion_notes}\n\n${new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}: ${notes.trim()}`
        : notes.trim()
      await api.updateContact(action.payload_id, {
        champion_notes: newNotes || null,
        next_checkin_date: date,
      })
      setDone(true)
      setTimeout(() => onRefresh(), 1200)
    } catch (err) { console.error('checkin save error', err) }
    finally { setSaving(false) }
  }

  if (done) {
    return (
      <div className="mt-3 pt-3 border-t border-theme text-xs text-green-600 dark:text-green-400">
        Check-in logged. Next reminder set.
      </div>
    )
  }

  return (
    <div className="mt-3 pt-3 border-t border-theme flex flex-col gap-2" onClick={e => e.stopPropagation()}>

      {/* EN/ES toggle */}
      <div className="flex justify-end">
        <div className="flex rounded-lg border border-theme overflow-hidden text-xs font-medium">
          <button onClick={() => setLanguage('en')} className={`px-1.5 py-0.5 transition-colors ${language === 'en' ? 'bg-blue-500 text-white' : 'text-muted'}`}>EN</button>
          <button onClick={() => setLanguage('es')} className={`px-1.5 py-0.5 transition-colors ${language === 'es' ? 'bg-blue-500 text-white' : 'text-muted'}`}>ES</button>
        </div>
      </div>

      {/* Prior notes */}
      {action.champion_notes && (
        <div className="text-xs text-muted bg-slate-50 dark:bg-slate-800/50 rounded-lg px-3 py-2 leading-relaxed whitespace-pre-wrap max-h-24 overflow-y-auto">
          {action.champion_notes}
        </div>
      )}

      {/* PENDING THREAD MODE — champion has an overdue follow-up */}
      {pending && (
        <div className="bg-orange-50 dark:bg-orange-950/20 border border-orange-200 dark:border-orange-800 rounded-lg px-3 py-2 flex flex-col gap-1">
          <div className="text-xs font-semibold text-orange-700 dark:text-orange-300">
            Pending reply · {pending.days_overdue} day{pending.days_overdue !== 1 ? 's' : ''} overdue
          </div>
          {pending.subject && <div className="text-xs text-muted">{pending.subject}</div>}
          {pending.last_message && (
            <pre className="text-xs text-muted whitespace-pre-wrap break-words max-h-20 overflow-y-auto font-mono leading-relaxed mt-1">{pending.last_message}</pre>
          )}
        </div>
      )}

      {/* Notes textarea */}
      <textarea
        rows={2}
        placeholder={pending ? 'Optional context for the nudge…' : 'What happened? (optional — seeds the draft)'}
        value={notes}
        onChange={e => setNotes(e.target.value)}
        className="w-full text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body placeholder:text-muted resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
      />

      {/* Draft / send flow */}
      {draftError && <div className="text-xs text-red-500">{draftError}</div>}
      {!hasDraft ? (
        <button
          onClick={pending ? handleDraftNudge : handleDraftFresh}
          disabled={drafting}
          className="w-full bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-2.5 text-xs font-semibold"
        >
          {drafting ? 'Drafting…' : pending ? 'Draft nudge →' : 'Draft message →'}
        </button>
      ) : !awaitingConfirm ? (
        <div className="flex flex-col gap-2">
          <input value={subject} onChange={e => setSubject(e.target.value)} className="w-full border border-theme rounded-lg px-3 py-2 text-xs bg-card text-body" placeholder="Subject" />
          <textarea value={body} onChange={e => setBody(e.target.value)} rows={4} className="w-full border border-theme rounded-lg px-3 py-2 text-xs bg-card text-body resize-none" />
          <div className="flex gap-2">
            <button onClick={handleRefineChampion} disabled={drafting || (!subject && !body)} className="text-xs px-3 py-2 border border-theme rounded-lg text-muted disabled:opacity-40">{drafting ? 'Refining…' : 'Refine ↺'}</button>
            <button onClick={handleOpenGmail} disabled={sending} className="flex-1 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-2 text-xs font-semibold">{sending ? 'Opening…' : 'Send via Gmail →'}</button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="text-xs text-muted text-center">Did you send the message?</div>
          <div className="flex gap-2">
            <button onClick={() => { setAwaitingConfirm(false); setMailtoUrl(null) }} className="flex-1 border border-theme text-body rounded-lg py-2 text-xs">No, go back</button>
            <button onClick={handleConfirmSent} disabled={sending} className="flex-1 bg-green-500 text-white rounded-lg py-2 text-xs font-semibold disabled:opacity-50">{sending ? '…' : 'Yes, sent ✓'}</button>
          </div>
          {mailtoUrl && <button onClick={() => window.open(mailtoUrl, '_blank')} className="text-xs text-blue-500 text-center">Re-open Gmail</button>}
        </div>
      )}

      {/* They agreed to introduce me */}
      <label className="flex items-center gap-2 text-xs text-body cursor-pointer">
        <input type="checkbox" checked={agreeIntro} onChange={e => setAgreeIntro(e.target.checked)} className="rounded border-theme" />
        They agreed to introduce me to someone
      </label>
      {agreeIntro && (
        <div className="flex flex-col gap-2 mt-1">
          <input type="text" placeholder="Target person name" value={introTarget} onChange={e => setIntroTarget(e.target.value)} className="w-full text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-amber-500" />
          <div className="flex gap-2">
            <input type="text" placeholder="Their company" value={introCompany} onChange={e => setIntroCompany(e.target.value)} className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-amber-500" />
            <input type="text" placeholder="Company type (e.g. BaaS)" value={introCompanyType} onChange={e => setIntroCompanyType(e.target.value)} className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-amber-500" />
          </div>
          {introDraft ? (
            <div className="p-3 bg-amber-50 dark:bg-amber-950/30 rounded-lg border border-amber-200 dark:border-amber-800 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-amber-700 dark:text-amber-300">Briefing note for {action.contact_name}</span>
                <button onClick={() => { const text = `Subject: ${introDraft.subject}\n\n${introDraft.body}`; navigator.clipboard?.writeText(text).catch(() => {}); setIntroCopied(true); setTimeout(() => setIntroCopied(false), 2000) }} className="text-xs text-amber-600 hover:underline">{introCopied ? 'Copied!' : 'Copy'}</button>
              </div>
              <div className="text-xs text-muted font-medium">{introDraft.subject}</div>
              <pre className="text-xs text-body whitespace-pre-wrap break-words leading-relaxed">{introDraft.body}</pre>
              <div className="flex gap-2">
                <button onClick={() => { const to = encodeURIComponent(action.contact_email || ''); const su = encodeURIComponent(introDraft.subject || ''); const bd = encodeURIComponent(introDraft.body || ''); window.open(`https://mail.google.com/mail/?view=cm&to=${to}&su=${su}&body=${bd}`, '_blank') }} className="flex-1 text-xs px-3 py-2 rounded-lg bg-amber-500 text-white font-semibold hover:bg-amber-600">Send via Gmail →</button>
                <button onClick={handleDraftIntro} disabled={introDrafting} className="text-xs text-amber-600 hover:underline disabled:opacity-40">Regenerate</button>
              </div>
            </div>
          ) : (
            <button disabled={introDrafting} onClick={handleDraftIntro} className="text-xs px-3 py-2 rounded-lg bg-amber-500 text-white font-medium disabled:opacity-40 hover:bg-amber-600 text-left">{introDrafting ? 'Drafting…' : 'Draft activation note'}</button>
          )}
        </div>
      )}

      {/* Next check-in date + Save */}
      <div className="flex items-center gap-2">
        <input type="date" value={date} onChange={e => setDate(e.target.value)} className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body focus:outline-none focus:ring-1 focus:ring-blue-500" />
        <button disabled={!date || saving} onClick={save} className="text-xs px-3 py-2 rounded-lg bg-blue-500 text-white font-medium disabled:opacity-40 hover:bg-blue-600">{saving ? 'Saving…' : 'Save'}</button>
      </div>
      {!closingPrompt ? (
        <button
          disabled={saving}
          onClick={e => { e.stopPropagation(); setClosingPrompt(true) }}
          className="text-xs text-muted hover:text-red-500 disabled:opacity-40 text-left"
        >
          Close relationship
        </button>
      ) : (
        <div className="flex flex-col gap-2" onClick={e => e.stopPropagation()}>
          <div className="text-xs font-medium text-body">Snooze or close this relationship?</div>
          <div className="flex gap-2">
            <input
              type="date"
              value={snoozeDate}
              onChange={e => setSnoozeDate(e.target.value)}
              className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body"
            />
            <button
              disabled={!snoozeDate || saving}
              onClick={async e => {
                e.stopPropagation()
                setSaving(true)
                try {
                  await api.updateContact(action.payload_id, { next_checkin_date: snoozeDate })
                  onRefresh()
                } catch (err) { console.error(err) } finally { setSaving(false) }
              }}
              className="text-xs px-3 py-2 rounded-lg bg-blue-500 text-white font-medium disabled:opacity-40"
            >
              {saving ? 'Saving…' : 'Snooze'}
            </button>
          </div>
          <div className="flex gap-2">
            <button
              onClick={e => { e.stopPropagation(); setClosingPrompt(false) }}
              className="flex-1 text-xs px-3 py-2 rounded-lg border border-theme text-muted"
            >
              Cancel
            </button>
            <button
              disabled={saving}
              onClick={async e => {
                e.stopPropagation()
                setSaving(true)
                try {
                  await api.updateContact(action.payload_id, { is_champion: false })
                  onRefresh()
                } catch (err) { console.error(err) } finally { setSaving(false) }
              }}
              className="flex-1 text-xs px-3 py-2 rounded-lg border border-red-300 text-red-500 hover:bg-red-50 disabled:opacity-40"
            >
              {saving ? 'Closing…' : 'Permanently close'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function EscalationControls({ action, onRefresh }) {
  const [saving, setSaving] = useState(false)
  const [rescheduling, setRescheduling] = useState(false)
  const [rescheduleDate, setRescheduleDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 7)
    return d.toISOString().slice(0, 10)
  })
  const [rescheduledLabel, setRescheduledLabel] = useState(null)
  const [localChannel, setLocalChannel] = useState(action.escalation_channel || 'linkedin_dm')
  const [dirty, setDirty] = useState(false)
  const [stopped, setStopped] = useState(false)
  const [stopError, setStopError] = useState(null)

  const confirmReschedule = async (e) => {
    e.stopPropagation()
    if (!rescheduleDate || !action.payload_id) return
    setSaving(true)
    try {
      await api.patchOutreach(action.payload_id, { escalation_snooze_until: rescheduleDate })
      setRescheduledLabel(new Date(rescheduleDate + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }))
      setRescheduling(false)
      setDirty(true)
    } catch (e) { console.error('reschedule error', e) } finally { setSaving(false) }
  }

  const setChannel = async (ch) => {
    if (!action.payload_id) return
    setLocalChannel(ch)
    setSaving(true)
    try {
      await api.patchOutreach(action.payload_id, { escalation_channel: ch })
      setDirty(true)
    } catch (e) {
      setLocalChannel(action.escalation_channel || 'linkedin_dm')
      console.error('channel error', e)
    } finally { setSaving(false) }
  }

  const stop = async () => {
    if (!action.payload_id) return
    setStopError(null)
    setStopped(true)
    try {
      await api.skipOutreach(action.payload_id)
      onRefresh && onRefresh()
    } catch (e) {
      console.error('stop error', e)
      setStopped(false)
      setStopError('Failed to stop — tap again to retry')
    }
  }

  if (stopped) return (
    <div className="mt-3 pt-3 border-t border-theme">
      <span className="text-xs text-muted">Stopping escalation...</span>
    </div>
  )

  return (
    <div className="mt-3 pt-3 border-t border-theme space-y-2">
      {!rescheduling && (
        <div className="flex items-center gap-3">
          {rescheduledLabel
            ? <span className="text-xs text-green-600 dark:text-green-400">Rescheduled to {rescheduledLabel} ✓</span>
            : <button onClick={e => { e.stopPropagation(); setRescheduling(true) }} className="text-xs text-muted hover:text-body hover:underline">Reschedule →</button>
          }
        </div>
      )}
      {rescheduling && (
        <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
          <input
            type="date"
            value={rescheduleDate}
            onChange={e => setRescheduleDate(e.target.value)}
            className="flex-1 text-xs rounded-lg border border-theme bg-transparent px-3 py-2 text-body focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <button disabled={!rescheduleDate || saving} onClick={confirmReschedule}
            className="text-xs px-3 py-2 rounded-lg border border-theme text-muted hover:text-body disabled:opacity-40">
            {saving ? 'Saving…' : 'Confirm'}
          </button>
          <button onClick={e => { e.stopPropagation(); setRescheduling(false) }}
            className="text-xs px-3 py-2 rounded-lg border border-theme text-muted hover:text-body">
            Cancel
          </button>
        </div>
      )}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-muted flex-shrink-0">Next via:</span>
        {[
          { key: 'linkedin_dm', label: 'LinkedIn DM' },
          { key: 'email', label: 'Gmail' },
        ].map(({ key, label }) => (
          <button key={key} disabled={saving}
            onClick={e => { e.stopPropagation(); setChannel(key) }}
            className={`text-xs px-2 py-1 rounded-md border disabled:opacity-40 transition-colors ${
              localChannel === key
                ? 'bg-purple-100 border-purple-400 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300'
                : 'border-theme text-muted hover:text-body'
            }`}>
            {label}
          </button>
        ))}
        {dirty && (
          <button
            onClick={e => { e.stopPropagation(); onRefresh && onRefresh() }}
            className="text-xs px-3 py-1 rounded-md bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 ml-auto">
            Done — dismiss
          </button>
        )}
        {!dirty && (
          <button disabled={saving}
            onClick={e => { e.stopPropagation(); stop() }}
            className="text-xs px-2 py-1 rounded-md border border-red-300 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40 disabled:opacity-40 ml-auto">
            Stop escalating
          </button>
        )}
      </div>
      {stopError && (
        <div className="text-xs text-red-500">{stopError}</div>
      )}
      {dirty && (
        <div className="flex justify-end">
          <button disabled={saving}
            onClick={e => { e.stopPropagation(); stop() }}
            className="text-xs px-2 py-1 rounded-md border border-red-300 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40 disabled:opacity-40">
            Stop escalating
          </button>
        </div>
      )}
    </div>
  )
}

function FollowUpCardActions({ action, onMarkSent, onRescheduled, onMetDraft }) {
  const [rescheduling, setRescheduling] = useState(false)
  const [newDate, setNewDate] = useState('')
  const [saving, setSaving] = useState(false)
  const [closing, setClosing] = useState(false)

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

  const handleMarkSent = (e) => {
    e.stopPropagation()
    onMarkSent(action)
  }

  const handleCloseOut = async (e) => {
    e.stopPropagation()
    if (closing) return
    setClosing(true)
    try {
      await api.updateOutreachResponse(action.payload_id, 'negative')
      onRescheduled && onRescheduled()
    } catch (err) {
      alert(err.message)
      setClosing(false)
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
        <div className="flex items-center gap-3 justify-center flex-wrap">
          <button
            onClick={handleMarkSent}
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
          <span className="text-theme/30">·</span>
          <button
            onClick={handleCloseOut}
            disabled={closing}
            className="text-xs text-red-400 hover:text-red-500 disabled:opacity-40"
          >
            {closing ? 'Closing…' : 'Close out'}
          </button>
        </div>
      )}
      {onMetDraft && !rescheduling && (
        <div className="mt-2 flex justify-center">
          <button
            onClick={e => { e.stopPropagation(); onMetDraft() }}
            className="text-xs text-green-600 dark:text-green-400 hover:underline"
          >
            We met — draft post-meeting email instead →
          </button>
        </div>
      )}
    </div>
  )
}

function Section({ title, icon: Icon, items, onAction, onMarkSent, onDismiss, onRefresh, badge, badgeColor = 'blue', defaultOpen = true, priorityIds = [] }) {
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
              const stableKey = `${action.action_type}-${action.payload_id ?? i}`

              // Inline follow-up cards (no modal)
              if (action.action_type === 'follow_up_3' || action.action_type === 'follow_up_7' ||
                  action.action_type === 'post_meeting_followup' || action.action_type === 'post_meeting_followup_2') {
                return <InlineFollowUpCard key={stableKey} action={action} onSent={onMarkSent} onDismiss={onDismiss} onRefresh={onRefresh} />
              }
              if (action.action_type === 'check_linkedin_acceptance' || action.action_type === 'email_escalation') {
                return <LinkedInAcceptanceCard key={stableKey} action={action} onRefresh={onRefresh} />
              }
              if (action.action_type === 'linkedin_not_accepted') {
                return <LinkedInNotAcceptedCard key={stableKey} action={action} onRefresh={onRefresh} />
              }
              if (action.action_type === 'email_bounce_retry') {
                return <EmailBounceRetryCard key={stableKey} action={action} onRefresh={onRefresh} />
              }
              if (action.action_type === 'new_reply') {
                const onMetDraft = action.contact_id ? () => onMarkSent && onMarkSent({ ...action, followup_day: 0 }) : undefined
                return <NewReplyCard key={stableKey} action={action} onDismiss={onDismiss} onRefresh={onRefresh} onMetDraft={onMetDraft} />
              }
              if (action.action_type === 'linkedin_accepted') {
                return <LinkedInAcceptedSyncCard key={stableKey} action={action} onDismiss={onDismiss} onRefresh={onRefresh} />
              }

              const CardIcon = ACTION_ICONS[action.action_type] || AlertCircle
              const cardColor = ACTION_COLORS[action.action_type] || 'border-theme bg-card'
              const iconColor = ACTION_ICON_COLORS[action.action_type] || 'text-muted'
              const isWarmPath = action.action_type === 'warm_path'
              const isChampionCheckin = action.action_type === 'champion_checkin'
              const isPriority = priorityIds.includes(action.company_id)

              return (
                <div
                  key={stableKey}
                  className={`w-full text-left p-4 rounded-xl border ${cardColor}`}
                >
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start gap-3">
                        <CardIcon size={16} className={`mt-0.5 flex-shrink-0 ${iconColor}`} />
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-body text-sm leading-snug flex items-center gap-1.5">
                            {isPriority && <Star size={11} className="text-amber-400 fill-amber-400 flex-shrink-0" />}
                            {action.label}
                          </div>
                          {(action.contact_title || action.company_name) && (
                            <div className="text-xs text-muted mt-0.5">
                              {[action.contact_title, action.company_name].filter(Boolean).join(' · ')}
                            </div>
                          )}
                          {action.detail && (
                            <div className="text-xs text-muted mt-0.5 leading-relaxed">{action.detail}</div>
                          )}
                          {!isChampionCheckin && !isWarmPath && (
                            <div className="mt-2">
                              <span className="text-xs font-semibold text-blue-500">{action.cta} →</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                    {onDismiss && (
                      <button
                        onClick={e => { e.stopPropagation(); onDismiss(action) }}
                        className="flex-shrink-0 p-1 text-muted hover:text-body"
                        title="Dismiss"
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                  {isWarmPath && onRefresh && (
                    <>
                      <WarmPathIntel action={action} />
                      <WarmPathSnooze action={action} onSnoozed={onRefresh} />
                      <WarmPathChampionToggle action={action} onRefresh={onRefresh} />
                      {action.contact_id && onMarkSent && (
                        <div className="mt-2 pt-2 border-t border-theme/50">
                          <button
                            onClick={e => { e.stopPropagation(); onMarkSent({ ...action, followup_day: 0 }) }}
                            className="text-xs text-green-600 dark:text-green-400 hover:underline text-left"
                          >
                            We met — draft post-meeting email →
                          </button>
                        </div>
                      )}
                    </>
                  )}
                  {isChampionCheckin && onRefresh && (
                    <ChampionCheckinCard action={action} onRefresh={onRefresh} />
                  )}
                  {action.action_type === 'publish_content' && (
                    <PublishContentCard action={action} onRefresh={onRefresh} />
                  )}
                  {action.action_type === 'try_linkedin_dm' && onRefresh && (
                    <EscalationControls action={action} onRefresh={onRefresh} />
                  )}
                  {action.action_type === 'prompt_review' && (
                    <div className="mt-3 pt-3 border-t border-theme flex gap-2">
                      <a href="/review" className="text-xs px-3 py-2 rounded-lg bg-blue-500 text-white font-medium hover:bg-blue-600">Open review →</a>
                    </div>
                  )}
                  {action.action_type === 'call' && (
                    <CallScriptCard action={action} />
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
    } else if (action.action_type === 'try_linkedin_dm') {
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

  const handleMarkSent = (action) => {
    setFollowUpModal(action)
  }

  const handleDismiss = async (action) => {
    try {
      await api.dismissBriefAction(action.action_type, action.payload_id ?? null)
      load()
    } catch (e) {
      console.error('dismiss error', e)
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
              onDismiss={handleDismiss}
              onRefresh={load}
              badgeColor="red"
              priorityIds={brief.priority_company_ids || []}
            />
            <div className="mx-4 border-t border-theme my-1" />
            <Section
              title="Companies"
              icon={Briefcase}
              items={brief.positions || []}
              onAction={handleAction}
              onDismiss={handleDismiss}
              badgeColor="orange"
            />
            <div className="mx-4 border-t border-theme my-1" />
            <Section
              title="Events"
              icon={Calendar}
              items={brief.events || []}
              onAction={handleAction}
              onDismiss={handleDismiss}
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
