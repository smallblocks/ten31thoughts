
import { setupManifest } from '@start9labs/start-sdk'
import { short, long } from './i18n'

export const manifest = setupManifest({
  id: 'tenthoughts',
  title: 'Ten31 Thoughts',
  license: 'MIT',
  packageRepo: 'https://github.com/smallblocks/ten31thoughts',
  upstreamRepo: 'https://github.com/smallblocks/ten31thoughts',
  marketingUrl: 'https://ten31timestamp.com',
  donationUrl: null,
  docsUrls: ['https://ten31.xyz'],
  description: { short, long },
  volumes: ['main'],
  images: {
    main: {
      source: {
        dockerTag: 'ghcr.io/smallblocks/tenthoughts:latest',
      },
      arch: ['x86_64', 'aarch64'],
    },
  },
  alerts: {
    install: null,
    update: null,
    uninstall: null,
    restore: null,
    start: null,
    stop: null,
  },
  dependencies: {},
})
