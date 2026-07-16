/**
 * Hook for locale-aware date/time/currency formatting.
 * Uses the app's current language to format values via Intl APIs.
 */
import { useCallback } from 'react';
import { useTheme } from '../context/ThemeContext';
import {
  formatDate,
  formatDateLong,
  formatTime,
  formatDateTime,
  formatMonthYear,
  formatMonth,
  formatCurrency,
  formatNumber,
} from '../utils/dateFormat';

export function useLocaleFormat() {
  const { languageCode } = useTheme();

  const fmtDate = useCallback(
    (date: string | Date | number | null | undefined, options?: Intl.DateTimeFormatOptions) =>
      options ? formatDate(date, languageCode, options) : formatDate(date, languageCode),
    [languageCode]
  );

  const fmtDateLong = useCallback(
    (date: string | Date | number | null | undefined) => formatDateLong(date, languageCode),
    [languageCode]
  );

  const fmtTime = useCallback(
    (date: string | Date | number | null | undefined) => formatTime(date, languageCode),
    [languageCode]
  );

  const fmtDateTime = useCallback(
    (date: string | Date | number | null | undefined) => formatDateTime(date, languageCode),
    [languageCode]
  );

  const fmtMonthYear = useCallback(
    (date: string | Date | number | null | undefined) => formatMonthYear(date, languageCode),
    [languageCode]
  );

  const fmtMonth = useCallback(
    (date: string | Date | number | null | undefined) => formatMonth(date, languageCode),
    [languageCode]
  );

  const fmtCurrency = useCallback(
    (amount: number, currency?: string) => formatCurrency(amount, languageCode, currency),
    [languageCode]
  );

  const fmtNumber = useCallback(
    (num: number) => formatNumber(num, languageCode),
    [languageCode]
  );

  return {
    fmtDate,
    fmtDateLong,
    fmtTime,
    fmtDateTime,
    fmtMonthYear,
    fmtMonth,
    fmtCurrency,
    fmtNumber,
    languageCode,
  };
}
