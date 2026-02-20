import { api } from '../api/client'
import type { JarvisStatus } from '../types'
import { Pause, Play, RefreshCw } from 'lucide-react'

interface Props {
  status: JarvisStatus | null
  onRefresh: () => void
}

export function ControlBar({ status, onRefresh }: Props) {
  const handlePause = async () => {
    if (status?.is_paused) {
      await api.resume()
    } else {
      await api.pause()
    }
    onRefresh()
  }

  return (
    <div className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className={`w-2.5 h-2.5 rounded-full ${
            status?.is_paused ? 'bg-yellow-500' :
            status ? 'bg-green-500 animate-pulse' :
            'bg-red-500'
          }`} />
          <span className="text-sm font-medium">
            {status?.is_paused ? 'Paused' : status ? 'Running' : 'Offline'}
          </span>
        </div>
        {status && (
          <>
            <span className="text-gray-600">|</span>
            <span className="text-xs text-gray-500">Iteration #{status.iteration}</span>
            {status.active_task && (
              <>
                <span className="text-gray-600">|</span>
                <span className="text-xs text-gray-400 max-w-md truncate">{status.active_task}</span>
              </>
            )}
            {status.current_model && (
              <>
                <span className="text-gray-600">|</span>
                <span className="text-xs text-gray-500 font-mono">
                  {(status as any).current_provider ? `${(status as any).current_provider}/` : ''}{status.current_model}
                </span>
              </>
            )}
          </>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={handlePause}
          className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm transition-colors ${
            status?.is_paused
              ? 'bg-green-900 text-green-300 hover:bg-green-800'
              : 'bg-yellow-900 text-yellow-300 hover:bg-yellow-800'
          }`}
        >
          {status?.is_paused ? <Play size={14} /> : <Pause size={14} />}
          {status?.is_paused ? 'Resume' : 'Pause'}
        </button>
        <button
          onClick={onRefresh}
          className="flex items-center gap-2 px-3 py-1.5 rounded text-sm bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>
    </div>
  )
}
