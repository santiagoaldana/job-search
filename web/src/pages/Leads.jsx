import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Badge from '../components/Badge'
import FitBar from '../components/FitBar'
import Spinner from '../components/Spinner'

export default function Leads() {
  const [leads, setLeads] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [minFit, setMinFit] = useState(0)
  const [locationOnly, setLocationOnly] = useState(false)
  const navigate = useNavigate()

  const load = async () => {
    setLoading(true)
    try {
      const params = {}
      if (minFit > 0) params.min_fit = minFit
      if (locationOnly) params.location_compatible = true
      setLeads(await api.getLeads(params))
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [minFit, locationOnly])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await api.refreshLeads()
      alert('Lead refresh started in background. Check back in a few minutes.')
    } catch (e) {
      alert(e.message)
    } finally {
      setRefreshing(false)
    }
  }

  const sorted = [...leads].sort((a, b) => {
    if (a.location_compatible !== b.location_compatible)
      return (b.location_compatible ? 1 : 0) - (a.location_compatible ? 1 : 0)
    return (b.fit_score || 0) - (a.fit_score || 0)
  })

  return (
    <div className="flex flex-col">
      <PageHeader
        title="Leads"
        subtitle={`${leads.length} opportunities`}
        action={
          <button onClick={handleRefresh} disabled={refreshing}
            className="flex items-center gap-1.5 text-sm text-blue-500 disabled:opacity-50">
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        }
      />

      <div className="flex items-center gap-3 px-4 pb-3">
        <div className="flex-1">
          <label className="text-xs text-muted block mb-1">Min fit: {minFit}%</label>
          <input type="range" min={0} max={90} step={5} value={minFit}
            onChange={e => setMinFit(Number(e.target.value))}
            className="w-full accent-blue-500" />
        </div>
        <button
          onClick={() => setLocationOnly(v => !v)}
          className={`flex-shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors ${
            locationOnly ? 'bg-blue-500 border-blue-400 text-white' : 'bg-card border-theme text-muted'
          }`}
        >
          Boston/Remote
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Spinner size={8} /></div>
      ) : (
        <div className="px-4 space-y-3 pb-4">
          {sorted.length === 0 && (
            <div className="py-12 text-center text-muted text-sm">No leads match your filters</div>
          )}
          {sorted.map(lead => (
            <div key={lead.id}
              className={`bg-card border rounded-xl p-4 ${!lead.location_compatible ? 'border-theme opacity-60' : 'border-theme'}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-body text-sm leading-snug">{lead.title}</div>
                  <div className="text-xs text-muted mt-0.5">
                    {lead.company_name || `Company #${lead.company_id}`} · {lead.location || 'Location unknown'}
                  </div>
                </div>
                {lead.fit_score >= 65 && lead.location_compatible && <Badge color="orange">HOT</Badge>}
                {!lead.location_compatible && <Badge color="slate">Onsite</Badge>}
              </div>

              {lead.fit_score > 0 && (
                <div className="mt-3"><FitBar score={lead.fit_score} /></div>
              )}

              {lead.fit_strengths && (() => {
                try {
                  const s = JSON.parse(lead.fit_strengths)
                  return s.length > 0 ? (
                    <div className="mt-2 text-xs text-green-600 dark:text-green-400 leading-relaxed">
                      ✓ {s.join(' · ')}
                    </div>
                  ) : null
                } catch { return null }
              })()}

              {lead.fit_gaps && (() => {
                try {
                  const g = JSON.parse(lead.fit_gaps)
                  return g.length > 0 ? (
                    <div className="mt-1 text-xs text-muted leading-relaxed">
                      △ {g.join(' · ')}
                    </div>
                  ) : null
                } catch { return null }
              })()}

              <div className="flex gap-3 mt-3">
                {lead.url && (
                  <a href={lead.url} target="_blank" rel="noopener noreferrer"
                    className="text-xs text-blue-500 font-medium">View posting →</a>
                )}
                {lead.company_id && (
                  <button onClick={() => navigate(`/company/${lead.company_id}`)}
                    className="text-xs text-muted hover:text-body">Company →</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
