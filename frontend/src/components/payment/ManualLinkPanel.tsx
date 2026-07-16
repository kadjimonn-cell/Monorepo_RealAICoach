import React from 'react';
import { Platform, Text, View } from 'react-native';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

// Always-dark manual copy-link panel input surface. Theme-exempt by design:
// this is a secondary fallback panel shown only when the primary Stripe UI
// is unavailable, and it must look identical on web regardless of theme.
/**
 * for brand consistency in both themes (matches the rest of the payment
 * panel suite). Panel chrome is themed by the parent wrapper.
 */
const MANUAL_LINK_INPUT_BG = 'var(--app-primary)';
const MANUAL_LINK_INPUT_FG = 'var(--app-primary)';

type ManualLinkPanelProps = {
  backgroundColor: string;
  borderColor: string;
  inputRef?: (node: any) => void;
  inputTestId: string;
  label: string;
  panelTestId: string;
  textColor: string;
  value: string;
};

export const ManualLinkPanel = ({
  backgroundColor,
  borderColor,
  inputRef,
  inputTestId,
  label,
  panelTestId,
  textColor,
  value,
}: ManualLinkPanelProps) => {
  if (Platform.OS !== 'web') return null;

  return (
    <View style={{ marginTop: 10, borderRadius: 14, borderWidth: 1, borderColor, backgroundColor, padding: 12 }} data-testid={panelTestId} testID={panelTestId}>
      <Text style={{ color: textColor, fontSize: 12, fontWeight: '700', marginBottom: 8 }}>{label}</Text>
      {React.createElement('input', {
        ref: inputRef,
        readOnly: true,
        value,
        onFocus: (event: any) => {
          try { event.target.select(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/payment/ManualLinkPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        },
        'data-testid': inputTestId,
        style: { width: '100%', padding: '10px 12px', borderRadius: 10, border: `1px solid ${borderColor}`, backgroundColor: MANUAL_LINK_INPUT_BG, color: MANUAL_LINK_INPUT_FG, fontSize: '12px' },
      })}
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
