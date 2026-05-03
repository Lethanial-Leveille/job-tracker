import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { ApplicationType, ApplicationPriority } from '../lib/types'

const inputClass =
  'w-full bg-surface border border-border rounded px-3 py-2 text-body text-sm ' +
  'focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors ' +
  'placeholder:text-muted'

export function AddApplication() {
  const navigate = useNavigate()

  const [url, setUrl] = useState('')
  const [type, setType] = useState<ApplicationType | ''>('')
  const [organization, setOrganization] = useState('')
  const [role, setRole] = useState('')
  const [deadline, setDeadline] = useState('')
  const [priority, setPriority] = useState<ApplicationPriority | ''>('')
  const [notes, setNotes] = useState('')

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!url.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const created = await api.applications.create({
        posting_url: url.trim(),
        type: type || undefined,
        organization: organization.trim() || undefined,
        role_or_program: role.trim() || undefined,
        deadline: deadline || undefined,
        priority: priority || undefined,
        notes: notes.trim() || undefined,
      })
      navigate(`/applications/${created.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
      setSubmitting(false)
    }
  }

  if (submitting) {
    return (
      <div className="flex flex-col items-center justify-center min-h-96 gap-5 text-center p-6">
        <div className="w-9 h-9 rounded-full border-2 border-surface-2 border-t-accent animate-spin" />
        <div>
          <p className="text-white font-medium">Parsing job description with Claude</p>
          <p className="text-muted text-sm mt-1">This usually takes 5 to 10 seconds</p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-xl">
      <Link to="/applications" className="text-muted hover:text-body text-sm transition-colors">
        ← Applications
      </Link>

      <h1 className="text-2xl font-bold text-white mt-6 mb-8">Add Application</h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="text-sm text-white block mb-2">
            Job or scholarship URL <span className="text-accent">*</span>
          </label>
          <input
            type="url"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://jobs.apple.com/..."
            required
            autoFocus
            className={inputClass}
          />
          <p className="text-muted text-xs mt-1.5">
            Claude will scrape this page and infer the organization, role, and type automatically.
          </p>
        </div>

        <div className="border-t border-border pt-5">
          <p className="text-xs uppercase tracking-wider text-muted mb-4">
            Optional overrides — leave blank to let Claude infer
          </p>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-muted block mb-1.5">Type</label>
                <select
                  value={type}
                  onChange={e => setType(e.target.value as ApplicationType | '')}
                  className={inputClass}
                >
                  <option value="">— infer from JD —</option>
                  <option value="internship">internship</option>
                  <option value="scholarship">scholarship</option>
                  <option value="fellowship">fellowship</option>
                  <option value="research">research</option>
                  <option value="grant">grant</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-muted block mb-1.5">Priority</label>
                <select
                  value={priority}
                  onChange={e => setPriority(e.target.value as ApplicationPriority | '')}
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
              <label className="text-xs text-muted block mb-1.5">Organization</label>
              <input
                type="text"
                value={organization}
                onChange={e => setOrganization(e.target.value)}
                placeholder="Apple, SMART Scholarship, ..."
                className={inputClass}
              />
            </div>

            <div>
              <label className="text-xs text-muted block mb-1.5">Role or program</label>
              <input
                type="text"
                value={role}
                onChange={e => setRole(e.target.value)}
                placeholder="Software Engineering Intern, ..."
                className={inputClass}
              />
            </div>

            <div>
              <label className="text-xs text-muted block mb-1.5">Deadline</label>
              <input
                type="date"
                value={deadline}
                onChange={e => setDeadline(e.target.value)}
                className={inputClass}
              />
            </div>

            <div>
              <label className="text-xs text-muted block mb-1.5">Notes</label>
              <textarea
                value={notes}
                onChange={e => setNotes(e.target.value)}
                rows={3}
                placeholder="Referred by..., target team..., etc."
                className={`${inputClass} resize-none`}
              />
            </div>
          </div>
        </div>

        {error && <p className="text-red-400 text-sm">{error}</p>}

        <div className="flex gap-3 pt-1">
          <button
            type="submit"
            className="px-5 py-2 rounded bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors"
          >
            Add Application
          </button>
          <Link
            to="/applications"
            className="px-5 py-2 rounded border border-border text-muted hover:text-body text-sm transition-colors inline-flex items-center"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  )
}
