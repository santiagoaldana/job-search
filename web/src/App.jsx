import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { Home, Kanban, Briefcase, Calendar, FileText, Settings, Cpu } from 'lucide-react'
import DailyBrief from './pages/DailyBrief'
import Funnel from './pages/Funnel'
import CompanyCard from './pages/CompanyCard'
import Leads from './pages/Leads'
import Events from './pages/Events'
import Content from './pages/Content'
import CVPage from './pages/CVPage'
import SettingsPage from './pages/Settings'
import Login from './pages/Login'

const NAV = [
  { to: '/', icon: Home, label: 'Brief' },
  { to: '/funnel', icon: Kanban, label: 'Funnel' },
  { to: '/leads', icon: Briefcase, label: 'Leads' },
  { to: '/events', icon: Calendar, label: 'Events' },
  { to: '/content', icon: FileText, label: 'Content' },
  { to: '/cv', icon: Cpu, label: 'CV' },
  { to: '/settings', icon: Settings, label: 'More' },
]

function BottomNav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 nav-bg border-t border-theme z-50 shadow-lg">
      <div className="flex justify-around max-w-lg mx-auto">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex flex-col items-center py-2 px-2 text-xs gap-1 transition-colors min-w-0 ${
                isActive ? 'text-blue-500' : 'text-muted'
              }`
            }
          >
            <Icon size={20} />
            <span>{label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}

export default function App() {
  const [authed, setAuthed] = useState(null) // null=loading, true=ok, false=login
  const [authError, setAuthError] = useState(null)

  useEffect(() => {
    // Check auth error from redirect
    const params = new URLSearchParams(window.location.search)
    const err = params.get('auth_error')
    if (err) { setAuthError(err); setAuthed(false); return }

    fetch('/auth/me', { credentials: 'include' })
      .then(r => r.ok ? setAuthed(true) : setAuthed(false))
      .catch(() => setAuthed(false))
  }, [])

  if (authed === null) return null // loading

  if (!authed) return <Login error={authError} />

  return (
    <BrowserRouter>
      <div className="flex flex-col min-h-screen max-w-lg mx-auto w-full pb-16">
        <Routes>
          <Route path="/" element={<DailyBrief />} />
          <Route path="/funnel" element={<Funnel />} />
          <Route path="/company/:id" element={<CompanyCard />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/events" element={<Events />} />
          <Route path="/content" element={<Content />} />
          <Route path="/cv" element={<CVPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </div>
      <BottomNav />
    </BrowserRouter>
  )
}
