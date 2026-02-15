import type { MemoryStats } from '../types'
import { Database, HardDrive } from 'lucide-react'

interface Props {
  stats: MemoryStats | null
}

export function MemoryPanel({ stats }: Props) {
  if (!stats) return <p className="text-gray-500">Loading memory stats...</p>

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">Memory System</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <div className="flex items-center gap-2 mb-4">
            <Database size={20} className="text-purple-400" />
            <h3 className="font-medium">Vector Memory (ChromaDB)</h3>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-400">Total Entries</span>
              <span className="text-gray-200 font-mono">{stats.vector.total_entries}</span>
            </div>
            <p className="text-xs text-gray-500">
              Long-term semantic memory with importance scoring and TTL-based expiry.
              Memories decay in importance over time unless marked permanent.
            </p>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <div className="flex items-center gap-2 mb-4">
            <HardDrive size={20} className="text-blue-400" />
            <h3 className="font-medium">Blob Storage</h3>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-400">Total Files</span>
              <span className="text-gray-200 font-mono">{stats.blob.total_files}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Total Size</span>
              <span className="text-gray-200 font-mono">{stats.blob.total_size_mb} MB</span>
            </div>
            <p className="text-xs text-gray-500">
              Append-only storage of all messages, tool outputs, and LLM responses.
              Never deleted — serves as complete audit trail.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
