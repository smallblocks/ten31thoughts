import { sdk } from './sdk'

export const createBackup = sdk.setupBackups(() => ({
  // Volume 'main' is backed up automatically
}))
