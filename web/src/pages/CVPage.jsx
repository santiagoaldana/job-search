import { useEffect, useState } from 'react'
import { Send, Check, X, Download, ChevronDown, ChevronUp } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Spinner from '../components/Spinner'

export default function CVPage() {
  const [instruction, setInstruction] = useState('')
  const [loading, setLoading] = useState(false)
  const [diff, setDiff] = useState(null)
  const [versionName, setVersionName] = useState('')
  const [approvedSections, setApprovedSections] = useState({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [versions, setVersions] = useState([])
  const [exportFormat, setExportFormat] = useState('pdf')

  useEffect(() => {
    api.listVersions().then(setVersions).catch(() => {})
  }, [])

  const handleChat = async () => {
    if (!instruction.trim()) return
    setLoading(true); setDiff(null); setSaved(false)
    try {
      const result = await api.chatEditCV({ instruction, version_name: versionName || undefined })
      setDiff(result)
      setVersionName(result.version_name || '')
      const approved = {}
      result.diff.forEach(d => { approved[d.section] = true })
      setApprovedSections(approved)
    } catch (e) { alert(e.message) }
    finally { setLoading(false) }
  }

  const handleApprove = async () => {
    setSaving(true)
    try {
      const sections = Object.entries(approvedSections).filter(([, v]) => v).map(([k]) => k)
      await api.approveCV({ version_name: versionName, approved_sections: sections })
      setSaved(true)
      api.listVersions().then(setVersions).catch(() => {})
    } catch (e) { alert(e.message) }
    finally { setSaving(false) }
  }

  const handleExport = (vname) => {
    window.open(api.exportCV(exportFormat, vname || undefined), '_blank')
  }

  return (
    <div className="flex flex-col">
      <PageHeader title="CV Editor" subtitle="Chat-driven edits with diff review" />

      <div className="px-4 mb-4">
        <div className="bg-card border border-theme rounded-xl p-3">
          <textarea
            value={instruction}
            onChange={e => setInstruction(e.target.value)}
            placeholder="e.g. Emphasize the SoyYo fraud prevention angle for a Stripe role…"
            rows={3}
            className="w-full bg-transparent text-sm text-body placeholder-faint resize-none outline-none leading-relaxed"
          />
          <div className="flex items-center gap-2 mt-2">
            <input
              value={versionName}
              onChange={e => setVersionName(e.target.value)}
              placeholder="Version name (optional)"
              className="flex-1 bg-card2 border border-theme rounded-lg px-3 py-1.5 text-xs text-body placeholder-faint outline-none"
            />
            <button
              onClick={handleChat}
              disabled={loading || !instruction.trim()}
              className="flex items-center gap-1.5 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white px-4 py-1.5 rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? <Spinner size={4} /> : <Send size={14} />}
              {loading ? 'Editing…' : 'Edit'}
            </button>
          </div>
        </div>
      </div>

      {diff && (
        <div className="px-4 mb-4">
          <div className="text-sm font-medium text-body mb-3">Review changes</div>
          <div className="space-y-3">
            {diff.diff.map(d => (
              <div key={d.section} className={`bg-card border rounded-xl overflow-hidden ${approvedSections[d.section] ? 'border-blue-400' : 'border-theme'}`}>
                <div className="flex items-center justify-between px-4 py-2.5 border-b border-theme">
                  <span className="text-sm font-medium text-body capitalize">{d.section}</span>
                  <button
                    onClick={() => setApprovedSections(s => ({ ...s, [d.section]: !s[d.section] }))}
                    className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md font-medium transition-colors ${
                      approvedSections[d.section] ? 'bg-blue-500 text-white' : 'bg-card2 text-muted border border-theme'
                    }`}
                  >
                    {approvedSections[d.section] ? <Check size={12} /> : <X size={12} />}
                    {approvedSections[d.section] ? 'Accept' : 'Reject'}
                  </button>
                </div>
                <DiffSection original={d.original} proposed={d.proposed} />
              </div>
            ))}
          </div>

          {!saved ? (
            <button onClick={handleApprove} disabled={saving}
              className="w-full mt-4 bg-green-500 hover:bg-green-600 disabled:opacity-50 text-white rounded-xl py-3 text-sm font-medium">
              {saving ? 'Saving…' : `Save version "${versionName}"`}
            </button>
          ) : (
            <div className="mt-4 bg-green-50 border border-green-200 dark:bg-green-900/40 dark:border-green-700 rounded-xl p-3 text-center text-green-600 dark:text-green-400 text-sm">
              ✓ Saved as "{versionName}"
            </div>
          )}
        </div>
      )}

      <div className="px-4 mb-4">
        <div className="bg-card border border-theme rounded-xl p-4">
          <div className="text-sm font-medium text-body mb-3">Export CV</div>
          <div className="flex gap-2 mb-3">
            {['pdf', 'html', 'plaintext'].map(f => (
              <button key={f} onClick={() => setExportFormat(f)}
                className={`flex-1 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  exportFormat === f ? 'bg-blue-500 border-blue-400 text-white' : 'bg-card2 border-theme text-muted'
                }`}
              >
                {f === 'plaintext' ? 'Plain Text' : f.toUpperCase()}
              </button>
            ))}
          </div>
          <button onClick={() => handleExport(null)}
            className="w-full flex items-center justify-center gap-2 bg-card2 hover:bg-card border border-theme text-body rounded-lg py-2.5 text-sm font-medium">
            <Download size={14} /> Export master CV
          </button>
        </div>
      </div>

      {versions.length > 0 && (
        <div className="px-4 pb-4">
          <div className="text-xs text-muted font-medium uppercase tracking-wide mb-2">Saved versions</div>
          <div className="space-y-2">
            {versions.map(v => (
              <div key={v} className="flex items-center justify-between bg-card border border-theme rounded-xl px-4 py-3">
                <span className="text-sm text-body">{v}</span>
                <button onClick={() => handleExport(v)}
                  className="flex items-center gap-1 text-xs text-blue-500">
                  <Download size={12} /> {exportFormat.toUpperCase()}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function DiffSection({ original, proposed }) {
  const [showOriginal, setShowOriginal] = useState(false)

  const renderValue = (val) => {
    if (typeof val === 'string') return <p className="text-xs text-body leading-relaxed">{val}</p>
    if (Array.isArray(val)) return (
      <ul className="text-xs text-body space-y-1">
        {val.map((item, i) => (
          <li key={i} className="flex gap-1.5">
            <span className="text-faint flex-shrink-0">•</span>
            <span className="leading-relaxed">{typeof item === 'string' ? item : JSON.stringify(item)}</span>
          </li>
        ))}
      </ul>
    )
    return <pre className="text-xs text-body whitespace-pre-wrap">{JSON.stringify(val, null, 2)}</pre>
  }

  return (
    <div className="p-4">
      <div className="text-xs text-green-600 dark:text-green-400 font-medium mb-1.5">Proposed</div>
      {renderValue(proposed)}
      <button onClick={() => setShowOriginal(v => !v)}
        className="flex items-center gap-1 text-xs text-muted mt-3">
        {showOriginal ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        {showOriginal ? 'Hide' : 'Show'} original
      </button>
      {showOriginal && (
        <div className="mt-2 pt-2 border-t border-theme">
          <div className="text-xs text-muted font-medium mb-1.5">Original</div>
          {renderValue(original)}
        </div>
      )}
    </div>
  )
}
