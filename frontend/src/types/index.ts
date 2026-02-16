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
  current_sleep_seconds?: number
  min_sleep_seconds?: number
  max_sleep_seconds?: number
}

export interface ProviderStatus {
  provider: string
  known_balance: number | null
  spent_tracked: number
  estimated_remaining: number | null
  tier: string
  currency: string         // USD, EUR, credits, requests, etc.
  notes: string | null
  balance_updated_at: string | null
}

export interface BudgetStatus {
  monthly_cap: number
  spent: number
  remaining: number
  percent_used: number
  providers?: ProviderStatus[]
}

export interface MemoryStats {
  vector: { total_entries: number }
  blob: { total_files: number; total_size_bytes: number; total_size_mb: number }
}

export interface VectorMemoryEntry {
  id: string
  content: string
  importance_score: number
  source: string
  permanent: boolean
  created_at: string
  ttl_hours: number
  distance?: number
  metadata: Record<string, unknown>
}

export interface BlobEntry {
  timestamp: string
  event_type: string
  content: string
  metadata: Record<string, unknown>
}

export interface MemoryConfig {
  retrieval_count: number
  max_context_tokens: number
  decay_factor: number
  relevance_threshold: number
}

export interface WorkingMemorySnapshot {
  system_prompt_length: number
  system_prompt_tokens: number
  message_count: number
  injected_memory_count: number
  injected_memories: VectorMemoryEntry[]
  total_tokens_estimate: number
  max_context_tokens: number
  config: MemoryConfig
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
  next_wake_seconds?: number
  [key: string]: unknown
}

export interface ChatMessage {
  id?: number
  role: 'creator' | 'jarvis'
  content: string
  timestamp?: string
  metadata?: Record<string, unknown>
}
