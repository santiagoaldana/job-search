import { useEffect, useState, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Send, Check, X, Download, ChevronDown, ChevronUp, FileText, Copy } from 'lucide-react'
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
  const [atsScore, setAtsScore] = useState(null)
  const [scoring, setScoring] = useState(false)

  const [coverOpen, setCoverOpen] = useState(false)
  const [coverForm, setCoverForm] = useState({
    lead_id: null, company_name: '', job_title: '', job_description: '',
    contact_name: '', contact_title: '', contact_linkedin_url: '', contact_notes: ''
  })
  const [coverResult, setCoverResult] = useState(null)
  const [coverLoading, setCoverLoading] = useState(false)
  const [coverLeads, setCoverLeads] = useState([])
  const [copied, setCopied] = useState(false)

  const [searchParams] = useSearchParams()
  const leadId = searchParams.get('lead_id') ? Number(searchParams.get('lead_id')) : null
  const [leadContext, setLeadContext] = useState(null)
  const [synthesizing, setSynthesizing] = useState(false)

  useEffect(() => {
    api.listVersions().then(setVersions).catch(() => {})
    api.getLeads({ status: 'active' }).then(data => {
      const list = Array.isArray(data) ? data : (data.leads || data.items || [])
      setCoverLeads(list)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (leadId) {
      setCoverOpen(true)
      setCoverForm(f => ({ ...f, lead_id: leadId }))
    }
  }, [leadId])

  useEffect(() => {
    if (!leadId) return
    api.getLead(leadId)
      .then(lead => setLeadContext({ company_name: lead.company_name, title: lead.title }))
      .catch(() => {})
    setSynthesizing(true)
    setDiff(null); setSaved(false)
    api.fetchLeadJD(leadId)
      .catch(() => {})
      .finally(() => {
        api.synthesizeCV(leadId)
          .then(result => {
            setDiff(result)
            setVersionName(result.version_name || '')
            const approved = {}
            result.diff.forEach(d => { approved[d.section] = true })
            setApprovedSections(approved)
          })
          .catch(e => alert(`Synthesis failed: ${e.message}`))
          .finally(() => setSynthesizing(false))
      })
  }, [leadId])

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

  const handleCoverLetter = async () => {
    setCoverLoading(true)
    setCoverResult(null)
    try {
      const payload = {}
      if (coverForm.lead_id) payload.lead_id = Number(coverForm.lead_id)
      if (coverForm.company_name) payload.company_name = coverForm.company_name
      if (coverForm.job_title) payload.job_title = coverForm.job_title
      if (coverForm.job_description) payload.job_description = coverForm.job_description
      if (coverForm.contact_name) payload.contact_name = coverForm.contact_name
      if (coverForm.contact_title) payload.contact_title = coverForm.contact_title
      if (coverForm.contact_linkedin_url) payload.contact_linkedin_url = coverForm.contact_linkedin_url
      if (coverForm.contact_notes) payload.contact_notes = coverForm.contact_notes
      const result = await api.generateCoverLetter(payload)
      setCoverResult(result)
    } catch (e) { alert(`Cover letter failed: ${e.message}`) }
    finally { setCoverLoading(false) }
  }

  const handleCopy = () => {
    if (!coverResult) return
    navigator.clipboard.writeText(coverResult.letter).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const handleATSScore = async () => {
    setScoring(true)
    try {
      const result = await api.atsScore(versionName || null)
      setAtsScore(result)
    } catch (e) { alert(e.message) }
    finally { setScoring(false) }
  }

  return (
    <div className="flex flex-col">
      <PageHeader title="CV Editor" subtitle="Chat-driven edits with diff review" />

      {leadContext && (
        <div className="mx-4 mb-3 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 rounded-xl px-4 py-3">
          <div className="text-xs text-blue-500 font-medium uppercase tracking-wide mb-0.5">Tailoring for</div>
          <div className="text-sm font-semibold text-body leading-snug">{leadContext.title}</div>
          <div className="text-xs text-muted mt-0.5">{leadContext.company_name}</div>
        </div>
      )}

      {synthesizing && (
        <div className="flex flex-col items-center gap-3 py-10">
          <Spinner size={8} />
          <div className="text-sm text-muted text-center px-6">
            {leadContext ? `Tailoring CV for ${leadContext.company_name}…` : 'Synthesizing CV…'}
          </div>
          <div className="text-xs text-faint text-center">This takes 15–30 seconds</div>
        </div>
      )}

      {!synthesizing && (
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
      )}

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

          <button onClick={handleATSScore} disabled={scoring}
            className="w-full mt-2 flex items-center justify-center gap-2 bg-card2 hover:bg-card border border-theme text-body rounded-lg py-2.5 text-sm font-medium disabled:opacity-50">
            {scoring ? <Spinner size={4} /> : null}
            {scoring ? 'Scoring…' : 'Check ATS Score'}
          </button>

          {atsScore && (
            <div className="mt-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-body">ATS Score</span>
                <span className={`text-2xl font-bold ${atsScore.score >= 7 ? 'text-green-500' : atsScore.score >= 5 ? 'text-yellow-500' : 'text-red-500'}`}>
                  {atsScore.score}/10
                </span>
              </div>
              {atsScore.verdict && <div className="text-xs text-muted">{atsScore.verdict}</div>}
              {atsScore.quick_wins?.map((w, i) => (
                <div key={i} className="text-xs text-blue-500">→ {w}</div>
              ))}
              {atsScore.structure_issues?.map((s, i) => (
                <div key={i} className="text-xs text-red-500">⚠ {s}</div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Cover Letter Section */}
      <div className="px-4 mb-4">
        <div className="bg-card border border-theme rounded-xl overflow-hidden">
          <button
            onClick={() => setCoverOpen(v => !v)}
            className="w-full flex items-center justify-between px-4 py-3"
          >
            <div className="flex items-center gap-2">
              <FileText size={14} className="text-muted" />
              <span className="text-sm font-medium text-body">Write Cover Letter</span>
            </div>
            {coverOpen ? <ChevronUp size={14} className="text-muted" /> : <ChevronDown size={14} className="text-muted" />}
          </button>

          {coverOpen && (
            <div className="px-4 pb-4 border-t border-theme pt-4 space-y-3">
              {/* Lead picker */}
              <div>
                <label className="text-xs text-muted block mb-1">Job (select lead or fill manually)</label>
                <select
                  value={coverForm.lead_id || ''}
                  onChange={e => setCoverForm(f => ({ ...f, lead_id: e.target.value || null }))}
                  className="w-full bg-card2 border border-theme rounded-lg px-3 py-2 text-sm text-body outline-none"
                >
                  <option value="">— Enter manually below —</option>
                  {coverLeads.map(l => (
                    <option key={l.id} value={l.id}>{l.title} @ {l.company_name}</option>
                  ))}
                </select>
              </div>

              {!coverForm.lead_id && (
                <>
                  <input
                    value={coverForm.company_name}
                    onChange={e => setCoverForm(f => ({ ...f, company_name: e.target.value }))}
                    placeholder="Company name"
                    className="w-full bg-card2 border border-theme rounded-lg px-3 py-2 text-sm text-body placeholder-faint outline-none"
                  />
                  <input
                    value={coverForm.job_title}
                    onChange={e => setCoverForm(f => ({ ...f, job_title: e.target.value }))}
                    placeholder="Job title (optional)"
                    className="w-full bg-card2 border border-theme rounded-lg px-3 py-2 text-sm text-body placeholder-faint outline-none"
                  />
                  <textarea
                    value={coverForm.job_description}
                    onChange={e => setCoverForm(f => ({ ...f, job_description: e.target.value }))}
                    placeholder="Paste job description (optional)"
                    rows={3}
                    className="w-full bg-card2 border border-theme rounded-lg px-3 py-2 text-sm text-body placeholder-faint outline-none resize-none"
                  />
                </>
              )}

              <div className="pt-1 border-t border-theme">
                <div className="text-xs text-muted mb-2">Contact (optional)</div>
                <div className="space-y-2">
                  <input
                    value={coverForm.contact_name}
                    onChange={e => setCoverForm(f => ({ ...f, contact_name: e.target.value }))}
                    placeholder="Contact name"
                    className="w-full bg-card2 border border-theme rounded-lg px-3 py-2 text-sm text-body placeholder-faint outline-none"
                  />
                  <input
                    value={coverForm.contact_title}
                    onChange={e => setCoverForm(f => ({ ...f, contact_title: e.target.value }))}
                    placeholder="Contact title"
                    className="w-full bg-card2 border border-theme rounded-lg px-3 py-2 text-sm text-body placeholder-faint outline-none"
                  />
                  <input
                    value={coverForm.contact_linkedin_url}
                    onChange={e => setCoverForm(f => ({ ...f, contact_linkedin_url: e.target.value }))}
                    placeholder="LinkedIn URL"
                    className="w-full bg-card2 border border-theme rounded-lg px-3 py-2 text-sm text-body placeholder-faint outline-none"
                  />
                  <input
                    value={coverForm.contact_notes}
                    onChange={e => setCoverForm(f => ({ ...f, contact_notes: e.target.value }))}
                    placeholder="How you know them / shared context (e.g. Boston Fintech Week)"
                    className="w-full bg-card2 border border-theme rounded-lg px-3 py-2 text-sm text-body placeholder-faint outline-none"
                  />
                </div>
              </div>

              <button
                onClick={handleCoverLetter}
                disabled={coverLoading || (!coverForm.lead_id && !coverForm.company_name)}
                className="w-full flex items-center justify-center gap-2 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-medium"
              >
                {coverLoading ? <Spinner size={4} /> : <FileText size={14} />}
                {coverLoading ? 'Generating… (~15s)' : 'Generate Cover Letter'}
              </button>

              {coverResult && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted">
                      {coverResult.letter.split(/\s+/).filter(Boolean).length} words
                    </span>
                    <button
                      onClick={handleCopy}
                      className="flex items-center gap-1.5 text-xs text-blue-500 font-medium"
                    >
                      <Copy size={12} />
                      {copied ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                  <textarea
                    value={coverResult.letter}
                    onChange={e => setCoverResult(r => ({ ...r, letter: e.target.value }))}
                    rows={14}
                    className="w-full bg-card2 border border-theme rounded-lg px-3 py-2 text-sm text-body outline-none resize-none leading-relaxed"
                  />
                  {coverResult.subject_line && (
                    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg px-3 py-2">
                      <span className="text-xs text-muted">Subject: </span>
                      <span className="text-xs text-body">{coverResult.subject_line}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
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
