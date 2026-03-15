import { setupManifest } from '@start9labs/start-sdk'

export const manifest = setupManifest({
  id: 'tenthoughts',
  title: 'Ten31 Thoughts',
  license: 'MIT',
  packageRepo: 'https://github.com/smallblocks/ten31thoughts',
  upstreamRepo: 'https://github.com/smallblocks/ten31thoughts',
  marketingUrl: 'https://ten31.xyz',
  donationUrl: null,
  docsUrls: ['https://github.com/smallblocks/ten31thoughts/blob/main/README.md'],
  description: {
    short: 'Macro intelligence service coordinating your thesis with external voices',
    long: 'Ten31 Thoughts ingests your published macro framework alongside external macro interviews to surface the top mental models for navigating the current macro landscape.',
  },
  volumes: ['main'],
  images: {
    main: {
      source: { dockerTag: 'start9/tenthoughts/main:0.3.0.1' },
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
