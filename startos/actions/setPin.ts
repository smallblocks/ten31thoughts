import { createHash } from 'crypto'
import { sdk } from '../sdk'
import { i18n } from '../i18n'
import { storeJson } from '../fileModels/store.json'

const { InputSpec, Value } = sdk

const inputSpec = InputSpec.of({
  pin: Value.text({
    name: i18n('PIN'),
    description: i18n(
      'Set a numeric PIN to protect the web interface. Leave blank to remove the PIN and disable auth.',
    ),
    required: false,
    default: null,
    placeholder: '1234',
    masked: true,
  }),
})

export const setPin = sdk.Action.withInput(
  'set-pin',

  async ({ effects }) => ({
    name: i18n('Set PIN'),
    description: i18n(
      'Set or clear the PIN for web interface authentication. Auth is dormant until a PIN is set.',
    ),
    warning: null,
    allowedStatuses: 'any',
    group: null,
    visibility: 'enabled',
  }),

  inputSpec,

  // Pre-fill: empty (never show existing PIN)
  async ({ effects }) => ({
    pin: null,
  }),

  // Save handler
  async ({ effects, input }) => {
    const pin = (input.pin || '').trim()
    const store = await storeJson.read((s) => s).once()
    // Ensure all required fields have values for the write call
    const s = store || {} as Partial<Record<string, string>>
    const base = {
      provider: (s as any).provider ?? ('anthropic' as const),
      anthropicApiKey: (s as any).anthropicApiKey ?? '',
      openaiApiKey: (s as any).openaiApiKey ?? '',
      openaiBaseUrl: (s as any).openaiBaseUrl ?? '',
      ollamaBaseUrl: (s as any).ollamaBaseUrl ?? 'http://localhost:11434',
      vllmBaseUrl: (s as any).vllmBaseUrl ?? '',
      analysisModel: (s as any).analysisModel ?? 'claude-sonnet-4-20250514',
      synthesisModel: (s as any).synthesisModel ?? 'claude-sonnet-4-20250514',
      chatModel: (s as any).chatModel ?? 'claude-sonnet-4-20250514',
      embeddingModel: (s as any).embeddingModel ?? 'text-embedding-3-small',
      whisperUrl: (s as any).whisperUrl ?? '',
      whisperApi: (s as any).whisperApi ?? ('openai' as const),
      whisperModel: (s as any).whisperModel ?? 'whisper-large-v3',
      pinHash: (s as any).pinHash ?? '',
    }

    if (pin) {
      // Hash with SHA-256 (matches Python backend)
      const pinHash = createHash('sha256').update(pin, 'utf-8').digest('hex')
      await storeJson.write(effects, { ...base, pinHash })
      return {
        version: '1' as const,
        title: i18n('PIN Set'),
        message: i18n(
          'PIN has been set. The web interface now requires authentication. Existing sessions have been invalidated — you will need to log in again.',
        ),
        result: null,
      }
    } else {
      // Clear PIN — disable auth
      await storeJson.write(effects, { ...base, pinHash: '' })
      return {
        version: '1' as const,
        title: i18n('PIN Cleared'),
        message: i18n(
          'PIN has been removed. The web interface is now open (no authentication required).',
        ),
        result: null,
      }
    }
  },
)
