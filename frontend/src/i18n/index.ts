import { createI18n } from 'vue-i18n';
import zhTW from './locales/zh-TW.json';
import en from './locales/en.json';
import ja from './locales/ja.json';

const savedLang = localStorage.getItem('lang');
const defaultLang = savedLang || 'zh-TW';

const i18n = createI18n({
  legacy: false,
  locale: defaultLang,
  fallbackLocale: 'en',
  messages: {
    'zh-TW': zhTW,
    'en': en,
    'ja': ja
  }
});

export default i18n;
