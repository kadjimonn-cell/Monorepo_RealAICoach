import React, { useEffect, useMemo, useState } from 'react';
import { Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { reportPreviewHealth } from '../services/previewHealthMonitor';
import { useLanguage } from '../i18n/LanguageContext';

function resolveExpectedPreviewHost(): string {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return '';
  const current = String(window.location.hostname || '').toLowerCase();
  if (current.includes('preview.emergentagent.com')) return current;

  const expected = String((window as any).__racExpectedHost || '').toLowerCase();
  if (expected.includes('preview.emergentagent.com')) return expected;
  return '';
}

function isWrapperShellHost(): boolean {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return false;
  const host = String(window.location.hostname || '').toLowerCase();
  return host === 'app.emergent.sh' || host.endsWith('.emergent.sh') || host === 'app.emergentagent.com' || host.endsWith('.emergentagent.com');
}

export const PreviewShellMismatchBanner = () => {
  const { t } = useLanguage();
  const { colors } = useTheme();
  const [dismissed, setDismissed] = useState(false);

  const expectedHost = useMemo(() => resolveExpectedPreviewHost(), []);
  const show = useMemo(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return false;
    if (!isWrapperShellHost()) return false;
    const current = String(window.location.hostname || '').toLowerCase();
    return Boolean(expectedHost && current !== expectedHost && !dismissed);
  }, [expectedHost, dismissed]);

  useEffect(() => {
    if (!show || Platform.OS !== 'web' || typeof window === 'undefined') return;
    void reportPreviewHealth('preview_shell_context_mismatch_detected', {
      current_host: window.location.hostname,
      expected_preview_host: expectedHost,
      pathname: window.location.pathname,
      href: window.location.href,
    });
  }, [show, expectedHost]);

  if (!show) return null;

  const openDirectPreview = () => {
    if (Platform.OS !== 'web' || typeof window === 'undefined' || !expectedHost) return;
    const target = `https://${expectedHost}${window.location.pathname || '/'}${window.location.search || ''}${window.location.hash || ''}`;
    void reportPreviewHealth('preview_shell_context_direct_open_clicked', {
      current_host: window.location.hostname,
      expected_preview_host: expectedHost,
      target,
    });
    window.location.href = target;
  };

  return (
    <View
      style={[styles.wrap, { borderColor: colors.warning, backgroundColor: colors.warningSoft }]}
      data-testid="preview-shell-mismatch-banner"
      testID="preview-shell-mismatch-banner"
    >
      <Ionicons name="warning-outline" size={16} color={colors.warningText} />
      <View style={styles.content}>
        <Text style={[styles.title, { color: colors.warningText }]} data-testid="preview-shell-mismatch-title" testID="preview-shell-mismatch-title">{t("adopt.app.preview.shell.detected")}</Text>
        <Text style={[styles.copy, { color: colors.warningText }]} data-testid="preview-shell-mismatch-copy" testID="preview-shell-mismatch-copy">{t("adopt.layout.may.appear.off.in.wrapper.mode.open")}</Text>
      </View>
      <TouchableOpacity
        onPress={openDirectPreview}
        style={[styles.action, { borderColor: colors.warning }]}
        data-testid="preview-shell-open-direct-button"
        testID="preview-shell-open-direct-button"
      >
        <Text style={[styles.actionText, { color: colors.warningText }]}>{t("adopt.open.direct")}</Text>
      </TouchableOpacity>
      <TouchableOpacity
        onPress={() => setDismissed(true)}
        style={[styles.dismiss, { borderColor: colors.warning }]}
        data-testid="preview-shell-mismatch-dismiss-button"
        testID="preview-shell-mismatch-dismiss-button"
      >
        <Text style={[styles.dismissText, { color: colors.warningText }]}>{t("admin.careerApplicationsPanel.auto.text.004")}</Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: {
    marginHorizontal: 12,
    marginTop: 8,
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  content: { flex: 1 },
  title: { fontSize: 12, fontWeight: '800' },
  copy: { fontSize: 11, lineHeight: 15, marginTop: 2 },
  action: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7 },
  actionText: { fontSize: 10, fontWeight: '800' },
  dismiss: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 7 },
  dismissText: { fontSize: 10, fontWeight: '700' },
});
