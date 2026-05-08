const BASE = '/api'

async function request(method, path, body) {
  const opts = { method, credentials: 'include', headers: { 'Content-Type': 'application/json' } }
  if (body !== undefined) opts.body = JSON.stringify(body)
  const res = await fetch(BASE + path, opts)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = Array.isArray(err.detail)
      ? err.detail.map(e => e.msg || JSON.stringify(e)).join('; ')
      : (err.detail || res.statusText)
    throw new Error(detail)
  }
  return res.json()
}

const get = (path) => request('GET', path)
const post = (path, body) => request('POST', path, body)
const patch = (path, body) => request('PATCH', path, body)

export const api = {
  // Daily brief
  getDailyBrief: () => get('/daily-brief'),
  dismissBriefAction: (action_type, payload_id) => post('/daily-brief/dismiss', { action_type, payload_id }),

  // Companies
  getCompanies: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return get('/companies' + (q ? '?' + q : ''))
  },
  getFunnel: () => get('/companies/funnel'),
  getCompany: (id) => get(`/companies/${id}`),
  createCompany: (data) => post('/companies', data),
  bulkArchive: (names) => post('/companies/bulk-archive', { names }),
  updateCompany: (id, data) => patch(`/companies/${id}`, data),
  advanceStage: (id, stage) => post(`/companies/${id}/stage`, { stage }),
  setCompanyStage: (id, stage) => post(`/companies/${id}/stage`, { stage }),
  archiveCompany: (id) => post(`/companies/${id}/archive`),
  refreshIntel: (id) => post(`/companies/${id}/intel/refresh`),
  findContacts: (id) => post(`/companies/${id}/find-contacts`),
  enrichCompany: (id) => post(`/companies/${id}/enrich`),
  enrichAllCompanies: () => post('/companies/enrich-all'),

  // Leads
  getLeads: (params = {}) => {
    const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null))
    const q = new URLSearchParams(clean).toString()
    return get('/leads' + (q ? '?' + q : ''))
  },
  getHotLeads: () => get('/leads/hot'),
  getLead: (id) => get(`/leads/${id}`),
  refreshLeads: () => post('/leads/refresh'),
  scoreLead: (id) => post(`/leads/${id}/score`),
  fetchLeadJD: (id) => post(`/leads/${id}/fetch-jd`),
  updateLeadStatus: (id, status, reason = null) => request('PATCH', `/leads/${id}/status?status=${status}${reason ? `&reason=${reason}` : ''}`),
  parseSalary: (id) => post(`/leads/${id}/parse-salary`),

  // Outreach
  getDueToday: () => get('/outreach/due-today'),
  getOutreachStats: () => get('/outreach/stats'),
  listOutreach: (params = {}) => { const q = new URLSearchParams(params).toString(); return get('/outreach' + (q ? '?' + q : '')) },
  createOutreach: (data) => post('/outreach', data),
  generateOutreach: (data) => post('/outreach/generate', data),
  logOutreach: (data) => post('/outreach', data),
  deleteOutreach: (id) => request('DELETE', `/outreach/${id}`),
  updateOutreachResponse: (id, status) => patch(`/outreach/${id}/response`, { response_status: status }),
  updateResponse: (id, status, notes) => patch(`/outreach/${id}/response`, { response_status: status, notes }),
  draftFollowup: (id, followup_day, language = 'en') => post(`/outreach/${id}/draft-followup`, { followup_day, language }),
  buildMailto: (id, data) => post(`/outreach/${id}/build-mailto`, data),
  draftTemplate: (id, followupType) => post(`/outreach/${id}/draft-template?followup_type=${followupType}`),
  markFollowupSent: (id, data) => post(`/outreach/${id}/mark-followup-sent`, data),
  sendFollowup: (id, data) => post(`/outreach/${id}/send-followup`, data),
  skipOutreach: (id) => post(`/outreach/${id}/skip`, {}),
  patchOutreach: (id, data) => patch(`/outreach/${id}`, data),

  // CV
  getMasterCV: () => get('/cv/master'),
  chatEditCV: (data) => post('/cv/chat', data),
  approveCV: (data) => post('/cv/approve', data),
  listVersions: () => get('/cv/versions'),
  exportCV: (format, version_name) => {
    const q = new URLSearchParams({ format, ...(version_name ? { version_name } : {}) })
    return BASE + '/cv/export?' + q
  },
  synthesizeCV: (lead_id, version_name) => post('/cv/synthesize', { lead_id, version_name }),
  atsScore: (version_name) => post('/cv/ats-score', { version_name }),
  generateCoverLetter: (data) => post('/cv/cover-letter', data),
  uploadMasterCV: (formData) => fetch(BASE + '/cv/upload-master', {
    method: 'POST', credentials: 'include', body: formData,
  }).then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail) })),

  // Applications
  getApplications: () => get('/applications'),
  createApplication: (data) => post('/applications', data),
  approveApplication: (id) => post(`/applications/${id}/approve`),
  submitApplication: (id, apply_url) => post(`/applications/${id}/submit`, { apply_url }),

  // Events
  getEvents: (mode) => get('/events' + (mode ? `?mode=${mode}` : '')),
  getThisWeekEvents: () => get('/events/this-week-checked'),
  getRegisterEvents: () => get('/events?mode=register'),
  addToCalendar: (event_id) => post(`/events/add-to-calendar?event_id=${event_id}`),
  markRegistered: (event_id, registered = true) => patch(`/events/${event_id}/register?registered=${registered}`),

  // Content (router prefix = /api/content)
  getDrafts: () => get('/content'),
  getSubstackDrafts: () => get('/content/substack'),
  generateSubstackDraft: (topic, count = 1) => post('/content/substack/generate', { topic, count }),
  getPublished: () => get('/content/published'),
  generateDrafts: (days, count) => post('/content/generate', { days, count }),
  approveDraft: (id) => patch(`/content/${id}`, { status: 'approved' }),
  schedulePost: (id, scheduled_at) => patch(`/content/${id}`, { status: 'scheduled', scheduled_at }),
  discardDraft: (id) => patch(`/content/${id}`, { status: 'discarded' }),
  regenerateDraft: (id, instructions) => post(`/content/${id}/regenerate`, { instructions }),
  saveDraftBody: (id, body) => patch(`/content/${id}`, { status: 'pending', body }),
  composePost: (context) => post('/content/compose', { context }),
  publishNow: (id) => post(`/content/${id}/publish-now`),
  runPublishCycle: () => post('/content/linkedin/run-cycle'),

  // LinkedIn OAuth
  getLinkedInStatus: () => get('/content/linkedin/status'),
  connectLinkedIn: () => post('/content/linkedin/connect'),
  getNextSlot: () => get('/content/linkedin/next-slot'),

  // Content feeds
  getFeeds: () => get('/content/feeds'),
  addFeed: (data) => post('/content/feeds', data),
  deleteFeed: (id) => request('DELETE', `/content/feeds/${id}`),

  // Contacts
  importLinkedInContacts: (formData) => fetch(BASE + '/contacts/import-linkedin', {
    method: 'POST', credentials: 'include', body: formData,
  }).then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail) })),
  listAllContacts: () => get('/contacts'),
  getContact: (id) => get(`/contacts/${id}`),
  quickAddContact: (data) => post('/contacts/quick-add', data),
  parseContactScreenshot: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(BASE + '/contacts/parse-screenshot', { method: 'POST', credentials: 'include', body: fd })
      .then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail) }))
  },
  updateContact: (id, data) => patch(`/contacts/${id}`, data),
  markEmailBounced: (id) => post(`/contacts/${id}/bounce`),
  getContactNextStep: (id) => get(`/contacts/${id}/next-step`),
  getNetworkPath: (companyId, refresh = false) => get(`/companies/${companyId}/network-path${refresh ? '?refresh=true' : ''}`),

  // References
  listReferences: (params = {}) => { const q = new URLSearchParams(params).toString(); return get('/references' + (q ? '?' + q : '')) },
  addReference: (data) => post('/references', data),
  updateReference: (id, data) => patch(`/references/${id}`, data),
  deleteReference: (id) => request('DELETE', `/references/${id}`),
  getReferencesForCompany: (companyId) => get(`/references/for-company/${companyId}`),

  // Reports
  getProgressReport: () => get('/reports/progress'),

  // AI Suggestions
  getSuggestions: () => get('/daily-brief/suggestions'),
  approveSuggestion: (id, motivation) => post(`/daily-brief/suggestions/${id}/approve`, { motivation }),
  skipSuggestion: (id) => post(`/daily-brief/suggestions/${id}/skip`),
  runDiscovery: () => post('/daily-brief/run-discovery'),
}
