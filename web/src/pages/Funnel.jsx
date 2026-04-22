import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Badge from '../components/Badge'
import Spinner from '../components/Spinner'

const STAGES = ['pool', 'researched', 'outreach', 'response', 'meeting', 'applied', 'interview', 'offer']

const FUNDING_BADGE = {
  series_b: { label: 'Series B', color: 'blue' },
  series_c: { label: 'Series C', color: 'purple' },
  series_d: { label: 'Series D', color: 'orange' },
  public:   { label: 'Public', color: 'green' },
  unknown:  { label: '?', color: 'slate' },
}

export default function Funnel() {
  const [funnel, setFunnel] = useState({})
  const [loading, setLoading] = useState(true)
  const [activeStage, setActiveStage] = useState('pool')
  const navigate = useNavigate()

  useEffect(() => {
    api.getFunnel()
      .then(setFunnel)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const companies = funnel[activeStage] || []
  const totalActive = Object.values(funnel).flat().length

  return (
    <div className="flex flex-col">
      <PageHeader title="Pipeline" subtitle={`${totalActive} active companies`} />

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

      {loading ? (
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
      )}
    </div>
  )
}
