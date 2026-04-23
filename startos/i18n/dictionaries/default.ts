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
  'vLLM (DGX Spark)': 46,
  'Anthropic API Key': 11,
  'Your Anthropic API key (starts with sk-ant-). Required if using Anthropic.': 12,
  'OpenAI API Key': 13,
  'Your OpenAI API key (starts with sk-). Required if using OpenAI.': 14,
  'OpenAI Base URL': 47,
  'Custom base URL for OpenAI-compatible APIs. Leave blank for default OpenAI API.': 48,
  'Ollama Base URL': 15,
  'URL of your Ollama instance. Only needed if using Ollama.': 16,
  'vLLM Base URL': 49,
  'URL of your vLLM instance on DGX Spark (e.g. http://192.168.86.52:8000/v1). Required if using vLLM.': 50,
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

  // actions/configureLlm.ts — Whisper fields
  'Whisper Server URL': 30,
  'URL of your local Whisper server on DGX Spark (e.g. http://dgx-spark.local:8000). Leave blank to disable voice fallback.': 31,
  'Whisper Server Type': 32,
  'Which Whisper server implementation is running on DGX Spark': 33,
  'faster-whisper-server (OpenAI-compatible)': 34,
  'whisper.cpp server': 35,
  'Whisper Model': 36,
  'Model name for transcription (e.g. whisper-large-v3)': 37,

  // actions/setPin.ts
  'PIN': 38,
  'Set a numeric PIN to protect the web interface. Leave blank to remove the PIN and disable auth.': 39,
  'Set PIN': 40,
  'Set or clear the PIN for web interface authentication. Auth is dormant until a PIN is set.': 41,
  'PIN Set': 42,
  'PIN has been set. The web interface now requires authentication. Existing sessions have been invalidated — you will need to log in again.': 43,
  'PIN Cleared': 44,
  'PIN has been removed. The web interface is now open (no authentication required).': 45,
} as const

export type I18nKey = keyof typeof dict
export type LangDict = Record<(typeof dict)[I18nKey], string>
export default dict
