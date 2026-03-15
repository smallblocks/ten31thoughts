import { sdk } from './sdk'

export const interfaces = sdk.setupInterfaces(builder =>
  builder.addUi({
    id: 'main',
    hasPrimary: true,
    username: null,
    path: '/',
    search: {},
  })
)
