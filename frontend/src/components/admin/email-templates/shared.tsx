import React from 'react';
import { View, Text } from 'react-native';
import { getAdminColors, useAdminTheme } from '../../../hooks/useAdminTheme';

export const CATEGORY_ICONS: Record<string, string> = {
  Onboarding: 'sparkles', Security: 'shield-checkmark', Billing: 'card', Support: 'chatbubbles',
  Communication: 'chatbubble-ellipses', Engagement: 'trending-up', Calendar: 'calendar',
  Employer: 'business', Verification: 'checkbox', Hiring: 'briefcase', AI: 'flash',
  Account: 'person-circle', 'Onboarding Drip': 'water',
};

const mapAdminToTemplateColors = (darkMode: boolean) => {
  const AC = getAdminColors(darkMode);
  return {
    bg: AC.bg,
    card: AC.card,
    border: AC.border,
    text: AC.text,
    primaryText: AC.primaryText || AC.buttonText || AC.text,
    muted: AC.textMuted,
    green: AC.success,
    red: AC.error,
    blue: AC.primary,
    purple: AC.purple,
    teal: AC.info,
    pink: AC.error,
    amber: AC.warning,
    indigo: AC.indigo,
  };
};

export const C = mapAdminToTemplateColors(true);

export const applyEmailTemplateTheme = (darkMode: boolean) => {
  Object.assign(C, mapAdminToTemplateColors(darkMode));
};

export interface CatalogItem {
  key: string;
  label: string;
  category: string;
  description: string;
  footer_version?: string;
  footer_last_updated?: string;
  footer_standard?: string;
  footer_cta_status?: string;
  footer_theme_support?: string[];
  footer_responsive_support?: string[];
  header_footer_theme_status?: string;
  footer_badge_block?: {
    width: number;
    height: number;
    source?: string;
  };
}

export function StatCard({ val, label, color }: { val: string | number; label: string; color: string }) {
  const C = useAdminTheme();
  return (
    <View style={{ flex: 1, minWidth: 90, backgroundColor: (globalThis as any).__alphaColor(color, '10'), borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '22') }}>
      <Text style={{ fontSize: 20, fontWeight: '800', color }}>{val}</Text>
      <Text style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>{label}</Text>
    </View>
  );
}

export function RateBar({ rate, color }: { rate: number; color: string }) {
  const C = useAdminTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
      <View style={{ flex: 1, height: 6, backgroundColor: C.border, borderRadius: 3, overflow: 'hidden' }}>
        <View style={{ width: `${Math.min(rate, 100)}%`, height: '100%', backgroundColor: color, borderRadius: 3 }} />
      </View>
      <Text style={{ fontSize: 11, fontWeight: '700', color, minWidth: 36, textAlign: 'right' }}>{rate}%</Text>
    </View>
  );
}

export function Badge({ text, color }: { text: string; color: string }) {
  return (
    <View style={{ backgroundColor: (globalThis as any).__alphaColor(color, '18'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
      <Text style={{ fontSize: 10, fontWeight: '700', color, textTransform: 'uppercase', letterSpacing: 0.3 }}>{text}</Text>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
