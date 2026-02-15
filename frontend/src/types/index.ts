export interface JarvisStatus {
  status: string
  directive: string
  goals: string[]
  short_term_goals: string[]
  mid_term_goals: string[]
  long_term_goals: string[]
  active_task: string | null
  iteration: number
  is_paused: boolean
  started_at: string | null
}

export interface BudgetStatus {
  monthly_cap: number
  spent: number
  remaining: number
  percent_used: number
}

export interface MemoryStats {
  vector: { total_entries: number }
  blob: { total_files: number; total_size_bytes: number; total_size_mb: number }
}

export interface LogEntry {
  timestamp: string
  event_type: string
  content: string
  metadata: Record<string, unknown>
}

export interface ToolSchema {
  name: string
  description: string
  parameters?: Record<string, unknown>
}

export interface ModelTier {
  provider: string
  model: string
  cost: string
  available: boolean
}

export interface WSMessage {
  type: string
  status?: string
  timestamp?: string
  iteration?: number
  error?: string
  [key: string]: unknown
}

export interface ChatMessage {
  id?: number
  role: 'creator' | 'jarvis'
  content: string
  timestamp?: string
  metadata?: Record<string, unknown>
}
