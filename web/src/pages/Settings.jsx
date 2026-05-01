import { useEffect, useState, useCallback, useRef } from 'react'
import { RefreshCw, Check, X, ChevronDown, ChevronUp, Plus, Trash2, Upload } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Badge from '../components/Badge'
import Spinner from '../components/Spinner'

const CATEGORY_COLORS = { thought_leader: 'purple', publication: 'blue', news: 'slate' }
const CATEGORY_LABELS = { thought_leader: 'Thought Leader', publication: 'Publication', news: 'News' }

function ThoughtLeaderFeeds() {
  const [feeds, setFeeds] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [category, setCategory] = useState('thought_leader')
  const [adding, setAdding] = useState(false)
  const [showForm, setShowForm] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    api.getFeeds()
      .then(setFeeds)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { if (open) load() }, [open, load])

  async function handleAdd() {
    if (!name.trim() || !url.trim()) return
    setAdding(true)
    try {
      await api.addFeed({ name: name.trim(), url: url.trim(), category })
      setName(''); setUrl(''); setCategory('thought_leader'); setShowForm(false)
      load()
    } catch (e) {
      alert(e.message)
    } finally {
      setAdding(false)
    }
  }

  async function handleDelete(id) {
    try {
      await api.deleteFeed(id)
      setFeeds(fs => fs.filter(f => f.id !== id))
    } catch (e) {
      alert(e.message)
    }
  }

  return (
    <div className="px-4 mb-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between bg-card border border-theme rounded-xl px-4 py-3"
      >
        <div>
          <div className="text-sm font-medium text-body text-left">Content Feeds</div>
          <div className="text-xs text-muted text-left">Thought leaders & publications for post generation</div>
        </div>
        {open ? <ChevronUp size={16} className="text-muted" /> : <ChevronDown size={16} className="text-muted" />}
      </button>

      {open && (
        <div className="mt-2 bg-card border border-theme rounded-xl overflow-hidden">
          {loading ? (
            <div className="flex justify-center py-8"><Spinner size={6} /></div>
          ) : (
            <>
              <div className="divide-y divide-theme max-h-[50vh] overflow-y-auto">
                {feeds.length === 0 && (
                  <div className="py-6 text-center text-sm text-muted">No feeds yet</div>
                )}
                {feeds.map(f => (
                  <div key={f.id} className="flex items-center gap-3 px-4 py-3">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-body truncate">{f.name}</div>
                      <div className="text-xs text-muted truncate">{f.url}</div>
                    </div>
                    <Badge color={CATEGORY_COLORS[f.category] || 'slate'}>
                      {CATEGORY_LABELS[f.category] || f.category}
                    </Badge>
                    <button onClick={() => handleDelete(f.id)} className="text-muted hover:text-red-500 transition-colors flex-shrink-0">
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>

              {showForm ? (
                <div className="border-t border-theme p-4 space-y-3">
                  <input
                    className="w-full bg-bg border border-theme rounded-lg px-3 py-2 text-sm text-body"
                    placeholder="Name (e.g. Judah Phillips)"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    autoFocus
                  />
                  <input
                    className="w-full bg-bg border border-theme rounded-lg px-3 py-2 text-sm text-body"
                    placeholder="RSS URL (e.g. https://name.substack.com/feed)"
                    value={url}
                    onChange={e => setUrl(e.target.value)}
                  />
                  <div className="flex gap-2">
                    {['thought_leader', 'publication', 'news'].map(c => (
                      <button
                        key={c}
                        onClick={() => setCategory(c)}
                        className={`flex-1 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                          category === c ? 'bg-blue-500 border-blue-400 text-white' : 'bg-bg border-theme text-muted'
                        }`}
                      >
                        {CATEGORY_LABELS[c]}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleAdd}
                      disabled={adding || !name.trim() || !url.trim()}
                      className="flex-1 bg-blue-500 text-white rounded-lg py-2 text-xs font-medium disabled:opacity-50"
                    >
                      {adding ? 'Adding…' : 'Add Feed'}
                    </button>
                    <button
                      onClick={() => { setShowForm(false); setName(''); setUrl('') }}
                      className="px-4 border border-theme rounded-lg text-xs text-muted"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowForm(true)}
                  className="w-full flex items-center justify-center gap-1.5 py-3 text-xs text-blue-500 border-t border-theme"
                >
                  <Plus size={13} /> Add Feed
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function IntelSummary({ company: c, onRefresh, refreshing }) {
  const [expanded, setExpanded] = useState(false)
  const preview = (c.intel_summary || '').replace(/[#*►]/g, '').trim().slice(0, 120)
  return (
    <div className="mt-0.5">
      {expanded
        ? <div className="text-xs text-muted leading-relaxed whitespace-pre-wrap pr-1">{c.intel_summary.replace(/[#*►]/g, '').trim()}</div>
        : <div className="text-xs text-muted leading-relaxed">{preview}{c.intel_summary.length > 120 ? '…' : ''}</div>
      }
      <div className="flex gap-3 mt-1">
        {c.intel_summary.length > 120 && (
          <button onClick={() => setExpanded(e => !e)} className="text-xs text-blue-500">
            {expanded ? 'Show less' : 'Read more'}
          </button>
        )}
        <button onClick={onRefresh} disabled={refreshing} className="text-xs text-muted disabled:opacity-50">
          {refreshing ? 'Refreshing…' : 'Refresh intel'}
        </button>
      </div>
    </div>
  )
}

function stageToGroup(stage) {
  if (['outreach', 'response', 'meeting', 'applied', 'interview'].includes(stage)) return 'in_play'
  if (stage === 'closed' || stage === 'offer') return 'closed'
  return 'target'
}

function BulkReview() {
  const [companies, setCompanies] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(true)
  const [saving, setSaving] = useState({})
  const [stageSaving, setStageSaving] = useState({})
  const [fetchingIntel, setFetchingIntel] = useState({})
  const [enriching, setEnriching] = useState(false)
  const [enrichingDone, setEnrichingDone] = useState(false)
  const [filter, setFilter] = useState('all')

  const load = useCallback(() => {
    setLoading(true)
    api.getCompanies({ active_only: false })
      .then(data => setCompanies(data.sort((a, b) => (b.lamp_score || 0) - (a.lamp_score || 0))))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  async function setMotivation(company, val) {
    const m = Math.max(1, Math.min(10, val))
    setCompanies(cs => cs.map(c => c.id === company.id ? { ...c, motivation: m } : c))
    setSaving(s => ({ ...s, [company.id]: true }))
    try {
      await api.updateCompany(company.id, { motivation: m })
    } catch (e) {
      console.error(e)
    } finally {
      setSaving(s => ({ ...s, [company.id]: false }))
    }
  }

  async function setStage(company, stageGroup) {
    setStageSaving(s => ({ ...s, [company.id]: true }))
    try {
      await api.setCompanyStage(company.id, stageGroup)
      setCompanies(cs => cs.map(c => c.id === company.id ? { ...c, stage: stageGroup } : c))
    } catch (e) {
      console.error(e)
    } finally {
      setStageSaving(s => ({ ...s, [company.id]: false }))
    }
  }

  async function getIntel(company) {
    setFetchingIntel(s => ({ ...s, [company.id]: true }))
    try {
      const result = await api.refreshIntel(company.id)
      setCompanies(cs => cs.map(c => c.id === company.id ? { ...c, intel_summary: result.intel_summary } : c))
    } catch (e) {
      console.error(e)
    } finally {
      setFetchingIntel(s => ({ ...s, [company.id]: false }))
    }
  }

  async function handleEnrichAll() {
    setEnriching(true)
    try {
      await api.enrichAllCompanies()
      setEnrichingDone(true)
    } catch (e) {
      console.error(e)
    } finally {
      setEnriching(false)
    }
  }

  const filtered = companies.filter(c => {
    if (filter === 'active') return c.motivation >= 7
    if (filter === 'inactive') return c.motivation < 7
    return true
  })

  return (
    <div className="px-4 mb-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between bg-card border border-theme rounded-xl px-4 py-3"
      >
        <div>
          <div className="text-sm font-medium text-body text-left">Bulk Review — Set Motivations</div>
          <div className="text-xs text-muted text-left">Review all {loading ? '…' : companies.length} companies, set priority 1–10</div>
        </div>
        {open ? <ChevronUp size={16} className="text-muted" /> : <ChevronDown size={16} className="text-muted" />}
      </button>

      {open && (
        <div className="mt-2 bg-card border border-theme rounded-xl overflow-hidden">
          {/* Filter tabs + Enrich All */}
          <div className="flex items-center border-b border-theme">
            <div className="flex flex-1">
              {[['all', 'All'], ['active', 'Active (≥7)'], ['inactive', 'Inactive (<7)']].map(([val, label]) => (
                <button
                  key={val}
                  onClick={() => setFilter(val)}
                  className={`flex-1 py-2 text-xs font-medium transition-colors ${
                    filter === val ? 'text-blue-500 border-b-2 border-blue-500' : 'text-muted'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              onClick={handleEnrichAll}
              disabled={enriching}
              className="px-3 py-2 text-xs text-blue-500 disabled:opacity-50 flex-shrink-0"
            >
              {enriching ? 'Enriching…' : 'Enrich all'}
            </button>
          </div>

          {enrichingDone && (
            <div className="px-4 py-2 bg-blue-500/10 border-b border-theme flex items-center justify-between">
              <span className="text-xs text-blue-400">Enrichment running in background (~4 min). Tap Reload when done.</span>
              <button onClick={() => { load(); setEnrichingDone(false) }} className="text-xs text-blue-500 font-medium ml-3">Reload</button>
            </div>
          )}

          {loading ? (
            <div className="flex justify-center py-8"><Spinner size={6} /></div>
          ) : (
            <div className="divide-y divide-theme max-h-[60vh] overflow-y-auto">
              {filtered.map(c => (
                <div key={c.id} className="flex items-start gap-3 px-4 py-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-body truncate">{c.name}</div>
                    {/* LAMP + inline stage selector */}
                    <div className="text-xs text-muted flex items-center gap-1 flex-wrap">
                      <span>LAMP {c.lamp_score?.toFixed(0) || '—'} ·</span>
                      <select
                        value={stageToGroup(c.stage)}
                        onChange={e => setStage(c, e.target.value)}
                        onClick={e => e.stopPropagation()}
                        disabled={stageSaving[c.id]}
                        className="text-xs text-muted bg-transparent border-none outline-none cursor-pointer disabled:opacity-50"
                      >
                        <option value="target">Target</option>
                        <option value="in_play">In Play</option>
                        <option value="closed">Closed</option>
                      </select>
                    </div>
                    {/* Funding + headcount from Apollo */}
                    {(c.funding_stage && c.funding_stage !== 'unknown' || c.headcount_range && c.headcount_range !== 'unknown') && (
                      <div className="text-xs text-muted mt-0.5">
                        {[
                          c.funding_stage && c.funding_stage !== 'unknown' && c.funding_stage.replace(/_/g, ' '),
                          c.headcount_range && c.headcount_range !== 'unknown' && `${c.headcount_range} employees`,
                        ].filter(Boolean).join(' · ')}
                      </div>
                    )}
                    {/* Short description from Apollo */}
                    {c.org_notes && (
                      <div className="text-xs text-muted leading-relaxed mt-0.5 line-clamp-2">{c.org_notes}</div>
                    )}
                    {/* Intel summary or Get Intel button */}
                    {c.intel_summary
                      ? <IntelSummary company={c} onRefresh={() => getIntel(c)} refreshing={fetchingIntel[c.id]} />
                      : <button
                          onClick={() => getIntel(c)}
                          disabled={fetchingIntel[c.id]}
                          className="text-xs text-blue-500 mt-0.5 disabled:opacity-50"
                        >
                          {fetchingIntel[c.id] ? 'Getting intel…' : 'Get Intel'}
                        </button>
                    }
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => setMotivation(c, c.motivation - 1)}
                      className="w-7 h-7 rounded-lg bg-bg border border-theme text-muted text-sm flex items-center justify-center"
                    >−</button>
                    <span className={`w-7 text-center text-sm font-semibold ${
                      c.motivation >= 7 ? 'text-blue-500' : 'text-muted'
                    }`}>
                      {saving[c.id] ? '…' : c.motivation}
                    </span>
                    <button
                      onClick={() => setMotivation(c, c.motivation + 1)}
                      className="w-7 h-7 rounded-lg bg-bg border border-theme text-muted text-sm flex items-center justify-center"
                    >+</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function LinkedInContactsImport() {
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState(null)
  const inputRef = useRef(null)

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true); setResult(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const data = await api.importLinkedInContacts(formData)
      let msg = `✓ ${data.imported} contacts imported`
      if (data.matched_to_funnel > 0) {
        msg += ` · ${data.matched_to_funnel} warm path${data.matched_to_funnel > 1 ? 's' : ''} found: ${(data.new_warm_paths || []).slice(0, 3).join(', ')}`
      }
      setResult(msg)
    } catch (err) {
      setResult(`Error: ${err.message}`)
    } finally {
      setImporting(false)
      e.target.value = ''
    }
  }

  return (
    <div className="px-4 mb-4">
      <div className="bg-card border border-theme rounded-xl p-4">
        <div className="text-sm font-medium text-body mb-0.5">LinkedIn Contacts</div>
        <div className="text-xs text-muted mb-3 leading-relaxed">
          Cross-reference your network against funnel companies to find warm paths.{' '}
          <span className="font-medium text-body">How to export:</span>{'\n'}
          1. linkedin.com → Me → Settings &amp; Privacy{'\n'}
          2. Data Privacy → Get a copy of your data{'\n'}
          3. Select Connections only → Request archive{'\n'}
          4. LinkedIn emails you the download link (~10 min){'\n'}
          5. Download zip → extract Connections.csv → upload below
        </div>
        <input
          type="file"
          accept=".csv"
          ref={inputRef}
          onChange={handleFile}
          className="hidden"
        />
        <button
          onClick={() => inputRef.current?.click()}
          disabled={importing}
          className="w-full flex items-center justify-center gap-2 bg-card2 hover:bg-card border border-theme text-body rounded-lg py-2.5 text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {importing ? <Spinner size={4} /> : <Upload size={14} />}
          {importing ? 'Importing contacts…' : 'Import LinkedIn Contacts (.csv)'}
        </button>
        {result && (
          <div className={`mt-2 text-xs text-center leading-relaxed ${result.startsWith('Error') ? 'text-red-500' : 'text-green-600 dark:text-green-400'}`}>
            {result}
          </div>
        )}
      </div>
    </div>
  )
}

function MasterCVUpload() {
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState(null)
  const fileInputRef = useRef(null)

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true); setResult(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const data = await api.uploadMasterCV(formData)
      setResult(`✓ Master CV updated — ${data.experience_count} roles loaded for ${data.name}`)
    } catch (err) {
      setResult(`Error: ${err.message}`)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  return (
    <div className="px-4 mb-4">
      <div className="bg-card border border-theme rounded-xl p-4">
        <div className="text-sm font-medium text-body mb-0.5">Master CV</div>
        <div className="text-xs text-muted mb-3">
          Upload your edited .docx to update the base template used for all tailored versions.
        </div>
        <input
          type="file"
          accept=".docx,.json"
          ref={fileInputRef}
          onChange={handleFile}
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="w-full flex items-center justify-center gap-2 bg-card2 hover:bg-card border border-theme text-body rounded-lg py-2.5 text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {uploading ? <Spinner size={4} /> : <Upload size={14} />}
          {uploading ? 'Uploading & parsing…' : 'Upload Master CV (.docx or .json)'}
        </button>
        {result && (
          <div className={`mt-2 text-xs text-center ${result.startsWith('Error') ? 'text-red-500' : 'text-green-600 dark:text-green-400'}`}>
            {result}
          </div>
        )}
      </div>
    </div>
  )
}

export default function SettingsPage() {
  const [suggestions, setSuggestions] = useState([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(true)
  const [runningDiscovery, setRunningDiscovery] = useState(false)
  const [approvingId, setApprovingId] = useState(null)
  const [pendingMotivation, setPendingMotivation] = useState({})

  const loadSuggestions = () => {
    setLoadingSuggestions(true)
    api.getSuggestions()
      .then(setSuggestions)
      .catch(console.error)
      .finally(() => setLoadingSuggestions(false))
  }

  useEffect(() => { loadSuggestions() }, [])

  const handleApprove = async (id) => {
    const motivation = pendingMotivation[id] ?? 7
    setApprovingId(id)
    try {
      await api.approveSuggestion(id, motivation)
      setSuggestions(s => s.filter(x => x.id !== id))
    }
    catch (e) { alert(e.message) }
    finally { setApprovingId(null) }
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

      <BulkReview />

      <MasterCVUpload />

      <LinkedInContactsImport />

      <ThoughtLeaderFeeds />

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
                <div className="mt-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted flex-shrink-0">Motivation</span>
                    <input
                      type="range" min={1} max={10} step={1}
                      value={pendingMotivation[s.id] ?? 7}
                      onChange={e => setPendingMotivation(m => ({ ...m, [s.id]: Number(e.target.value) }))}
                      className="flex-1 accent-blue-500"
                    />
                    <span className="text-xs font-medium text-body w-4 text-right">
                      {pendingMotivation[s.id] ?? 7}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => handleApprove(s.id)} disabled={approvingId === s.id}
                      className="flex items-center gap-1.5 flex-1 justify-center bg-blue-500 hover:bg-blue-600 text-white rounded-lg py-2 text-xs font-medium disabled:opacity-50">
                      <Check size={12} /> Add to funnel
                    </button>
                    <button onClick={() => handleSkip(s.id)}
                      className="flex items-center gap-1.5 flex-1 justify-center bg-card2 border border-theme text-body rounded-lg py-2 text-xs font-medium">
                      <X size={12} /> Skip
                    </button>
                  </div>
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
            { label: 'Backend', value: 'FastAPI + PostgreSQL' },
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
