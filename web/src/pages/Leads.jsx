import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { RefreshCw, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Badge from '../components/Badge'
import FitBar from '../components/FitBar'
import Spinner from '../components/Spinner'
import AICostBadge from '../components/AICostBadge'

export default function Leads() {
  const [leads, setLeads] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [minFit, setMinFit] = useState(65)
  const [locationOnly, setLocationOnly] = useState(false)
  const [expanded, setExpanded] = useState({})
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const companyFilter = searchParams.get('company_id') ? Number(searchParams.get('company_id')) : null

  const load = async () => {
    setLoading(true)
    try {
      const params = { status: 'active' }
      if (minFit > 0) params.min_fit = minFit
      if (locationOnly) params.location_compatible = true
      if (companyFilter) params.company_id = companyFilter

      // Also load applied leads
      const [activeLeads, appliedLeads] = await Promise.all([
        api.getLeads(params),
        api.getLeads({ ...params, status: 'applied', min_fit: undefined }),
      ])
      setLeads([...activeLeads, ...appliedLeads])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [minFit, locationOnly, companyFilter])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await api.refreshLeads()
      alert('Lead refresh started. Check back in a few minutes.')
    } catch (e) {
      alert(e.message)
    } finally {
      setRefreshing(false)
    }
  }

  const handleMarkApplied = async (leadId) => {
    try {
      await api.updateLeadStatus(leadId, 'applied')
      setLeads(prev => prev.map(l => l.id === leadId ? { ...l, status: 'applied' } : l))
    } catch (e) {
      alert(e.message)
    }
  }

  const handleSalaryParsed = (updated) => {
    setLeads(prev => prev.map(l => l.id === updated.id ? { ...l, ...updated } : l))
  }

  const toggleExpanded = (id) => setExpanded(e => ({ ...e, [id]: !e[id] }))

  const sorted = [...leads].sort((a, b) => {
    if (a.location_compatible !== b.location_compatible)
      return (b.location_compatible ? 1 : 0) - (a.location_compatible ? 1 : 0)
    return (b.fit_score || 0) - (a.fit_score || 0)
  })

  const active = sorted.filter(l => l.status === 'active')
  const applied = sorted.filter(l => l.status === 'applied')

  const subtitle = companyFilter
    ? `Filtered by company · ${active.length} active`
    : `${active.length} active${minFit > 0 ? ` · fit ≥ ${minFit}%` : ''}${applied.length > 0 ? ` · ${applied.length} applied` : ''}`

  return (
    <div className="flex flex-col">
      <PageHeader
        title="Leads"
        subtitle={subtitle}
        action={
          <button onClick={handleRefresh} disabled={refreshing}
            className="flex items-center gap-1.5 text-sm text-blue-500 disabled:opacity-50">
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        }
      />

      {/* Filter bar */}
      <div className="px-4 pb-3 space-y-2">
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-muted">
            <span>Min fit score</span>
            <span className={minFit >= 65 ? 'text-orange-500 font-medium' : 'text-muted'}>
              {minFit > 0 ? `${minFit}%` : 'All'}
            </span>
          </div>
          <div className="relative">
            <input
              type="range" min={0} max={100} step={5}
              value={minFit}
              onChange={e => setMinFit(Number(e.target.value))}
              className="w-full accent-blue-500"
            />
            <div className="absolute top-0 flex flex-col items-center pointer-events-none"
              style={{ left: '65%', transform: 'translateX(-50%)' }}>
              <div className="w-px h-2 bg-orange-400 mt-1" />
              <span className="text-[10px] text-orange-400 mt-0.5">65%</span>
            </div>
          </div>
        </div>
        <button
          onClick={() => setLocationOnly(v => !v)}
          className={`w-full px-3 py-2 rounded-lg text-xs border transition-colors font-medium ${
            locationOnly ? 'bg-blue-500 border-blue-400 text-white' : 'bg-card border-theme text-muted'
          }`}
        >
          Boston / Remote
        </button>
      </div>

      {companyFilter && (
        <div className="mx-4 mb-3 flex items-center justify-between bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 rounded-xl px-3 py-2">
          <span className="text-xs text-blue-600 dark:text-blue-300">Filtered by company</span>
          <button
            onClick={() => navigate('/leads')}
            className="text-xs text-blue-500 underline"
          >
            Clear filter
          </button>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16"><Spinner size={8} /></div>
      ) : (
        <div className="px-4 space-y-3 pb-4">
          {active.length === 0 && applied.length === 0 && (
            <div className="py-12 text-center text-muted text-sm">No leads match your filters</div>
          )}

          {active.map(lead => (
            <LeadCard
              key={lead.id}
              lead={lead}
              expanded={expanded[lead.id]}
              onToggle={() => toggleExpanded(lead.id)}
              onMarkApplied={handleMarkApplied}
              onSalaryParsed={handleSalaryParsed}
              navigate={navigate}
            />
          ))}

          {applied.length > 0 && (
            <>
              <div className="text-xs text-muted font-semibold uppercase tracking-wide pt-2 pb-1">
                Applied ({applied.length})
              </div>
              {applied.map(lead => (
                <LeadCard
                  key={lead.id}
                  lead={lead}
                  expanded={expanded[lead.id]}
                  onToggle={() => toggleExpanded(lead.id)}
                  onMarkApplied={handleMarkApplied}
                  onSalaryParsed={handleSalaryParsed}
                  navigate={navigate}
                />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function fmtSalary(lead) {
  if (!lead.salary_min && !lead.salary_max) return null
  const cur = lead.salary_currency || 'USD'
  const fmt = (n) => n?.toLocaleString()
  if (lead.salary_min && lead.salary_max)
    return `${cur} ${fmt(lead.salary_min)} – ${fmt(lead.salary_max)}`
  if (lead.salary_min) return `${cur} ${fmt(lead.salary_min)}+`
  return `Up to ${cur} ${fmt(lead.salary_max)}`
}

function LeadCard({ lead, expanded, onToggle, onMarkApplied, onSalaryParsed, navigate }) {
  const [parsingSalary, setParsingSalary] = useState(false)
  const isHot = lead.fit_score >= 65 && lead.location_compatible && lead.status !== 'applied'
  const isApplied = lead.status === 'applied'

  let strengths = []
  let gaps = []
  try { strengths = JSON.parse(lead.fit_strengths || '[]') } catch {}
  try { gaps = JSON.parse(lead.fit_gaps || '[]') } catch {}
  const hasDetails = strengths.length > 0 || gaps.length > 0

  const handleParseSalary = async () => {
    setParsingSalary(true)
    try {
      const updated = await api.parseSalary(lead.id)
      onSalaryParsed(updated)
    } catch (e) { console.error(e) } finally { setParsingSalary(false) }
  }

  const salaryStr = fmtSalary(lead)

  return (
    <div className={`bg-card border rounded-xl p-4 ${
      isApplied ? 'border-green-300 dark:border-green-700' :
      isHot ? 'border-orange-300 dark:border-orange-600' :
      !lead.location_compatible ? 'border-theme opacity-60' :
      'border-theme'
    }`}>
      {/* Row 1: Title + badges */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="font-medium text-body text-sm leading-snug">{lead.title}</div>
          <div className="text-xs text-muted mt-0.5">
            {lead.company_name || `Company #${lead.company_id}`} · {lead.location || 'Location unknown'}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          {isApplied && <Badge color="green">Applied</Badge>}
          {isHot && <Badge color="orange">HOT</Badge>}
          {!lead.location_compatible && !isApplied && <Badge color="slate">Onsite</Badge>}
        </div>
      </div>

      {/* Row 2: Fit bar */}
      {lead.fit_score > 0 && (
        <div className="mt-3"><FitBar score={lead.fit_score} /></div>
      )}

      {/* Row 3: Collapsible fit details */}
      {hasDetails && (
        <button
          onClick={onToggle}
          className="mt-2 flex items-center gap-1 text-xs text-muted"
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? 'Hide details' : 'Why I fit'}
        </button>
      )}
      {expanded && hasDetails && (
        <div className="mt-2 space-y-1">
          {strengths.length > 0 && (
            <div className="text-xs text-green-600 dark:text-green-400 leading-relaxed">
              ✓ {strengths.join(' · ')}
            </div>
          )}
          {gaps.length > 0 && (
            <div className="text-xs text-muted leading-relaxed">
              △ {gaps.join(' · ')}
            </div>
          )}
        </div>
      )}

      {/* Salary */}
      {salaryStr ? (
        <div className="mt-2 text-xs">
          <span className="font-medium text-body">{salaryStr}</span>
          {lead.salary_notes && <span className="ml-1 text-muted">· {lead.salary_notes}</span>}
        </div>
      ) : lead.description && !lead.salary_min ? (
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xs text-muted">Salary not listed</span>
          <button
            onClick={handleParseSalary}
            disabled={parsingSalary}
            className="inline-flex items-center gap-1.5 text-xs text-blue-500 underline disabled:opacity-50"
          >
            {parsingSalary ? 'Parsing…' : 'Parse salary'}
            {!parsingSalary && <AICostBadge model="haiku" cost="$0.001" />}
          </button>
        </div>
      ) : null}

      {/* Row 4: Actions */}
      <div className="flex gap-2 mt-3 items-center">
        {lead.url && (
          <a
            href={lead.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 flex items-center justify-center gap-1.5 bg-card2 border border-theme text-body text-xs font-medium px-3 py-2.5 rounded-lg"
          >
            <ExternalLink size={11} />
            View posting
          </a>
        )}
        {!isApplied && (
          <button
            onClick={() => onMarkApplied(lead.id)}
            className="text-xs text-muted border border-theme px-3 py-2.5 rounded-lg flex-shrink-0"
          >
            Mark Applied
          </button>
        )}
        <button
          onClick={() => navigate(`/cv?lead_id=${lead.id}`)}
          className="bg-blue-500 text-white text-xs font-medium px-3 py-2.5 rounded-lg flex-shrink-0 flex items-center gap-1.5"
        >
          Tailor CV
          <AICostBadge model="opus" cost="$0.07" />
        </button>
      </div>
    </div>
  )
}
