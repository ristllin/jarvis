import { useState, useEffect } from 'react'
import { api } from '../api/client'
import type { BudgetStatus, ProviderStatus } from '../types'
import { DollarSign, RefreshCw, Plus, Check, X, Edit2, Key, Eye, EyeOff } from 'lucide-react'

interface Props {
  budget: BudgetStatus | null
  onRefresh: () => void
}

const TIER_COLORS: Record<string, string> = {
  paid: 'blue',
  free: 'green',
  unknown: 'gray',
}

const PROVIDER_ICONS: Record<string, string> = {
  anthropic: '🅰️',
  openai: '🤖',
  mistral: '🌬️',
  grok: '⚡',
  tavily: '🔍',
  ollama: '🦙',
}

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
}

function isMonetary(currency: string): boolean {
  return ['USD', 'EUR', 'GBP'].includes(currency)
}

function fmtBalance(value: number | null | undefined, currency: string, decimals?: number): string {
  if (value == null) return 'unknown'
  const sym = CURRENCY_SYMBOLS[currency]
  if (sym) {
    return `${sym}${value.toFixed(decimals ?? 2)}`
  }
  // Non-monetary: "989 credits", "150 requests"
  return `${Math.round(value)} ${currency}`
}

function fmtSpent(value: number, currency: string): string {
  if (isMonetary(currency)) {
    return `${CURRENCY_SYMBOLS[currency] || ''}${value.toFixed(4)} spent`
  }
  return `${Math.round(value)} ${currency} used`
}

const COMMON_CURRENCIES = ['USD', 'EUR', 'GBP', 'credits', 'requests']

export function BudgetPanel({ budget, onRefresh }: Props) {
  const [newCap, setNewCap] = useState('')
  const [providers, setProviders] = useState<ProviderStatus[]>([])
  const [editingProvider, setEditingProvider] = useState<string | null>(null)
  const [editBalance, setEditBalance] = useState('')
  const [editNotes, setEditNotes] = useState('')
  const [editCurrency, setEditCurrency] = useState('')
  const [editApiKey, setEditApiKey] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [newProvider, setNewProvider] = useState({
    provider: '', api_key: '', known_balance: '', tier: 'unknown', currency: 'USD', notes: ''
  })

  useEffect(() => {
    if (budget?.providers) {
      setProviders(budget.providers)
    } else {
      loadProviders()
    }
  }, [budget])

  const loadProviders = async () => {
    try {
      const data = await api.getProviders()
      setProviders(data.providers || [])
    } catch {}
  }

  const handleOverride = async () => {
    const val = parseFloat(newCap)
    if (isNaN(val) || val <= 0) return
    await api.overrideBudget(val)
    setNewCap('')
    onRefresh()
  }

  const startEdit = (p: ProviderStatus) => {
    setEditingProvider(p.provider)
    setEditBalance(p.known_balance != null ? String(p.known_balance) : '')
    setEditNotes(p.notes || '')
    setEditCurrency(p.currency || 'USD')
    setEditApiKey('')
  }

  const saveEdit = async () => {
    if (!editingProvider) return
    const update: any = {}
    const bal = parseFloat(editBalance)
    if (!isNaN(bal)) {
      update.known_balance = bal
      update.reset_spending = true
    }
    if (editNotes) update.notes = editNotes
    if (editCurrency) update.currency = editCurrency
    if (editApiKey.trim()) update.api_key = editApiKey.trim()
    await api.updateProvider(editingProvider, update)
    setEditingProvider(null)
    setEditApiKey('')
    onRefresh()
    loadProviders()
  }

  const handleAddProvider = async () => {
    if (!newProvider.provider) return
    const data: any = {
      provider: newProvider.provider,
      tier: newProvider.tier,
      currency: newProvider.currency,
    }
    if (newProvider.api_key) data.api_key = newProvider.api_key
    if (newProvider.known_balance) data.known_balance = parseFloat(newProvider.known_balance)
    if (newProvider.notes) data.notes = newProvider.notes
    await api.addProvider(data)
    setShowAddForm(false)
    setNewProvider({ provider: '', api_key: '', known_balance: '', tier: 'unknown', currency: 'USD', notes: '' })
    onRefresh()
    loadProviders()
  }

  if (!budget) return <p className="text-gray-500">Loading budget data...</p>

  // Separate monetary from non-monetary for the summary
  const monetaryProviders = providers.filter(p => isMonetary(p.currency || 'USD'))
  const nonMonetaryProviders = providers.filter(p => !isMonetary(p.currency || 'USD'))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Budget & Resources</h2>
        <button onClick={() => { onRefresh(); loadProviders() }} className="text-gray-400 hover:text-gray-200 transition-colors">
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Overall summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Total Available (USD)</p>
          <p className="text-3xl font-bold text-green-400 mt-2">${budget.remaining.toFixed(2)}</p>
          <p className="text-xs text-gray-600 mt-1">across paid providers</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Total Spent (USD)</p>
          <p className="text-3xl font-bold text-red-400 mt-2">${budget.spent.toFixed(2)}</p>
          <p className="text-xs text-gray-600 mt-1">this month</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Providers</p>
          <p className="text-3xl font-bold text-blue-400 mt-2">{providers.length}</p>
          <p className="text-xs text-gray-600 mt-1">{providers.filter(p => p.tier === 'paid').length} paid, {providers.filter(p => p.tier === 'free').length} free</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Usage (USD)</p>
          <p className={`text-3xl font-bold mt-2 ${budget.percent_used > 80 ? 'text-red-400' : budget.percent_used > 50 ? 'text-yellow-400' : 'text-green-400'}`}>
            {budget.percent_used.toFixed(1)}%
          </p>
          <div className="mt-2 w-full bg-gray-800 rounded-full h-1.5">
            <div
              className={`h-1.5 rounded-full ${budget.percent_used > 80 ? 'bg-red-500' : budget.percent_used > 50 ? 'bg-yellow-500' : 'bg-green-500'}`}
              style={{ width: `${Math.min(100, budget.percent_used)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Non-monetary provider summaries (credits, requests, etc.) */}
      {nonMonetaryProviders.filter(p => p.known_balance != null).length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h4 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Non-USD Resources</h4>
          <div className="flex gap-4 flex-wrap">
            {nonMonetaryProviders.filter(p => p.known_balance != null).map(p => (
              <div key={p.provider} className="flex items-center gap-2">
                <span>{PROVIDER_ICONS[p.provider] || '🔌'}</span>
                <span className="text-sm text-gray-300 capitalize">{p.provider}:</span>
                <span className="text-sm font-bold text-green-400">
                  {fmtBalance(p.estimated_remaining, p.currency)}
                </span>
                <span className="text-xs text-gray-500">/ {fmtBalance(p.known_balance, p.currency)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per-provider cards */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-gray-400">Provider Balances</h3>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="flex items-center gap-1 text-xs text-jarvis-400 hover:text-jarvis-300 transition-colors"
          >
            <Plus size={14} /> Add Provider
          </button>
        </div>

        {/* Add provider form */}
        {showAddForm && (
          <div className="bg-gray-900 border border-jarvis-800 rounded-lg p-4 mb-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <input
                value={newProvider.provider}
                onChange={e => setNewProvider({ ...newProvider, provider: e.target.value })}
                placeholder="Provider name (e.g. groq)"
                className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-jarvis-500"
              />
              <input
                value={newProvider.api_key}
                onChange={e => setNewProvider({ ...newProvider, api_key: e.target.value })}
                placeholder="API key (optional)"
                type="password"
                className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-jarvis-500"
              />
              <input
                value={newProvider.known_balance}
                onChange={e => setNewProvider({ ...newProvider, known_balance: e.target.value })}
                placeholder="Balance"
                type="number"
                className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-jarvis-500"
              />
              <select
                value={newProvider.currency}
                onChange={e => setNewProvider({ ...newProvider, currency: e.target.value })}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-jarvis-500"
              >
                {COMMON_CURRENCIES.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <select
                value={newProvider.tier}
                onChange={e => setNewProvider({ ...newProvider, tier: e.target.value })}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-jarvis-500"
              >
                <option value="paid">Paid</option>
                <option value="free">Free Tier</option>
                <option value="unknown">Unknown</option>
              </select>
            </div>
            <input
              value={newProvider.notes}
              onChange={e => setNewProvider({ ...newProvider, notes: e.target.value })}
              placeholder="Notes (optional)"
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-jarvis-500"
            />
            <div className="flex gap-2">
              <button onClick={handleAddProvider} className="px-3 py-1.5 bg-jarvis-700 text-white rounded text-sm hover:bg-jarvis-600">
                Add
              </button>
              <button onClick={() => setShowAddForm(false)} className="px-3 py-1.5 bg-gray-800 text-gray-400 rounded text-sm hover:bg-gray-700">
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {providers.map((p) => (
            <ProviderCard
              key={p.provider}
              provider={p}
              isEditing={editingProvider === p.provider}
              editBalance={editBalance}
              editNotes={editNotes}
              editCurrency={editCurrency}
              editApiKey={editApiKey}
              onEditBalance={setEditBalance}
              onEditNotes={setEditNotes}
              onEditCurrency={setEditCurrency}
              onEditApiKey={setEditApiKey}
              onStartEdit={() => startEdit(p)}
              onSave={saveEdit}
              onCancel={() => setEditingProvider(null)}
            />
          ))}
        </div>
      </div>

      {/* Monthly cap override */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <h3 className="text-sm font-medium text-gray-400 mb-3">Override Monthly Cap</h3>
        <div className="flex gap-3">
          <input
            type="number"
            value={newCap}
            onChange={(e) => setNewCap(e.target.value)}
            placeholder="New cap (USD)"
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-jarvis-500"
          />
          <button
            onClick={handleOverride}
            className="px-4 py-2 bg-jarvis-700 text-white rounded text-sm hover:bg-jarvis-600 transition-colors"
          >
            Update Cap
          </button>
        </div>
      </div>
    </div>
  )
}

function ProviderCard({
  provider: p,
  isEditing,
  editBalance,
  editNotes,
  editCurrency,
  editApiKey,
  onEditBalance,
  onEditNotes,
  onEditCurrency,
  onEditApiKey,
  onStartEdit,
  onSave,
  onCancel,
}: {
  provider: ProviderStatus
  isEditing: boolean
  editBalance: string
  editNotes: string
  editCurrency: string
  editApiKey: string
  onEditBalance: (v: string) => void
  onEditNotes: (v: string) => void
  onEditCurrency: (v: string) => void
  onEditApiKey: (v: string) => void
  onStartEdit: () => void
  onSave: () => void
  onCancel: () => void
}) {
  const [showApiKey, setShowApiKey] = useState(false)
  const icon = PROVIDER_ICONS[p.provider] || '🔌'
  const tierColor = TIER_COLORS[p.tier] || 'gray'
  const currency = p.currency || 'USD'
  const hasBalance = p.known_balance != null
  const remaining = p.estimated_remaining
  const monetary = isMonetary(currency)

  // Compute usage percentage for the bar
  let usagePct = 0
  if (hasBalance && p.known_balance! > 0) {
    usagePct = Math.min(100, (p.spent_tracked / p.known_balance!) * 100)
  }

  return (
    <div className={`bg-gray-900 border rounded-lg p-4 ${isEditing ? 'border-jarvis-500' : 'border-gray-800'}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <h4 className="font-medium text-gray-200 capitalize">{p.provider}</h4>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded bg-${tierColor}-500/20 text-${tierColor}-400 uppercase`}>
            {p.tier}
          </span>
          {!monetary && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400 uppercase">
              {currency}
            </span>
          )}
          {!isEditing && (
            <button onClick={onStartEdit} className="text-gray-500 hover:text-gray-300">
              <Edit2 size={12} />
            </button>
          )}
        </div>
      </div>

      {isEditing ? (
        <div className="space-y-2 mt-2">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] text-gray-500 uppercase">Balance</label>
              <input
                type="number"
                value={editBalance}
                onChange={e => onEditBalance(e.target.value)}
                placeholder="Current balance"
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-jarvis-500"
              />
            </div>
            <div>
              <label className="text-[10px] text-gray-500 uppercase">Currency</label>
              <select
                value={editCurrency}
                onChange={e => onEditCurrency(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-jarvis-500"
              >
                {COMMON_CURRENCIES.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="text-[10px] text-gray-500 uppercase flex items-center gap-1">
              <Key size={10} /> API Key
            </label>
            <div className="relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                value={editApiKey}
                onChange={e => onEditApiKey(e.target.value)}
                placeholder="Enter new key to update (leave blank to keep current)"
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 pr-8 text-sm focus:outline-none focus:border-jarvis-500"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
              >
                {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>
          <div>
            <label className="text-[10px] text-gray-500 uppercase">Notes</label>
            <input
              value={editNotes}
              onChange={e => onEditNotes(e.target.value)}
              placeholder="Notes"
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm focus:outline-none focus:border-jarvis-500"
            />
          </div>
          <div className="flex gap-2">
            <button onClick={onSave} className="flex items-center gap-1 px-2 py-1 bg-green-800/50 text-green-400 rounded text-xs hover:bg-green-700/50">
              <Check size={12} /> Save
            </button>
            <button onClick={onCancel} className="flex items-center gap-1 px-2 py-1 bg-gray-800 text-gray-400 rounded text-xs hover:bg-gray-700">
              <X size={12} /> Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          {hasBalance ? (
            <div className="space-y-1.5">
              <div className="flex justify-between items-baseline">
                <span className="text-2xl font-bold text-green-400">{fmtBalance(remaining, currency)}</span>
                <span className="text-xs text-gray-500">of {fmtBalance(p.known_balance, currency)}</span>
              </div>
              <div className="w-full bg-gray-800 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full ${usagePct > 80 ? 'bg-red-500' : usagePct > 50 ? 'bg-yellow-500' : 'bg-green-500'}`}
                  style={{ width: `${usagePct}%` }}
                />
              </div>
              <p className="text-[11px] text-gray-500">
                {fmtSpent(p.spent_tracked, currency)}
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              <p className="text-sm text-gray-400">Balance unknown</p>
              <p className="text-[11px] text-gray-500">
                {fmtSpent(p.spent_tracked, currency)}
              </p>
            </div>
          )}
          {p.notes && (
            <p className="text-[11px] text-gray-600 mt-2">{p.notes}</p>
          )}
          {p.balance_updated_at && (
            <p className="text-[10px] text-gray-700 mt-1">
              Updated: {new Date(p.balance_updated_at).toLocaleDateString()}
            </p>
          )}
        </>
      )}
    </div>
  )
}
