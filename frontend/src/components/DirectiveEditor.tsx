import { useState, useEffect } from 'react'
import { api } from '../api/client'

interface Props {
  currentDirective: string
  onUpdate: () => void
}

export function DirectiveEditor({ currentDirective, onUpdate }: Props) {
  const [directive, setDirective] = useState(currentDirective)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setDirective(currentDirective)
  }, [currentDirective])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.updateDirective(directive)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      onUpdate()
    } catch {}
    setSaving(false)
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">Directive Editor</h2>
      <p className="text-sm text-gray-400">
        This is the modifiable directive that guides JARVIS's behavior. Immutable safety rules cannot be changed.
      </p>

      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <textarea
          value={directive}
          onChange={(e) => setDirective(e.target.value)}
          rows={8}
          className="w-full bg-gray-800 border border-gray-700 rounded p-4 text-sm text-gray-200 focus:outline-none focus:border-jarvis-500 resize-y"
          placeholder="Enter JARVIS's directive..."
        />
        <div className="flex items-center justify-between mt-4">
          <p className="text-xs text-gray-500">
            Changes take effect on the next loop iteration.
          </p>
          <div className="flex items-center gap-3">
            {saved && <span className="text-green-400 text-sm">Saved!</span>}
            <button
              onClick={handleSave}
              disabled={saving || directive === currentDirective}
              className="px-4 py-2 bg-jarvis-700 text-white rounded text-sm hover:bg-jarvis-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Saving...' : 'Update Directive'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
