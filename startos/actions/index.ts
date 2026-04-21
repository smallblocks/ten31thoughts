import { sdk } from '../sdk'
import { configureLlm } from './configureLlm'
import { setPin } from './setPin'

export const actions = sdk.Actions.of().addAction(configureLlm).addAction(setPin)
