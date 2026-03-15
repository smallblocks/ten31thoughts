export const DEFAULT_LANG = 'en_US'

const dict = {
  // main.ts
  'Starting Ten31 Thoughts!': 0,
  'Web Interface': 1,
  'Ten31 Thoughts is ready': 2,
  'Ten31 Thoughts is not responding': 3,

  // interfaces.ts
  'Web UI': 4,
  'The Ten31 Thoughts web interface': 5,

  // actions/configureLlm.ts
  'LLM Provider': 6,
  'Which LLM provider to use for analysis, synthesis, and chat': 7,
  'Anthropic (Claude)': 8,
  'OpenAI (GPT)': 9,
  'Ollama (Local)': 10,
  'Anthropic API Key': 11,
  'Your Anthropic API key (starts with sk-ant-). Required if using Anthropic.': 12,
  'OpenAI API Key': 13,
  'Your OpenAI API key (starts with sk-). Required if using OpenAI.': 14,
  'Ollama Base URL': 15,
  'URL of your Ollama instance. Only needed if using Ollama.': 16,
  'Analysis Model': 17,
  'Model for content analysis (e.g. claude-sonnet-4-20250514, gpt-4o)': 18,
  'Synthesis Model': 19,
  'Model for weekly synthesis (e.g. claude-sonnet-4-20250514, gpt-4o)': 20,
  'Chat Model': 21,
  'Model for chat responses (e.g. claude-sonnet-4-20250514, gpt-4o)': 22,
  'Embedding Model': 23,
  'Model for text embeddings (e.g. text-embedding-3-small)': 24,
  'Configure LLM': 25,
  'Set your LLM provider, API key, and model preferences': 26,
  'LLM Configured': 27,
  'LLM settings saved. Restart the service for changes to take effect.': 28,

  // init/taskConfigureLlm.ts
  'Configure your LLM provider and API key to enable AI features': 29,
} as const

export type I18nKey = keyof typeof dict
export type LangDict = Record<(typeof dict)[I18nKey], string>
export default dict
