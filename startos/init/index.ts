import { sdk } from '../sdk'

export const init = sdk.setupInit(async () => {
  // Nothing special needed - directories are created by Docker
})

export const uninit = sdk.setupUninit(async () => {
  // Cleanup if needed
})
