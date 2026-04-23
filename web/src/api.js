const BASE = '/api'

async function request(method, path, body) {
  const opts = { method, credentials: 'include', headers: { 'Content-Type': 'application/json' } }
  if (body !== undefined) opts.body = JSON.stringify(body)
  const res = await fetch(BASE + path, opts)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

const get = (path) => request('GET', path)
const post = (path, body) => request('POST', path, body)
const patch = (path, body) => request('PATCH', path, body)

export const api = {
  // Daily brief
  getDailyBrief: () => get('/daily-brief'),

  // Companies
  getCompanies: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return get('/companies' + (q ? '?' + q : ''))
  },
  getFunnel: () => get('/companies/funnel'),
  getCompany: (id) => get(`/companies/${id}`),
  createCompany: (data) => post('/companies', data),
  updateCompany: (id, data) => patch(`/companies/${id}`, data),
  advanceStage: (id, stage) => post(`/companies/${id}/stage`, { stage }),
  archiveCompany: (id) => post(`/companies/${id}/archive`),
  refreshIntel: (id) => post(`/companies/${id}/intel/refresh`),

  // Leads
  getLeads: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return get('/leads' + (q ? '?' + q : ''))
  },
  getHotLeads: () => get('/leads/hot'),
  refreshLeads: () => post('/leads/refresh'),
  scoreLead: (id) => post(`/leads/${id}/score`),

  // Outreach
  getDueToday: () => get('/outreach/due-today'),
  createOutreach: (data) => post('/outreach', data),
  generateOutreach: (data) => post('/outreach/generate', data),
  logOutreach: (data) => post('/outreach', data),
  updateOutreachResponse: (id, status) => patch(`/outreach/${id}/response`, { response_status: status }),
  updateResponse: (id, status, notes) => patch(`/outreach/${id}/response`, { response_status: status, notes }),

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
  generateDrafts: (days, count) => post('/content/generate', { days, count }),
  approveDraft: (id) => patch(`/content/${id}`, { status: 'approved' }),
  discardDraft: (id) => patch(`/content/${id}`, { status: 'discarded' }),
  regenerateDraft: (id, instructions) => post(`/content/${id}/regenerate`, { instructions }),
  composePost: (context) => post('/content/compose', { context }),

  // AI Suggestions
  getSuggestions: () => get('/daily-brief/suggestions'),
  approveSuggestion: (id) => post(`/daily-brief/suggestions/${id}/approve`),
  skipSuggestion: (id) => post(`/daily-brief/suggestions/${id}/skip`),
  runDiscovery: () => post('/daily-brief/run-discovery'),
}
