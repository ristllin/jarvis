import type { JarvisStatus, BudgetStatus, MemoryStats, WSMessage } from '../types'
import { Activity, Target, Zap, Database, DollarSign, Clock, Flag, Compass, Star } from 'lucide-react'

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
              <p className="text-xs text-gray-500">remaining of ${budget.monthly_cap.toFixed(2)}</p>
              <div className="mt-2 w-full bg-gray-800 rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${budget.percent_used > 80 ? 'bg-red-500' : budget.percent_used > 50 ? 'bg-yellow-500' : 'bg-green-500'}`}
                  style={{ width: `${Math.min(100, budget.percent_used)}%` }}
                />
              </div>
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

        <Card title="Last Update" icon={<Clock size={16} />} color="cyan">
          {lastMessage ? (
            <div className="space-y-1">
              <p className="text-sm text-gray-200">{lastMessage.status || lastMessage.type}</p>
              <p className="text-xs text-gray-500">{lastMessage.timestamp ? new Date(lastMessage.timestamp).toLocaleString() : ''}</p>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Waiting for updates...</p>
          )}
        </Card>

        <Card title="Directive" icon={<Zap size={16} />} color="yellow">
          <p className="text-sm text-gray-300 line-clamp-4">{status?.directive || 'Loading...'}</p>
        </Card>
      </div>
    </div>
  )
}
