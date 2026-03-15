import { VersionInfo, IMPOSSIBLE } from '@start9labs/start-sdk'

export const v0_3_0_1_a0 = VersionInfo.of({
  version: '0.3.0:1-alpha.0',
  releaseNotes: {
    en_US:
      'Initial release of Ten31 Thoughts macro intelligence service for StartOS.',
  },
  migrations: {
    up: async ({ effects }) => {},
    down: IMPOSSIBLE,
  },
})
