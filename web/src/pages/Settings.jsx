import { useEffect, useState } from 'react'
import { RefreshCw, Check, X } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Badge from '../components/Badge'
import Spinner from '../components/Spinner'

export default function SettingsPage() {
  const [suggestions, setSuggestions] = useState([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(true)
  const [runningDiscovery, setRunningDiscovery] = useState(false)

  const loadSuggestions = () => {
    setLoadingSuggestions(true)
    api.getSuggestions()
      .then(setSuggestions)
      .catch(console.error)
      .finally(() => setLoadingSuggestions(false))
  }

  useEffect(() => { loadSuggestions() }, [])

  const handleApprove = async (id) => {
    try { await api.approveSuggestion(id); setSuggestions(s => s.filter(x => x.id !== id)) }
    catch (e) { alert(e.message) }
  }

  const handleSkip = async (id) => {
    try { await api.skipSuggestion(id); setSuggestions(s => s.filter(x => x.id !== id)) }
    catch (e) { alert(e.message) }
  }

  const handleRunDiscovery = async () => {
    setRunningDiscovery(true)
    try { await api.runDiscovery(); await loadSuggestions() }
    catch (e) { alert(e.message) }
    finally { setRunningDiscovery(false) }
  }

  return (
    <div className="flex flex-col">
      <PageHeader title="Settings & Targets" />

      <div className="px-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-medium text-body">
            New target suggestions
            {suggestions.length > 0 && (
              <span className="ml-2 bg-orange-500 text-white text-xs px-1.5 py-0.5 rounded-full">
                {suggestions.length}
              </span>
            )}
          </div>
          <button onClick={handleRunDiscovery} disabled={runningDiscovery}
            className="flex items-center gap-1.5 text-xs text-blue-500 disabled:opacity-50">
            <RefreshCw size={12} className={runningDiscovery ? 'animate-spin' : ''} />
            {runningDiscovery ? 'Running…' : 'Run discovery'}
          </button>
        </div>

        {loadingSuggestions ? (
          <div className="flex justify-center py-8"><Spinner size={6} /></div>
        ) : suggestions.length === 0 ? (
          <div className="bg-card border border-theme rounded-xl p-6 text-center text-muted text-sm">
            No pending suggestions. Run discovery to find new Series B/C targets.
          </div>
        ) : (
          <div className="space-y-3">
            {suggestions.map(s => (
              <div key={s.id} className="bg-card border border-theme rounded-xl p-4">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="font-medium text-body">{s.name}</div>
                  <div className="flex gap-1 flex-wrap">
                    {s.funding_stage && <Badge color="blue">{s.funding_stage.replace('_', ' ')}</Badge>}
                    {s.domain && <Badge color="purple">{s.domain}</Badge>}
                  </div>
                </div>
                {s.location_notes && <div className="text-xs text-muted mb-2">{s.location_notes}</div>}
                {s.reason && <div className="text-xs text-muted leading-relaxed">{s.reason}</div>}
                <div className="flex gap-2 mt-3">
                  <button onClick={() => handleApprove(s.id)}
                    className="flex items-center gap-1.5 flex-1 justify-center bg-blue-500 hover:bg-blue-600 text-white rounded-lg py-2 text-xs font-medium">
                    <Check size={12} /> Add to funnel
                  </button>
                  <button onClick={() => handleSkip(s.id)}
                    className="flex items-center gap-1.5 flex-1 justify-center bg-card2 border border-theme text-body rounded-lg py-2 text-xs font-medium">
                    <X size={12} /> Skip
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="px-4 pb-4">
        <div className="text-xs text-muted font-medium uppercase tracking-wide mb-2">System</div>
        <div className="bg-card border border-theme rounded-xl divide-y divide-theme">
          {[
            { label: 'Backend', value: 'FastAPI + SQLite' },
            { label: 'Models', value: 'Opus 4.6 / Haiku 4.5' },
            { label: 'Lead scraping', value: 'Greenhouse + Lever + BeautifulSoup' },
            { label: 'Scheduler', value: 'APScheduler (6h refresh)' },
          ].map(({ label, value }) => (
            <div key={label} className="flex items-center justify-between px-4 py-3">
              <span className="text-sm text-body">{label}</span>
              <span className="text-xs text-muted flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                {value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
