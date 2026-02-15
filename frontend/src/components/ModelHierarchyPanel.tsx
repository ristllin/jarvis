import { useState, useEffect } from 'react'
import { api } from '../api/client'
import type { ModelTier } from '../types'

export function ModelHierarchyPanel() {
  const [tiers, setTiers] = useState<Record<string, ModelTier[]>>({})
  const [providers, setProviders] = useState<string[]>([])

  useEffect(() => {
    api.getModels().then((data) => {
      setTiers(data.tiers || {})
      setProviders(data.available_providers || [])
    })
  }, [])

  const tierLabels: Record<string, string> = {
    level1: 'Level 1 — High Intelligence (Planning)',
    level2: 'Level 2 — Task Execution',
    level3: 'Level 3 — Lightweight / Fallback',
    local_only: 'Local Only — Budget Exhausted Fallback',
  }

  const costColors: Record<string, string> = {
    high: 'text-red-400',
    medium: 'text-yellow-400',
    low: 'text-green-400',
    free: 'text-cyan-400',
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">LLM Model Hierarchy</h2>
      <p className="text-sm text-gray-400">
        Active providers: {providers.length > 0 ? providers.join(', ') : 'None'}
      </p>

      <div className="space-y-4">
        {Object.entries(tiers).map(([tier, models]) => (
          <div key={tier} className="bg-gray-900 border border-gray-800 rounded-lg p-5">
            <h3 className="font-medium text-gray-200 mb-3">{tierLabels[tier] || tier}</h3>
            <div className="space-y-2">
              {models.map((m, i) => (
                <div key={i} className="flex items-center justify-between text-sm bg-gray-800 rounded px-3 py-2">
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${m.available ? 'bg-green-500' : 'bg-gray-600'}`} />
                    <span className="font-mono text-gray-300">{m.model}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-gray-500">{m.provider}</span>
                    <span className={`text-xs font-medium uppercase ${costColors[m.cost] || 'text-gray-500'}`}>
                      {m.cost}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
