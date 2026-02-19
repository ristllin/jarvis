import { useState } from 'react'
import { api } from '../api/client'
import type { JarvisStatus, BudgetStatus, MemoryStats, WSMessage } from '../types'
import { Activity, Target, Zap, Database, DollarSign, Clock, Flag, Compass, Star, Timer, Bell } from 'lucide-react'
, NewsPanel

interface Props {
  status: JarvisStatus | null
  budget: BudgetStatus | null
  memory: MemoryStats | null
  lastMessage: WSMessage | null
}

function Card({ title, icon, children, color = 'gray' }: { title: string; icon: React.ReactNode; children: React.ReactNode; color?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className={`text-${color}-400`}>{icon}</span>
        <h3 className="text-sm font-medium text-gray-400">{title}</h3>
      </div>
      {children}
    </div>
  )
}

export function Dashboard({ status, budget, memory, lastMessage }: Props) {
  const statusColor = status?.is_paused ? 'yellow' : status ? 'green' : 'red'
  const statusText = status?.is_paused ? 'PAUSED' : status ? 'RUNNING' : 'OFFLINE'

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className={`w-3 h-3 rounded-full bg-${statusColor}-500 animate-pulse`} />
        <h2 className="text-2xl font-bold">{statusText}</h2>
        {status && <span className="text-gray-500 text-sm">Iteration #{status.iteration}</span>}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <Card title="Short-Term Goals" icon={<Flag size={16} />} color="jarvis">
          <div className="space-y-1">
            {(status?.short_term_goals?.length || status?.goals?.length) ? (
              (status?.short_term_goals || status?.goals || []).map((g, i) => (
                <p key={i} className="text-sm text-gray-200">• {g}</p>
              ))
            ) : (
              <p className="text-sm text-gray-500">No short-term goals</p>
            )}
          </div>
        </Card>
<NewsPanel limit={5} />

        <Card title="Mid-Term Goals" icon={<Compass size={16} />} color="blue">
          <div className="space-y-1">
            {status?.mid_term_goals?.length ? (
              status.mid_term_goals.map((g, i) => (
                <p key={i} className="text-sm text-gray-200">• {g}</p>
              ))
            ) : (
              <p className="text-sm text-gray-500">No mid-term goals</p>
            )}
          </div>
        </Card>

        <Card title="Long-Term Goals" icon={<Star size={16} />} color="yellow">
          <div className="space-y-1">
            {status?.long_term_goals?.length ? (
              status.long_term_goals.map((g, i) => (
                <p key={i} className="text-sm text-gray-200">• {g}</p>
              ))
            ) : (
              <p className="text-sm text-gray-500">No long-term goals</p>
            )}
          </div>
        </Card>

        <Card title="Active Task" icon={<Activity size={16} />} color="blue">
          <p className="text-sm text-gray-200">{status?.active_task || 'Idle'}</p>
        </Card>

        <Card title="Budget" icon={<DollarSign size={16} />} color="green">
          {budget ? (
            <div>
              <p className="text-2xl font-bold text-green-400">${budget.remaining.toFixed(2)}</p>
              <p className="text-xs text-gray-500">
                {budget.source === 'providers'
                  ? `from provider balances ($${budget.spent.toFixed(2)} spent)`
                  : `remaining of $${budget.monthly_cap.toFixed(2)} cap`}
              </p>
              <div className="mt-2 w-full bg-gray-800 rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${budget.percent_used > 80 ? 'bg-red-500' : budget.percent_used > 50 ? 'bg-yellow-500' : 'bg-green-500'}`}
                  style={{ width: `${Math.min(100, budget.percent_used)}%` }}
                />
              </div>
              {budget.providers?.filter(p => p.currency && !['USD', 'EUR', 'GBP'].includes(p.currency) && p.estimated_remaining != null).length ? (
                <div className="mt-2 pt-2 border-t border-gray-800 space-y-1">
                  {budget.providers
                    .filter(p => p.currency && !['USD', 'EUR', 'GBP'].includes(p.currency) && p.estimated_remaining != null)
                    .map(p => (
                      <p key={p.provider} className="text-xs text-gray-400">
                        <span className="capitalize">{p.provider}:</span>{' '}
                        <span className="text-gray-300">{Math.round(p.estimated_remaining!)} {p.currency}</span>
                      </p>
                    ))}
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Loading...</p>
          )}
        </Card>

        <Card title="Memory" icon={<Database size={16} />} color="purple">
          {memory ? (
            <div className="space-y-1">
              <p className="text-sm"><span className="text-gray-400">Vector entries:</span> <span className="text-gray-200">{memory.vector.total_entries}</span></p>
              <p className="text-sm"><span className="text-gray-400">Blob files:</span> <span className="text-gray-200">{memory.blob.total_files}</span></p>
              <p className="text-sm"><span className="text-gray-400">Blob size:</span> <span className="text-gray-200">{memory.blob.total_size_mb} MB</span></p>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Loading...</p>
          )}
        </Card>

        <Card title="Iteration Speed" icon={<Timer size={16} />} color="cyan">
          <IterationSpeedDisplay
            sleepSeconds={status?.current_sleep_seconds}
            lastMessage={lastMessage}
          />
        </Card>

        <Card title="Directive" icon={<Zap size={16} />} color="yellow">
          <p className="text-sm text-gray-300 line-clamp-4">{status?.directive || 'Loading...'}</p>
        </Card>
      </div>
    </div>
  )
}

function formatDuration(seconds: number | undefined | null): string {
  if (!seconds && seconds !== 0) return '—'
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60)
    const s = Math.round(seconds % 60)
    return s > 0 ? `${m}m ${s}s` : `${m}m`
  }
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

function sleepLabel(seconds: number | undefined | null): { text: string; color: string } {
  if (!seconds && seconds !== 0) return { text: 'Unknown', color: 'gray' }
  if (seconds <= 30) return { text: 'Sprinting', color: 'green' }
  if (seconds <= 120) return { text: 'Active', color: 'blue' }
  if (seconds <= 600) return { text: 'Idle', color: 'yellow' }
  return { text: 'Deep Sleep', color: 'orange' }
}

function IterationSpeedDisplay({
  sleepSeconds,
  lastMessage,
}: {
  sleepSeconds?: number
  lastMessage: WSMessage | null
}) {
  const [waking, setWaking] = useState(false)

  // Use the WebSocket next_wake_seconds if available (more real-time)
  const displaySleep = lastMessage?.next_wake_seconds != null
    ? (lastMessage.next_wake_seconds as number)
    : sleepSeconds

  const label = sleepLabel(displaySleep)

  const handleWake = async () => {
    setWaking(true)
    try {
      await api.wake()
    } catch {}
    setTimeout(() => setWaking(false), 2000)
  }

  // Visual bar: map sleep to 0-100% where 10s=0%, 3600s=100%
  const barPct = displaySleep != null
    ? Math.min(100, Math.max(0, ((displaySleep - 10) / (3600 - 10)) * 100))
    : 0

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <p className="text-2xl font-bold text-cyan-400">{formatDuration(displaySleep)}</p>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full bg-${label.color}-500/20 text-${label.color}-400`}>
          {label.text}
        </span>
      </div>

      <p className="text-xs text-gray-500">between iterations (JARVIS-controlled)</p>

      {/* Sleep duration bar */}
      <div className="w-full bg-gray-800 rounded-full h-1.5 mt-1">
        <div
          className={`h-1.5 rounded-full transition-all duration-500 ${
            barPct < 10 ? 'bg-green-500' : barPct < 30 ? 'bg-blue-500' : barPct < 60 ? 'bg-yellow-500' : 'bg-orange-500'
          }`}
          style={{ width: `${barPct}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-gray-600">
        <span>10s</span>
        <span>1m</span>
        <span>10m</span>
        <span>1h</span>
      </div>

      {/* Last WS update */}
      {lastMessage?.timestamp && (
        <p className="text-[11px] text-gray-600 mt-1">
          Last update: {new Date(lastMessage.timestamp).toLocaleTimeString()}
          {lastMessage.status && ` · ${lastMessage.status}`}
        </p>
      )}

      {/* Wake button */}
      <button
        onClick={handleWake}
        disabled={waking}
        className={`w-full mt-1 flex items-center justify-center gap-2 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
          waking
            ? 'bg-cyan-900/30 text-cyan-600 cursor-not-allowed'
            : 'bg-cyan-900/40 text-cyan-400 hover:bg-cyan-800/50 hover:text-cyan-300'
        }`}
      >
        <Bell size={12} />
        {waking ? 'Waking...' : 'Wake Now'}
      </button>
    </div>
  )
}
