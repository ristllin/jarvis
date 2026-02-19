const BASE = '/api'

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    ...options,
  })
  if (res.status === 401) {
    const data = await res.json().catch(() => ({}))
    const loginUrl = (data as { login_url?: string }).login_url || '/api/auth/login'
    window.location.href = loginUrl
    throw new Error('Not authenticated')
  }
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

  // Auth
  getMe: () => fetchJSON<any>('/auth/me'),
  logout: () => {
    window.location.href = '/api/auth/logout'
  },

  // Providers
  getProviders: () => fetchJSON<any>('/providers'),
  updateProvider: (provider: string, data: { known_balance?: number; tier?: string; currency?: string; notes?: string; reset_spending?: boolean; api_key?: string }) =>
    fetchJSON<any>(`/providers/${provider}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  addProvider: (data: { provider: string; api_key?: string; known_balance?: number; tier?: string; currency?: string; notes?: string }) =>
    fetchJSON<any>('/providers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Memory browsing
  browseVectorMemory: (query?: string, limit = 50, offset = 0) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (query) params.set('query', query)
    return fetchJSON<any>(`/memory/vector?${params}`)
  },
  deleteVectorMemory: (id: string) =>
    fetchJSON<any>(`/memory/vector/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  browseBlob: (eventType?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (eventType) params.set('event_type', eventType)
    return fetchJSON<any>(`/memory/blob?${params}`)
  },
  getWorkingMemory: () => fetchJSON<any>('/memory/working'),
  updateMemoryConfig: (config: Record<string, number>) =>
    fetchJSON<any>('/memory/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  // Short-term memories
  getShortTermMemories: () => fetchJSON<any>('/memory/short-term'),
  updateShortTermMemories: (data: { add?: string[]; remove?: number[]; replace?: string[] }) =>
    fetchJSON<any>('/memory/short-term', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  clearShortTermMemories: () =>
    fetchJSON<any>('/memory/short-term', { method: 'DELETE' }),

  // Analytics
  getAnalytics: (range = '24h') => fetchJSON<any>(`/analytics?range=${range}`),

  // Chat
  sendChat: (message: string) =>
    fetchJSON<any>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  getChatHistory: (limit = 50) => fetchJSON<any>(`/chat/history?limit=${limit}`),
  getNews: (query = "latest news", limit = 5) => fetchJSON<any>(`/news?query=${encodeURIComponent(query)}&limit=${limit}`),
}
