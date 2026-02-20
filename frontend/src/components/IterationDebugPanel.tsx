import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'
import { RefreshCw, ChevronDown, ChevronRight, Cpu, Zap, Clock, MessageCircle } from 'lucide-react'

interface ActionDetail {
  tool: string
  tier: string
  parameters_keys: string[]
}

interface IterationEntry {
  timestamp: string
  iteration: number | null
  model: string
  provider: string
  tokens: number
  thinking: string
  status_message: string
  chat_reply: string | null
  sleep_seconds: number | null
  action_count: number
  actions: ActionDetail[]
}

const TIER_COLORS: Record<string, string> = {
  level1: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
  level2: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  level3: 'bg-green-500/20 text-green-300 border-green-500/40',
  coding_level1: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  coding_level2: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
  coding_level3: 'bg-lime-500/20 text-lime-300 border-lime-500/40',
  default: 'bg-gray-500/20 text-gray-300 border-gray-500/40',
}

function TierBadge({ tier }: { tier: string }) {
  const cls = TIER_COLORS[tier] || TIER_COLORS.default
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded border ${cls}`}>
      {tier}
    </span>
  )
}

function IterationRow({ entry }: { entry: IterationEntry }) {
  const [expanded, setExpanded] = useState(false)

  const ts = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '—'
  const hasChat = !!entry.chat_reply

  return (
    <div className="border border-gray-700 rounded-lg mb-2 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-800/50 transition-colors"
      >
        {expanded ? <ChevronDown size={16} className="text-gray-500" /> : <ChevronRight size={16} className="text-gray-500" />}

        <span className="text-xs text-gray-500 w-16 shrink-0">
          #{entry.iteration ?? '?'}
        </span>

        <span className="text-xs text-gray-500 w-20 shrink-0">{ts}</span>

        <div className="flex items-center gap-2 w-48 shrink-0">
          <Cpu size={14} className="text-gray-500" />
          <span className="text-sm text-gray-300 truncate">
            {entry.model || 'unknown'}
          </span>
        </div>

        <span className="text-xs text-gray-500 w-16 shrink-0">{entry.provider}</span>

        <div className="flex items-center gap-1.5 w-28 shrink-0">
          <Zap size={14} className="text-jarvis-400" />
          <span className="text-xs text-gray-400">
            {entry.action_count} action{entry.action_count !== 1 ? 's' : ''}
          </span>
        </div>

        <div className="flex items-center gap-1.5 w-20 shrink-0">
          <span className="text-xs text-gray-500">{entry.tokens} tok</span>
        </div>

        {hasChat && (
          <MessageCircle size={14} className="text-blue-400 shrink-0" />
        )}

        <span className="text-xs text-gray-500 truncate flex-1">
          {entry.status_message || ''}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-700/50 space-y-3">
          {/* Thinking */}
          {entry.thinking && (
            <div className="mt-3">
              <h4 className="text-xs font-semibold text-gray-400 uppercase mb-1">Thinking</h4>
              <pre className="text-xs text-gray-300 bg-gray-800/50 rounded p-3 whitespace-pre-wrap max-h-40 overflow-auto">
                {entry.thinking}
              </pre>
            </div>
          )}

          {/* Actions */}
          {entry.actions.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-400 uppercase mb-1">Actions</h4>
              <div className="space-y-1">
                {entry.actions.map((action, i) => (
                  <div key={i} className="flex items-center gap-3 bg-gray-800/30 rounded px-3 py-2">
                    <span className="text-xs text-gray-500 w-6">{i + 1}.</span>
                    <span className="text-sm text-gray-200 font-mono">{action.tool}</span>
                    <TierBadge tier={action.tier} />
                    {action.parameters_keys.length > 0 && (
                      <span className="text-xs text-gray-500">
                        ({action.parameters_keys.join(', ')})
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Chat reply */}
          {entry.chat_reply && (
            <div>
              <h4 className="text-xs font-semibold text-gray-400 uppercase mb-1">Chat Reply</h4>
              <pre className="text-xs text-blue-200 bg-blue-900/20 rounded p-3 whitespace-pre-wrap max-h-32 overflow-auto">
                {entry.chat_reply}
              </pre>
            </div>
          )}

          {/* Sleep */}
          {entry.sleep_seconds != null && (
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <Clock size={12} />
              <span>Sleep: {entry.sleep_seconds}s</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function IterationDebugPanel() {
  const [iterations, setIterations] = useState<IterationEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await api.getIterationHistory(30)
      setIterations(data.iterations || [])
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    if (!autoRefresh) return
    const interval = setInterval(load, 8000)
    return () => clearInterval(interval)
  }, [load, autoRefresh])

  const modelCounts: Record<string, number> = {}
  const providerCounts: Record<string, number> = {}
  let totalTokens = 0
  let totalActions = 0
  for (const it of iterations) {
    if (it.model) modelCounts[it.model] = (modelCounts[it.model] || 0) + 1
    if (it.provider) providerCounts[it.provider] = (providerCounts[it.provider] || 0) + 1
    totalTokens += it.tokens || 0
    totalActions += it.action_count || 0
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-200">Iteration Debug</h2>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-400">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-gray-600 bg-gray-800 text-jarvis-400 focus:ring-jarvis-400"
            />
            Auto-refresh
          </label>
          <button
            onClick={load}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-400 hover:text-gray-200 border border-gray-700 rounded hover:bg-gray-800 transition-colors"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3">
          <div className="text-xs text-gray-500 uppercase">Iterations</div>
          <div className="text-xl font-bold text-gray-200">{iterations.length}</div>
        </div>
        <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3">
          <div className="text-xs text-gray-500 uppercase">Total Tokens</div>
          <div className="text-xl font-bold text-gray-200">{totalTokens.toLocaleString()}</div>
        </div>
        <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3">
          <div className="text-xs text-gray-500 uppercase">Total Actions</div>
          <div className="text-xl font-bold text-gray-200">{totalActions}</div>
        </div>
        <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3">
          <div className="text-xs text-gray-500 uppercase">Models Used</div>
          <div className="text-sm text-gray-300 mt-1">
            {Object.entries(modelCounts).map(([m, c]) => (
              <div key={m} className="flex justify-between text-xs">
                <span className="truncate">{m}</span>
                <span className="text-gray-500 ml-2">{c}x</span>
              </div>
            ))}
            {Object.keys(modelCounts).length === 0 && <span className="text-gray-500">—</span>}
          </div>
        </div>
      </div>

      {/* Timeline */}
      <div>
        {loading && iterations.length === 0 ? (
          <div className="text-center text-gray-500 py-8">Loading iterations...</div>
        ) : iterations.length === 0 ? (
          <div className="text-center text-gray-500 py-8">No iteration data yet</div>
        ) : (
          iterations.map((entry, i) => (
            <IterationRow key={`${entry.iteration ?? i}-${entry.timestamp}`} entry={entry} />
          ))
        )}
      </div>
    </div>
  )
}
