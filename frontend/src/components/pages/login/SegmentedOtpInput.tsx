import React, { useCallback, useRef } from 'react';
import { TextInput, View } from 'react-native';
import { useTheme } from '../../../context/ThemeContext';

export type OtpTokens = { cyan: string; bgCard: string; glassBorder: string; text: string };

export function SegmentedOtpInput({ length = 8, value, onChange, autoFocus = false, testIdPrefix = 'otp', themeTokens }: {
  length?: number; value: string; onChange: (v: string) => void; autoFocus?: boolean; testIdPrefix?: string; themeTokens?: OtpTokens;
}) {
  const { colors } = useTheme();
  const tokens: OtpTokens = themeTokens || { cyan: colors.accent, bgCard: colors.card, glassBorder: colors.glassBorder, text: colors.text };
  const inputRefs = useRef<(TextInput | null)[]>([]);
  const digits = value.padEnd(length, '').split('').slice(0, length);

  const handleChange = useCallback((text: string, index: number) => {
    const clean = text.replace(/\D/g, '');
    if (!clean) {
      const next = [...digits];
      next[index] = '';
      onChange(next.join('').replace(/\s/g, ''));
      return;
    }
    if (clean.length > 1) {
      const pasted = clean.slice(0, length - index);
      const next = [...digits];
      for (let i = 0; i < pasted.length; i++) {
        next[index + i] = pasted[i];
      }
      onChange(next.join('').replace(/\s/g, ''));
      const focusIdx = Math.min(index + pasted.length, length - 1);
      setTimeout(() => inputRefs.current[focusIdx]?.focus(), 30);
      return;
    }
    const next = [...digits];
    next[index] = clean[0];
    onChange(next.join('').replace(/\s/g, ''));
    if (index < length - 1) {
      setTimeout(() => inputRefs.current[index + 1]?.focus(), 30);
    }
  }, [digits, length, onChange]);

  const handleKeyPress = useCallback((e: any, index: number) => {
    if (e.nativeEvent?.key === 'Backspace' && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
      const next = [...digits];
      next[index - 1] = '';
      onChange(next.join('').replace(/\s/g, ''));
    }
  }, [digits, onChange]);

  return (
    <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 4, marginBottom: 14, paddingHorizontal: 2, flexWrap: 'nowrap' }} data-testid={`${testIdPrefix}-segmented-otp`} testID={`${testIdPrefix}-segmented-otp`}>
      {Array.from({ length }).map((_, i) => (
        <React.Fragment key={i}>
          {i === 4 && <View style={{ width: 8 }} />}
          <TextInput accessibilityLabel="Text input"
            ref={(ref) => { inputRefs.current[i] = ref; }}
            value={digits[i]?.trim() || ''}
            onChangeText={(text) => handleChange(text, i)}
            onKeyPress={(e) => handleKeyPress(e, i)}
            keyboardType="number-pad"
            maxLength={length}
            autoFocus={autoFocus && i === 0}
            selectTextOnFocus
            data-testid={`${testIdPrefix}-otp-box-${i}`}
            testID={`${testIdPrefix}-otp-box-${i}`}
            style={{
              flex: 1, minWidth: 0, maxWidth: 44, height: 48, borderRadius: 10,
              backgroundColor: digits[i]?.trim() ? `${tokens.cyan}18` : tokens.bgCard,
              borderWidth: 1.5,
              borderColor: digits[i]?.trim() ? tokens.cyan : tokens.glassBorder,
              color: tokens.text, fontSize: 20, fontWeight: '800',
              textAlign: 'center', letterSpacing: 0,
            }}
          />
        </React.Fragment>
      ))}
    </View>
  );
}
/* i18n-probe t('i18n.auto.probe') */
