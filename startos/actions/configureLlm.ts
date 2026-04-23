import { sdk } from '../sdk'
import { i18n } from '../i18n'
import { storeJson } from '../fileModels/store.json'

const { InputSpec, Value } = sdk

const inputSpec = InputSpec.of({
  provider: Value.select({
    name: i18n('LLM Provider'),
    description: i18n('Which LLM provider to use for analysis, synthesis, and chat'),
    default: 'anthropic',
    values: {
      anthropic: i18n('Anthropic (Claude)'),
      openai: i18n('OpenAI (GPT)'),
      ollama: i18n('Ollama (Local)'),
      vllm: i18n('vLLM (DGX Spark)'),
    },
  }),
  anthropicApiKey: Value.text({
    name: i18n('Anthropic API Key'),
    description: i18n('Your Anthropic API key (starts with sk-ant-). Required if using Anthropic.'),
    required: false,
    default: null,
    placeholder: 'sk-ant-...',
    masked: true,
  }),
  openaiApiKey: Value.text({
    name: i18n('OpenAI API Key'),
    description: i18n('Your OpenAI API key (starts with sk-). Required if using OpenAI.'),
    required: false,
    default: null,
    placeholder: 'sk-...',
    masked: true,
  }),
  openaiBaseUrl: Value.text({
    name: i18n('OpenAI Base URL'),
    description: i18n('Custom base URL for OpenAI-compatible APIs. Leave blank for default OpenAI API.'),
    required: false,
    default: '',
    placeholder: 'https://api.openai.com/v1',
    masked: false,
  }),
  ollamaBaseUrl: Value.text({
    name: i18n('Ollama Base URL'),
    description: i18n('URL of your Ollama instance. Only needed if using Ollama.'),
    required: false,
    default: 'http://localhost:11434',
    placeholder: 'http://localhost:11434',
    masked: false,
  }),
  vllmBaseUrl: Value.text({
    name: i18n('vLLM Base URL'),
    description: i18n('URL of your vLLM instance on DGX Spark (e.g. http://192.168.86.52:8000/v1). Required if using vLLM.'),
    required: false,
    default: '',
    placeholder: 'http://192.168.86.52:8000/v1',
    masked: false,
  }),
  analysisModel: Value.text({
    name: i18n('Analysis Model'),
    description: i18n('Model for content analysis (e.g. claude-sonnet-4-20250514, gpt-4o)'),
    required: false,
    default: 'claude-sonnet-4-20250514',
    placeholder: 'claude-sonnet-4-20250514',
    masked: false,
  }),
  synthesisModel: Value.text({
    name: i18n('Synthesis Model'),
    description: i18n('Model for weekly synthesis (e.g. claude-sonnet-4-20250514, gpt-4o)'),
    required: false,
    default: 'claude-sonnet-4-20250514',
    placeholder: 'claude-sonnet-4-20250514',
    masked: false,
  }),
  chatModel: Value.text({
    name: i18n('Chat Model'),
    description: i18n('Model for chat responses (e.g. claude-sonnet-4-20250514, gpt-4o)'),
    required: false,
    default: 'claude-sonnet-4-20250514',
    placeholder: 'claude-sonnet-4-20250514',
    masked: false,
  }),
  embeddingModel: Value.text({
    name: i18n('Embedding Model'),
    description: i18n('Model for text embeddings (e.g. text-embedding-3-small)'),
    required: false,
    default: 'text-embedding-3-small',
    placeholder: 'text-embedding-3-small',
    masked: false,
  }),
  whisperUrl: Value.text({
    name: i18n('Whisper Server URL'),
    description: i18n('URL of your local Whisper server on DGX Spark (e.g. http://dgx-spark.local:8000). Leave blank to disable voice fallback.'),
    required: false,
    default: '',
    placeholder: 'http://dgx-spark.local:8000',
    masked: false,
  }),
  whisperApi: Value.select({
    name: i18n('Whisper Server Type'),
    description: i18n('Which Whisper server implementation is running on DGX Spark'),
    default: 'openai',
    values: {
      openai: i18n('faster-whisper-server (OpenAI-compatible)'),
      'whisper-cpp': i18n('whisper.cpp server'),
    },
  }),
  whisperModel: Value.text({
    name: i18n('Whisper Model'),
    description: i18n('Model name for transcription (e.g. whisper-large-v3)'),
    required: false,
    default: 'whisper-large-v3',
    placeholder: 'whisper-large-v3',
    masked: false,
  }),
})

export const configureLlm = sdk.Action.withInput(
  'configure-llm',

  async ({ effects }) => ({
    name: i18n('Configure LLM'),
    description: i18n('Set your LLM provider, API key, and model preferences'),
    warning: null,
    allowedStatuses: 'any',
    group: null,
    visibility: 'enabled',
  }),

  inputSpec,

  // Pre-fill form with current values
  async ({ effects }) => {
    const store = await storeJson.read((s) => s).once()
    return {
      provider: store?.provider ?? 'anthropic',
      anthropicApiKey: store?.anthropicApiKey ?? null,
      openaiApiKey: store?.openaiApiKey ?? null,
      openaiBaseUrl: store?.openaiBaseUrl ?? '',
      ollamaBaseUrl: store?.ollamaBaseUrl ?? 'http://localhost:11434',
      vllmBaseUrl: store?.vllmBaseUrl ?? '',
      analysisModel: store?.analysisModel ?? 'claude-sonnet-4-20250514',
      synthesisModel: store?.synthesisModel ?? 'claude-sonnet-4-20250514',
      chatModel: store?.chatModel ?? 'claude-sonnet-4-20250514',
      embeddingModel: store?.embeddingModel ?? 'text-embedding-3-small',
      whisperUrl: store?.whisperUrl ?? '',
      whisperApi: store?.whisperApi ?? 'openai',
      whisperModel: store?.whisperModel ?? 'whisper-large-v3',
    }
  },

  // Save handler
  async ({ effects, input }) => {
    const existing = await storeJson.read((s) => s).once()
    await storeJson.write(effects, {
      pinHash: (existing as any)?.pinHash ?? '',
      provider: input.provider as 'anthropic' | 'openai' | 'ollama' | 'vllm',
      anthropicApiKey: input.anthropicApiKey || '',
      openaiApiKey: input.openaiApiKey || '',
      openaiBaseUrl: input.openaiBaseUrl || '',
      ollamaBaseUrl: input.ollamaBaseUrl || 'http://localhost:11434',
      vllmBaseUrl: input.vllmBaseUrl || '',
      analysisModel: input.analysisModel || 'claude-sonnet-4-20250514',
      synthesisModel: input.synthesisModel || 'claude-sonnet-4-20250514',
      chatModel: input.chatModel || 'claude-sonnet-4-20250514',
      embeddingModel: input.embeddingModel || 'text-embedding-3-small',
      whisperUrl: input.whisperUrl || '',
      whisperApi: input.whisperApi as 'openai' | 'whisper-cpp',
      whisperModel: input.whisperModel || 'whisper-large-v3',
    })

    return {
      version: '1' as const,
      title: i18n('LLM Configured'),
      message: i18n('LLM settings saved. Restart the service for changes to take effect.'),
      result: null,
    }
  },
)
