export type ModelOption = {
  value: string
  label: string
  description: string
  provider: 'claude' | 'codex'
}

export const MODEL_OPTIONS: ModelOption[] = [
  { value: 'claude:sonnet', label: 'Claude Sonnet', description: 'Balanced reasoning and coding', provider: 'claude' },
  { value: 'claude:opus', label: 'Claude Opus', description: 'Highest-end Claude capability', provider: 'claude' },
  { value: 'claude:haiku', label: 'Claude Haiku', description: 'Fast Claude execution', provider: 'claude' },
  { value: 'codex:gpt-5-codex', label: 'Codex GPT-5', description: 'OpenAI Codex coding agent', provider: 'codex' },
  { value: 'codex:gpt-5.3-codex', label: 'Codex GPT-5.3', description: 'Latest high-capability Codex model', provider: 'codex' },
]

export function getModelLabel(raw: string | null | undefined): string {
  if (!raw) return 'Unknown model'
  const exact = MODEL_OPTIONS.find((option) => option.value === raw)
  if (exact) return exact.label

  if (!raw.includes(':')) {
    const legacy = MODEL_OPTIONS.find((option) => option.value === `claude:${raw}`)
    if (legacy) return legacy.label
  }

  const [provider, model] = raw.includes(':') ? raw.split(':', 2) : ['claude', raw]
  if (provider === 'codex') return `Codex ${model}`
  if (provider === 'claude') return `Claude ${model}`
  return raw
}

export function getDefaultModel(): string {
  return MODEL_OPTIONS[0].value
}
