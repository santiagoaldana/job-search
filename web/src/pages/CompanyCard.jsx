import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Archive, Send, Check, Copy, Users } from 'lucide-react'
import { api } from '../api'
import Badge from '../components/Badge'
import FitBar from '../components/FitBar'
import Spinner from '../components/Spinner'

const TABS = ['Intel', 'Contacts', 'Leads', 'Outreach']
const STAGES = ['pool', 'researched', 'outreach', 'response', 'meeting', 'applied', 'interview', 'offer']
const FUNDING_BADGE = {
  series_b: 'Series B', series_c: 'Series C', series_d: 'Series D', public: 'Public', unknown: '?',
}

export default function CompanyCard() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [company, setCompany] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('Intel')
  const [refreshingIntel, setRefreshingIntel] = useState(false)
  const [motivation, setMotivation] = useState(null)
  const [savingMotivation, setSavingMotivation] = useState(false)
  const [generatingOutreach, setGeneratingOutreach] = useState(false)
  const [outreachDraft, setOutreachDraft] = useState(null)
  const [findingContacts, setFindingContacts] = useState(false)

  const load = () => {
    setLoading(true)
    api.getCompany(id)
      .then(c => { setCompany(c); setMotivation(c.motivation) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }
  useEffect(load, [id])

  const handleRefreshIntel = async () => {
    setRefreshingIntel(true)
    try { await api.refreshIntel(id); load() }
    catch (e) { alert(e.message) }
    finally { setRefreshingIntel(false) }
  }

  const handleMotivationChange = async (val) => {
    setMotivation(val); setSavingMotivation(true)
    try { await api.updateCompany(id, { motivation: val }); setCompany(c => ({ ...c, motivation: val })) }
    catch (e) { alert(e.message) }
    finally { setSavingMotivation(false) }
  }

  const handleStageChange = async (stage) => {
    try { await api.advanceStage(id, stage); setCompany(c => ({ ...c, stage })) }
    catch (e) { alert(e.message) }
  }

  const handleArchive = async () => {
    if (!confirm('Archive this company?')) return
    try { await api.archiveCompany(id); navigate(-1) }
    catch (e) { alert(e.message) }
  }

  const handleFindContacts = async () => {
    setFindingContacts(true)
    try {
      const result = await api.findContacts(id)
      if (result.found === 0) {
        alert('No new contacts found. Try generating intel first, then searching again.')
      }
      load()
    } catch (e) {
      alert(e.message)
    } finally {
      setFindingContacts(false)
    }
  }

  const handleGenerateOutreach = async () => {
    setGeneratingOutreach(true)
    try {
      const contact = company.contacts?.[0]
      const result = await api.generateOutreach({
        company_id: Number(id),
        contact_id: contact?.id,
        context: company.intel_summary || '',
      })
      setOutreachDraft(result)
    } catch (e) { alert(e.message) }
    finally { setGeneratingOutreach(false) }
  }

  if (loading) return <div className="flex justify-center py-16"><Spinner size={8} /></div>
  if (!company) return <div className="p-8 text-center text-muted">Company not found</div>

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-3 px-4 pt-5 pb-3">
        <button onClick={() => navigate(-1)} className="p-1.5 text-muted hover:text-body">
          <ArrowLeft size={20} />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-lg font-bold text-body truncate">{company.name}</h1>
          <div className="flex items-center gap-2 mt-0.5">
            <Badge color="blue">{FUNDING_BADGE[company.funding_stage] || '?'}</Badge>
            <span className="text-xs text-muted">LAMP {company.lamp_score?.toFixed(0) || '—'}</span>
          </div>
        </div>
        <button onClick={handleArchive} className="p-1.5 text-muted hover:text-orange-500">
          <Archive size={18} />
        </button>
      </div>

      <div className="mx-4 mb-3 bg-card border border-theme rounded-xl p-4">
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm text-muted">Motivation</span>
          <span className="text-sm font-bold text-body">{motivation}/10
            {savingMotivation && <span className="ml-1 text-xs text-blue-500">saving…</span>}
          </span>
        </div>
        <input type="range" min={1} max={10} value={motivation}
          onChange={e => handleMotivationChange(Number(e.target.value))}
          className="w-full accent-blue-500" />
      </div>

      <div className="mx-4 mb-3">
        <select value={company.stage} onChange={e => handleStageChange(e.target.value)}
          className="w-full bg-card border border-theme text-body rounded-xl px-4 py-2.5 text-sm outline-none">
          {STAGES.map(s => (
            <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
          ))}
        </select>
      </div>

      <div className="flex gap-1 px-4 mb-3 border-b border-theme">
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t ? 'border-blue-500 text-blue-500' : 'border-transparent text-muted'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="px-4 pb-4">
        {tab === 'Intel' && (
          <div>
            <button onClick={handleRefreshIntel} disabled={refreshingIntel}
              className="flex items-center gap-2 text-sm text-blue-500 mb-4 disabled:opacity-50">
              <RefreshCw size={14} className={refreshingIntel ? 'animate-spin' : ''} />
              {refreshingIntel ? 'Generating…' : 'Refresh intel'}
            </button>
            {company.intel_summary ? (
              <div className="bg-card border border-theme rounded-xl p-4 text-sm text-body leading-relaxed whitespace-pre-wrap">
                {company.intel_summary}
              </div>
            ) : (
              <div className="text-center text-muted text-sm py-8">
                No intel yet. Tap "Refresh intel" to generate a brief.
              </div>
            )}
            {company.org_notes && (
              <div className="mt-3 bg-card border border-theme rounded-xl p-4">
                <div className="text-xs text-muted font-medium uppercase tracking-wide mb-2">Notes</div>
                <div className="text-sm text-body">{company.org_notes}</div>
              </div>
            )}
          </div>
        )}

        {tab === 'Contacts' && (
          <div className="space-y-3">
            {(!company.contacts || company.contacts.length === 0) ? (
              <div className="py-10 text-center">
                <div className="text-muted text-sm mb-4">No contacts yet</div>
                <button
                  onClick={handleFindContacts}
                  disabled={findingContacts}
                  className="flex items-center gap-2 mx-auto bg-blue-500 text-white rounded-xl px-5 py-2.5 text-sm font-medium disabled:opacity-50"
                >
                  <Users size={15} />
                  {findingContacts ? 'Searching…' : 'Find Contacts'}
                </button>
              </div>
            ) : (
              <>
                {company.contacts.map(c => (
                  <div key={c.id} className="bg-card border border-theme rounded-xl p-4">
                    <div className="font-medium text-body">{c.name}</div>
                    {c.title && <div className="text-sm text-muted mt-0.5">{c.title}</div>}
                    {c.email && <div className="text-xs text-blue-500 mt-1">{c.email}</div>}
                    <div className="flex items-center gap-2 mt-2 flex-wrap">
                      {c.connection_degree && (
                        <Badge color={c.connection_degree === 1 ? 'green' : c.connection_degree === 2 ? 'blue' : 'slate'}>
                          {c.connection_degree}° connection
                        </Badge>
                      )}
                      {c.warmth && (
                        <Badge color={c.warmth === 'hot' ? 'red' : c.warmth === 'warm' ? 'orange' : 'slate'}>
                          {c.warmth}
                        </Badge>
                      )}
                    </div>
                    {c.linkedin_url && (
                      <a href={c.linkedin_url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-blue-500 mt-2 block">LinkedIn →</a>
                    )}
                  </div>
                ))}
                <button
                  onClick={handleFindContacts}
                  disabled={findingContacts}
                  className="flex items-center gap-1.5 text-xs text-blue-500 disabled:opacity-50 mt-1"
                >
                  <Users size={12} />
                  {findingContacts ? 'Searching…' : 'Find more contacts'}
                </button>
              </>
            )}
          </div>
        )}

        {tab === 'Leads' && (
          <div className="space-y-3">
            {(!company.leads || company.leads.length === 0) && (
              <div className="text-center text-muted text-sm py-8">No open roles found</div>
            )}
            {company.leads?.map(l => (
              <div key={l.id} className={`bg-card border rounded-xl p-4 ${!l.location_compatible ? 'border-theme opacity-60' : 'border-theme'}`}>
                <div className="font-medium text-body">{l.title}</div>
                <div className="text-xs text-muted mt-0.5">{l.location || 'Location unknown'}</div>
                {l.fit_score > 0 && <div className="mt-2"><FitBar score={l.fit_score} /></div>}
                {!l.location_compatible && <Badge color="slate" className="mt-2">Location mismatch</Badge>}
                {l.url && (
                  <a href={l.url} target="_blank" rel="noopener noreferrer"
                    className="text-xs text-blue-500 mt-2 block">View posting →</a>
                )}
              </div>
            ))}
          </div>
        )}

        {tab === 'Outreach' && (
          <OutreachTab company={company} onReload={load} />
        )}
      </div>
    </div>
  )
}

function OutreachTab({ company, onReload }) {
  const [emailType, setEmailType] = useState('cold')
  const [context, setContext] = useState('')
  const [hook, setHook] = useState('')
  const [ask, setAsk] = useState('')
  const [selectedContact, setSelectedContact] = useState(company.contacts?.[0]?.id || null)
  const [generating, setGenerating] = useState(false)
  const [draft, setDraft] = useState(null)
  const [logging, setLogging] = useState(false)
  const [copied, setCopied] = useState(false)

  const handleGenerate = async () => {
    setGenerating(true)
    setDraft(null)
    try {
      const result = await api.generateOutreach({
        company_id: company.id,
        contact_id: selectedContact || undefined,
        context: context || undefined,
        hook: hook || undefined,
        ask: ask || undefined,
        email_type: emailType,
      })
      setDraft(result)
    } catch (e) {
      alert(e.message)
    } finally {
      setGenerating(false)
    }
  }

  const handleLogSent = async () => {
    if (!draft) return
    setLogging(true)
    try {
      await api.logOutreach({
        company_id: company.id,
        contact_id: selectedContact || undefined,
        channel: 'email',
        subject: draft.subject,
        body: draft.body,
        sent_at: new Date().toISOString(),
      })
      setDraft(null)
      setContext('')
      setHook('')
      setAsk('')
      onReload()
    } catch (e) {
      alert(e.message)
    } finally {
      setLogging(false)
    }
  }

  const handleCopy = () => {
    const text = `Subject: ${draft.subject}\n\n${draft.body}`
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleResponseUpdate = async (outreachId, status) => {
    try {
      await api.updateOutreachResponse(outreachId, status)
      onReload()
    } catch (e) {
      alert(e.message)
    }
  }

  return (
    <div className="space-y-4">
      {/* Email type selector */}
      <div className="flex gap-1 bg-card2 border border-theme rounded-xl p-1">
        {[
          { value: 'cold', label: 'Cold' },
          { value: 'event_met', label: 'Met at event' },
          { value: 'followup', label: 'Follow-up' },
        ].map(t => (
          <button key={t.value} onClick={() => setEmailType(t.value)}
            className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              emailType === t.value
                ? 'bg-white dark:bg-slate-700 text-body shadow-sm'
                : 'text-muted'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Contact selector */}
      {company.contacts?.length > 0 && (
        <select
          value={selectedContact || ''}
          onChange={e => setSelectedContact(Number(e.target.value) || null)}
          className="w-full bg-card border border-theme text-body rounded-xl px-3 py-2 text-sm outline-none"
        >
          <option value="">No specific contact</option>
          {company.contacts.map(c => (
            <option key={c.id} value={c.id}>{c.name} — {c.title}</option>
          ))}
        </select>
      )}

      {/* Context fields */}
      <div className="space-y-2">
        <textarea
          value={context}
          onChange={e => setContext(e.target.value)}
          placeholder={emailType === 'event_met'
            ? 'How you met, what you discussed, what they said…'
            : 'Any context about your connection or shared interest…'}
          rows={2}
          className="w-full bg-card border border-theme rounded-xl px-3 py-2.5 text-sm text-body placeholder-faint resize-none outline-none leading-relaxed"
        />
        <input
          value={hook}
          onChange={e => setHook(e.target.value)}
          placeholder='Specific angle or topic to lead with (e.g. "Supercharged Scams from EmTech AI")'
          className="w-full bg-card border border-theme rounded-xl px-3 py-2.5 text-sm text-body placeholder-faint outline-none"
        />
        <input
          value={ask}
          onChange={e => setAsk(e.target.value)}
          placeholder='What you want from this email (e.g. "20-min call about their editorial vision on AI fraud")'
          className="w-full bg-card border border-theme rounded-xl px-3 py-2.5 text-sm text-body placeholder-faint outline-none"
        />
      </div>

      <button
        onClick={handleGenerate}
        disabled={generating}
        className="w-full bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-3 text-sm font-medium transition-colors flex items-center justify-center gap-2"
      >
        {generating ? <><RefreshCw size={14} className="animate-spin" /> Drafting…</> : <><Send size={14} /> Generate email</>}
      </button>

      {/* Draft result */}
      {draft && (
        <div className="bg-card border border-blue-300 dark:border-blue-700 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-theme bg-blue-50 dark:bg-blue-950/40">
            <div>
              <span className="text-xs font-medium text-blue-600 dark:text-blue-400 uppercase tracking-wide">Draft</span>
              {draft.word_count && (
                <span className={`ml-2 text-xs ${draft.word_count > 75 ? 'text-orange-500' : 'text-green-600 dark:text-green-400'}`}>
                  {draft.word_count} words
                </span>
              )}
            </div>
            <button onClick={handleCopy}
              className="flex items-center gap-1 text-xs text-muted hover:text-body">
              {copied ? <><Check size={12} className="text-green-500" /> Copied</> : <><Copy size={12} /> Copy</>}
            </button>
          </div>
          <div className="p-4 space-y-2">
            <div className="text-sm font-semibold text-body">{draft.subject}</div>
            <div className="text-sm text-body whitespace-pre-wrap leading-relaxed">{draft.body}</div>
            {draft.rationale && (
              <div className="text-xs text-muted italic pt-1 border-t border-theme">{draft.rationale}</div>
            )}
          </div>
          <div className="flex gap-2 px-4 pb-4">
            <button onClick={handleGenerate} disabled={generating}
              className="flex-1 bg-card2 border border-theme text-body rounded-lg py-2 text-xs font-medium">
              Regenerate
            </button>
            <button onClick={handleLogSent} disabled={logging}
              className="flex-1 bg-green-500 hover:bg-green-600 disabled:opacity-50 text-white rounded-lg py-2 text-xs font-medium">
              {logging ? 'Saving…' : 'Mark as sent →'}
            </button>
          </div>
        </div>
      )}

      {/* Outreach history */}
      {(!company.outreach || company.outreach.length === 0) ? (
        <div className="text-center text-muted text-sm py-6">No outreach logged yet</div>
      ) : (
        <div className="space-y-3 pt-2">
          <div className="text-xs text-muted font-medium uppercase tracking-wide">History</div>
          {company.outreach.map(o => (
            <div key={o.id} className="bg-card border border-theme rounded-xl p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-body">{o.subject || o.channel}</span>
                <Badge color={
                  o.response_status === 'positive' ? 'green' :
                  o.response_status === 'negative' ? 'red' :
                  o.response_status === 'ghosted' ? 'slate' : 'yellow'
                }>{o.response_status}</Badge>
              </div>
              <div className="text-xs text-muted mb-2">
                {o.sent_at ? `Sent ${o.sent_at.slice(0,10)}` : 'Draft'}
                {o.follow_up_3_due && ` · Follow-up due ${o.follow_up_3_due}`}
              </div>
              {o.body && (
                <div className="text-xs text-muted line-clamp-2 leading-relaxed">{o.body}</div>
              )}
              {o.response_status === 'pending' && (
                <div className="flex gap-2 mt-3">
                  {['positive', 'negative', 'ghosted'].map(s => (
                    <button key={s} onClick={() => handleResponseUpdate(o.id, s)}
                      className="flex-1 text-xs py-1.5 rounded-lg border border-theme bg-card2 text-muted hover:text-body capitalize transition-colors">
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
