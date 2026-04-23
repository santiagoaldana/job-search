import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Search, X } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Badge from '../components/Badge'
import Spinner from '../components/Spinner'

const STAGES = ['pool', 'researched', 'outreach', 'response', 'meeting', 'applied', 'interview', 'offer']

const STAGE_COLORS = {
  pool: 'slate', researched: 'blue', outreach: 'yellow', response: 'orange',
  meeting: 'purple', applied: 'indigo', interview: 'pink', offer: 'green',
}

const FUNDING_BADGE = {
  series_b: { label: 'Series B', color: 'blue' },
  series_c: { label: 'Series C', color: 'purple' },
  series_d: { label: 'Series D', color: 'orange' },
  public:   { label: 'Public', color: 'green' },
  unknown:  { label: '?', color: 'slate' },
}

const CHANNELS = ['email', 'linkedin', 'referral']

function OutreachModal({ company, onClose, onSaved }) {
  const [contact, setContact] = useState('')
  const [channel, setChannel] = useState('email')
  const [subject, setSubject] = useState('')
  const [saving, setSaving] = useState(false)

  async function save() {
    if (!contact.trim()) return
    setSaving(true)
    try {
      await api.logOutreach({
        company_id: company.id,
        channel,
        subject: subject || `Outreach to ${contact}`,
        body: contact,
      })
      onSaved()
    } catch (e) {
      alert(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-end justify-center" onClick={onClose}>
      <div className="bg-card w-full max-w-lg rounded-t-2xl p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div className="font-semibold text-body">Log Outreach — {company.name}</div>
          <button onClick={onClose}><X size={18} className="text-muted" /></button>
        </div>

        <div>
          <label className="text-xs text-muted mb-1 block">Contact name *</label>
          <input
            className="w-full bg-bg border border-theme rounded-lg px-3 py-2 text-sm text-body"
            placeholder="e.g. Rafael Ayala"
            value={contact}
            onChange={e => setContact(e.target.value)}
            autoFocus
          />
        </div>

        <div>
          <label className="text-xs text-muted mb-1 block">Channel</label>
          <div className="flex gap-2">
            {CHANNELS.map(c => (
              <button
                key={c}
                onClick={() => setChannel(c)}
                className={`flex-1 py-2 rounded-lg text-xs font-medium border transition-colors ${
                  channel === c ? 'bg-blue-500 border-blue-400 text-white' : 'bg-bg border-theme text-muted'
                }`}
              >
                {c.charAt(0).toUpperCase() + c.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-xs text-muted mb-1 block">Subject / notes (optional)</label>
          <input
            className="w-full bg-bg border border-theme rounded-lg px-3 py-2 text-sm text-body"
            placeholder="e.g. Director of Product, Risk & Fraud"
            value={subject}
            onChange={e => setSubject(e.target.value)}
          />
        </div>

        <button
          onClick={save}
          disabled={saving || !contact.trim()}
          className="w-full bg-blue-500 text-white rounded-xl py-3 text-sm font-medium disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Log Outreach + Schedule Follow-ups'}
        </button>
      </div>
    </div>
  )
}

function MotivationEdit({ company, onUpdated }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(company.motivation)

  async function save() {
    setEditing(false)
    if (val !== company.motivation) {
      await api.updateCompany(company.id, { motivation: val })
      onUpdated()
    }
  }

  if (editing) {
    return (
      <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
        <input
          type="number" min="1" max="10"
          className="w-12 bg-bg border border-theme rounded px-1 py-0.5 text-xs text-body text-center"
          value={val}
          onChange={e => setVal(Number(e.target.value))}
          onBlur={save}
          autoFocus
        />
        <span className="text-xs text-muted">/10</span>
      </div>
    )
  }
  return (
    <button
      onClick={e => { e.stopPropagation(); setEditing(true) }}
      className="text-xs text-muted hover:text-blue-500 transition-colors"
    >
      Motivation {val}/10
    </button>
  )
}

export default function Funnel() {
  const [funnel, setFunnel] = useState({})
  const [loading, setLoading] = useState(true)
  const [activeStage, setActiveStage] = useState('pool')
  const [searchQ, setSearchQ] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [outreachTarget, setOutreachTarget] = useState(null)
  const debounceRef = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    loadFunnel()
  }, [])

  function loadFunnel() {
    setLoading(true)
    api.getFunnel()
      .then(setFunnel)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    clearTimeout(debounceRef.current)
    if (!searchQ.trim()) { setSearchResults([]); return }
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      try {
        const results = await api.getCompanies({ q: searchQ, active_only: false })
        setSearchResults(results)
      } catch (e) {
        console.error(e)
      } finally {
        setSearching(false)
      }
    }, 300)
  }, [searchQ])

  async function addCompany() {
    const name = searchQ.trim()
    if (!name) return
    const company = await api.createCompany({ name, motivation: 7 })
    setOutreachTarget(company)
    setSearchQ('')
  }

  const isSearching = searchQ.trim().length > 0
  const companies = funnel[activeStage] || []
  const totalActive = Object.values(funnel).flat().length

  return (
    <div className="flex flex-col">
      <PageHeader title="Pipeline" subtitle={`${totalActive} active companies`} />

      {/* Search bar */}
      <div className="px-4 pb-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            className="w-full bg-card border border-theme rounded-xl pl-8 pr-8 py-2 text-sm text-body placeholder:text-faint"
            placeholder="Search all companies…"
            value={searchQ}
            onChange={e => setSearchQ(e.target.value)}
          />
          {searchQ && (
            <button className="absolute right-3 top-1/2 -translate-y-1/2" onClick={() => setSearchQ('')}>
              <X size={14} className="text-muted" />
            </button>
          )}
        </div>
      </div>

      {/* Stage tabs — hidden while searching */}
      {!isSearching && (
        <div className="flex gap-2 px-4 pb-3 overflow-x-auto" style={{ scrollbarWidth: 'none' }}>
          {STAGES.map(s => {
            const count = (funnel[s] || []).length
            return (
              <button
                key={s}
                onClick={() => setActiveStage(s)}
                className={`flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                  activeStage === s
                    ? 'bg-blue-500 border-blue-400 text-white'
                    : 'bg-card border-theme text-muted'
                }`}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}
                {count > 0 && <span className="ml-1 opacity-60">{count}</span>}
              </button>
            )
          })}
        </div>
      )}

      {/* Search results */}
      {isSearching ? (
        <div className="px-4 space-y-3 pb-4">
          {searching && <div className="flex justify-center py-8"><Spinner size={6} /></div>}
          {!searching && searchResults.length === 0 && (
            <div className="py-8 text-center space-y-3">
              <div className="text-sm text-muted">No companies found for "{searchQ}"</div>
              <button
                onClick={addCompany}
                className="bg-blue-500 text-white text-sm rounded-xl px-4 py-2"
              >
                + Add "{searchQ}" to list
              </button>
            </div>
          )}
          {!searching && searchResults.map(c => (
            <SearchResultCard
              key={c.id}
              company={c}
              onNavigate={() => navigate(`/company/${c.id}`)}
              onLogOutreach={() => setOutreachTarget(c)}
              onUpdated={loadFunnel}
            />
          ))}
        </div>
      ) : (
        /* Normal kanban list */
        loading ? (
          <div className="flex justify-center py-16"><Spinner size={8} /></div>
        ) : (
          <div className="px-4 space-y-3 pb-4">
            {companies.length === 0 && (
              <div className="py-12 text-center text-muted text-sm">
                No companies in {activeStage} stage
              </div>
            )}
            {companies.map(c => {
              const funding = FUNDING_BADGE[c.funding_stage] || FUNDING_BADGE.unknown
              return (
                <button
                  key={c.id}
                  onClick={() => navigate(`/company/${c.id}`)}
                  className="w-full text-left bg-card border border-theme rounded-xl p-4 hover:border-theme2 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-body truncate">{c.name}</div>
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        <Badge color={funding.color}>{funding.label}</Badge>
                        <span className="text-xs text-muted">LAMP {c.lamp_score?.toFixed(0) || '—'}</span>
                        <span className="text-xs text-muted">Motivation {c.motivation}/10</span>
                      </div>
                    </div>
                    <ChevronRight size={16} className="text-faint mt-1 flex-shrink-0" />
                  </div>
                </button>
              )
            })}
          </div>
        )
      )}

      {outreachTarget && (
        <OutreachModal
          company={outreachTarget}
          onClose={() => setOutreachTarget(null)}
          onSaved={() => { setOutreachTarget(null); setSearchQ(''); loadFunnel() }}
        />
      )}
    </div>
  )
}

function SearchResultCard({ company, onNavigate, onLogOutreach, onUpdated }) {
  const funding = FUNDING_BADGE[company.funding_stage] || FUNDING_BADGE.unknown
  const stageColor = STAGE_COLORS[company.stage] || 'slate'
  return (
    <div className="bg-card border border-theme rounded-xl p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <button className="flex-1 text-left" onClick={onNavigate}>
          <div className="font-semibold text-body truncate">{company.name}</div>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <Badge color={stageColor}>{company.stage}</Badge>
            <Badge color={funding.color}>{funding.label}</Badge>
            <MotivationEdit company={company} onUpdated={onUpdated} />
          </div>
        </button>
      </div>
      <button
        onClick={onLogOutreach}
        className="w-full text-center text-xs text-blue-500 border border-blue-300 rounded-lg py-1.5 hover:bg-blue-50 dark:hover:bg-blue-950/30 transition-colors"
      >
        Log Outreach
      </button>
    </div>
  )
}
