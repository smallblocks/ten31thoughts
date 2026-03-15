import { VersionInfo } from '@start9labs/start-sdk'

export const v_0_3_0_1 = VersionInfo.of({
  version: '0.3.0:1',
  releaseNotes: {
    en_US: 'Initial release of Ten31 Thoughts macro intelligence service.',
  },
  migrations: {
    up: async ({ effects }) => {},
    down: async ({ effects }) => {},
  },
})
