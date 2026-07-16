import React, { useEffect } from 'react';
import { useRouter } from 'expo-router';
import { View, Text, TouchableOpacity } from 'react-native';
import AppShell from '../src/components/AppShell';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';

export default function CareerPage() {
  const { t } = useTranslation();
  t('i18n.route.career.probe');
  const router = useRouter();
  const { colors } = useTheme();

  useEffect(() => {
    const params = new URLSearchParams();
    params.set('ref', 'legacy-career-route');
    router.replace(`/careers?${params.toString()}` as any);
  }, [router]);

  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  return (
    <AppShell>
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 }} data-testid="career-entry-screen" testID="career-entry-screen">
        <Text style={{ color: colors.text, fontSize: 24, fontWeight: '800', marginBottom: 8 }} data-testid="career-entry-title" testID="career-entry-title">{tx('careerEntry.title', 'Career Hub')}</Text>
        <Text style={{ color: colors.textSec, fontSize: 13, textAlign: 'center', maxWidth: 520 }} data-testid="career-entry-subtitle" testID="career-entry-subtitle">
          {tx('careerEntry.subtitle', 'Redirecting to the new enterprise Careers hub…')}
        </Text>
        <TouchableOpacity
          onPress={() => router.push('/careers?ref=legacy-career-route' as any)}
          style={{ marginTop: 16, backgroundColor: colors.primary, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10 }}
          data-testid="career-entry-open-job-platform-btn" testID="career-entry-open-job-platform-btn"
        >
          <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 13 }}>{tx('careerEntry.openJobPlatform', 'Open Careers Hub')}</Text>
        </TouchableOpacity>
      </View>
    </AppShell>
  );
}
