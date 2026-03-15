import { sdk } from './sdk'

export const main = sdk.setupMain(async ({ effects }) => {
  console.info('Starting Ten31 Thoughts...')

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
      command: ['/usr/local/bin/uvicorn'],
      args: ['src.app:app', '--host', '0.0.0.0', '--port', '8431', '--workers', '1'],
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONPATH: '/app',
        DATABASE_URL: 'sqlite:////data/ten31thoughts.db',
        CHROMADB_PERSIST_DIR: '/data/chromadb',
      },
    },
    ready: {
      display: 'Web Interface',
      fn: () =>
        sdk.healthCheck.checkPortListening(effects, 8431, {
          successMessage: 'Ten31 Thoughts is ready',
          errorMessage: 'Ten31 Thoughts is not responding',
        }),
    },
    requires: [],
  })
})
