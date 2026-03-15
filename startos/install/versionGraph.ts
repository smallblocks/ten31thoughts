import { VersionGraph } from '@start9labs/start-sdk'
import { current, other } from './versions'

export const versionGraph = VersionGraph.of({
  current,
  other,
  preInstall: async ({ effects }) => {
    // No pre-install setup needed for Ten31 Thoughts.
    // The Dockerfile creates /data directories already.
  },
})
