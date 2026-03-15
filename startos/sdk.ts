import { StartSdk } from '@start9labs/start-sdk'
import { manifest } from './manifest'

// SDK initialized with package-specific type info from the manifest.
// Use this `sdk` throughout the startos/ directory.
export const sdk = StartSdk.of(manifest)
