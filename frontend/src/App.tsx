import { useState, useEffect } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { api } from './api/client'
import { LogOut } from 'lucide-react'
import { Dashboard } from './components/Dashboard'
import { BudgetPanel } from './components/BudgetPanel'
import { MemoryPanel } from './components/MemoryPanel'
import { LogViewer } from './components/LogViewer'
import { ToolUsagePanel } from './components/ToolUsagePanel'
import { ModelHierarchyPanel } from './components/ModelHierarchyPanel'
import { DirectiveEditor } from './components/DirectiveEditor'
import { ControlBar } from './components/ControlBar'
import { ChatPanel } from './components/ChatPanel'
import { AnalyticsPanel } from './components/AnalyticsPanel'
import { IterationDebugPanel } from './components/IterationDebugPanel'
import type { JarvisStatus, BudgetStatus, MemoryStats } from './types'
import { Bot, DollarSign, Brain, ScrollText, Wrench, Cpu, FileEdit, MessageCircle, BarChart3, Activity } from 'lucide-react'

type Tab = 'dashboard' | 'chat' | 'analytics' | 'budget' | 'memory' | 'logs' | 'tools' | 'models' | 'directive' | 'iterations'

const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <Bot size={18} /> },
  { id: 'chat', label: 'Chat', icon: <MessageCircle size={18} /> },
  { id: 'iterations', label: 'Iterations', icon: <Activity size={18} /> },
  { id: 'analytics', label: 'Analytics', icon: <BarChart3 size={18} /> },
  { id: 'budget', label: 'Budget', icon: <DollarSign size={18} /> },
  { id: 'memory', label: 'Memory', icon: <Brain size={18} /> },
  { id: 'logs', label: 'Logs', icon: <ScrollText size={18} /> },
  { id: 'tools', label: 'Tools', icon: <Wrench size={18} /> },
  { id: 'models', label: 'Models', icon: <Cpu size={18} /> },
  { id: 'directive', label: 'Directive', icon: <FileEdit size={18} /> },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard')
  const [status, setStatus] = useState<JarvisStatus | null>(null)
  const [budget, setBudget] = useState<BudgetStatus | null>(null)
  const [memoryStats, setMemoryStats] = useState<MemoryStats | null>(null)
  const [user, setUser] = useState<{ email: string; name?: string; auth_enabled?: boolean } | null>(null)
  const { lastMessage, connected } = useWebSocket()

  useEffect(() => {
    api.getMe().then(setUser).catch(() => setUser(null))
  }, [])

  const refresh = async () => {
    try {
      const [s, b, m] = await Promise.all([
        api.getStatus(),
        api.getBudget(),
        api.getMemoryStats(),
      ])
      setStatus(s)
      setBudget(b)
      setMemoryStats(m)
    } catch {}
  }

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 10000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (lastMessage?.type === 'state_update') {
      refresh()
    }
  }, [lastMessage])

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <h1 className="text-xl font-bold text-jarvis-400 tracking-wide">JARVIS</h1>
          <p className="text-xs text-gray-500 mt-1">
            v{status?.version ?? '—'} — Autonomous AI
          </p>
        </div>
        <nav className="flex-1 py-2">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                tab === t.id
                  ? 'bg-jarvis-950 text-jarvis-400 border-r-2 border-jarvis-400'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </nav>
        <div className="p-4 border-t border-gray-800 space-y-2">
          {user?.auth_enabled && (
            <button
              onClick={() => api.logout()}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-400 hover:text-gray-200 hover:bg-gray-800 rounded transition-colors"
            >
              <LogOut size={16} />
              Log out ({user.email})
            </button>
          )}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-xs text-gray-500">{connected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col">
        <ControlBar status={status} onRefresh={refresh} />
        <div className="flex-1 overflow-auto p-6">
          {tab === 'dashboard' && <Dashboard status={status} budget={budget} memory={memoryStats} lastMessage={lastMessage} />}
          {tab === 'chat' && <ChatPanel lastMessage={lastMessage} />}
          {tab === 'analytics' && <AnalyticsPanel />}
          {tab === 'budget' && <BudgetPanel budget={budget} onRefresh={refresh} />}
          {tab === 'memory' && <MemoryPanel stats={memoryStats} />}
          {tab === 'logs' && <LogViewer />}
          {tab === 'tools' && <ToolUsagePanel />}
          {tab === 'models' && <ModelHierarchyPanel />}
          {tab === 'iterations' && <IterationDebugPanel />}
          {tab === 'directive' && <DirectiveEditor currentDirective={status?.directive || ''} onUpdate={refresh} />}
        </div>
      </main>
    </div>
  )
}
