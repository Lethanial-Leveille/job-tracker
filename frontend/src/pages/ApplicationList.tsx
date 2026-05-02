import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { Application } from '../lib/types'

const STATUS_COLORS: Record<string, string> = {
  discovered:          'bg-gray-700 text-gray-300',
  shortlisted:         'bg-blue-900 text-blue-300',
  drafting:            'bg-yellow-900 text-yellow-300',
  ready:               'bg-teal-900 text-teal-300',
  applied:             'bg-indigo-900 text-indigo-300',
  applied_confirmed:   'bg-indigo-800 text-indigo-200',
  recruiter_engaged:   'bg-purple-900 text-purple-300',
  phone_screen:        'bg-purple-800 text-purple-200',
  technical_interview: 'bg-orange-900 text-orange-300',
  onsite:              'bg-orange-800 text-orange-200',
  offer:               'bg-green-900 text-green-300',
  accepted:            'bg-green-700 text-green-100',
  declined:            'bg-gray-600 text-gray-300',
  rejected:            'bg-red-900 text-red-300',
  ghosted:             'bg-gray-800 text-gray-500',
  missed_deadline:     'bg-red-950 text-red-400',
}

const PRIORITY_COLORS: Record<string, string> = {
  top_target: 'text-yellow-400',
  standard:   'text-gray-400',
  longshot:   'text-gray-600',
}

function StatusBadge({ status }: { status: string }) {
  const colors = STATUS_COLORS[status] ?? 'bg-gray-700 text-gray-300'
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

  useEffect(() => {
    api.applications.list()
      .then(setApplications)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
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
        <h1 className="text-2xl font-semibold text-gray-100">Applications</h1>
        <span className="text-sm text-gray-500">{applications.length} total</span>
      </div>

      {applications.length === 0 ? (
        <div className="text-center text-gray-600 py-16">
          No applications yet.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="border-b border-gray-800 text-gray-500 text-xs uppercase tracking-wider">
                <th className="pb-3 pr-4">Organization</th>
                <th className="pb-3 pr-4">Role</th>
                <th className="pb-3 pr-4">Type</th>
                <th className="pb-3 pr-4">Status</th>
                <th className="pb-3 pr-4">Priority</th>
                <th className="pb-3">Deadline</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-900">
              {applications.map((app) => (
                <tr key={app.id} className="hover:bg-gray-900 transition-colors">
                  <td className="py-3 pr-4 font-medium text-gray-100">{app.organization}</td>
                  <td className="py-3 pr-4 text-gray-400 max-w-xs truncate">{app.role_or_program}</td>
                  <td className="py-3 pr-4 text-gray-500 capitalize">{app.type}</td>
                  <td className="py-3 pr-4">
                    <StatusBadge status={app.status} />
                  </td>
                  <td className={`py-3 pr-4 capitalize text-xs font-medium ${PRIORITY_COLORS[app.priority ?? ''] ?? 'text-gray-600'}`}>
                    {app.priority?.replace(/_/g, ' ') ?? '—'}
                  </td>
                  <td className="py-3 text-gray-500">
                    {app.deadline
                      ? new Date(app.deadline).toLocaleDateString()
                      : '—'}
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
