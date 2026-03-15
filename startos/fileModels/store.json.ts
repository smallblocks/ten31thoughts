import { sdk } from '../sdk'

const { z } = sdk

const shape = z.object({
  provider: z.enum(['anthropic', 'openai', 'ollama']).catch('anthropic'),
  anthropicApiKey: z.string().catch(''),
  openaiApiKey: z.string().catch(''),
  ollamaBaseUrl: z.string().catch('http://localhost:11434'),
  analysisModel: z.string().catch('claude-sonnet-4-20250514'),
  synthesisModel: z.string().catch('claude-sonnet-4-20250514'),
  chatModel: z.string().catch('claude-sonnet-4-20250514'),
  embeddingModel: z.string().catch('text-embedding-3-small'),
})

export const storeJson = sdk.FileModel.of({
  volumeId: 'main',
  path: 'store.json',
  format: 'json',
  shape,
})
