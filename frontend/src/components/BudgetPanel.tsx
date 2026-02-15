import { useState } from 'react'
import { api } from '../api/client'
import type { BudgetStatus } from '../types'

interface Props {
  budget: BudgetStatus | null
  onRefresh: () => void
}

export function BudgetPanel({ budget, onRefresh }: Props) {
  const [newCap, setNewCap] = useState('')

  const handleOverride = async () => {
    const val = parseFloat(newCap)
    if (isNaN(val) || val <= 0) return
    await api.overrideBudget(val)
    setNewCap('')
    onRefresh()
  }

  if (!budget) return <p className="text-gray-500">Loading budget data...</p>

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">Budget Management</h2>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Monthly Cap</p>
          <p className="text-3xl font-bold text-gray-200 mt-2">${budget.monthly_cap.toFixed(2)}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Spent</p>
          <p className="text-3xl font-bold text-red-400 mt-2">${budget.spent.toFixed(2)}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Remaining</p>
          <p className="text-3xl font-bold text-green-400 mt-2">${budget.remaining.toFixed(2)}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Used</p>
          <p className={`text-3xl font-bold mt-2 ${budget.percent_used > 80 ? 'text-red-400' : budget.percent_used > 50 ? 'text-yellow-400' : 'text-green-400'}`}>
            {budget.percent_used.toFixed(1)}%
          </p>
        </div>
      </div>

      <div className="w-full bg-gray-800 rounded-full h-4">
        <div
          className={`h-4 rounded-full transition-all ${budget.percent_used > 80 ? 'bg-red-500' : budget.percent_used > 50 ? 'bg-yellow-500' : 'bg-green-500'}`}
          style={{ width: `${Math.min(100, budget.percent_used)}%` }}
        />
      </div>

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
