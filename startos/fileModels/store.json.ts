import { FileHelper, z } from '@start9labs/start-sdk'
import { sdk } from '../sdk'

const shape = z.object({
  provider: z.enum(['anthropic', 'openai', 'ollama']).catch('anthropic'),
  anthropicApiKey: z.string().catch(''),
  openaiApiKey: z.string().catch(''),
  ollamaBaseUrl: z.string().catch('http://localhost:11434'),
  analysisModel: z.string().catch('claude-sonnet-4-20250514'),
  synthesisModel: z.string().catch('claude-sonnet-4-20250514'),
  chatModel: z.string().catch('claude-sonnet-4-20250514'),
  embeddingModel: z.string().catch('text-embedding-3-small'),
  whisperUrl: z.string().catch(''),
  whisperApi: z.enum(['openai', 'whisper-cpp']).catch('openai'),
  whisperModel: z.string().catch('whisper-large-v3'),
})

export const storeJson = FileHelper.json(
  { base: sdk.volumes.main, subpath: 'store.json' },
  shape,
)

export type StoreData = z.infer<typeof shape>
