import type { Application } from './types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(error.detail ?? 'Request failed')
  }
  return res.json() as Promise<T>
}

export const api = {
  applications: {
    list: (params?: { status?: string; type?: string; priority?: string }) => {
      const qs = new URLSearchParams(
        Object.entries(params ?? {}).filter(([, v]) => v != null) as [string, string][]
      ).toString()
      return request<Application[]>(`/applications/${qs ? `?${qs}` : ''}`)
    },

    get: (id: string) =>
      request<Application>(`/applications/${id}`),

    create: (body: { posting_url: string; type?: string; organization?: string; role_or_program?: string; deadline?: string; priority?: string; notes?: string }) =>
      request<Application>('/applications/', { method: 'POST', body: JSON.stringify(body) }),

    update: (id: string, body: { status?: string; priority?: string; notes?: string; deadline?: string }) =>
      request<Application>(`/applications/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

    delete: (id: string) =>
      request<void>(`/applications/${id}`, { method: 'DELETE' }),
  },
}
