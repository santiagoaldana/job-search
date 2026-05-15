import { useEffect, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Archive, Send, Check, Copy, Users, Network, Plus, X, ChevronDown, ChevronUp, ChevronRight, Pencil, BookOpen, ExternalLink } from 'lucide-react'
import { api } from '../api'
import Badge from '../components/Badge'
import FitBar from '../components/FitBar'
import Spinner from '../components/Spinner'

const TABS = ['Intel', 'Contacts', 'Leads', 'Outreach', 'References']
const STAGES = [
  { value: 'pool', label: 'Target' },
  { value: 'outreach', label: 'In Play' },
  { value: 'closed', label: 'Closed' },
]

const STAGE_DISPLAY = (stage) => {
  if (['pool', 'researched'].includes(stage)) return 'pool'
  if (['outreach', 'response', 'meeting', 'applied', 'interview', 'offer'].includes(stage)) return 'outreach'
  return 'closed'
}
const FUNDING_BADGE = {
  series_b: 'Series B', series_c: 'Series C', series_d: 'Series D', public: 'Public', unknown: '?',
}

export default function CompanyCard() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [company, setCompany] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState(searchParams.get('tab') || 'Intel')
  const [refreshingIntel, setRefreshingIntel] = useState(false)
  const [editingIntel, setEditingIntel] = useState(false)
  const [intelDraft, setIntelDraft] = useState('')
  const [savingIntel, setSavingIntel] = useState(false)
  const [motivation, setMotivation] = useState(null)
  const [savingMotivation, setSavingMotivation] = useState(false)
  const [generatingOutreach, setGeneratingOutreach] = useState(false)
  const [outreachDraft, setOutreachDraft] = useState(null)
  const [findingContacts, setFindingContacts] = useState(false)
  const [contactModal, setContactModal] = useState(null) // null=closed | 'new' | contact-object
  const [prepModal, setPrepModal] = useState(false)
  const [prepBrief, setPrepBrief] = useState(null)
  const [generatingPrep, setGeneratingPrep] = useState(false)

  const load = () => {
    setLoading(true)
    api.getCompany(id)
      .then(r => {
        const c = { ...r.company, contacts: r.contacts, leads: r.leads, outreach: r.outreach, applications: r.applications, referral_contacts: r.referral_contacts || [] }
        setCompany(c); setMotivation(c.motivation)
      })
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
      alert(typeof e.message === 'string' ? e.message : JSON.stringify(e))
    } finally {
      setFindingContacts(false)
    }
  }

  const handleGeneratePrep = async () => {
    setGeneratingPrep(true)
    setPrepBrief(null)
    setPrepModal(true)
    try {
      const result = await api.getInterviewPrep(id, {
        contact_name: company.contacts?.[0]?.name || '',
        contact_title: company.contacts?.[0]?.title || '',
        role_title: '',
      })
      setPrepBrief(result)
    } catch (e) {
      setPrepBrief({ error: e.message })
    } finally {
      setGeneratingPrep(false)
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
        <select value={STAGE_DISPLAY(company.stage)} onChange={e => handleStageChange(e.target.value)}
          className="w-full bg-card border border-theme text-body rounded-xl px-4 py-2.5 text-sm outline-none">
          {STAGES.map(s => (
            <option key={s.value} value={s.value}>{s.label}</option>
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
            <div className="flex items-center gap-3 mb-4">
              <button onClick={handleRefreshIntel} disabled={refreshingIntel}
                className="flex items-center gap-2 text-sm text-blue-500 disabled:opacity-50">
                <RefreshCw size={14} className={refreshingIntel ? 'animate-spin' : ''} />
                {refreshingIntel ? 'Generating…' : 'Refresh intel'}
              </button>
              {!editingIntel && (
                <button
                  onClick={() => { setIntelDraft(company.intel_summary || ''); setEditingIntel(true) }}
                  className="flex items-center gap-1 text-sm text-muted hover:text-body"
                >
                  <Pencil size={13} /> Edit
                </button>
              )}
              <button onClick={handleGeneratePrep} disabled={generatingPrep}
                className="flex items-center gap-2 text-sm text-purple-500 disabled:opacity-50">
                <BookOpen size={14} className={generatingPrep ? 'animate-pulse' : ''} />
                {generatingPrep ? 'Generating...' : 'Meeting Prep'}
              </button>
            </div>

            {editingIntel ? (
              <div className="space-y-2">
                <textarea
                  value={intelDraft}
                  onChange={e => setIntelDraft(e.target.value)}
                  rows={10}
                  className="w-full border border-theme rounded-xl p-4 text-sm bg-card text-body resize-none leading-relaxed"
                  placeholder="Add intel: news, funding, hiring signals, key initiatives, people notes…"
                  autoFocus
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => setEditingIntel(false)}
                    className="flex-1 border border-theme text-muted rounded-xl py-2 text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    disabled={savingIntel}
                    onClick={async () => {
                      setSavingIntel(true)
                      try {
                        await api.updateCompany(id, { intel_summary: intelDraft })
                        setCompany(c => ({ ...c, intel_summary: intelDraft }))
                        setEditingIntel(false)
                      } catch (e) { alert(e.message) }
                      setSavingIntel(false)
                    }}
                    className="flex-1 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-2 text-sm font-semibold"
                  >
                    {savingIntel ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </div>
            ) : company.intel_summary ? (
              <div className="bg-card border border-theme rounded-xl p-4 text-sm text-body leading-relaxed whitespace-pre-wrap">
                {company.intel_summary}
              </div>
            ) : (
              <div className="text-center text-muted text-sm py-8">
                No intel yet. Tap "Refresh intel" to generate, or "Edit" to add manually.
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
            <NetworkPath companyId={id} />

            {/* Header row: contact count + Add button */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted font-medium uppercase tracking-wide">
                {company.contacts?.length || 0} contact{company.contacts?.length !== 1 ? 's' : ''}
              </span>
              <button
                onClick={() => setContactModal('new')}
                className="flex items-center gap-1 text-xs text-blue-500 font-medium"
              >
                <Plus size={13} /> Add contact
              </button>
            </div>

            {(!company.contacts || company.contacts.length === 0) ? (
              <div className="py-6 text-center">
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
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-body">{c.name}</div>
                        {c.title && <div className="text-sm text-muted mt-0.5">{c.title}</div>}
                        {c.met_via && (
                          <div className="text-xs text-blue-500 mt-1">via {c.met_via}</div>
                        )}
                        {c.relationship_notes && (
                          <div className="text-xs text-muted italic mt-0.5">{c.relationship_notes}</div>
                        )}
                        {c.email && <div className="text-xs text-muted mt-1">{c.email}</div>}
                      </div>
                      <div className="flex flex-col gap-1 items-end flex-shrink-0">
                        <button
                          onClick={() => setContactModal(c)}
                          className="text-xs text-muted underline mb-1"
                        >
                          Edit
                        </button>
                        {c.connection_degree && (
                          <Badge color={c.connection_degree === 1 ? 'green' : c.connection_degree === 2 ? 'blue' : 'slate'}>
                            {c.connection_degree}°
                          </Badge>
                        )}
                        {c.warmth && (
                          <Badge color={c.warmth === 'hot' ? 'red' : c.warmth === 'warm' ? 'orange' : 'slate'}>
                            {c.warmth}
                          </Badge>
                        )}
                      </div>
                    </div>
                    {c.linkedin_url && (
                      <a href={c.linkedin_url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-blue-500 mt-2 block">LinkedIn →</a>
                    )}
                    {c.introduced_by_name && (
                      <div className="text-xs text-purple-500 mt-1">Introduced by {c.introduced_by_name}</div>
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

            {/* Referral Sources */}
            {company.referral_contacts?.length > 0 && (
              <div className="mt-4">
                <div className="text-xs text-muted font-medium uppercase tracking-wide mb-2">
                  Referral sources ({company.referral_contacts.length})
                </div>
                {company.referral_contacts.map(c => (
                  <div key={c.id} className="bg-card border border-theme rounded-xl p-4 mb-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-body">{c.name}</div>
                        {c.title && <div className="text-sm text-muted mt-0.5">{c.title}</div>}
                        {c.current_company_name && (
                          <div className="text-xs text-muted mt-0.5">Now at {c.current_company_name}</div>
                        )}
                        {c.relationship_notes && (
                          <div className="text-xs text-muted italic mt-0.5">{c.relationship_notes}</div>
                        )}
                      </div>
                      <Badge color={c.warmth === 'hot' ? 'red' : c.warmth === 'warm' ? 'orange' : 'slate'}>
                        {c.warmth}
                      </Badge>
                    </div>
                    {c.linkedin_url && (
                      <a href={c.linkedin_url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-blue-500 mt-2 block">LinkedIn →</a>
                    )}
                  </div>
                ))}
              </div>
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
                <div className="flex items-start justify-between gap-2">
                  <div className="font-medium text-body">{l.title}</div>
                  {l.status === 'applied' && <Badge color="green">Applied</Badge>}
                </div>
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
          <OutreachTab company={company} onReload={load} defaultContactId={Number(searchParams.get('contact_id')) || null} />
        )}

        {tab === 'References' && (
          <ReferencesTab companyId={company.id} />
        )}
      </div>

      {contactModal && (
        <ContactModal
          company={company}
          contact={contactModal === 'new' ? null : contactModal}
          onClose={() => setContactModal(null)}
          onSaved={() => { setContactModal(null); load() }}
        />
      )}

      {prepModal && (
        <PrepBriefModal
          company={company}
          brief={prepBrief}
          loading={generatingPrep}
          onClose={() => { setPrepModal(false); setPrepBrief(null) }}
        />
      )}
    </div>
  )
}

const STRENGTH_COLOR = { strong: 'green', medium: 'yellow', weak: 'slate' }

function ReferencesTab({ companyId }) {
  const [refs, setRefs] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ contact_name: '', contact_title: '', relationship: '', strength: 'medium', role_types: '', notes: '' })
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try { setRefs(await api.getReferencesForCompany(companyId)) } catch (e) { console.error(e) } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [companyId])

  const set = (f) => (e) => setForm(prev => ({ ...prev, [f]: e.target.value }))

  const handleAdd = async () => {
    if (!form.contact_name.trim()) return
    setSaving(true)
    try {
      await api.addReference({ ...form, company_id: companyId, role_types: form.role_types || undefined, notes: form.notes || undefined })
      setForm({ contact_name: '', contact_title: '', relationship: '', strength: 'medium', role_types: '', notes: '' })
      setShowAdd(false)
      await load()
    } catch (e) { alert(e.message) } finally { setSaving(false) }
  }

  const handleDelete = async (id) => {
    await api.deleteReference(id)
    setRefs(r => r.filter(x => x.id !== id))
  }

  return (
    <div className="p-4 space-y-3">
      <button
        onClick={() => setShowAdd(v => !v)}
        className="flex items-center gap-1.5 text-sm text-blue-500"
      >
        <Plus size={14} /> Add Reference
      </button>

      {showAdd && (
        <div className="bg-card border border-theme rounded-xl p-4 space-y-3">
          <div className="text-sm font-medium text-body">Add Reference</div>
          {[
            { field: 'contact_name', label: 'Name *', placeholder: 'John Smith' },
            { field: 'contact_title', label: 'Title', placeholder: 'VP Payments at Sardine' },
            { field: 'relationship', label: 'Relationship', placeholder: 'Worked together at Uff Móvil 2019-2021' },
            { field: 'role_types', label: 'Good for roles', placeholder: 'payments, fintech, agentic-ai' },
            { field: 'notes', label: 'Notes', placeholder: 'Strong reference for executive roles' },
          ].map(({ field, label, placeholder }) => (
            <div key={field}>
              <div className="text-xs text-muted mb-1">{label}</div>
              <input
                value={form[field]}
                onChange={set(field)}
                placeholder={placeholder}
                className="w-full text-sm bg-app border border-theme rounded-lg px-3 py-2 text-body placeholder:text-muted"
              />
            </div>
          ))}
          <div>
            <div className="text-xs text-muted mb-1">Strength</div>
            <div className="flex gap-2">
              {['strong', 'medium', 'weak'].map(s => (
                <button
                  key={s}
                  onClick={() => setForm(f => ({ ...f, strength: s }))}
                  className={`text-xs px-3 py-1.5 rounded-lg border capitalize transition-colors ${
                    form.strength === s ? 'border-blue-400 text-blue-500 bg-blue-50 dark:bg-blue-950/30' : 'border-theme text-muted'
                  }`}
                >{s}</button>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={handleAdd} disabled={saving || !form.contact_name.trim()}
              className="bg-blue-500 text-white text-sm px-4 py-2 rounded-lg disabled:opacity-50">
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button onClick={() => setShowAdd(false)} className="text-sm text-muted px-4 py-2">Cancel</button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-8"><Spinner size={5} /></div>
      ) : refs.length === 0 ? (
        <div className="text-sm text-muted text-center py-8">No references yet — add someone who can vouch for you here</div>
      ) : (
        refs.map(ref => (
          <div key={ref.id} className="bg-card border border-theme rounded-xl p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="font-medium text-sm text-body">{ref.contact_name}</div>
                {ref.contact_title && <div className="text-xs text-muted">{ref.contact_title}</div>}
              </div>
              <div className="flex items-center gap-2">
                <Badge color={STRENGTH_COLOR[ref.strength] || 'slate'}>{ref.strength}</Badge>
                <button onClick={() => handleDelete(ref.id)} className="text-muted hover:text-red-500 transition-colors">
                  <X size={14} />
                </button>
              </div>
            </div>
            {ref.relationship && <div className="text-xs text-muted mt-2 italic">{ref.relationship}</div>}
            {ref.role_types && <div className="text-xs text-muted mt-1">Good for: {ref.role_types}</div>}
            {ref.notes && <div className="text-xs text-muted mt-1">{ref.notes}</div>}
          </div>
        ))
      )}
    </div>
  )
}

const NEXT_STEP_LABELS = {
  draft_email: { label: 'Draft email', color: 'bg-blue-500', detail: 'Confirmed email on file' },
  draft_email_guessed: { label: 'Draft email (unverified address)', color: 'bg-yellow-500', detail: '⚠ Guessed from company domain' },
  prompt_manual_email: { label: 'Check LinkedIn for email', color: 'bg-orange-500', detail: 'Open their profile → Contact Info tab' },
  draft_linkedin_dm: { label: 'Draft LinkedIn DM', color: 'bg-purple-500', detail: 'All email patterns tried' },
  draft_connection_request: { label: 'Send connection request', color: 'bg-slate-500', detail: 'Not yet a 1st-degree connection' },
}

function NextStepChip({ nextStep, contactName, onDone }) {
  if (!nextStep) return null
  const info = NEXT_STEP_LABELS[nextStep.action] || { label: nextStep.action, color: 'bg-slate-500', detail: '' }

  return (
    <div className="mt-3 rounded-xl border border-theme bg-card2 p-3">
      <div className="text-xs font-semibold text-body mb-0.5">Contact added — next step</div>
      <div className="text-xs text-muted mb-2">{info.detail}{nextStep.guessed_email ? `: ${nextStep.guessed_email}` : ''}</div>
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={onDone}
          className={`text-xs px-3 py-1.5 rounded-lg text-white font-medium ${info.color}`}
        >
          {info.label}
        </button>
        <button onClick={onDone} className="text-xs px-3 py-1.5 rounded-lg border border-theme text-muted">
          Later
        </button>
      </div>
    </div>
  )
}

function ContactModal({ company, contact, onClose, onSaved }) {
  const isEdit = !!contact
  console.log('[ContactModal] outreach records:', company.outreach, 'contact.id:', contact?.id)
  const linkedOutreach = isEdit
    ? (company.outreach || []).find(o => o.contact_id === contact.id)
      || [...(company.outreach || [])].sort((a, b) => b.id - a.id)[0]
      || null
    : null
  console.log('[ContactModal] linkedOutreach:', linkedOutreach)
  const [form, setForm] = useState({
    name: contact?.name || '',
    title: contact?.title || '',
    linkedin_url: contact?.linkedin_url || '',
    email: contact?.email || '',
    met_via: contact?.met_via || '',
    relationship_notes: contact?.relationship_notes || '',
    introduced_by_contact_id: contact?.introduced_by_contact_id || '',
  })
  const [saving, setSaving] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [nextStep, setNextStep] = useState(null)
  const [savedContactName, setSavedContactName] = useState('')
  const [allContacts, setAllContacts] = useState([])
  const [outreachDone, setOutreachDone] = useState(false)
  const [outreachChannel, setOutreachChannel] = useState('linkedin')
  const [outreachDate, setOutreachDate] = useState(new Date().toISOString().slice(0, 10))
  const [isReferral, setIsReferral] = useState(contact?.referral_target_company_id === company.id)
  const [due3, setDue3] = useState(linkedOutreach?.follow_up_3_due || '')
  const [due7, setDue7] = useState(linkedOutreach?.follow_up_7_due || '')
  const [snoozeUntil, setSnoozeUntil] = useState(contact?.snooze_until?.slice(0, 10) || '')

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }))

  useEffect(() => {
    api.listAllContacts().then(setAllContacts).catch(() => setAllContacts(company.contacts || []))
  }, [])

  const handleScreenshotPaste = async (file) => {
    if (!file || !file.type.startsWith('image/')) return
    setParsing(true)
    try {
      const extracted = await api.parseContactScreenshot(file)
      setForm(f => ({
        ...f,
        name: extracted.name || f.name,
        title: extracted.title || f.title,
        linkedin_url: extracted.linkedin_url || f.linkedin_url,
      }))
    } catch (e) {
      // silently ignore parse failures — form stays blank for manual entry
    } finally {
      setParsing(false)
    }
  }

  useEffect(() => {
    if (isEdit) return
    const onPaste = (e) => {
      const file = Array.from(e.clipboardData?.items || [])
        .find(i => i.type.startsWith('image/'))?.getAsFile()
      if (file) handleScreenshotPaste(file)
    }
    document.addEventListener('paste', onPaste)
    return () => document.removeEventListener('paste', onPaste)
  }, [isEdit])

  const handleSave = async () => {
    if (!isEdit && !form.name.trim()) return
    setSaving(true)
    const introducedById = form.introduced_by_contact_id ? Number(form.introduced_by_contact_id) : undefined
    try {
      if (isEdit) {
        await api.updateContact(contact.id, {
          title: form.title || undefined,
          met_via: form.met_via || undefined,
          relationship_notes: form.relationship_notes || undefined,
          introduced_by_contact_id: introducedById,
          referral_target_company_id: isReferral ? company.id : null,
          snooze_until: snoozeUntil || null,
        })
        if (linkedOutreach) {
          const datesChanged = due3 !== (linkedOutreach.follow_up_3_due || '') || due7 !== (linkedOutreach.follow_up_7_due || '')
          const needsContactLink = linkedOutreach.contact_id !== contact.id
          if (datesChanged || needsContactLink) {
            await api.patchOutreach(linkedOutreach.id, {
              ...(datesChanged ? { follow_up_3_due: due3 || null, follow_up_7_due: due7 || null } : {}),
              ...(needsContactLink ? { contact_id: contact.id } : {}),
            })
          }
        }
        onSaved()
      } else {
        const result = await api.quickAddContact({
          name: form.name.trim(),
          title: form.title || undefined,
          linkedin_url: form.linkedin_url || undefined,
          email: form.email || undefined,
          company_name: company.name,
          met_via: form.met_via || undefined,
          relationship_notes: form.relationship_notes || undefined,
          introduced_by_contact_id: introducedById,
        })
        if (isReferral && result.contact_id) {
          await api.updateContact(result.contact_id, { referral_target_company_id: company.id })
        }
        if (outreachDone && result.contact_id) {
          await api.createOutreach({
            company_id: company.id,
            contact_id: result.contact_id,
            channel: outreachChannel,
            sent_at: outreachDate + 'T00:00:00',
            subject: `${outreachChannel === 'linkedin' ? 'LinkedIn connection request' : 'Email outreach'} — ${form.name.trim()}`,
            body: `${outreachChannel === 'linkedin' ? 'Sent LinkedIn connection request' : 'Sent email outreach'} to ${form.name.trim()} at ${company.name}.`,
          })
        }
        if (result.next_step && !outreachDone) {
          setSavedContactName(form.name.trim())
          setNextStep(result.next_step)
        } else {
          onSaved()
        }
      }
    } catch (e) {
      alert(e.message)
      setSaving(false)
    }
  }

  if (nextStep) {
    return (
      <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50">
        <div className="bg-white dark:bg-slate-900 w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl shadow-xl p-5">
          <div className="text-sm font-semibold text-body mb-1">{savedContactName} added</div>
          <NextStepChip nextStep={nextStep} contactName={savedContactName} onDone={onSaved} />
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-slate-900 w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl shadow-xl flex flex-col" style={{maxHeight: '85dvh'}}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 pt-4 pb-3 border-b border-theme flex-shrink-0">
          <div className="text-sm font-semibold text-body">
            {isEdit ? `Edit — ${contact.name}` : `Add contact at ${company.name}`}
          </div>
          <button onClick={onClose} className="p-1 text-muted hover:text-body">
            <X size={18} />
          </button>
        </div>

        {/* Fields */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {!isEdit && (
            <>
              <div
                onDragOver={e => e.preventDefault()}
                onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleScreenshotPaste(f) }}
                className="border-2 border-dashed border-theme rounded-lg px-3 py-3 text-center text-xs text-muted cursor-default select-none"
              >
                {parsing ? (
                  <span className="animate-pulse">Parsing screenshot...</span>
                ) : (
                  <span>Paste or drop a LinkedIn screenshot to auto-fill</span>
                )}
              </div>
              <div>
                <label className="text-xs text-muted block mb-1">Name *</label>
                <input value={form.name} onChange={set('name')}
                  className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body"
                  placeholder="First Last" autoFocus />
              </div>
              <div>
                <label className="text-xs text-muted block mb-1">Title</label>
                <input value={form.title} onChange={set('title')}
                  className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body"
                  placeholder="VP Product" />
              </div>
              <div>
                <label className="text-xs text-muted block mb-1">LinkedIn URL</label>
                <input value={form.linkedin_url} onChange={set('linkedin_url')}
                  className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body"
                  placeholder="https://linkedin.com/in/..." />
              </div>
              <div>
                <label className="text-xs text-muted block mb-1">Email</label>
                <input value={form.email} onChange={set('email')} type="email"
                  className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body"
                  placeholder="name@company.com" />
              </div>
            </>
          )}

          {isEdit && (
            <div>
              <label className="text-xs text-muted block mb-1">Title</label>
              <input value={form.title} onChange={set('title')}
                className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body"
                placeholder="VP Product" />
            </div>
          )}

          <div>
            <label className="text-xs text-muted block mb-1">How you know them</label>
            <input value={form.met_via} onChange={set('met_via')}
              className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body"
              placeholder="Boston Fintech Week · Intro from Maria · LinkedIn DM" />
          </div>
          <div>
            <label className="text-xs text-muted block mb-1">Notes</label>
            <textarea value={form.relationship_notes} onChange={set('relationship_notes')}
              rows={2}
              className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body resize-none"
              placeholder="Runs payments infra team · interested in agentic AI" />
          </div>
          <div>
            <label className="text-xs text-muted block mb-1">Introduced by</label>
            <select value={form.introduced_by_contact_id} onChange={set('introduced_by_contact_id')}
              className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body">
              <option value="">— Direct connection / nobody —</option>
              {allContacts.filter(c => c.id !== contact?.id).map(c => (
                <option key={c.id} value={c.id}>
                  {c.name}{c.company_name ? ` @ ${c.company_name}` : ''}{c.title ? ` · ${c.title}` : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center justify-between border border-theme rounded-xl px-3 py-2.5 bg-slate-50 dark:bg-slate-900/40">
            <label className="text-xs font-medium text-body">Can refer me to {company.name}</label>
            <button
              type="button"
              onClick={() => setIsReferral(v => !v)}
              className={`relative w-10 h-5 rounded-full transition-colors ${isReferral ? 'bg-purple-500' : 'bg-slate-300 dark:bg-slate-600'}`}
            >
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${isReferral ? 'translate-x-5' : ''}`} />
            </button>
          </div>

          {isEdit && (
            <div className="border border-theme rounded-xl p-3 space-y-2 bg-slate-50 dark:bg-slate-900/40">
              <div className="text-xs font-medium text-body mb-1">Follow-up dates</div>
              <div className="flex gap-2">
                <div className="flex-1">
                  <label className="text-xs text-muted block mb-1">Day 3 bump</label>
                  <input
                    type="date"
                    value={due3}
                    onChange={e => setDue3(e.target.value)}
                    className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body"
                  />
                </div>
                <div className="flex-1">
                  <label className="text-xs text-muted block mb-1">Day 7 close</label>
                  <input
                    type="date"
                    value={due7}
                    onChange={e => setDue7(e.target.value)}
                    className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs text-muted block mb-1">Snooze — resurface on brief</label>
                <input
                  type="date"
                  value={snoozeUntil}
                  onChange={e => setSnoozeUntil(e.target.value)}
                  className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body"
                />
              </div>
            </div>
          )}

          {!isEdit && (
            <div className="border border-theme rounded-xl p-3 space-y-2 bg-slate-50 dark:bg-slate-900/40">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-body">Already reached out?</label>
                <button
                  type="button"
                  onClick={() => setOutreachDone(v => !v)}
                  className={`relative w-10 h-5 rounded-full transition-colors ${outreachDone ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-600'}`}
                >
                  <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${outreachDone ? 'translate-x-5' : ''}`} />
                </button>
              </div>
              {outreachDone && (
                <div className="space-y-2 pt-1">
                  <div className="flex gap-2">
                    {['linkedin', 'email'].map(ch => (
                      <button
                        key={ch}
                        type="button"
                        onClick={() => setOutreachChannel(ch)}
                        className={`flex-1 py-1.5 rounded-lg text-xs font-medium border transition-colors ${outreachChannel === ch ? 'bg-blue-500 text-white border-blue-500' : 'border-theme text-muted'}`}
                      >
                        {ch === 'linkedin' ? 'LinkedIn' : 'Email'}
                      </button>
                    ))}
                  </div>
                  <div>
                    <label className="text-xs text-muted block mb-1">Date sent</label>
                    <input
                      type="date"
                      value={outreachDate}
                      onChange={e => setOutreachDate(e.target.value)}
                      className="w-full border border-theme rounded-lg px-3 py-2 text-sm bg-card text-body"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Save button at bottom of scroll area */}
          <div className="pt-2 pb-2" style={{paddingBottom: 'calc(0.5rem + env(safe-area-inset-bottom))'}}>
            <button
              onClick={handleSave}
              disabled={saving || (!isEdit && !form.name.trim())}
              className="w-full bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-3 text-sm font-semibold transition-colors"
            >
              {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Add contact'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function PrepBriefModal({ company, brief, loading, onClose }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    if (!brief?.sections) return
    const text = brief.sections.map(s => `## ${s.title}\n\n${s.content}`).join('\n\n---\n\n')
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-slate-900 w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl shadow-xl flex flex-col" style={{maxHeight: '90dvh'}}>
        <div className="flex items-center justify-between px-4 pt-4 pb-3 border-b border-theme flex-shrink-0">
          <div className="flex items-center gap-2">
            <BookOpen size={15} className="text-purple-500" />
            <span className="text-sm font-semibold text-body">Meeting Prep - {company.name}</span>
          </div>
          <div className="flex items-center gap-3">
            {brief?.sections && (
              <button onClick={handleCopy} className="flex items-center gap-1 text-xs text-muted hover:text-body">
                {copied ? <Check size={13} className="text-green-500" /> : <Copy size={13} />}
                {copied ? 'Copied' : 'Copy all'}
              </button>
            )}
            <button onClick={onClose} className="p-1 text-muted hover:text-body"><X size={18} /></button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4">
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Spinner size={6} />
              <span className="text-sm text-muted">Generating brief - this takes about 15 seconds...</span>
            </div>
          )}
          {!loading && brief?.error && (
            <div className="text-sm text-red-500 py-4">{brief.error}</div>
          )}
          {!loading && brief?.sections && (
            <div className="space-y-5">
              {brief.sections.map((section, i) => (
                <div key={i}>
                  <div className="text-xs font-semibold uppercase tracking-wide text-purple-600 dark:text-purple-400 mb-2">
                    {section.title}
                  </div>
                  <div className="text-sm text-body leading-relaxed whitespace-pre-wrap">
                    {section.content}
                  </div>
                </div>
              ))}
              <div className="text-xs text-muted pt-2 border-t border-theme">
                Generated {brief.generated_at ? brief.generated_at.slice(0, 16).replace('T', ' ') + ' UTC' : ''}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function NetworkPath({ companyId }) {
  const [path, setPath] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async (refresh = false) => {
    setLoading(true)
    try {
      const result = await api.getNetworkPath(companyId, refresh)
      setPath(result)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(false) }, [companyId])

  return (
    <div className="bg-card border border-theme rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <Network size={13} className="text-muted" />
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">Network Path</span>
        </div>
        <button onClick={() => load(true)} disabled={loading} className="text-xs text-blue-500 disabled:opacity-50 flex items-center gap-1.5">
          {loading ? 'Analyzing…' : path ? 'Re-analyze' : 'Analyze'}
        </button>
      </div>

      {loading && <div className="flex justify-center py-4"><Spinner size={5} /></div>}

      {path && !loading && (
        <div className="space-y-3">
          {path.direct_connections.length > 0 ? (
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl p-3">
              <div className="text-xs font-semibold text-green-700 dark:text-green-400 mb-2">
                Direct connections ({path.direct_connections.length})
              </div>
              {path.direct_connections.map((c, i) => (
                <div key={i} className="text-xs text-body mb-1">
                  <span className="font-medium">{c.name}</span>
                  {c.title && <span className="text-muted"> — {c.title}</span>}
                  {c.met_via && <span className="text-blue-500"> · via {c.met_via}</span>}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-muted">No direct connections yet — import LinkedIn CSV in Settings to find warm paths.</div>
          )}

          {path.likely_connectors.length > 0 && (
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-3">
              <div className="text-xs font-semibold text-blue-700 dark:text-blue-400 mb-2">
                Ask for intro
              </div>
              {path.likely_connectors.map((c, i) => (
                <div key={i} className="mb-2">
                  <div className="text-xs font-medium text-body">{c.name}{c.title ? ` (${c.title})` : ''}</div>
                  <div className="text-xs text-muted leading-relaxed">{c.reason}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!path && !loading && (
        <div className="text-xs text-muted text-center py-2">Tap Analyze to find your network path in</div>
      )}
    </div>
  )
}

function OutreachHistoryCard({ o, onResponseUpdate, onUseAsContext, onDatesUpdated }) {
  const [expanded, setExpanded] = useState(false)
  const [editingDates, setEditingDates] = useState(false)
  const [due3, setDue3] = useState(o.follow_up_3_due || '')
  const [due7, setDue7] = useState(o.follow_up_7_due || '')
  const [savingDates, setSavingDates] = useState(false)
  const hasBody = !!o.body

  const handleSaveDates = async () => {
    setSavingDates(true)
    try {
      await api.patchOutreach(o.id, { follow_up_3_due: due3 || null, follow_up_7_due: due7 || null })
      setEditingDates(false)
      onDatesUpdated?.()
    } catch (e) { alert(e.message) } finally { setSavingDates(false) }
  }

  return (
    <div className="bg-card border border-theme rounded-xl p-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-body">{o.subject || o.channel}</span>
        <Badge color={
          o.response_status === 'positive' ? 'green' :
          o.response_status === 'negative' ? 'red' :
          o.response_status === 'ghosted' ? 'slate' : 'yellow'
        }>{o.response_status}</Badge>
      </div>
      <div className="text-xs text-muted mb-2 flex items-center gap-2 flex-wrap">
        <span>{o.sent_at ? `Sent ${o.sent_at.slice(0, 10)}` : 'Draft'}</span>
        {!editingDates && (
          <>
            {due3 && <span>· D3 {due3}</span>}
            {due7 && <span>· D7 {due7}</span>}
            <button onClick={() => setEditingDates(true)} className="text-blue-500 underline">Edit dates</button>
          </>
        )}
      </div>
      {editingDates && (
        <div className="mb-2 flex flex-wrap gap-2 items-end">
          <div>
            <label className="text-[10px] text-muted block mb-0.5">Day 3 due</label>
            <input type="date" value={due3} onChange={e => setDue3(e.target.value)}
              className="border border-theme rounded-lg px-2 py-1 text-xs bg-card text-body" />
          </div>
          <div>
            <label className="text-[10px] text-muted block mb-0.5">Day 7 due</label>
            <input type="date" value={due7} onChange={e => setDue7(e.target.value)}
              className="border border-theme rounded-lg px-2 py-1 text-xs bg-card text-body" />
          </div>
          <button onClick={handleSaveDates} disabled={savingDates}
            className="text-xs bg-blue-500 text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
            {savingDates ? 'Saving…' : 'Save'}
          </button>
          <button onClick={() => setEditingDates(false)} className="text-xs text-muted">Cancel</button>
        </div>
      )}

      {hasBody && (
        <>
          <div
            className={`text-xs text-muted leading-relaxed whitespace-pre-wrap ${expanded ? '' : 'line-clamp-2'}`}
          >
            {o.body}
          </div>
          <div className="flex items-center gap-3 mt-2">
            <button
              onClick={() => setExpanded(v => !v)}
              className="flex items-center gap-1 text-xs text-blue-500 hover:text-blue-400"
            >
              {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
              {expanded ? 'Collapse' : 'Show full email'}
            </button>
            {expanded && (
              <button
                onClick={() => {
                  const ctx = o.subject
                    ? `Previous email (${o.sent_at?.slice(0, 10)}):\nSubject: ${o.subject}\n\n${o.body}`
                    : `Previous email (${o.sent_at?.slice(0, 10)}):\n\n${o.body}`
                  onUseAsContext(ctx)
                  // Scroll to context field
                  document.getElementById('outreach-context')?.scrollIntoView({ behavior: 'smooth' })
                }}
                className="text-xs text-amber-400 hover:text-amber-300"
              >
                Use as context ↑
              </button>
            )}
          </div>
        </>
      )}

      {!hasBody && (
        <div className="text-xs text-faint italic">
          {o.channel === 'linkedin' ? 'LinkedIn outreach — no message body' : 'No message body stored'}
        </div>
      )}

      {o.response_status === 'pending' && (
        <div className="flex gap-2 mt-3">
          {['positive', 'negative', 'ghosted'].map(s => (
            <button key={s} onClick={() => onResponseUpdate(o.id, s)}
              className="flex-1 text-xs py-1.5 rounded-lg border border-theme bg-card2 text-muted hover:text-body capitalize transition-colors">
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function OutreachTab({ company, onReload, defaultContactId }) {
  const [emailType, setEmailType] = useState('cold')
  const [context, setContext] = useState('')
  const [hook, setHook] = useState('')
  const [ask, setAsk] = useState('')
  const [selectedContact, setSelectedContact] = useState(defaultContactId || company.contacts?.[0]?.id || null)
  const [generating, setGenerating] = useState(false)
  const [draft, setDraft] = useState(null)
  const [logging, setLogging] = useState(false)
  const [copied, setCopied] = useState(false)
  const [refineCopied, setRefineCopied] = useState(false)
  const [undoId, setUndoId] = useState(null)
  const [awaitingConfirm, setAwaitingConfirm] = useState(null) // 'gmail' | 'dm' | null

  const selectedContactObj = company.contacts?.find(c => c.id === selectedContact) || null
  const contactEmail = selectedContactObj?.email || null

  const handleGenerate = async () => {
    setGenerating(true)
    setDraft(null)
    setAwaitingConfirm(null)
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

  const _doLog = async (channel = 'email') => {
    const result = await api.logOutreach({
      company_id: company.id,
      contact_id: selectedContact || undefined,
      channel,
      subject: draft.subject,
      body: draft.body,
      sent_at: new Date().toISOString(),
    })
    return result.id
  }

  const handleSendViaGmail = async () => {
    if (!draft) return
    const to = encodeURIComponent(contactEmail || '')
    const subject = encodeURIComponent(draft.subject || '')
    const body = encodeURIComponent(draft.body || '')
    window.open(`mailto:${to}?subject=${subject}&body=${body}`, '_self')
    setAwaitingConfirm('gmail')
  }

  const handleCopyForDM = async () => {
    if (!draft) return
    await navigator.clipboard.writeText(draft.body)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
    setAwaitingConfirm('dm')
  }

  const handleConfirmSent = async () => {
    setLogging(true)
    try {
      const channel = awaitingConfirm === 'dm' ? 'linkedin' : 'email'
      const savedDraft = draft
      const id = await _doLog(channel)
      setDraft(null)
      setContext('')
      setHook('')
      setAsk('')
      setAwaitingConfirm(null)
      setUndoId({ id, draft: savedDraft })
      onReload()
    } catch (e) {
      alert(e.message)
    } finally {
      setLogging(false)
    }
  }

  const handleConfirmBack = () => {
    setAwaitingConfirm(null)
  }

  const handleUndo = async () => {
    if (!undoId) return
    try {
      await api.deleteOutreach(undoId.id)
      setDraft(undoId.draft)
      setUndoId(null)
      onReload()
    } catch (e) {
      alert(e.message)
    }
  }

  const handleWriteMyself = () => {
    setDraft({ subject: '', body: '', manual: true, contact_name: selectedContactObj?.name })
    setAwaitingConfirm(null)
  }

  const handleCopyFull = () => {
    const text = draft.subject ? `Subject: ${draft.subject}\n\n${draft.body}` : draft.body
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleRefineWithAI = async () => {
    if (!draft) return
    const contactName = selectedContactObj?.name || 'the contact'
    const contactTitle = selectedContactObj?.title || ''
    const channelLabel = emailType === 'linkedin_dm' ? 'LinkedIn DM' : 'email'
    const prompt = [
      `You are helping Santiago Aldana refine an outreach ${channelLabel}. Here is his full context:`,
      ``,
      `SANTIAGO'S PROFILE: MIT Sloan MBA, 20+ years in FinTech/AI/payments/LATAM leadership. Serial founder. Core expertise: BaaS, Embedded Finance, Agentic AI for Financial Services, Digital Identity, Cross-border Payments. Currently based in Boston. Target roles: C-suite or SVP at growth-stage fintechs. Key credentials: built SoyYo (Colombia's national biometric identity layer), scaled Avianca LifeMiles, Uff Movil (MVNO in complex regulatory markets).`,
      ``,
      `CONTACT: ${contactName}${contactTitle ? `, ${contactTitle}` : ''} at ${company.name}`,
      context ? `CONTEXT: ${context}` : '',
      ``,
      `## Current draft`,
      draft.subject ? `Subject: ${draft.subject}` : '',
      draft.body,
      ``,
      `## Style rules (non-negotiable)`,
      `- 75 words max in the body`,
      `- At least half the words must be about the contact or their company's situation, not Santiago`,
      `- Open with something specific and verifiable about their work, not a generic compliment`,
      `- One Santiago credential woven in naturally as evidence, not as the pitch (SoyYo, Avianca, Uff Movil, MIT Sloan)`,
      `- End with a light ask about their perspective, not Santiago's needs ("15 min to hear how you see X evolving")`,
      `- No em dashes, no hyphens, no en dashes`,
      `- No signature block`,
      `- No forbidden phrases: "hope this finds you", "excited to", "pick your brain", "circle back", "touch base", "synergy", "leverage"`,
      `- LATAM experience is proof of complexity, not the hook — only mention if directly relevant to their work`,
      ``,
      `Return the improved draft only — subject line first (if email), then body. No explanation, no commentary.`,
    ].filter(l => l !== null).join('\n')

    await navigator.clipboard.writeText(prompt)
    window.open('https://claude.ai/new', '_blank')
    setRefineCopied(true)
    setTimeout(() => setRefineCopied(false), 6000)
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
          { value: 'linkedin_dm', label: 'LinkedIn DM' },
        ].map(t => (
          <button key={t.value} onClick={() => { setEmailType(t.value); setDraft(null); setAwaitingConfirm(null) }}
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
        <div className="space-y-1.5">
          <div className="text-xs text-muted font-medium uppercase tracking-wide">Contact</div>
          <div className="space-y-1.5">
            {[{ id: null, name: 'No specific contact' }, ...company.contacts].map(c => {
              const isSelected = selectedContact === c.id
              const contact = company.contacts.find(x => x.id === c.id)
              return (
                <button
                  key={c.id ?? 'none'}
                  onClick={() => {
                    setSelectedContact(c.id)
                    setDraft(null)
                    setAwaitingConfirm(null)
                    if (contact?.met_via && !context) setContext(`Met via ${contact.met_via}${contact.relationship_notes ? '. ' + contact.relationship_notes : ''}`)
                  }}
                  className={`w-full text-left rounded-xl px-3 py-2.5 border transition-all ${
                    isSelected ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-400' : 'bg-card border-theme'
                  }`}
                >
                  <div className="text-sm font-medium text-body">{c.name}</div>
                  {contact && (
                    <div className="text-xs text-muted mt-0.5 space-y-0.5">
                      {contact.title && <div>{contact.title}</div>}
                      {contact.met_via && <div className="text-blue-500">Met via {contact.met_via}</div>}
                      {contact.relationship_notes && <div className="italic">{contact.relationship_notes}</div>}
                      {contact.connected_on && <div>Connected {contact.connected_on}</div>}
                      {contact.warmth && contact.warmth !== 'cold' && (
                        <div className={contact.warmth === 'hot' ? 'text-red-500' : 'text-orange-500'}>
                          {contact.warmth} contact
                        </div>
                      )}
                    </div>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Draft card */}
      {draft ? (
        <div className="bg-card border border-blue-300 dark:border-blue-700 rounded-xl overflow-hidden">
          {/* Confirmation overlay */}
          {awaitingConfirm ? (
            <div className="p-4 space-y-3">
              <div className="text-sm text-body">
                {awaitingConfirm === 'gmail'
                  ? `Gmail opened with ${contactEmail || 'your email client'}. Did you send it?`
                  : `DM copied to clipboard. Did you send it?`}
              </div>
              <div className="flex gap-2">
                <button onClick={handleConfirmBack}
                  className="flex-1 border border-theme text-body rounded-xl py-2.5 text-sm font-medium">
                  Back
                </button>
                <button onClick={handleConfirmSent} disabled={logging}
                  className="flex-1 bg-green-500 hover:bg-green-600 disabled:opacity-50 text-white rounded-xl py-2.5 text-sm font-semibold">
                  {logging ? 'Saving…' : 'Yes, sent'}
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* Draft header */}
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-theme bg-blue-50 dark:bg-blue-950/40">
                <div className="flex items-center gap-2">
                  {selectedContactObj && (
                    <span className="text-xs text-blue-700 dark:text-blue-300 font-medium">
                      To: {selectedContactObj.name}
                      {contactEmail && <span className="text-blue-500 ml-1">· {contactEmail}</span>}
                    </span>
                  )}
                  {draft.word_count && (
                    <span className={`text-xs ${draft.word_count > 75 ? 'text-orange-500' : 'text-green-600 dark:text-green-400'}`}>
                      {draft.word_count}w
                    </span>
                  )}
                </div>
                <button onClick={handleCopyFull}
                  className="flex items-center gap-1 text-xs text-muted hover:text-body">
                  {copied ? <><Check size={12} className="text-green-500" /> Copied</> : <><Copy size={12} /> Copy</>}
                </button>
              </div>

              {/* Editable draft body */}
              <div className="p-4 space-y-2">
                {emailType !== 'linkedin_dm' && (
                  <input
                    value={draft.subject}
                    onChange={e => setDraft(d => ({ ...d, subject: e.target.value }))}
                    placeholder="Subject"
                    className="w-full text-sm font-semibold text-body bg-transparent border-b border-theme pb-1 outline-none"
                  />
                )}
                <textarea
                  value={draft.body}
                  onChange={e => setDraft(d => ({ ...d, body: e.target.value }))}
                  placeholder="Write your message…"
                  rows={6}
                  className="w-full text-sm text-body bg-transparent outline-none resize-none leading-relaxed"
                />
              </div>

              {/* Refine with AI link */}
              <div className="px-4 pb-3">
                <button onClick={handleRefineWithAI}
                  className="text-xs text-blue-500 hover:text-blue-600 flex items-center gap-1">
                  {refineCopied
                    ? <><Check size={11} className="text-green-500" /> Prompt copied — paste into Claude, then paste the response back above</>
                    : <><ExternalLink size={11} /> Refine with AI</>}
                </button>
              </div>

              {/* Send actions */}
              <div className="flex gap-2 px-4 pb-3">
                <button onClick={handleGenerate} disabled={generating}
                  className="border border-theme text-muted rounded-lg py-2 px-3 text-xs font-medium">
                  {generating ? <RefreshCw size={12} className="animate-spin" /> : 'Regenerate'}
                </button>
                {emailType === 'linkedin_dm' || !contactEmail ? (
                  <button onClick={handleCopyForDM}
                    className="flex-1 bg-blue-500 hover:bg-blue-600 text-white rounded-lg py-2 text-xs font-semibold flex items-center justify-center gap-1.5">
                    <Copy size={12} /> Copy for DM
                  </button>
                ) : (
                  <button onClick={handleSendViaGmail}
                    className="flex-1 bg-blue-500 hover:bg-blue-600 text-white rounded-lg py-2 text-xs font-semibold flex items-center justify-center gap-1.5">
                    <Send size={12} /> Send via Gmail
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      ) : (
        /* No draft yet — show generate buttons */
        <div className="flex gap-2">
          <button onClick={handleWriteMyself}
            className="flex-1 border border-theme text-body rounded-xl py-3 text-sm font-medium transition-colors">
            Write myself
          </button>
          <button onClick={handleGenerate} disabled={generating}
            className="flex-1 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-3 text-sm font-medium transition-colors flex items-center justify-center gap-2">
            {generating ? <><RefreshCw size={14} className="animate-spin" /> Drafting…</> : <><Send size={14} /> Draft</>}
          </button>
        </div>
      )}

      {/* Customize disclosure */}
      <details className="group">
        <summary className="text-xs text-blue-500 cursor-pointer list-none flex items-center gap-1 select-none">
          <ChevronRight size={12} className="group-open:rotate-90 transition-transform" /> Customize draft
        </summary>
        <div className="mt-2 space-y-2">
          <textarea
            id="outreach-context"
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
            placeholder='Specific angle or topic to lead with'
            className="w-full bg-card border border-theme rounded-xl px-3 py-2.5 text-sm text-body placeholder-faint outline-none"
          />
          <input
            value={ask}
            onChange={e => setAsk(e.target.value)}
            placeholder='What you want from this message'
            className="w-full bg-card border border-theme rounded-xl px-3 py-2.5 text-sm text-body placeholder-faint outline-none"
          />
          <button onClick={handleGenerate} disabled={generating}
            className="w-full bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl py-2.5 text-sm font-medium flex items-center justify-center gap-2">
            {generating ? <><RefreshCw size={14} className="animate-spin" /> Drafting…</> : 'Regenerate with context'}
          </button>
        </div>
      </details>

      {/* Undo banner */}
      {undoId && (
        <div className="flex items-center justify-between bg-green-50 dark:bg-green-950/40 border border-green-200 dark:border-green-800 rounded-xl px-4 py-2.5">
          <span className="text-xs text-green-700 dark:text-green-300">Logged as sent</span>
          <button onClick={handleUndo} className="text-xs font-medium text-green-700 dark:text-green-300 underline">
            Undo
          </button>
        </div>
      )}

      {/* Outreach history */}
      {(!company.outreach || company.outreach.length === 0) ? (
        <div className="text-center text-muted text-sm py-6">No outreach logged yet</div>
      ) : (
        <div className="space-y-3 pt-2">
          <div className="text-xs text-muted font-medium uppercase tracking-wide">History</div>
          {company.outreach.map(o => (
            <OutreachHistoryCard
              key={o.id}
              o={o}
              onResponseUpdate={handleResponseUpdate}
              onUseAsContext={(text) => setContext(text)}
              onDatesUpdated={onReload}
            />
          ))}
        </div>
      )}
    </div>
  )
}
