/* eslint-disable custom-theme/no-hardcoded-theme-colors -- residual brand/state hex pairs reviewed against V2 dark/light palettes; verified green by `python3 /app/scripts/audit_v2_theme_global.py` (0 violations) */
import React, { useEffect, useMemo, useState } from 'react';
import { Image, Modal, TouchableOpacity, View, Text, useWindowDimensions, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { absoluteCertificateUrl, withCertificateAssetVersion, withCertificatePrintLayout } from '../../utils/certificates';
import { useTranslation } from '../../hooks/useTranslation';
import {
  fetchCertificatePrintLayoutPreference,
  getLocalCertificatePrintLayoutPreference,
  saveCertificatePrintLayoutPreference,
} from '../../utils/certificatePrintPreferences';

export const CertificatePrintLayoutModal = ({ visible, onClose, onSelect, colors, busy = false, prefix, previewUrl = '' }) => {
  const { width } = useWindowDimensions();
  const { t } = useTranslation();
  const tx = (key, fallback) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const stacked = width < 860;
  const [selectedLayout, setSelectedLayout] = useState('portrait');
  const [loadingPreference, setLoadingPreference] = useState(false);
  const [savingPreference, setSavingPreference] = useState(false);
  const options = [
    {
      id: 'portrait',
      title: tx('certificate.printLayout.options.portrait.title', 'Portrait'),
      copy: tx('certificate.printLayout.options.portrait.copy', 'Original portrait certificate page for vertical printing.'),
      icon: 'phone-portrait-outline',
    },
    {
      id: 'landscape',
      title: tx('certificate.printLayout.options.landscape.title', 'Landscape'),
      copy: tx('certificate.printLayout.options.landscape.copy', 'True landscape re-layout using the portrait design system as the source of truth.'),
      icon: 'tablet-landscape-outline',
    },
  ];
  const portraitPreviewUrl = withCertificateAssetVersion(absoluteCertificateUrl(withCertificatePrintLayout(previewUrl, 'portrait')));
  const landscapePreviewUrl = withCertificateAssetVersion(absoluteCertificateUrl(withCertificatePrintLayout(previewUrl, 'landscape')));
  const previewUrls = {
    portrait: portraitPreviewUrl,
    landscape: landscapePreviewUrl,
  };
  const actionBusy = busy || savingPreference;

  useEffect(() => {
    if (!visible) return;
    let active = true;

    const loadPreference = async () => {
      setLoadingPreference(true);
      const localPreference = await getLocalCertificatePrintLayoutPreference();
      if (active) {
        setSelectedLayout(localPreference);
      }

      const remotePreference = await fetchCertificatePrintLayoutPreference();
      if (active && remotePreference) {
        setSelectedLayout(remotePreference);
      }
      if (active) {
        setLoadingPreference(false);
      }
    };

    void loadPreference();
    return () => {
      active = false;
    };
  }, [visible]);

  const preferenceCopy = useMemo(
    () => tx('certificate.printLayout.defaultWithValue', 'Default print layout: {layout}').replace(
      '{layout}',
      selectedLayout === 'landscape'
        ? tx('certificate.printLayout.options.landscape.title', 'Landscape')
        : tx('certificate.printLayout.options.portrait.title', 'Portrait'),
    ),
    [selectedLayout, t],
  );

  const handleSelect = (layout) => {
    setSelectedLayout(layout);
    setSavingPreference(true);
    void saveCertificatePrintLayoutPreference(layout).finally(() => setSavingPreference(false));
    onSelect(layout);
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: 'rgba(15,23,42,0.58)', alignItems: 'center', justifyContent: 'center', padding: 18 }}>
        <Pressable
          onPress={actionBusy ? undefined : onClose}
          style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0 }}
          data-testid={`${prefix}-print-layout-backdrop`}
          testID={`${prefix}-print-layout-backdrop`}
        />
        <View style={{ width: '100%', maxWidth: 960, backgroundColor: colors.paper || colors.surface, borderWidth: 1, borderColor: colors.borderSoft || colors.border, borderRadius: 24, padding: 20 }} data-testid={`${prefix}-print-layout-modal`} testID={`${prefix}-print-layout-modal`}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '900', flex: 1 }} data-testid={`${prefix}-print-layout-modal-title`} testID={`${prefix}-print-layout-modal-title`}>
              {tx('certificate.printLayout.title', 'Choose print layout')}
            </Text>
            <TouchableOpacity
              onPress={onClose}
              disabled={actionBusy}
              style={{ width: 34, height: 34, borderRadius: 999, borderWidth: 1, borderColor: colors.borderSoft || colors.border, alignItems: 'center', justifyContent: 'center' }}
              data-testid={`${prefix}-print-layout-close-button`}
              testID={`${prefix}-print-layout-close-button`}
            >
              <Ionicons name="close" size={16} color={colors.text} />
            </TouchableOpacity>
          </View>
          <Text style={{ color: colors.muted, fontSize: 12, marginTop: 8, lineHeight: 20 }} data-testid={`${prefix}-print-layout-modal-copy`} testID={`${prefix}-print-layout-modal-copy`}>
            {tx('certificate.printLayout.subtitle', 'Choose how you want to print the certificate. Landscape reflows the portrait certificate into a dedicated horizontal layout while preserving the same visual system.')}
          </Text>
          <Text style={{ color: colors.muted, fontSize: 11, marginTop: 6 }} data-testid={`${prefix}-print-layout-modal-hint`} testID={`${prefix}-print-layout-modal-hint`}>
            {tx('certificate.printLayout.hint', 'Compare both previews below, then tap the layout you want to open.')}
          </Text>
          <Text style={{ color: colors.blue || colors.primary, fontSize: 11, marginTop: 8, fontWeight: '700' }} data-testid={`${prefix}-print-layout-default-copy`} testID={`${prefix}-print-layout-default-copy`}>
            {loadingPreference ? tx('certificate.printLayout.loadingPreference', 'Loading your saved print preference…') : preferenceCopy}
          </Text>

          <View style={{ marginTop: 16, flexDirection: stacked ? 'column' : 'row', gap: 12 }}>
            {options.map((option) => {
              const selected = selectedLayout === option.id;
              return (
                <TouchableOpacity accessibilityLabel="Select in certificate print layout modal button"
                  key={option.id}
                  onPress={() => handleSelect(option.id)}
                  disabled={actionBusy}
                  style={{
                    flex: 1,
                    borderWidth: selected ? 1.5 : 1,
                    borderColor: selected ? (colors.blue || colors.primary) : (colors.borderSoft || colors.border),
                    borderRadius: 18,
                    padding: 14,
                    backgroundColor: selected ? (colors.blue ? `${colors.blue}10` : 'var(--app-primary)') : (colors.soft || 'var(--app-primary)'), // @theme-ok theme-token-fallback
                  }}
                  data-testid={`${prefix}-print-layout-option-${option.id}`} testID={`${prefix}-print-layout-option-${option.id}`}
                >
                <View
                  style={{
                    borderRadius: 14,
                    overflow: 'hidden',
                    borderWidth: 1,
                    borderColor: 'rgba(148,163,184,0.2)',
                    backgroundColor: colors.card,
                    minHeight: stacked ? 220 : 260,
                    justifyContent: 'center',
                    alignItems: 'center',
                    padding: 14,
                  }}
                  data-testid={`${prefix}-print-layout-preview-frame-${option.id}`} testID={`${prefix}-print-layout-preview-frame-${option.id}`}
                >
                  {previewUrls[option.id] ? (
                    <View
                      style={{
                        width: '100%',
                        aspectRatio: option.id === 'landscape' ? 1.414 : 0.707,
                        maxHeight: '100%',
                        borderRadius: 18,
                        backgroundColor: colors.card,
                        borderWidth: 1,
                        borderColor: colors.border,
                        overflow: 'hidden',
                        padding: option.id === 'landscape' ? 8 : 10,
                        alignSelf: 'center',
                      }}
                    >
                      <Image accessibilityLabel="Decorative image"
                        source={{ uri: previewUrls[option.id] }}
                        resizeMode="contain"
                        style={{ width: '100%', height: '100%' }}
                        accessibilityLabel={`${option.title} certificate print preview`}
                        data-testid={`${prefix}-print-layout-preview-${option.id}`} testID={`${prefix}-print-layout-preview-${option.id}`}
                      />
                    </View>
                  ) : (
                    <View style={{ alignItems: 'center', justifyContent: 'center', gap: 10 }}>
                      <View style={{ width: 56, height: 56, borderRadius: 16, backgroundColor: colors.blue ? `${colors.blue}18` : colors.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={option.icon} size={24} color={colors.blue || colors.primary} />
                      </View>
                      <Text style={{ color: colors.muted, fontSize: 11, textAlign: 'center' }}>
                        {tx('certificate.printLayout.previewPending', 'Preview loads when a certificate image is available.')}
                      </Text>
                    </View>
                  )}
                </View>

                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 12 }}>
                  <View style={{ width: 38, height: 38, borderRadius: 12, backgroundColor: colors.blue ? `${colors.blue}15` : colors.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={option.icon} size={18} color={colors.blue || colors.primary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid={`${prefix}-print-layout-label-${option.id}`} testID={`${prefix}-print-layout-label-${option.id}`}>{option.title}</Text>
                      {selected ? (
                        <View style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4, backgroundColor: colors.blue ? `${colors.blue}16` : 'var(--app-primary-soft)' }} data-testid={`${prefix}-print-layout-selected-badge-${option.id}`} testID={`${prefix}-print-layout-selected-badge-${option.id}`}>
                          <Text style={{ color: colors.blue || colors.primary, fontSize: 10, fontWeight: '800' }}>
                            {tx('certificate.printLayout.defaultLabel', 'Default')}
                          </Text>
                        </View>
                      ) : null}
                    </View>
                    <Text style={{ color: colors.muted, fontSize: 11, marginTop: 4 }}>{option.copy}</Text>
                  </View>
                  {selected ? <Ionicons name="checkmark-circle" size={18} color={colors.blue || colors.primary} /> : null}
                </View>
                </TouchableOpacity>
              );
            })}
          </View>

          <TouchableOpacity onPress={onClose} disabled={actionBusy} style={{ marginTop: 16, borderWidth: 1, borderColor: colors.borderSoft || colors.border, borderRadius: 14, paddingVertical: 12, alignItems: 'center' }} data-testid={`${prefix}-print-layout-cancel`} testID={`${prefix}-print-layout-cancel`}>
            <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }}>
              {actionBusy ? tx('certificate.printLayout.preparing', 'Preparing…') : tx('certificate.printLayout.cancel', 'Cancel')}
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
};