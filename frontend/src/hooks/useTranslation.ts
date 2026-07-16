import { useEffect, useMemo, useState } from 'react';
import { useTheme } from '../context/ThemeContext';
import { translate } from '../utils/translations';
import { loadLocale } from '../i18n/translationLoader';
import { trackTranslationFallbackHit } from '../i18n/fallbackTelemetry';
import { useAutoTranslate } from './useAutoTranslate';

export const useTranslation = () => {
  const { language, languageCode } = useTheme();
  const resolvedLanguage = languageCode || language;
  const [, setReadyTick] = useState(0);
  const { tt } = useAutoTranslate();

  const isBackgroundOnlyI18nMode = () => {
    if (typeof window === 'undefined') return false;
    return Boolean((window as any).__racI18nBackgroundOnly);
  };

  useEffect(() => {
    if (!resolvedLanguage || resolvedLanguage === 'en') return;
    loadLocale(resolvedLanguage)
      .then(() => setReadyTick((v) => v + 1))
      .catch(() => {});
  }, [resolvedLanguage]);


  const t = useMemo(() => {
    return (key: string) => {
      const source = translate('en', key);
      const localized = translate(resolvedLanguage, key);
      if (resolvedLanguage === 'en' || localized !== source || source === key) {
        return localized;
      }
      if (isBackgroundOnlyI18nMode()) {
        return source;
      }
      trackTranslationFallbackHit(resolvedLanguage, key);
      return tt(source);
    };
  }, [resolvedLanguage, tt]);

  const tx = useMemo(() => {
    return (key: string, fallback: string) => {
      const value = t(key);
      return value === key ? fallback : value;
    };
  }, [t]);

  return { t, tx, language };
};
