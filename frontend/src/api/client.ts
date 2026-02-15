const BASE = '/api'

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export const api = {
  getStatus: () => fetchJSON<any>('/status'),
  getBudget: () => fetchJSON<any>('/budget'),
  getMemoryStats: () => fetchJSON<any>('/memory/stats'),
  getLogs: (limit = 50) => fetchJSON<any>(`/logs?limit=${limit}`),
  getTools: () => fetchJSON<any>('/tools'),
  getModels: () => fetchJSON<any>('/models'),
  updateDirective: (directive: string) =>
    fetchJSON<any>('/directive', {
      method: 'POST',
      body: JSON.stringify({ directive }),
    }),
  updateGoals: (goals: { short_term?: string[]; mid_term?: string[]; long_term?: string[] }) =>
    fetchJSON<any>('/goals', {
      method: 'POST',
      body: JSON.stringify(goals),
    }),
  pause: () => fetchJSON<any>('/control/pause', { method: 'POST' }),
  resume: () => fetchJSON<any>('/control/resume', { method: 'POST' }),
  wake: () => fetchJSON<any>('/control/wake', { method: 'POST' }),
  overrideBudget: (new_cap_usd: number) =>
    fetchJSON<any>('/budget/override', {
      method: 'POST',
      body: JSON.stringify({ new_cap_usd }),
    }),
  health: () => fetchJSON<any>('/health'),

  // Providers
  getProviders: () => fetchJSON<any>('/providers'),
  updateProvider: (provider: string, data: { known_balance?: number; tier?: string; notes?: string; reset_spending?: boolean }) =>
    fetchJSON<any>(`/providers/${provider}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  addProvider: (data: { provider: string; api_key?: string; known_balance?: number; tier?: string; notes?: string }) =>
    fetchJSON<any>('/providers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Chat
  sendChat: (message: string) =>
    fetchJSON<any>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  getChatHistory: (limit = 50) => fetchJSON<any>(`/chat/history?limit=${limit}`),
}
