import React, { useEffect, useMemo, useState } from 'react';
import { Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { reportPreviewHealth } from '../services/previewHealthMonitor';
import { useLanguage } from '../i18n/LanguageContext';

const BANNER_KEY = 'preview-host-recovery-banner-seen-v1';

function readRecoverySignal() {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return { recovered: false, source: '' };
  const params = new URLSearchParams(window.location.search || '');
  const recovered = params.get('previewHostRecovered') === '1';
  return {
    recovered,
    source: recovered ? (window.location.pathname || '/') : '',
  };
}

export const PreviewHostRecoveryBanner = () => {
  const { t } = useLanguage();
  const { colors } = useTheme();
  const [{ recovered }, setSignal] = useState(() => readRecoverySignal());
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    const next = readRecoverySignal();
    setSignal(next);
    if (!next.recovered) return;

    try {
      window.sessionStorage.setItem(BANNER_KEY, '1');
    } catch {
      // best-effort only
    }

    void reportPreviewHealth('preview_wrapper_path_recovered_banner_visible', {
      source_path: next.source,
      href: window.location.href,
    });
  }, []);

  const visible = useMemo(() => recovered && !dismissed, [recovered, dismissed]);
  if (!visible) return null;

  return (
    <View
      style={[styles.wrap, { borderColor: colors.success, backgroundColor: colors.successSoft }]}
      data-testid="preview-host-recovery-banner"
      testID="preview-host-recovery-banner"
    >
      <Ionicons name="checkmark-circle" size={16} color={colors.successText} />
      <View style={styles.content}>
        <Text
          style={[styles.title, { color: colors.successText }]}
          data-testid="preview-host-recovery-banner-title"
          testID="preview-host-recovery-banner-title"
        >{t("adopt.recovered.to.latest.preview.build")}</Text>
        <Text
          style={[styles.copy, { color: colors.successText }]}
          data-testid="preview-host-recovery-banner-copy"
          testID="preview-host-recovery-banner-copy"
        >{t("adopt.wrapper.path.was.auto.corrected.so.you.re")}</Text>
      </View>
      <TouchableOpacity
        onPress={() => setDismissed(true)}
        style={[styles.dismiss, { borderColor: colors.success }]}
        data-testid="preview-host-recovery-banner-dismiss-button"
        testID="preview-host-recovery-banner-dismiss-button"
        accessibilityLabel="Dismiss preview host recovery banner"
      >
        <Text style={[styles.dismissText, { color: colors.successText }]}>{t("admin.careerApplicationsPanel.auto.text.004")}</Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: {
    marginHorizontal: 12,
    marginTop: 8,
    marginBottom: 6,
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  content: {
    flex: 1,
    gap: 2,
  },
  title: {
    fontSize: 12,
    fontWeight: '800',
  },
  copy: {
    fontSize: 11,
  },
  dismiss: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  dismissText: {
    fontSize: 10,
    fontWeight: '800',
  },
});
