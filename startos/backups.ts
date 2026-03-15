import { sdk } from './sdk'

export const { backups, restoreInit } = sdk.setupBackups({
  // Back up the main data volume (SQLite DB, ChromaDB, briefings)
  volumes: ['main'],
})
