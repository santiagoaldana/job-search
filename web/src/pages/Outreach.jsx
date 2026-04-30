import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mail, Ghost, RefreshCw, ChevronRight } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Spinner from '../components/Spinner'
import Badge from '../components/Badge'

const STATUS_COLOR = {
  pending: 'yellow',
  positive: 'green',
  negative: 'red',
  ghosted: 'slate',
}

function daysSince(dateStr) {
  if (!dateStr) return null
  const d = new Date(dateStr.slice(0, 10))
  return Math.floor((Date.now() - d.getTime()) / 86400000)
}

function nextAction(r) {
  const today = new Date().toISOString().slice(0, 10)
  if (!r.follow_up_3_sent && r.follow_up_3_due <= today) return { label: 'Day 3 bump due', urgent: true }
  if (r.follow_up_3_sent && !r.follow_up_7_sent && r.follow_up_7_due <= today) return { label: 'Day 7 close due', urgent: true }
  if (!r.follow_up_3_sent) return { label: `Day 3 on ${r.follow_up_3_due}`, urgent: false }
  if (!r.follow_up_7_sent) return { label: `Day 7 on ${r.follow_up_7_due}`, urgent: false }
  return { label: 'All follow-ups sent', urgent: false }
}

function OutreachCard({ record, companyMap, onStatusChange }) {
  const navigate = useNavigate()
  const company = companyMap[record.company_id]
  const days = daysSince(record.sent_at)
  const action = record.response_status === 'pending' ? nextAction(record) : null

  return (
    <div className="bg-card border border-theme rounded-xl p-4 mb-3">
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="flex-1 min-w-0">
          <div className="font-medium text-body text-sm truncate">{record.subject || '(no subject)'}</div>
          <div
            className="text-xs text-blue-500 cursor-pointer mt-0.5"
            onClick={() => company && navigate(`/company/${record.company_id}`)}
          >
            {company?.name || `Company #${record.company_id}`}
          </div>
        </div>
        <Badge color={STATUS_COLOR[record.response_status] || 'slate'}>{record.response_status}</Badge>
      </div>

      <div className="text-xs text-muted mt-1">
        Sent {record.sent_at?.slice(0, 10)}{days !== null ? ` · ${days}d ago` : ''}
      </div>

      {action && (
        <div className={`mt-2 text-xs font-medium ${action.urgent ? 'text-red-500' : 'text-muted'}`}>
          {action.urgent ? '⚡ ' : ''}{action.label}
        </div>
      )}

      {record.notes && (
        <div className="mt-2 text-xs text-muted italic line-clamp-2">{record.notes}</div>
      )}

      {record.response_status !== 'ghosted' && (
        <div className="flex gap-2 mt-3 flex-wrap">
          {['positive', 'negative', 'ghosted'].map(s => (
            <button
              key={s}
              onClick={() => onStatusChange(record.id, s)}
              className="text-xs px-2 py-1 border border-theme rounded-lg text-muted hover:text-body transition-colors capitalize"
            >{s}</button>
          ))}
        </div>
      )}

      {record.response_status === 'ghosted' && (
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => onStatusChange(record.id, 'pending')}
            className="text-xs px-2 py-1 border border-blue-300 rounded-lg text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950/30 transition-colors"
          >Re-engage</button>
          <button
            onClick={() => onStatusChange(record.id, 'negative')}
            className="text-xs px-2 py-1 border border-theme rounded-lg text-muted hover:text-body transition-colors"
          >Close out</button>
        </div>
      )}
    </div>
  )
}

export default function OutreachPage() {
  const [tab, setTab] = useState('active')
  const [records, setRecords] = useState([])
  const [companyMap, setCompanyMap] = useState({})
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [active, ghosted, companies] = await Promise.all([
        api.listOutreach({ response_status: 'pending' }),
        api.listOutreach({ response_status: 'ghosted' }),
        api.getCompanies({ active_only: false }),
      ])
      const map = {}
      companies.forEach(c => { map[c.id] = c })
      setCompanyMap(map)
      setRecords({ active, ghosted })
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleStatusChange = async (id, status) => {
    await api.updateOutreachResponse(id, status)
    load()
  }

  const shown = tab === 'active' ? (records.active || []) : (records.ghosted || [])

  // Deduplicate by company+contact keeping most recent
  const seen = new Set()
  const deduped = shown.filter(r => {
    const key = `${r.company_id}-${r.contact_id}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })

  return (
    <div className="flex flex-col min-h-screen bg-app">
      <PageHeader title="Outreach" />

      {/* Tabs */}
      <div className="flex border-b border-theme px-4">
        {[
          { key: 'active', label: 'Active', icon: Mail },
          { key: 'ghosted', label: 'Ghosted', icon: Ghost },
        ].map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              tab === key ? 'border-blue-500 text-blue-500' : 'border-transparent text-muted'
            }`}
          >
            <Icon size={14} />
            {label}
            {records[key] && <span className="ml-1 text-xs bg-slate-100 dark:bg-slate-800 rounded-full px-1.5 py-0.5">{records[key].length}</span>}
          </button>
        ))}
        <button onClick={load} className="ml-auto p-3 text-muted hover:text-body">
          <RefreshCw size={15} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {loading ? (
          <div className="flex justify-center py-12"><Spinner size={6} /></div>
        ) : deduped.length === 0 ? (
          <div className="text-center text-muted text-sm py-12">
            {tab === 'active' ? 'No active outreach' : 'No ghosted contacts'}
          </div>
        ) : (
          deduped.map(r => (
            <OutreachCard
              key={r.id}
              record={r}
              companyMap={companyMap}
              onStatusChange={handleStatusChange}
            />
          ))
        )}
      </div>
    </div>
  )
}
