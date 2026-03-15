export const DEFAULT_LANG = 'en_US'

const dict = {
  'Starting Ten31 Thoughts!': 0,
  'Web Interface': 1,
  'Ten31 Thoughts is ready': 2,
  'Ten31 Thoughts is not responding': 3,
  'Web UI': 4,
  'The Ten31 Thoughts web interface': 5,
} as const

export type I18nKey = keyof typeof dict
export type LangDict = Record<(typeof dict)[I18nKey], string>
export default dict
