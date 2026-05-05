import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mail, Ghost, RefreshCw, BarChart2, ChevronDown, ChevronUp } from 'lucide-react'
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

function pct(v) { return v != null ? `${Math.round(v * 100)}%` : '—' }

function StatsCard() {
  const [open, setOpen] = useState(false)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    if (stats) return
    setLoading(true)
    try { setStats(await api.getOutreachStats()) } catch (e) { console.error(e) } finally { setLoading(false) }
  }

  const toggle = () => {
    if (!open) load()
    setOpen(o => !o)
  }

  const channels = ['email', 'linkedin', 'referral']

  return (
    <div className="mx-4 mb-3 bg-card border border-theme rounded-xl overflow-hidden">
      <button onClick={toggle} className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-body">
        <span className="flex items-center gap-2"><BarChart2 size={14} /> Effectiveness Stats</span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-theme">
          {loading ? (
            <div className="py-4 flex justify-center"><Spinner size={5} /></div>
          ) : stats ? (
            <div className="mt-3 space-y-4">
              {/* Summary row */}
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: 'Total sent', value: stats.total_sent },
                  { label: 'Last 30 days', value: stats.sent_last_30d },
                  { label: 'Response rate', value: pct(stats.overall_response_rate) },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-2 text-center">
                    <div className="text-lg font-semibold text-body">{value}</div>
                    <div className="text-xs text-muted">{label}</div>
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-2 text-center">
                  <div className="text-lg font-semibold text-body">{pct(stats.overall_ghosted_pct)}</div>
                  <div className="text-xs text-muted">Ghosted</div>
                </div>
                <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-2 text-center">
                  <div className="text-lg font-semibold text-body">{stats.avg_days_to_positive != null ? `${stats.avg_days_to_positive}d` : '—'}</div>
                  <div className="text-xs text-muted">Avg days to reply</div>
                </div>
              </div>

              {/* Best channel */}
              {stats.best_channel && (
                <div className="text-xs text-muted">
                  Best channel: <span className="font-medium text-body capitalize">{stats.best_channel}</span>
                  {' '}({pct(stats.by_channel[stats.best_channel]?.response_rate)} response rate)
                </div>
              )}

              {/* By channel table */}
              <div>
                <div className="text-xs font-medium text-muted mb-1">By channel</div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-muted">
                      <th className="text-left py-1">Channel</th>
                      <th className="text-right py-1">Sent</th>
                      <th className="text-right py-1">Response</th>
                      <th className="text-right py-1">Ghosted</th>
                    </tr>
                  </thead>
                  <tbody>
                    {channels.map(ch => {
                      const d = stats.by_channel[ch] || { sent: 0, response_rate: 0, ghosted_pct: 0 }
                      return (
                        <tr key={ch} className="border-t border-theme">
                          <td className="py-1 capitalize text-body">{ch}</td>
                          <td className="py-1 text-right text-muted">{d.sent}</td>
                          <td className="py-1 text-right text-green-600">{pct(d.response_rate)}</td>
                          <td className="py-1 text-right text-slate-400">{pct(d.ghosted_pct)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="py-4 text-xs text-muted text-center">No data yet</div>
          )}
        </div>
      )}
    </div>
  )
}

function OutreachCard({ record, companyMap, contactMap, onStatusChange, onSkip, onReload }) {
  const navigate = useNavigate()
  const company = companyMap[record.company_id]
  const contact = record.contact_id ? contactMap[record.contact_id] : null
  const days = daysSince(record.sent_at)
  const action = record.response_status === 'pending' ? nextAction(record) : null
  const [editingDates, setEditingDates] = useState(false)
  const [due3, setDue3] = useState(record.follow_up_3_due || '')
  const [due7, setDue7] = useState(record.follow_up_7_due || '')
  const [savingDates, setSavingDates] = useState(false)

  const handleSaveDates = async () => {
    setSavingDates(true)
    try {
      await api.patchOutreach(record.id, { follow_up_3_due: due3 || null, follow_up_7_due: due7 || null })
      setEditingDates(false)
      onReload?.()
    } catch (e) { alert(e.message) } finally { setSavingDates(false) }
  }

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

      {/* Next action + edit dates */}
      {action && !editingDates && (
        <div className="mt-2 flex items-center gap-2 flex-wrap">
          <span className={`text-xs font-medium ${action.urgent ? 'text-red-500' : 'text-muted'}`}>
            {action.urgent ? '⚡ ' : ''}{action.label}
          </span>
          <button onClick={() => setEditingDates(true)} className="text-xs text-blue-500 underline">Edit dates</button>
        </div>
      )}
      {editingDates && (
        <div className="mt-2 flex flex-wrap gap-2 items-end">
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

      {/* Notes */}
      {record.notes && (
        <div className="mt-2 text-xs text-muted italic line-clamp-2">{record.notes}</div>
      )}

      {/* Actions */}
      {record.response_status !== 'ghosted' ? (
        <div className="flex gap-2 mt-3 flex-wrap items-center">
          <button
            onClick={() => onSkip(record.id)}
            className="text-xs px-2 py-1 border border-slate-300 dark:border-slate-600 rounded-lg text-slate-500 dark:text-slate-400 hover:text-body transition-colors"
          >Skip follow-ups</button>
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

  const handleSkip = async (id) => {
    try {
      await api.skipOutreach(id)
      load()
    } catch (e) {
      alert(e.message)
    }
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
    ? sort(records.active, false)
    : sort(records.ghosted, true)

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
              {(records[key] || []).length}
            </span>
          </button>
        ))}
        <button onClick={load} className="ml-auto p-3 text-muted hover:text-body">
          <RefreshCw size={15} />
        </button>
      </div>

      <StatsCard />

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
              onSkip={handleSkip}
              onReload={load}
            />
          ))
        )}
      </div>
    </div>
  )
}
