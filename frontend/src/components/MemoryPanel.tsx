import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'
import type { MemoryStats, VectorMemoryEntry, BlobEntry, WorkingMemorySnapshot, MemoryConfig } from '../types'
import {
  Database, HardDrive, Brain, Search, Trash2, Star, Clock, ChevronDown, ChevronRight,
  Settings, RefreshCw, Filter, Eye, Zap, Shield, StickyNote, Plus, X,
} from 'lucide-react'

interface Props {
  stats: MemoryStats | null
}

type SubTab = 'overview' | 'short-term' | 'vector' | 'blob' | 'working' | 'config'

export function MemoryPanel({ stats }: Props) {
  const [subTab, setSubTab] = useState<SubTab>('overview')

  const subTabs: { id: SubTab; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Overview', icon: <Brain size={16} /> },
    { id: 'short-term', label: 'Scratch Pad', icon: <StickyNote size={16} /> },
    { id: 'working', label: 'Working Context', icon: <Zap size={16} /> },
    { id: 'vector', label: 'Vector Memory', icon: <Database size={16} /> },
    { id: 'blob', label: 'Blob Storage', icon: <HardDrive size={16} /> },
    { id: 'config', label: 'Config', icon: <Settings size={16} /> },
  ]

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Memory System</h2>

      {/* Sub-tabs */}
      <div className="flex gap-1 bg-gray-900 rounded-lg p-1 border border-gray-800 overflow-x-auto">
        {subTabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setSubTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm transition-colors whitespace-nowrap ${
              subTab === t.id
                ? 'bg-gray-800 text-jarvis-400'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {subTab === 'overview' && <OverviewTab stats={stats} />}
      {subTab === 'short-term' && <ShortTermMemoryTab />}
      {subTab === 'working' && <WorkingContextTab />}
      {subTab === 'vector' && <VectorBrowserTab />}
      {subTab === 'blob' && <BlobBrowserTab />}
      {subTab === 'config' && <ConfigTab />}
    </div>
  )
}


/* ─── Overview Tab ──────────────────────────────────────────────────── */

function OverviewTab({ stats }: { stats: MemoryStats | null }) {
  const [working, setWorking] = useState<WorkingMemorySnapshot | null>(null)
  const [stmCount, setStmCount] = useState<number>(0)

  useEffect(() => {
    api.getWorkingMemory().then(setWorking).catch(() => {})
    api.getShortTermMemories().then((d) => setStmCount(d.count || 0)).catch(() => {})
  }, [])

  if (!stats) return <p className="text-gray-500">Loading memory stats...</p>

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      {/* Short-term card */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-3">
          <StickyNote size={20} className="text-orange-400" />
          <h3 className="font-medium">Scratch Pad</h3>
        </div>
        <div className="text-3xl font-bold text-orange-400">{stmCount}</div>
        <p className="text-xs text-gray-500 mt-1">short-term notes (max 50)</p>
        <p className="text-xs text-gray-600 mt-2">
          Rolling operational notes. Auto-expire after 48h, oldest evicted at cap.
        </p>
      </div>

      {/* Vector card */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-3">
          <Database size={20} className="text-purple-400" />
          <h3 className="font-medium">Vector Memory</h3>
        </div>
        <div className="text-3xl font-bold text-purple-400">{stats.vector.total_entries}</div>
        <p className="text-xs text-gray-500 mt-1">long-term semantic memories</p>
        <p className="text-xs text-gray-600 mt-2">
          Importance-scored, TTL-based expiry. Memories decay unless marked permanent.
        </p>
      </div>

      {/* Blob card */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-3">
          <HardDrive size={20} className="text-blue-400" />
          <h3 className="font-medium">Blob Storage</h3>
        </div>
        <div className="text-3xl font-bold text-blue-400">{stats.blob.total_size_mb} MB</div>
        <p className="text-xs text-gray-500 mt-1">{stats.blob.total_files} log file{stats.blob.total_files !== 1 ? 's' : ''}</p>
        <p className="text-xs text-gray-600 mt-2">
          Append-only audit trail of all calls, tool outputs, and LLM responses.
        </p>
      </div>

      {/* Working context card */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-3">
          <Zap size={20} className="text-yellow-400" />
          <h3 className="font-medium">Working Context</h3>
        </div>
        {working ? (
          <>
            <div className="text-3xl font-bold text-yellow-400">{working.injected_memory_count}</div>
            <p className="text-xs text-gray-500 mt-1">memories loaded this iteration</p>
            <div className="mt-2 text-xs text-gray-600">
              {(working.total_tokens_estimate / 1000).toFixed(1)}k / {(working.max_context_tokens / 1000).toFixed(0)}k tokens used
            </div>
            <div className="mt-1 w-full bg-gray-800 rounded-full h-1.5">
              <div
                className="bg-yellow-500 h-1.5 rounded-full transition-all"
                style={{ width: `${Math.min(100, (working.total_tokens_estimate / working.max_context_tokens) * 100)}%` }}
              />
            </div>
          </>
        ) : (
          <p className="text-xs text-gray-500">Not yet available</p>
        )}
      </div>
    </div>
  )
}


/* ─── Short-Term Memory Tab (Scratch Pad) ──────────────────────────── */

function ShortTermMemoryTab() {
  const [memories, setMemories] = useState<any[]>([])
  const [count, setCount] = useState(0)
  const [maxEntries, setMaxEntries] = useState(50)
  const [loading, setLoading] = useState(true)
  const [newNote, setNewNote] = useState('')
  const [adding, setAdding] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getShortTermMemories()
      setMemories(data.memories || [])
      setCount(data.count || 0)
      setMaxEntries(data.max_entries || 50)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const handleAdd = async () => {
    if (!newNote.trim()) return
    setAdding(true)
    try {
      await api.updateShortTermMemories({ add: [newNote.trim()] })
      setNewNote('')
      await load()
    } catch (e) {
      console.error(e)
    }
    setAdding(false)
  }

  const handleRemove = async (idx: number) => {
    try {
      await api.updateShortTermMemories({ remove: [idx] })
      await load()
    } catch (e) {
      console.error(e)
    }
  }

  const handleClear = async () => {
    if (!confirm('Clear all short-term memories?')) return
    try {
      await api.clearShortTermMemories()
      await load()
    } catch (e) {
      console.error(e)
    }
  }

  const formatAge = (isoStr: string) => {
    try {
      const created = new Date(isoStr)
      const now = new Date()
      const diffMs = now.getTime() - created.getTime()
      const mins = Math.floor(diffMs / 60000)
      if (mins < 60) return `${mins}m ago`
      const hours = Math.floor(mins / 60)
      if (hours < 24) return `${hours}h ago`
      return `${Math.floor(hours / 24)}d ago`
    } catch {
      return '?'
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <StickyNote size={20} className="text-orange-400" />
            Short-Term Memories
            <span className="text-sm font-normal text-gray-500">({count}/{maxEntries})</span>
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            Rolling scratch pad — operational notes that persist across iterations. Auto-expires after 48h.
            JARVIS and tool results auto-add entries here.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="flex items-center gap-1 px-3 py-1.5 rounded bg-gray-800 text-gray-300 text-sm hover:bg-gray-700">
            <RefreshCw size={14} />
            Refresh
          </button>
          {count > 0 && (
            <button onClick={handleClear} className="flex items-center gap-1 px-3 py-1.5 rounded bg-red-900/30 text-red-400 text-sm hover:bg-red-900/50">
              <Trash2 size={14} />
              Clear All
            </button>
          )}
        </div>
      </div>

      {/* Capacity bar */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Capacity</span>
          <span>{count} / {maxEntries} slots used</span>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all ${
              count / maxEntries > 0.8 ? 'bg-red-500' : count / maxEntries > 0.5 ? 'bg-yellow-500' : 'bg-orange-500'
            }`}
            style={{ width: `${Math.min(100, (count / maxEntries) * 100)}%` }}
          />
        </div>
      </div>

      {/* Add note */}
      <div className="flex gap-2">
        <input
          type="text"
          value={newNote}
          onChange={(e) => setNewNote(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          placeholder="Add a note for JARVIS..."
          className="flex-1 px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-orange-400"
        />
        <button
          onClick={handleAdd}
          disabled={adding || !newNote.trim()}
          className="flex items-center gap-1 px-4 py-2 bg-orange-600 text-white rounded-lg text-sm hover:bg-orange-500 disabled:opacity-50"
        >
          <Plus size={14} />
          Add
        </button>
      </div>

      {/* Memory list */}
      {loading ? (
        <div className="text-gray-500 py-4">Loading...</div>
      ) : memories.length === 0 ? (
        <div className="text-gray-500 py-8 text-center">
          No short-term memories yet. They'll appear as JARVIS runs iterations and executes tools.
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-lg divide-y divide-gray-800 max-h-[600px] overflow-auto">
          {memories.map((mem, idx) => (
            <div key={idx} className="px-4 py-3 group hover:bg-gray-800/50">
              <div className="flex items-start gap-3">
                <span className="text-xs font-mono text-gray-600 mt-0.5 w-6 text-right">[{idx}]</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-300">{mem.content}</p>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-xs text-gray-600 flex items-center gap-1">
                      <Clock size={10} />
                      {formatAge(mem.created_at)}
                    </span>
                    {mem.iteration > 0 && (
                      <span className="text-xs text-gray-600">iter #{mem.iteration}</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleRemove(idx)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-600 hover:text-red-400 p-1"
                  title="Remove"
                >
                  <X size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


/* ─── Working Context Tab ───────────────────────────────────────────── */

function WorkingContextTab() {
  const [snapshot, setSnapshot] = useState<WorkingMemorySnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getWorkingMemory()
      setSnapshot(data)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  if (loading && !snapshot) return <p className="text-gray-500">Loading working context...</p>

  if (!snapshot) return <p className="text-gray-500">Working memory not available yet. Wait for an iteration.</p>

  const tokenPct = (snapshot.total_tokens_estimate / snapshot.max_context_tokens) * 100

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Zap size={20} className="text-yellow-400" />
            Current Working Context
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            What JARVIS currently has loaded into memory for its next iteration
          </p>
        </div>
        <button onClick={load} className="flex items-center gap-1 px-3 py-1.5 rounded bg-gray-800 text-gray-300 text-sm hover:bg-gray-700">
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {/* Context stats bar */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="grid grid-cols-4 gap-4 text-center">
          <div>
            <div className="text-2xl font-bold text-yellow-400">{snapshot.injected_memory_count}</div>
            <div className="text-xs text-gray-500">Memories Loaded</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-blue-400">{snapshot.message_count}</div>
            <div className="text-xs text-gray-500">Messages</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-purple-400">{(snapshot.total_tokens_estimate / 1000).toFixed(1)}k</div>
            <div className="text-xs text-gray-500">Tokens Used</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-300">{(snapshot.system_prompt_tokens / 1000).toFixed(1)}k</div>
            <div className="text-xs text-gray-500">System Prompt</div>
          </div>
        </div>
        <div className="mt-3">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>Context Window Usage</span>
            <span>{tokenPct.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all ${
                tokenPct > 80 ? 'bg-red-500' : tokenPct > 50 ? 'bg-yellow-500' : 'bg-green-500'
              }`}
              style={{ width: `${Math.min(100, tokenPct)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Injected memories list */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg">
        <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
          <h4 className="font-medium text-sm flex items-center gap-2">
            <Brain size={16} className="text-purple-400" />
            Injected Memories ({snapshot.injected_memory_count})
          </h4>
          <span className="text-xs text-gray-500">
            Retrieved by relevance to current goals
          </span>
        </div>
        {snapshot.injected_memories.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">No memories injected yet. Memories appear after the first iteration.</div>
        ) : (
          <div className="divide-y divide-gray-800 max-h-[500px] overflow-auto">
            {snapshot.injected_memories.map((mem: any, idx: number) => (
              <div key={idx} className="px-4 py-3 hover:bg-gray-800/50 cursor-pointer"
                   onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}>
                <div className="flex items-start gap-2">
                  <div className="mt-0.5">
                    {expandedIdx === idx ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono text-jarvis-400">#{idx + 1}</span>
                      {mem.distance != null && (
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          (1 - mem.distance) > 0.7 ? 'bg-green-900/50 text-green-400' :
                          (1 - mem.distance) > 0.4 ? 'bg-yellow-900/50 text-yellow-400' :
                          'bg-gray-800 text-gray-400'
                        }`}>
                          {((1 - mem.distance) * 100).toFixed(0)}% match
                        </span>
                      )}
                      {mem.metadata?.importance_score != null && (
                        <span className="text-xs text-gray-500">
                          importance: {Number(mem.metadata.importance_score).toFixed(2)}
                        </span>
                      )}
                      {mem.metadata?.source && (
                        <span className="text-xs bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">
                          {String(mem.metadata.source)}
                        </span>
                      )}
                    </div>
                    <p className={`text-sm text-gray-300 ${expandedIdx === idx ? '' : 'line-clamp-2'}`}>
                      {mem.content}
                    </p>
                    {expandedIdx === idx && mem.metadata && (
                      <div className="mt-2 text-xs text-gray-500 bg-gray-800/50 rounded p-2 font-mono">
                        {Object.entries(mem.metadata).map(([k, v]) => (
                          <div key={k}><span className="text-gray-400">{k}:</span> {String(v)}</div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}


/* ─── Vector Browser Tab ────────────────────────────────────────────── */

function VectorBrowserTab() {
  const [entries, setEntries] = useState<VectorMemoryEntry[]>([])
  const [total, setTotal] = useState(0)
  const [query, setQuery] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const limit = 50

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.browseVectorMemory(searchQuery || undefined, limit, offset)
      setEntries(data.entries || [])
      setTotal(data.total || 0)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }, [searchQuery, offset])

  useEffect(() => { load() }, [load])

  const handleSearch = () => {
    setOffset(0)
    setSearchQuery(query)
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this memory? This cannot be undone.')) return
    try {
      await api.deleteVectorMemory(id)
      setEntries(prev => prev.filter(e => e.id !== id))
      setTotal(prev => prev - 1)
    } catch (e) {
      console.error(e)
    }
  }

  const handleMarkPermanent = async (id: string) => {
    try {
      await fetch(`/api/memory/mark-permanent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ memory_id: id }),
      })
      load()
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Database size={20} className="text-purple-400" />
          Vector Memory Browser
          <span className="text-sm font-normal text-gray-500">({total} total)</span>
        </h3>
      </div>

      {/* Search bar */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search memories by semantic similarity..."
            className="w-full pl-10 pr-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-jarvis-400"
          />
        </div>
        <button onClick={handleSearch} className="px-4 py-2 bg-jarvis-600 text-white rounded-lg text-sm hover:bg-jarvis-500">
          Search
        </button>
        {searchQuery && (
          <button
            onClick={() => { setQuery(''); setSearchQuery(''); setOffset(0) }}
            className="px-4 py-2 bg-gray-800 text-gray-300 rounded-lg text-sm hover:bg-gray-700"
          >
            Clear
          </button>
        )}
      </div>

      {searchQuery && (
        <div className="text-sm text-gray-400 flex items-center gap-2">
          <Filter size={14} />
          Showing results for: <span className="text-jarvis-400">"{searchQuery}"</span>
          (sorted by relevance)
        </div>
      )}

      {/* Entries list */}
      {loading ? (
        <div className="text-gray-500 py-4">Loading memories...</div>
      ) : entries.length === 0 ? (
        <div className="text-gray-500 py-8 text-center">
          {searchQuery ? 'No memories match your search.' : 'No memories stored yet.'}
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-lg divide-y divide-gray-800 max-h-[600px] overflow-auto">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="px-4 py-3 hover:bg-gray-800/50"
            >
              <div className="flex items-start gap-2">
                <button
                  className="mt-0.5 text-gray-500"
                  onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                >
                  {expandedId === entry.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>
                <div className="flex-1 min-w-0">
                  {/* Header badges */}
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    {entry.permanent && (
                      <span className="text-xs bg-yellow-900/50 text-yellow-400 px-1.5 py-0.5 rounded flex items-center gap-1">
                        <Shield size={10} /> Permanent
                      </span>
                    )}
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      entry.importance_score > 0.7 ? 'bg-green-900/50 text-green-400' :
                      entry.importance_score > 0.3 ? 'bg-yellow-900/50 text-yellow-400' :
                      'bg-gray-800 text-gray-500'
                    }`}>
                      importance: {entry.importance_score.toFixed(2)}
                    </span>
                    {entry.distance != null && (
                      <span className="text-xs bg-purple-900/30 text-purple-400 px-1.5 py-0.5 rounded">
                        {((1 - entry.distance) * 100).toFixed(0)}% match
                      </span>
                    )}
                    {entry.source && (
                      <span className="text-xs bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">{entry.source}</span>
                    )}
                    {entry.ttl_hours > 0 && (
                      <span className="text-xs text-gray-500 flex items-center gap-1">
                        <Clock size={10} /> TTL: {entry.ttl_hours}h
                      </span>
                    )}
                  </div>

                  {/* Content */}
                  <p className={`text-sm text-gray-300 ${expandedId === entry.id ? '' : 'line-clamp-2'}`}>
                    {entry.content}
                  </p>

                  {/* Expanded details */}
                  {expandedId === entry.id && (
                    <div className="mt-2 space-y-2">
                      <div className="text-xs text-gray-500 font-mono bg-gray-800/50 rounded p-2">
                        <div><span className="text-gray-400">ID:</span> {entry.id}</div>
                        <div><span className="text-gray-400">Created:</span> {entry.created_at}</div>
                        {Object.entries(entry.metadata || {}).map(([k, v]) => (
                          <div key={k}><span className="text-gray-400">{k}:</span> {String(v)}</div>
                        ))}
                      </div>
                      <div className="flex gap-2">
                        {!entry.permanent && (
                          <button
                            onClick={() => handleMarkPermanent(entry.id)}
                            className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-yellow-900/30 text-yellow-400 hover:bg-yellow-900/50"
                          >
                            <Star size={12} /> Mark Permanent
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(entry.id)}
                          className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-900/30 text-red-400 hover:bg-red-900/50"
                        >
                          <Trash2 size={12} /> Delete
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {!searchQuery && total > limit && (
        <div className="flex items-center justify-between text-sm">
          <button
            onClick={() => setOffset(Math.max(0, offset - limit))}
            disabled={offset === 0}
            className="px-3 py-1.5 rounded bg-gray-800 text-gray-300 disabled:opacity-30 hover:bg-gray-700"
          >
            Previous
          </button>
          <span className="text-gray-500">
            Showing {offset + 1}-{Math.min(offset + limit, total)} of {total}
          </span>
          <button
            onClick={() => setOffset(offset + limit)}
            disabled={offset + limit >= total}
            className="px-3 py-1.5 rounded bg-gray-800 text-gray-300 disabled:opacity-30 hover:bg-gray-700"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}


/* ─── Blob Browser Tab ──────────────────────────────────────────────── */

function BlobBrowserTab() {
  const [entries, setEntries] = useState<BlobEntry[]>([])
  const [eventTypes, setEventTypes] = useState<string[]>([])
  const [selectedType, setSelectedType] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const [limit, setLimit] = useState(50)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.browseBlob(selectedType || undefined, limit)
      setEntries(data.entries || [])
      setEventTypes(data.event_types || [])
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }, [selectedType, limit])

  useEffect(() => { load() }, [load])

  const getTypeColor = (type: string) => {
    const colors: Record<string, string> = {
      'llm_request': 'text-purple-400 bg-purple-900/30',
      'llm_response': 'text-purple-300 bg-purple-900/20',
      'tool_call': 'text-blue-400 bg-blue-900/30',
      'tool_result': 'text-blue-300 bg-blue-900/20',
      'chat_creator': 'text-green-400 bg-green-900/30',
      'chat_jarvis': 'text-jarvis-400 bg-jarvis-900/30',
      'system': 'text-yellow-400 bg-yellow-900/30',
      'error': 'text-red-400 bg-red-900/30',
      'planning': 'text-orange-400 bg-orange-900/30',
    }
    return colors[type] || 'text-gray-400 bg-gray-800'
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <HardDrive size={20} className="text-blue-400" />
          Blob Storage Browser
        </h3>
        <button onClick={load} className="flex items-center gap-1 px-3 py-1.5 rounded bg-gray-800 text-gray-300 text-sm hover:bg-gray-700">
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setSelectedType('')}
          className={`px-3 py-1.5 rounded text-xs transition-colors ${
            !selectedType ? 'bg-jarvis-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          All
        </button>
        {eventTypes.map((type) => (
          <button
            key={type}
            onClick={() => setSelectedType(type)}
            className={`px-3 py-1.5 rounded text-xs transition-colors ${
              selectedType === type ? 'bg-jarvis-600 text-white' : getTypeColor(type)
            }`}
          >
            {type}
          </button>
        ))}
      </div>

      {/* Entries list */}
      {loading ? (
        <div className="text-gray-500 py-4">Loading blob entries...</div>
      ) : entries.length === 0 ? (
        <div className="text-gray-500 py-8 text-center">No blob entries found.</div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-lg divide-y divide-gray-800 max-h-[600px] overflow-auto">
          {entries.map((entry, idx) => (
            <div
              key={idx}
              className="px-4 py-3 hover:bg-gray-800/50 cursor-pointer"
              onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
            >
              <div className="flex items-start gap-2">
                <div className="mt-0.5">
                  {expandedIdx === idx ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${getTypeColor(entry.event_type)}`}>
                      {entry.event_type}
                    </span>
                    <span className="text-xs text-gray-500">
                      {new Date(entry.timestamp).toLocaleString()}
                    </span>
                  </div>
                  <p className={`text-sm text-gray-300 ${expandedIdx === idx ? 'whitespace-pre-wrap' : 'line-clamp-2'}`}>
                    {entry.content}
                  </p>
                  {expandedIdx === idx && entry.metadata && Object.keys(entry.metadata).length > 0 && (
                    <div className="mt-2 text-xs text-gray-500 bg-gray-800/50 rounded p-2 font-mono">
                      {Object.entries(entry.metadata).map(([k, v]) => (
                        <div key={k}><span className="text-gray-400">{k}:</span> {typeof v === 'object' ? JSON.stringify(v) : String(v)}</div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Load more */}
      <div className="flex justify-center">
        <button
          onClick={() => setLimit(prev => prev + 50)}
          className="px-4 py-2 rounded bg-gray-800 text-gray-300 text-sm hover:bg-gray-700"
        >
          Load More (showing {entries.length})
        </button>
      </div>
    </div>
  )
}


/* ─── Config Tab ────────────────────────────────────────────────────── */

function ConfigTab() {
  const [config, setConfig] = useState<MemoryConfig | null>(null)
  const [editValues, setEditValues] = useState<Partial<MemoryConfig>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.getWorkingMemory().then((data) => {
      if (data.config) {
        setConfig(data.config)
        setEditValues(data.config)
      }
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const result = await api.updateMemoryConfig(editValues as Record<string, number>)
      if (result.config) {
        setConfig(result.config)
        setEditValues(result.config)
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      console.error(e)
    }
    setSaving(false)
  }

  if (loading) return <p className="text-gray-500">Loading config...</p>

  const configFields = [
    {
      key: 'retrieval_count' as keyof MemoryConfig,
      label: 'Memory Retrieval Count',
      description: 'How many vector memories to inject per iteration. Higher = more context but more tokens.',
      min: 1, max: 100, step: 1,
    },
    {
      key: 'relevance_threshold' as keyof MemoryConfig,
      label: 'Relevance Threshold',
      description: 'Minimum similarity score (0-1) to include a memory. 0 = include all matches.',
      min: 0, max: 1, step: 0.05,
    },
    {
      key: 'decay_factor' as keyof MemoryConfig,
      label: 'Importance Decay Factor',
      description: 'How fast old memories lose importance each maintenance cycle (every 10 iterations). Lower = faster decay.',
      min: 0.5, max: 1.0, step: 0.01,
    },
    {
      key: 'max_context_tokens' as keyof MemoryConfig,
      label: 'Max Context Tokens',
      description: 'Maximum working context window size. Older messages get trimmed to fit.',
      min: 10000, max: 200000, step: 10000,
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Settings size={20} className="text-gray-400" />
            Memory Configuration
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            These settings can also be changed by JARVIS itself via the <code className="text-jarvis-400">memory_config</code> field in its plan response.
          </p>
        </div>
      </div>

      <div className="space-y-4">
        {configFields.map((field) => (
          <div key={field.key} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-1">
              <label className="text-sm font-medium text-gray-200">{field.label}</label>
              <span className="text-sm font-mono text-jarvis-400">
                {editValues[field.key] ?? config?.[field.key] ?? ''}
              </span>
            </div>
            <p className="text-xs text-gray-500 mb-3">{field.description}</p>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-500 w-10">{field.min}</span>
              <input
                type="range"
                min={field.min}
                max={field.max}
                step={field.step}
                value={editValues[field.key] ?? config?.[field.key] ?? field.min}
                onChange={(e) => setEditValues(prev => ({
                  ...prev,
                  [field.key]: field.step < 1 ? parseFloat(e.target.value) : parseInt(e.target.value)
                }))}
                className="flex-1 accent-jarvis-400"
              />
              <span className="text-xs text-gray-500 w-14 text-right">{field.max}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 bg-jarvis-600 text-white rounded-lg text-sm hover:bg-jarvis-500 disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Apply Changes'}
        </button>
        {saved && <span className="text-sm text-green-400">Saved!</span>}
        <p className="text-xs text-gray-500">
          Changes take effect on the next iteration. JARVIS can also override these at any time.
        </p>
      </div>
    </div>
  )
}
