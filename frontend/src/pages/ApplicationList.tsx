import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { Application } from '../lib/types'

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

const PRIORITY_LABELS: Record<string, string> = {
  top_target: 'text-gold',
  standard:   'text-muted',
  longshot:   'text-muted opacity-60',
}

function StatusBadge({ status }: { status: string }) {
  const colors = STATUS_COLORS[status] ?? 'bg-surface-2 text-muted'
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

export function ApplicationList() {
  const [applications, setApplications] = useState<Application[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.applications.list()
      .then(setApplications)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-muted">
        Loading...
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400">
        Error: {error}
      </div>
    )
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-white">Applications</h1>
        <span className="text-sm text-muted">{applications.length} total</span>
      </div>

      {applications.length === 0 ? (
        <div className="text-center text-muted py-16">
          No applications yet. Add one to get started.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="border-b border-border text-muted text-xs uppercase tracking-wider">
                <th className="pb-3 pr-4">Organization</th>
                <th className="pb-3 pr-4">Role</th>
                <th className="pb-3 pr-4">Type</th>
                <th className="pb-3 pr-4">Status</th>
                <th className="pb-3 pr-4">Priority</th>
                <th className="pb-3">Deadline</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {applications.map((app) => (
                <tr
                  key={app.id}
                  onClick={() => navigate(`/applications/${app.id}`)}
                  className="hover:bg-surface cursor-pointer transition-colors"
                >
                  <td className="py-3 pr-4 font-medium text-white">{app.organization}</td>
                  <td className="py-3 pr-4 text-body max-w-xs truncate">{app.role_or_program}</td>
                  <td className="py-3 pr-4 text-muted capitalize">{app.type}</td>
                  <td className="py-3 pr-4">
                    <StatusBadge status={app.status} />
                  </td>
                  <td className={`py-3 pr-4 capitalize text-xs font-medium ${PRIORITY_LABELS[app.priority ?? ''] ?? 'text-muted'}`}>
                    {app.priority?.replace(/_/g, ' ') ?? '—'}
                  </td>
                  <td className="py-3 text-muted">
                    {app.deadline ? new Date(app.deadline).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
