import { setupI18n } from '@start9labs/start-sdk'

export const { i18n, t } = setupI18n<string>({
  en_US: (key: string) => key,
})
