import { i18n } from './i18n'
import { sdk } from './sdk'
import { uiPort } from './utils'
import { storeJson } from './fileModels/store.json'

export const main = sdk.setupMain(async ({ effects }) => {
  console.info(i18n('Starting Ten31 Thoughts!'))

  // Read LLM config from store — reactive: restarts daemon if config changes
  const store = await storeJson.read((s) => s).const(effects)

  // Build env vars from stored config
  const llmEnv: Record<string, string> = {
    PYTHONUNBUFFERED: '1',
    PYTHONPATH: '/app',
    DATABASE_URL: 'sqlite:////data/ten31thoughts.db',
    CHROMADB_PERSIST_DIR: '/data/chromadb',
  }

  // Set API keys based on provider
  console.log('DEBUG store:', JSON.stringify(store))
  console.log('DEBUG anthropicApiKey exists:', !!store?.anthropicApiKey)
  if (store?.anthropicApiKey) {
    llmEnv.ANTHROPIC_API_KEY = store.anthropicApiKey
    console.log('DEBUG added ANTHROPIC_API_KEY to env')
  }
  if (store?.openaiApiKey) {
    llmEnv.OPENAI_API_KEY = store.openaiApiKey
  }
  if (store?.ollamaBaseUrl) {
    llmEnv.OLLAMA_BASE_URL = store.ollamaBaseUrl
  }

  // Set model preferences
  if (store?.analysisModel) {
    llmEnv.TEN31_LLM_ANALYSIS_MODEL = store.analysisModel
  }
  if (store?.synthesisModel) {
    llmEnv.TEN31_LLM_SYNTHESIS_MODEL = store.synthesisModel
  }
  if (store?.chatModel) {
    llmEnv.TEN31_LLM_CHAT_MODEL = store.chatModel
  }
  if (store?.embeddingModel) {
    llmEnv.TEN31_LLM_EMBEDDING_MODEL = store.embeddingModel
  }

  console.log('DEBUG final llmEnv:', JSON.stringify(llmEnv))

  // Create subcontainer from the main image with the data volume mounted
  const subcontainer = await sdk.SubContainer.of(
    effects,
    { imageId: 'main' },
    sdk.Mounts.of().mountVolume({
      volumeId: 'main',
      subpath: null,
      mountpoint: '/data',
      readonly: false,
    }),
    'tenthoughts',
  )

  return sdk.Daemons.of(effects).addDaemon('primary', {
    subcontainer,
    exec: {
      command: [
        'uvicorn',
        'src.app:app',
        '--host',
        '0.0.0.0',
        '--port',
        String(uiPort),
        '--workers',
        '1',
      ],
      env: llmEnv,
    },
    ready: {
      display: i18n('Web Interface'),
      fn: () =>
        sdk.healthCheck.checkPortListening(effects, uiPort, {
          successMessage: i18n('Ten31 Thoughts is ready'),
          errorMessage: i18n('Ten31 Thoughts is not responding'),
        }),
    },
    requires: [],
  })
})
