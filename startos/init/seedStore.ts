import { sdk } from '../sdk'
import { i18n } from '../i18n'
import { storeJson } from '../fileModels/store.json'
import { configureLlm } from '../actions/configureLlm'

export const seedStore = sdk.setupOnInit(async (effects, kind) => {
  if (kind !== 'install') return

  // Seed the store with defaults on fresh install
  await storeJson.write(effects, {
    provider: 'anthropic',
    anthropicApiKey: '',
    openaiApiKey: '',
    ollamaBaseUrl: 'http://localhost:11434',
    analysisModel: 'claude-sonnet-4-20250514',
    synthesisModel: 'claude-sonnet-4-20250514',
    chatModel: 'claude-sonnet-4-20250514',
    embeddingModel: 'text-embedding-3-small',
  })

  // Create a task prompting the user to configure their LLM
  await sdk.action.createOwnTask(effects, configureLlm, 'critical', {
    reason: i18n('Configure your LLM provider and API key to enable AI features'),
  })
})
