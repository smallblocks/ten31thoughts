import { sdk } from '../sdk'
import { configureLlm } from './configureLlm'

export const actions = sdk.Actions.of().add(configureLlm)
