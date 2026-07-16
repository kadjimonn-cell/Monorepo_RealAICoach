/**
 * Locale-aware date formatting utility.
 * Maps the app's language codes to BCP-47 locale strings
 * and provides helpers that respect the user's chosen language.
 */

import { LanguageCode } from './translations';

/** Map app language codes → BCP-47 locale tags used by Intl */
const LOCALE_MAP: Record<LanguageCode, string> = {
  en: 'en-US',
  es: 'es-ES',
  fr: 'fr-FR',
  de: 'de-DE',
  it: 'it-IT',
  pt: 'pt-BR',
  zh: 'zh-CN',
  ja: 'ja-JP',
  ko: 'ko-KR',
  hi: 'hi-IN',
  ar: 'ar-SA',
  ru: 'ru-RU',
  tr: 'tr-TR',
  nl: 'nl-NL',
  sv: 'sv-SE',
  pl: 'pl-PL',
  th: 'th-TH',
  vi: 'vi-VN',
  id: 'id-ID',
  ms: 'ms-MY',
  sw: 'sw-TZ',
  uk: 'uk-UA',
};

/** Resolve BCP-47 locale from app language code */
export function getLocale(langCode: LanguageCode | string): string {
  return LOCALE_MAP[langCode as LanguageCode] || 'en-US';
}

/** Format a date as a short date: "Jan 5, 2026" / locale equivalent */
export function formatDate(
  date: string | Date | number | null | undefined,
  langCode: LanguageCode | string,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!date) return '';
  try {
    const d = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date;
    if (isNaN(d.getTime())) return '';
    const locale = getLocale(langCode);
    const defaults: Intl.DateTimeFormatOptions = {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    };
    return d.toLocaleDateString(locale, options || defaults);
  } catch {
    return '';
  }
}

/** Format a date with full month: "January 5, 2026" */
export function formatDateLong(
  date: string | Date | number | null | undefined,
  langCode: LanguageCode | string
): string {
  return formatDate(date, langCode, { year: 'numeric', month: 'long', day: 'numeric' });
}

/** Format time only: "2:30 PM" / locale equivalent */
export function formatTime(
  date: string | Date | number | null | undefined,
  langCode: LanguageCode | string
): string {
  if (!date) return '';
  try {
    const d = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date;
    if (isNaN(d.getTime())) return '';
    const locale = getLocale(langCode);
    return d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

/** Format date + time: "Jan 5, 2026, 2:30 PM" */
export function formatDateTime(
  date: string | Date | number | null | undefined,
  langCode: LanguageCode | string
): string {
  if (!date) return '';
  try {
    const d = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date;
    if (isNaN(d.getTime())) return '';
    const locale = getLocale(langCode);
    return d.toLocaleString(locale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

/** Format relative date like "month year": "Jan 2026" */
export function formatMonthYear(
  date: string | Date | number | null | undefined,
  langCode: LanguageCode | string
): string {
  return formatDate(date, langCode, { month: 'short', year: 'numeric' });
}

/** Format just month: "Jan" */
export function formatMonth(
  date: string | Date | number | null | undefined,
  langCode: LanguageCode | string
): string {
  return formatDate(date, langCode, { month: 'short' });
}

/** Currency formatting with locale awareness */
export function formatCurrency(
  amount: number,
  langCode: LanguageCode | string,
  currency: string = 'USD'
): string {
  try {
    const locale = getLocale(langCode);
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

/** Number formatting with locale awareness */
export function formatNumber(
  num: number,
  langCode: LanguageCode | string
): string {
  try {
    const locale = getLocale(langCode);
    return new Intl.NumberFormat(locale).format(num);
  } catch {
    return num.toLocaleString();
  }
}
