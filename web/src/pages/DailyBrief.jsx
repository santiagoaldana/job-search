import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Flame, Calendar, Mail, BookOpen, Send, Lightbulb, RefreshCw } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Spinner from '../components/Spinner'

const ICONS = {
  follow_up: AlertCircle,
  hot_lead: Flame,
  event: Calendar,
  start_outreach: Mail,
  interview_prep: BookOpen,
  publish_content: Send,
  review_suggestions: Lightbulb,
}

const COLORS = {
  1: 'border-red-300 bg-red-50 dark:border-red-700 dark:bg-red-950/40',
  2: 'border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-950/40',
  3: 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/40',
  4: 'border-purple-300 bg-purple-50 dark:border-purple-700 dark:bg-purple-950/40',
  5: 'border-yellow-300 bg-yellow-50 dark:border-yellow-700 dark:bg-yellow-950/40',
  6: 'border-green-300 bg-green-50 dark:border-green-700 dark:bg-green-950/40',
  7: 'border-theme bg-card',
}

const ICON_COLORS = {
  1: 'text-red-500', 2: 'text-orange-500', 3: 'text-blue-500',
  4: 'text-purple-500', 5: 'text-yellow-500', 6: 'text-green-500', 7: 'text-muted',
}

export default function DailyBrief() {
  const [brief, setBrief] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
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
    if (action.payload_type === 'company' || action.action_type === 'start_outreach') {
      navigate(`/company/${action.company_id || action.payload_id}`)
    } else if (action.payload_type === 'lead') {
      navigate('/leads')
    } else if (action.payload_type === 'event') {
      navigate('/events')
    } else if (action.payload_type === 'content') {
      navigate('/content')
    } else if (action.payload_type === 'suggestions') {
      navigate('/settings')
    } else if (action.payload_type === 'outreach' && action.company_id) {
      navigate(`/company/${action.company_id}`)
    }
  }

  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })

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
          <div className="flex gap-3 px-4 pb-4">
            <div className="flex-1 bg-card border border-theme rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-body">{brief.total_actions}</div>
              <div className="text-xs text-muted mt-0.5">actions</div>
            </div>
            <div className="flex-1 bg-red-50 border border-red-200 dark:bg-red-950/60 dark:border-red-800 rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-red-500 dark:text-red-400">{brief.overdue_count}</div>
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

          <div className="px-4 space-y-3 pb-4">
            {brief.actions.map((action, i) => {
              const Icon = ICONS[action.action_type] || AlertCircle
              return (
                <button
                  key={i}
                  onClick={() => handleAction(action)}
                  className={`w-full text-left p-4 rounded-xl border ${COLORS[action.priority] || 'border-theme bg-card'} transition-all`}
                >
                  <div className="flex items-start gap-3">
                    <Icon size={18} className={`mt-0.5 flex-shrink-0 ${ICON_COLORS[action.priority] || 'text-muted'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-body text-sm leading-snug">{action.label}</div>
                      {action.detail && (
                        <div className="text-xs text-muted mt-1 leading-relaxed">{action.detail}</div>
                      )}
                      <div className="mt-2">
                        <span className="text-xs font-medium text-blue-500">{action.cta} →</span>
                      </div>
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
