import { useEffect, useState } from 'react'
import { ExternalLink, MapPin, Clock, Calendar, Users, CheckCircle, PlusCircle } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import Badge from '../components/Badge'
import Spinner from '../components/Spinner'

const CATEGORY_COLOR = {
  STRATEGIC: 'purple', strategic: 'purple',
  HIGH_PROBABILITY: 'blue', high_probability: 'blue',
  WILDCARD: 'orange', wildcard: 'orange',
}

const NOISE_PHRASES = [
  'sticker', 'crafts', 'yoga', 'cooking', 'art class', 'dance', 'wedding',
  'birthday', 'baby shower', 'wine tasting', 'painting', 'knitting',
  'lisa frank', 'rainbow', 'diy workshop', 'workshop for kids',
  'happy hour', 'datathon', 'applying ai', 'knowledge graph', 'research copilot',
]

const RELEVANT_KEYWORDS = [
  'fintech', 'payments', 'banking', 'identity', 'fraud', 'embedded',
  'agentic', 'startup', 'venture', 'cto', 'cpo', 'executive',
  'mit sloan', 'mit imagination', 'sloan', 'techstars', 'emtech',
  'series b', 'series c', 'smarter faster', 'nacha', 'fintech week',
]

function isRelevant(event) {
  const text = `${event.name} ${event.description || ''}`.toLowerCase()
  // Always filter noise regardless of category
  if (NOISE_PHRASES.some(kw => text.includes(kw))) return false
  return true
}

export default function Events() {
  const [tab, setTab] = useState('this_week')
  const [thisWeek, setThisWeek] = useState([])
  const [upcoming, setUpcoming] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    Promise.all([
      api.getThisWeekEvents(),
      api.getRegisterEvents(),
    ]).then(([week, reg]) => {
      setThisWeek(week.filter(isRelevant))
      setUpcoming(reg.filter(isRelevant))
    }).catch(console.error)
    .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const onCalendarAdded = (eventId) => {
    setThisWeek(prev => prev.map(e => e.id === eventId ? { ...e, in_calendar: true } : e))
  }

  return (
    <div className="flex flex-col">
      <PageHeader
        title="Events"
        subtitle={tab === 'this_week'
          ? `${thisWeek.length} this week`
          : `${upcoming.length} upcoming · Boston/Cambridge`}
      />

      {/* Tab switcher */}
      <div className="flex mx-4 mb-4 bg-card2 rounded-xl p-1 border border-theme">
        <button
          onClick={() => setTab('this_week')}
          className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === 'this_week' ? 'bg-white dark:bg-slate-700 text-body shadow-sm' : 'text-muted'
          }`}
        >
          This Week
          {thisWeek.length > 0 && (
            <span className="ml-1.5 bg-blue-500 text-white text-xs px-1.5 py-0.5 rounded-full">
              {thisWeek.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setTab('register')}
          className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === 'register' ? 'bg-white dark:bg-slate-700 text-body shadow-sm' : 'text-muted'
          }`}
        >
          Register
          {upcoming.length > 0 && (
            <span className="ml-1.5 bg-orange-500 text-white text-xs px-1.5 py-0.5 rounded-full">
              {upcoming.length}
            </span>
          )}
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Spinner size={8} /></div>
      ) : (
        <div className="px-4 space-y-3 pb-4">
          {tab === 'this_week' && (
            <>
              {thisWeek.length === 0 ? (
                <div className="py-12 text-center text-muted text-sm">No events this week</div>
              ) : (
                thisWeek.map(e => (
                  <ThisWeekCard key={e.id} event={e} onCalendarAdded={onCalendarAdded} />
                ))
              )}
            </>
          )}

          {tab === 'register' && (
            <>
              <div className="bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 rounded-xl px-4 py-3 text-xs text-blue-700 dark:text-blue-300 leading-relaxed">
                Boston/Cambridge events 2–13 weeks out. Register while spots remain. Tap "Register now" — I'll add it to your Google Calendar automatically.
              </div>
              {upcoming.length === 0 ? (
                <div className="py-12 text-center text-muted text-sm">
                  No upcoming Boston/Cambridge events found
                </div>
              ) : (
                upcoming.map(e => <RegisterCard key={e.id} event={e} onAdded={onCalendarAdded} />)
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function ThisWeekCard({ event, onCalendarAdded }) {
  const daysAway = event.days_away
  const isToday = daysAway === 0
  const isTomorrow = daysAway === 1
  const [adding, setAdding] = useState(false)

  const handleAddToCalendar = async () => {
    setAdding(true)
    try {
      await api.addToCalendar(event.id)
      onCalendarAdded(event.id)
    } catch (e) {
      alert(e.message)
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className={`bg-card border rounded-xl p-4 ${isToday ? 'border-orange-300 dark:border-orange-600' : 'border-theme'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-body text-sm leading-snug">{event.name}</div>
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          {isToday && <Badge color="orange">Today</Badge>}
          {isTomorrow && <Badge color="yellow">Tomorrow</Badge>}
          {!isToday && !isTomorrow && daysAway !== null && (
            <Badge color="blue">{daysAway}d away</Badge>
          )}
        </div>
      </div>

      {event.location && (
        <div className="flex items-start gap-1.5 mt-2 text-xs text-muted">
          <MapPin size={12} className="mt-0.5 flex-shrink-0 text-blue-500" />
          <span>{event.location}</span>
        </div>
      )}

      <div className="flex items-center gap-1.5 mt-1 text-xs text-muted">
        <Clock size={12} />
        <span>{event.date}{event.time ? ` · ${event.time}` : ' · Check event page for time'}</span>
      </div>

      {/* Calendar status */}
      <div className="mt-2">
        {event.in_calendar ? (
          <span className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400 font-medium">
            <CheckCircle size={12} /> On your Google Calendar
          </span>
        ) : (
          <button
            onClick={handleAddToCalendar}
            disabled={adding}
            className="flex items-center gap-1.5 text-xs text-orange-500 font-medium disabled:opacity-50"
          >
            <PlusCircle size={12} />
            {adding ? 'Adding…' : 'Add to Google Calendar'}
          </button>
        )}
      </div>

      {event.meetings_booked > 0 && (
        <div className="flex items-center gap-1 mt-2 text-xs text-muted">
          <Users size={11} /> {event.meetings_booked} meetings booked
        </div>
      )}

      {event.notes && (
        <div className="mt-2 text-xs text-muted leading-relaxed line-clamp-2">{event.notes}</div>
      )}

      {event.url && (
        <a href={event.url} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-blue-500 font-medium mt-3">
          <ExternalLink size={11} /> Open event page
        </a>
      )}
    </div>
  )
}

function RegisterCard({ event, onAdded }) {
  const weeks = event.weeks_away
  const urgency = weeks <= 3 ? 'red' : weeks <= 6 ? 'orange' : 'slate'
  const [busy, setBusy] = useState(false)
  const [registered, setRegistered] = useState(event.is_registered || false)

  const handleRegister = async () => {
    if (event.url) window.open(event.url, '_blank')
    setBusy(true)
    try {
      await api.addToCalendar(event.id)
      await api.markRegistered(event.id, true)
      setRegistered(true)
      onAdded && onAdded(event.id)
    } catch (e) {
      // silent — user still got the URL
    } finally {
      setBusy(false)
    }
  }

  const handleAddCalendarOnly = async () => {
    setBusy(true)
    try {
      await api.addToCalendar(event.id)
      onAdded && onAdded(event.id)
    } catch (e) {
      alert(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleUnregister = async () => {
    await api.markRegistered(event.id, false)
    setRegistered(false)
  }

  return (
    <div className={`bg-card border rounded-xl p-4 ${registered ? 'border-green-300 dark:border-green-700' : 'border-theme'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-body text-sm leading-snug">{event.name}</div>
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          {registered && <Badge color="green">Registered</Badge>}
          {weeks !== null && (
            <Badge color={urgency}>
              {weeks < 2 ? `${event.days_away}d` : `${Math.round(weeks)}w away`}
            </Badge>
          )}
          {event.category && (
            <Badge color={CATEGORY_COLOR[event.category] || 'slate'}>
              {event.category.toLowerCase().replace('_', ' ')}
            </Badge>
          )}
        </div>
      </div>

      {event.location && (
        <div className="flex items-start gap-1.5 mt-2 text-xs text-muted">
          <MapPin size={12} className="mt-0.5 flex-shrink-0 text-blue-500" />
          <span>{event.location}</span>
        </div>
      )}

      <div className="flex items-center gap-1.5 mt-1 text-xs text-muted">
        <Calendar size={12} />
        <span>{event.date}</span>
        {event.cost && <span className="ml-1">· {event.cost}</span>}
      </div>

      {event.notes && (
        <div className="mt-2 text-xs text-muted leading-relaxed line-clamp-3">{event.notes}</div>
      )}

      {registered ? (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400 font-medium">
            <CheckCircle size={14} /> Already registered
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleAddCalendarOnly}
              disabled={busy}
              className="flex-1 flex items-center justify-center gap-1.5 border border-theme rounded-lg py-2 text-xs text-muted font-medium"
            >
              <Calendar size={12} /> {busy ? 'Adding…' : 'Add to calendar'}
            </button>
            <button
              onClick={handleUnregister}
              className="text-xs text-muted underline px-2"
            >
              Undo
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={handleRegister}
          disabled={busy}
          className="mt-3 flex items-center justify-center gap-2 w-full bg-blue-500 hover:bg-blue-600 disabled:opacity-60 text-white rounded-lg py-2.5 text-sm font-medium transition-colors"
        >
          <ExternalLink size={14} />
          {busy ? 'Opening + saving…' : 'Register + add to calendar'}
        </button>
      )}
    </div>
  )
}
