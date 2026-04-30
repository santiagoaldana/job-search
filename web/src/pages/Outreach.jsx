import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mail, Ghost, RefreshCw } from 'lucide-react'
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
  return Math.floor((Date.now() - new Date(dateStr.slice(0, 10)).getTime()) / 86400000)
}

function nextAction(r) {
  const today = new Date().toISOString().slice(0, 10)
  if (!r.follow_up_3_sent && r.follow_up_3_due <= today) return { label: 'Day 3 bump due', urgent: true }
  if (r.follow_up_3_sent && !r.follow_up_7_sent && r.follow_up_7_due <= today) return { label: 'Day 7 close due', urgent: true }
  if (!r.follow_up_3_sent) return { label: `Day 3 on ${r.follow_up_3_due}`, urgent: false }
  if (!r.follow_up_7_sent) return { label: `Day 7 on ${r.follow_up_7_due}`, urgent: false }
  return { label: 'All follow-ups sent', urgent: false }
}

function OutreachCard({ record, companyMap, contactMap, onStatusChange }) {
  const navigate = useNavigate()
  const company = companyMap[record.company_id]
  const contact = record.contact_id ? contactMap[record.contact_id] : null
  const days = daysSince(record.sent_at)
  const action = record.response_status === 'pending' ? nextAction(record) : null

  const primaryName = contact?.name || company?.name || `Company #${record.company_id}`
  const secondaryLine = contact
    ? [contact.title, company?.name].filter(Boolean).join(' · ')
    : null

  return (
    <div className="bg-card border border-theme rounded-xl p-4 mb-3">
      {/* Header: name + status */}
      <div className="flex items-start justify-between gap-2 mb-0.5">
        <div className="font-semibold text-body text-base leading-tight">{primaryName}</div>
        <Badge color={STATUS_COLOR[record.response_status] || 'slate'}>{record.response_status}</Badge>
      </div>

      {/* Company + title */}
      {secondaryLine && (
        <div
          className="text-xs text-blue-500 cursor-pointer mb-1"
          onClick={() => company && navigate(`/company/${record.company_id}`)}
        >
          {secondaryLine}
        </div>
      )}
      {!contact && company && (
        <div
          className="text-xs text-blue-500 cursor-pointer mb-1"
          onClick={() => navigate(`/company/${record.company_id}`)}
        >
          {company.name}
        </div>
      )}

      {/* Subject = position context */}
      {record.subject && (
        <div className="text-xs text-muted mt-1 truncate">{record.subject}</div>
      )}

      {/* Sent date */}
      <div className="text-xs text-muted mt-1">
        Sent {record.sent_at?.slice(0, 10)}{days !== null ? ` · ${days}d ago` : ''}
      </div>

      {/* Next action */}
      {action && (
        <div className={`mt-2 text-xs font-medium ${action.urgent ? 'text-red-500' : 'text-muted'}`}>
          {action.urgent ? '⚡ ' : ''}{action.label}
        </div>
      )}

      {/* Notes */}
      {record.notes && (
        <div className="mt-2 text-xs text-muted italic line-clamp-2">{record.notes}</div>
      )}

      {/* Actions */}
      {record.response_status !== 'ghosted' ? (
        <div className="flex gap-2 mt-3 flex-wrap">
          {['positive', 'negative', 'ghosted'].map(s => (
            <button
              key={s}
              onClick={() => onStatusChange(record.id, s)}
              className="text-xs px-2 py-1 border border-theme rounded-lg text-muted hover:text-body transition-colors capitalize"
            >{s}</button>
          ))}
        </div>
      ) : (
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
  const [records, setRecords] = useState({ active: [], ghosted: [] })
  const [companyMap, setCompanyMap] = useState({})
  const [contactMap, setContactMap] = useState({})
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [active, ghosted, companies] = await Promise.all([
        api.listOutreach({ response_status: 'pending' }),
        api.listOutreach({ response_status: 'ghosted' }),
        api.getCompanies({ active_only: false }),
      ])

      const cmap = {}
      companies.forEach(c => { cmap[c.id] = c })
      setCompanyMap(cmap)

      const allRecords = [...active, ...ghosted]
      const contactIds = [...new Set(allRecords.filter(r => r.contact_id).map(r => r.contact_id))]
      const entries = await Promise.all(
        contactIds.map(id => api.getContact(id).then(c => [id, c]).catch(() => [id, null]))
      )
      setContactMap(Object.fromEntries(entries))
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

  const dedup = (list) => {
    const seen = new Set()
    return list.filter(r => {
      const key = `${r.company_id}-${r.contact_id}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }

  const sort = (list, isGhosted) => {
    if (isGhosted) {
      return [...list].sort((a, b) => daysSince(b.sent_at) - daysSince(a.sent_at))
    }
    const today = new Date().toISOString().slice(0, 10)
    const urgent = r => (!r.follow_up_3_sent && r.follow_up_3_due <= today) ||
      (r.follow_up_3_sent && !r.follow_up_7_sent && r.follow_up_7_due <= today)
    return [...list].sort((a, b) => {
      if (urgent(a) && !urgent(b)) return -1
      if (!urgent(a) && urgent(b)) return 1
      return daysSince(b.sent_at) - daysSince(a.sent_at)
    })
  }

  const shown = tab === 'active'
    ? sort(dedup(records.active), false)
    : sort(dedup(records.ghosted), true)

  return (
    <div className="flex flex-col min-h-screen bg-app">
      <PageHeader title="Outreach" />

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
            <span className="ml-1 text-xs bg-slate-100 dark:bg-slate-800 rounded-full px-1.5 py-0.5">
              {dedup(records[key] || []).length}
            </span>
          </button>
        ))}
        <button onClick={load} className="ml-auto p-3 text-muted hover:text-body">
          <RefreshCw size={15} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {loading ? (
          <div className="flex justify-center py-12"><Spinner size={6} /></div>
        ) : shown.length === 0 ? (
          <div className="text-center text-muted text-sm py-12">
            {tab === 'active' ? 'No active outreach' : 'No ghosted contacts'}
          </div>
        ) : (
          shown.map(r => (
            <OutreachCard
              key={r.id}
              record={r}
              companyMap={companyMap}
              contactMap={contactMap}
              onStatusChange={handleStatusChange}
            />
          ))
        )}
      </div>
    </div>
  )
}
