import { sdk } from '../sdk'
import { storeJson } from '../fileModels/store.json'
import { configureLlm } from '../actions/configureLlm'
import { i18n } from '../i18n'

export const taskConfigureLlm = sdk.setupOnInit(async (effects, kind) => {
  // Only create task on fresh install
  if (kind !== 'install') return

  const store = await storeJson.read((s) => s).once()
  const hasApiKey = !!(store?.anthropicApiKey || store?.openaiApiKey)

  if (!hasApiKey) {
    await sdk.action.createOwnTask(effects, configureLlm, 'critical', {
      reason: i18n('Configure your LLM provider and API key to enable AI features'),
    })
  }
})
