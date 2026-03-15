import { i18n } from './i18n'
import { sdk } from './sdk'
import { uiPort } from './utils'

export const main = sdk.setupMain(async ({ effects }) => {
  console.info(i18n('Starting Ten31 Thoughts!'))

  return sdk.Daemons.of(effects).addDaemon('primary', {
    subcontainer: await sdk.SubContainer.of(
      effects,
      { imageId: 'main' },
      sdk.Mounts.of().mountVolume({
        volumeId: 'main',
        subpath: null,
        mountpoint: '/data',
        readonly: false,
      }),
      'tenthoughts-main',
    ),
    exec: { 
      command: [
        '/usr/local/bin/uvicorn',
        'src.app:app',
        '--host', '0.0.0.0',
        '--port', String(uiPort),
        '--workers', '1',
      ],
    },
    ready: {
      display: i18n('Web Interface'),
      fn: () =>
        sdk.healthCheck.checkPortListening(effects, uiPort, {
          successMessage: i18n('Ten31 Thoughts is ready'),
          errorMessage: i18n('Ten31 Thoughts is not responding'),
        }),
    },
    requires: [],
  })
})
