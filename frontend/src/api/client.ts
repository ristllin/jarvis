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
  overrideBudget: (new_cap_usd: number) =>
    fetchJSON<any>('/budget/override', {
      method: 'POST',
      body: JSON.stringify({ new_cap_usd }),
    }),
  health: () => fetchJSON<any>('/health'),

  // Chat
  sendChat: (message: string) =>
    fetchJSON<any>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  getChatHistory: (limit = 50) => fetchJSON<any>(`/chat/history?limit=${limit}`),
}
