import { useState, useEffect, useRef } from 'react'
import { api } from '../api/client'
import { RefreshCw } from 'lucide-react'

export function LogViewer() {
  const [logs, setLogs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const fetchLogs = async () => {
    setLoading(true)
    try {
      const data = await api.getLogs(100)
      setLogs(data.logs || [])
    } catch {}
    setLoading(false)
  }

  useEffect(() => {
    fetchLogs()
    const interval = setInterval(fetchLogs, 5000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Logs</h2>
        <button onClick={fetchLogs} className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-200">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
        <div className="max-h-[600px] overflow-y-auto p-4 font-mono text-xs space-y-1">
          {logs.length === 0 ? (
            <p className="text-gray-500">No logs yet...</p>
          ) : (
            logs.map((entry, i) => (
              <div key={i} className="flex gap-3 hover:bg-gray-800 px-2 py-1 rounded">
                <span className="text-gray-600 shrink-0">
                  {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '--:--:--'}
                </span>
                <span className={`shrink-0 uppercase ${
                  entry.event_type === 'error' ? 'text-red-400' :
                  entry.event_type === 'tool_output' ? 'text-blue-400' :
                  entry.event_type === 'plan' ? 'text-yellow-400' :
                  'text-gray-500'
                }`}>
                  [{entry.event_type}]
                </span>
                <span className="text-gray-300 break-all">
                  {entry.content?.substring(0, 200)}
                </span>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  )
}
