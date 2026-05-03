import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { Application, ApplicationStatus } from '../lib/types'

const ALL_STATUSES: ApplicationStatus[] = [
  'discovered', 'shortlisted', 'drafting', 'ready', 'applied',
  'applied_confirmed', 'recruiter_engaged', 'phone_screen', 'technical_interview',
  'onsite', 'offer', 'accepted', 'declined', 'rejected', 'ghosted', 'missed_deadline',
]

const STATUS_COLORS: Record<string, string> = {
  discovered:          'bg-surface-2 text-muted',
  shortlisted:         'bg-blue-950 text-blue-300',
  drafting:            'bg-yellow-950 text-yellow-300',
  ready:               'bg-teal-950 text-teal-300',
  applied:             'bg-indigo-950 text-indigo-300',
  applied_confirmed:   'bg-indigo-900 text-indigo-200',
  recruiter_engaged:   'bg-violet-950 text-violet-300',
  phone_screen:        'bg-violet-900 text-violet-200',
  technical_interview: 'bg-orange-950 text-orange-300',
  onsite:              'bg-orange-900 text-orange-200',
  offer:               'bg-surface-2 text-gold',
  accepted:            'bg-surface-2 text-gold',
  declined:            'bg-surface-2 text-muted',
  rejected:            'bg-red-950 text-red-400',
  ghosted:             'bg-surface text-muted',
  missed_deadline:     'bg-red-950 text-red-500',
}

function StatusBadge({ status }: { status: string }) {
  const colors = STATUS_COLORS[status] ?? 'bg-surface-2 text-muted'
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

function Tag({ label, variant }: { label: string; variant: 'accent' | 'muted' | 'dim' }) {
  const styles = {
    accent: 'bg-accent/10 text-accent border border-accent/20',
    muted:  'bg-surface-2 text-body border border-border',
    dim:    'bg-surface text-muted border border-border',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs ${styles[variant]}`}>
      {label}
    </span>
  )
}

const inputClass =
  'w-full bg-surface border border-border rounded px-3 py-2 text-body text-sm ' +
  'focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors'

export function ApplicationDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [app, setApp] = useState<Application | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const [draftStatus, setDraftStatus] = useState<ApplicationStatus>('discovered')
  const [draftPriority, setDraftPriority] = useState('')
  const [draftDeadline, setDraftDeadline] = useState('')
  const [draftNotes, setDraftNotes] = useState('')

  useEffect(() => {
    if (!id) return
    api.applications.get(id)
      .then(data => {
        setApp(data)
        setDraftStatus(data.status)
        setDraftPriority(data.priority ?? '')
        setDraftDeadline(data.deadline ? data.deadline.slice(0, 10) : '')
        setDraftNotes(data.notes ?? '')
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  async function handleSave() {
    if (!id) return
    setSaving(true)
    setSaveError(null)
    try {
      const updated = await api.applications.update(id, {
        status: draftStatus,
        priority: draftPriority || undefined,
        deadline: draftDeadline || undefined,
        notes: draftNotes || undefined,
      })
      setApp(updated)
      setEditing(false)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  function handleCancel() {
    if (!app) return
    setDraftStatus(app.status)
    setDraftPriority(app.priority ?? '')
    setDraftDeadline(app.deadline ? app.deadline.slice(0, 10) : '')
    setDraftNotes(app.notes ?? '')
    setEditing(false)
    setSaveError(null)
  }

  async function handleDelete() {
    if (!id || !confirm('Delete this application? This cannot be undone.')) return
    await api.applications.delete(id)
    navigate('/applications')
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted">Loading...</div>
  }

  if (error || !app) {
    return <div className="flex items-center justify-center h-64 text-red-400">{error ?? 'Not found.'}</div>
  }

  const isWin = app.status === 'offer' || app.status === 'accepted'

  return (
    <div className="p-6">
      <Link to="/applications" className="text-muted hover:text-body text-sm transition-colors">
        ← Applications
      </Link>

      {/* header */}
      <div className="flex items-start justify-between mt-6 mb-6">
        <div>
          <h1 className={`text-3xl font-bold ${isWin ? 'text-gold' : 'text-white'}`}>
            {app.organization}
          </h1>
          <p className="text-body mt-1">{app.role_or_program}</p>
          <div className="flex items-center gap-2 mt-3">
            <span className="text-xs text-muted capitalize border border-border rounded px-2 py-0.5">
              {app.type}
            </span>
            <StatusBadge status={app.status} />
            {app.priority && (
              <span className={`text-xs font-medium capitalize ${app.priority === 'top_target' ? 'text-gold' : 'text-muted'}`}>
                {app.priority.replace(/_/g, ' ')}
              </span>
            )}
          </div>
        </div>
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            className="px-4 py-1.5 rounded border border-border text-muted hover:border-accent hover:text-accent text-sm transition-colors"
          >
            Edit
          </button>
        )}
      </div>

      {/* metadata card */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-surface rounded-lg border border-border text-sm mb-8">
        {app.posting_url && (
          <div className="col-span-2">
            <span className="text-muted text-xs block mb-1">Posting URL</span>
            <a
              href={app.posting_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:text-accent-hover transition-colors truncate block"
            >
              {app.posting_url}
            </a>
          </div>
        )}
        {app.deadline && (
          <div>
            <span className="text-muted text-xs block mb-1">Deadline</span>
            <span className="text-body">{new Date(app.deadline).toLocaleDateString()}</span>
          </div>
        )}
        <div>
          <span className="text-muted text-xs block mb-1">Added</span>
          <span className="text-body">{new Date(app.created_at).toLocaleDateString()}</span>
        </div>
        <div>
          <span className="text-muted text-xs block mb-1">Last updated</span>
          <span className="text-body">{new Date(app.updated_at).toLocaleDateString()}</span>
        </div>
      </div>

      {/* parsed JD */}
      {app.jd_parsed && (
        <div className="space-y-6 mb-8">
          {app.jd_parsed.summary && (
            <div>
              <h2 className="text-xs uppercase tracking-wider text-muted mb-2">Summary</h2>
              <p className="text-body leading-relaxed">{app.jd_parsed.summary}</p>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {app.jd_parsed.required_skills.length > 0 && (
              <div>
                <h2 className="text-xs uppercase tracking-wider text-muted mb-2">Required Skills</h2>
                <div className="flex flex-wrap gap-1.5">
                  {app.jd_parsed.required_skills.map(s => <Tag key={s} label={s} variant="accent" />)}
                </div>
              </div>
            )}
            {app.jd_parsed.nice_to_haves.length > 0 && (
              <div>
                <h2 className="text-xs uppercase tracking-wider text-muted mb-2">Nice to Haves</h2>
                <div className="flex flex-wrap gap-1.5">
                  {app.jd_parsed.nice_to_haves.map(s => <Tag key={s} label={s} variant="muted" />)}
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-6 text-sm">
            {app.jd_parsed.seniority && (
              <div>
                <span className="text-muted text-xs block mb-0.5">Seniority</span>
                <span className="text-body">{app.jd_parsed.seniority}</span>
              </div>
            )}
            {app.jd_parsed.location && (
              <div>
                <span className="text-muted text-xs block mb-0.5">Location</span>
                <span className="text-body">{app.jd_parsed.location}</span>
              </div>
            )}
            {app.jd_parsed.compensation && (
              <div>
                <span className="text-muted text-xs block mb-0.5">Compensation</span>
                <span className="text-body">{app.jd_parsed.compensation}</span>
              </div>
            )}
          </div>

          {app.jd_parsed.keywords.length > 0 && (
            <div>
              <h2 className="text-xs uppercase tracking-wider text-muted mb-2">Keywords</h2>
              <div className="flex flex-wrap gap-1.5">
                {app.jd_parsed.keywords.map(k => <Tag key={k} label={k} variant="dim" />)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* notes / edit section */}
      <div className="border-t border-border pt-6">
        {editing ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-muted block mb-1.5">Status</label>
                <select
                  value={draftStatus}
                  onChange={e => setDraftStatus(e.target.value as ApplicationStatus)}
                  className={inputClass}
                >
                  {ALL_STATUSES.map(s => (
                    <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-muted block mb-1.5">Priority</label>
                <select
                  value={draftPriority}
                  onChange={e => setDraftPriority(e.target.value)}
                  className={inputClass}
                >
                  <option value="">— none —</option>
                  <option value="top_target">top target</option>
                  <option value="standard">standard</option>
                  <option value="longshot">longshot</option>
                </select>
              </div>
            </div>

            <div>
              <label className="text-xs text-muted block mb-1.5">Deadline</label>
              <input
                type="date"
                value={draftDeadline}
                onChange={e => setDraftDeadline(e.target.value)}
                className={inputClass}
              />
            </div>

            <div>
              <label className="text-xs text-muted block mb-1.5">Notes</label>
              <textarea
                value={draftNotes}
                onChange={e => setDraftNotes(e.target.value)}
                rows={4}
                placeholder="Add notes..."
                className={`${inputClass} resize-none`}
              />
            </div>

            {saveError && <p className="text-red-400 text-sm">{saveError}</p>}

            <div className="flex items-center justify-between">
              <div className="flex gap-3">
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-4 py-1.5 rounded bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium transition-colors"
                >
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button
                  onClick={handleCancel}
                  disabled={saving}
                  className="px-4 py-1.5 rounded border border-border text-muted hover:text-body text-sm transition-colors"
                >
                  Cancel
                </button>
              </div>
              <button
                onClick={handleDelete}
                className="text-xs text-red-700 hover:text-red-400 transition-colors"
              >
                Delete application
              </button>
            </div>
          </div>
        ) : (
          <div>
            <h2 className="text-xs uppercase tracking-wider text-muted mb-2">Notes</h2>
            {app.notes ? (
              <p className="text-body text-sm leading-relaxed whitespace-pre-wrap">{app.notes}</p>
            ) : (
              <p className="text-muted text-sm italic">No notes yet.</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
