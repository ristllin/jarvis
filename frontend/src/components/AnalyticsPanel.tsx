import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts'
import {
  BarChart3, RefreshCw, DollarSign, Zap, AlertTriangle,
  Clock, Cpu, Wrench,
} from 'lucide-react'

type TimeRange = '1h' | '6h' | '24h' | '7d' | '30d'

interface SeriesPoint {
  time: string
  cost: number
  input_tokens: number
  output_tokens: number
  llm_calls: number
  tool_calls: number
  tool_errors: number
}

interface AnalyticsSummary {
  total_cost: number
  total_llm_calls: number
  total_tool_calls: number
  total_tool_errors: number
  error_rate: number
  total_input_tokens: number
  total_output_tokens: number
  models: Record<string, number>
  providers: Record<string, number>
  tools: Record<string, number>
}

interface AnalyticsData {
  range: string
  bucket_label: string
  summary: AnalyticsSummary
  series: SeriesPoint[]
}

type ChartView = 'cost' | 'tokens' | 'calls' | 'errors'

const COLORS = [
  '#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444',
  '#ec4899', '#3b82f6', '#14b8a6', '#f97316', '#6366f1',
]

const PIE_COLORS = [
  '#8b5cf6', '#06b6d4', '#f59e0b', '#10b981', '#ef4444',
  '#ec4899', '#3b82f6', '#14b8a6',
]

export function AnalyticsPanel() {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [range, setRange] = useState<TimeRange>('24h')
  const [chartView, setChartView] = useState<ChartView>('cost')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.getAnalytics(range)
      setData(result)
    } catch (e) {
      console.error('Analytics fetch failed:', e)
    }
    setLoading(false)
  }, [range])

  useEffect(() => { load() }, [load])

  const ranges: { id: TimeRange; label: string }[] = [
    { id: '1h', label: '1H' },
    { id: '6h', label: '6H' },
    { id: '24h', label: '24H' },
    { id: '7d', label: '7D' },
    { id: '30d', label: '30D' },
  ]

  const chartViews: { id: ChartView; label: string; icon: React.ReactNode }[] = [
    { id: 'cost', label: 'Cost', icon: <DollarSign size={14} /> },
    { id: 'tokens', label: 'Tokens', icon: <Zap size={14} /> },
    { id: 'calls', label: 'Calls', icon: <Cpu size={14} /> },
    { id: 'errors', label: 'Errors', icon: <AlertTriangle size={14} /> },
  ]

  const formatTime = (time: string) => {
    try {
      const d = new Date(time + 'Z')
      if (range === '1h' || range === '6h') return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      if (range === '24h') return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      if (range === '7d') return d.toLocaleDateString([], { weekday: 'short', hour: '2-digit' })
      return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
    } catch {
      return time
    }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <BarChart3 size={22} className="text-jarvis-400" />
          Analytics
        </h2>
        <div className="flex items-center gap-3">
          {/* Time range selector */}
          <div className="flex bg-gray-900 rounded-lg border border-gray-800 p-0.5">
            {ranges.map(r => (
              <button
                key={r.id}
                onClick={() => setRange(r.id)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  range === r.id
                    ? 'bg-gray-700 text-jarvis-400'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <button onClick={load} className="text-gray-400 hover:text-gray-200">
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {loading && !data ? (
        <div className="text-gray-500 py-8 text-center">Loading analytics...</div>
      ) : !data ? (
        <div className="text-gray-500 py-8 text-center">No data available</div>
      ) : (
        <>
          {/* Summary cards */}
          <SummaryCards summary={data.summary} />

          {/* Chart view selector */}
          <div className="flex gap-1 bg-gray-900 rounded-lg p-1 border border-gray-800">
            {chartViews.map(v => (
              <button
                key={v.id}
                onClick={() => setChartView(v.id)}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm transition-colors ${
                  chartView === v.id
                    ? 'bg-gray-800 text-jarvis-400'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {v.icon}
                {v.label}
              </button>
            ))}
          </div>

          {/* Main chart */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <MainChart
              series={data.series}
              view={chartView}
              formatTime={formatTime}
              bucketLabel={data.bucket_label}
            />
          </div>

          {/* Breakdown panels */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <BreakdownPanel
              title="Models"
              icon={<Cpu size={16} className="text-purple-400" />}
              data={data.summary.models}
              colorOffset={0}
            />
            <BreakdownPanel
              title="Providers"
              icon={<DollarSign size={16} className="text-cyan-400" />}
              data={data.summary.providers}
              colorOffset={2}
            />
            <BreakdownPanel
              title="Tools"
              icon={<Wrench size={16} className="text-yellow-400" />}
              data={data.summary.tools}
              colorOffset={4}
            />
          </div>
        </>
      )}
    </div>
  )
}


/* ─── Summary Cards ─────────────────────────────────────────────────── */

function SummaryCards({ summary }: { summary: AnalyticsSummary }) {
  const cards = [
    {
      label: 'Total Cost',
      value: `$${summary.total_cost.toFixed(4)}`,
      color: 'text-green-400',
      icon: <DollarSign size={18} />,
    },
    {
      label: 'LLM Calls',
      value: summary.total_llm_calls,
      color: 'text-purple-400',
      icon: <Cpu size={18} />,
    },
    {
      label: 'Tool Calls',
      value: summary.total_tool_calls,
      color: 'text-cyan-400',
      icon: <Wrench size={18} />,
    },
    {
      label: 'Error Rate',
      value: `${summary.error_rate.toFixed(1)}%`,
      color: summary.error_rate > 20 ? 'text-red-400' : summary.error_rate > 5 ? 'text-yellow-400' : 'text-green-400',
      icon: <AlertTriangle size={18} />,
    },
    {
      label: 'Input Tokens',
      value: `${(summary.total_input_tokens / 1000).toFixed(1)}k`,
      color: 'text-blue-400',
      icon: <Zap size={18} />,
    },
    {
      label: 'Output Tokens',
      value: `${(summary.total_output_tokens / 1000).toFixed(1)}k`,
      color: 'text-orange-400',
      icon: <Zap size={18} />,
    },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map(c => (
        <div key={c.label} className="bg-gray-900 border border-gray-800 rounded-lg p-3">
          <div className="flex items-center gap-1.5 mb-1">
            <span className={c.color}>{c.icon}</span>
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">{c.label}</span>
          </div>
          <div className={`text-xl font-bold ${c.color}`}>{c.value}</div>
        </div>
      ))}
    </div>
  )
}


/* ─── Main Chart ────────────────────────────────────────────────────── */

function MainChart({
  series,
  view,
  formatTime,
  bucketLabel,
}: {
  series: SeriesPoint[]
  view: ChartView
  formatTime: (t: string) => string
  bucketLabel: string
}) {
  const tooltipFormatter = (value: number, name: string) => {
    if (name === 'cost') return [`$${value.toFixed(6)}`, 'Cost']
    if (name.includes('token')) return [`${(value / 1000).toFixed(1)}k`, name]
    return [value, name]
  }

  if (view === 'cost') {
    return (
      <div>
        <h3 className="text-sm text-gray-400 mb-3">
          Cost over time <span className="text-gray-600">(per {bucketLabel})</span>
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={series}>
            <defs>
              <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="time" tickFormatter={formatTime} stroke="#6b7280" fontSize={11} />
            <YAxis stroke="#6b7280" fontSize={11} tickFormatter={v => `$${v.toFixed(2)}`} />
            <Tooltip
              contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
              labelFormatter={formatTime}
              formatter={tooltipFormatter}
            />
            <Area type="monotone" dataKey="cost" stroke="#10b981" fill="url(#costGrad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (view === 'tokens') {
    return (
      <div>
        <h3 className="text-sm text-gray-400 mb-3">
          Token usage over time <span className="text-gray-600">(per {bucketLabel})</span>
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={series}>
            <defs>
              <linearGradient id="inGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="outGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="time" tickFormatter={formatTime} stroke="#6b7280" fontSize={11} />
            <YAxis stroke="#6b7280" fontSize={11} tickFormatter={v => `${(v / 1000).toFixed(0)}k`} />
            <Tooltip
              contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
              labelFormatter={formatTime}
              formatter={tooltipFormatter}
            />
            <Legend />
            <Area type="monotone" dataKey="input_tokens" name="Input Tokens" stroke="#3b82f6" fill="url(#inGrad)" strokeWidth={2} />
            <Area type="monotone" dataKey="output_tokens" name="Output Tokens" stroke="#f97316" fill="url(#outGrad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (view === 'calls') {
    return (
      <div>
        <h3 className="text-sm text-gray-400 mb-3">
          API & Tool calls over time <span className="text-gray-600">(per {bucketLabel})</span>
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={series}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="time" tickFormatter={formatTime} stroke="#6b7280" fontSize={11} />
            <YAxis stroke="#6b7280" fontSize={11} />
            <Tooltip
              contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
              labelFormatter={formatTime}
            />
            <Legend />
            <Bar dataKey="llm_calls" name="LLM Calls" fill="#8b5cf6" radius={[2, 2, 0, 0]} />
            <Bar dataKey="tool_calls" name="Tool Calls" fill="#06b6d4" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  // errors view
  return (
    <div>
      <h3 className="text-sm text-gray-400 mb-3">
        Errors over time <span className="text-gray-600">(per {bucketLabel})</span>
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={series}>
          <defs>
            <linearGradient id="errGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="time" tickFormatter={formatTime} stroke="#6b7280" fontSize={11} />
          <YAxis stroke="#6b7280" fontSize={11} />
          <Tooltip
            contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
            labelFormatter={formatTime}
          />
          <Legend />
          <Area type="monotone" dataKey="tool_calls" name="Total Calls" stroke="#06b6d4" fill="transparent" strokeWidth={1.5} strokeDasharray="4 4" />
          <Area type="monotone" dataKey="tool_errors" name="Errors" stroke="#ef4444" fill="url(#errGrad)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}


/* ─── Breakdown Panel (pie + list) ──────────────────────────────────── */

function BreakdownPanel({
  title,
  icon,
  data,
  colorOffset = 0,
}: {
  title: string
  icon: React.ReactNode
  data: Record<string, number>
  colorOffset?: number
}) {
  const entries = Object.entries(data)
    .sort((a, b) => b[1] - a[1])

  const total = entries.reduce((sum, [, v]) => sum + v, 0)

  if (entries.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          {icon}
          <h4 className="text-sm font-medium text-gray-300">{title}</h4>
        </div>
        <p className="text-xs text-gray-500">No data in this period</p>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h4 className="text-sm font-medium text-gray-300">{title}</h4>
        <span className="text-xs text-gray-600 ml-auto">{total} total</span>
      </div>

      {/* Mini pie chart */}
      {entries.length > 1 && (
        <div className="flex justify-center mb-3">
          <ResponsiveContainer width={120} height={120}>
            <PieChart>
              <Pie
                data={entries.map(([name, value]) => ({ name, value }))}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={50}
                innerRadius={25}
              >
                {entries.map((_, idx) => (
                  <Cell key={idx} fill={PIE_COLORS[(idx + colorOffset) % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px', fontSize: '12px' }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* List */}
      <div className="space-y-1.5 max-h-[200px] overflow-auto">
        {entries.map(([name, count], idx) => {
          const pct = total > 0 ? (count / total) * 100 : 0
          const color = PIE_COLORS[(idx + colorOffset) % PIE_COLORS.length]
          return (
            <div key={name} className="flex items-center gap-2 text-xs">
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
              <span className="text-gray-300 truncate flex-1" title={name}>{name}</span>
              <span className="text-gray-500 font-mono">{count}</span>
              <span className="text-gray-600 w-10 text-right">{pct.toFixed(0)}%</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
