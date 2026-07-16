import React from 'react';
import { Text, View } from 'react-native';

import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { getCertificateStatusMeta } from '../../utils/certificates';

export const CertificateStatusBadge = ({ status, testID }) => {
  const { darkMode } = useTheme();
  const { t } = useTranslation();
  const meta = getCertificateStatusMeta(status, darkMode);
  const normalized = String(status || 'valid').toLowerCase();
  const labelMap = {
    valid: t('certificate.common.status.valid') === 'certificate.common.status.valid' ? 'Valid' : t('certificate.common.status.valid'),
    expired: t('certificate.common.status.expired') === 'certificate.common.status.expired' ? 'Expired' : t('certificate.common.status.expired'),
    revoked: t('certificate.common.status.revoked') === 'certificate.common.status.revoked' ? 'Revoked' : t('certificate.common.status.revoked'),
    invalid: t('certificate.common.status.invalid') === 'certificate.common.status.invalid' ? 'Invalid' : t('certificate.common.status.invalid'),
  };
  const label = labelMap[normalized] || meta.label;

  return (
    <View
      style={{
        alignSelf: 'flex-start',
        backgroundColor: meta.soft,
        borderWidth: 1,
        borderColor: meta.border,
        borderRadius: 999,
        paddingHorizontal: 10,
        paddingVertical: 5,
      }}
      data-testid={testID} testID={testID}
    >
      <Text style={{ color: meta.color, fontSize: 10, fontWeight: '800', letterSpacing: 0.6 }}>
        {String(label).toUpperCase()}
      </Text>
    </View>
  );
};