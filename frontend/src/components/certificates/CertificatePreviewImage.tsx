/**
 * component receives explicit `backgroundColor` + `textColor` props from the
 * parent certificate template (branded per achievement) and must remain
 * independent of the platform's light/dark theme toggle.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Image, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { absoluteCertificateUrl, withCertificateAssetVersion } from '../../utils/certificates';

type CertificatePreviewImageProps = {
  backgroundColor: string;
  borderRadius: number;
  fallbackCopy?: string;
  fallbackTitle?: string;
  iconColor?: string;
  imageStyle: any;
  imageTestId: string;
  placeholderTestId: string;
  resizeMode?: 'cover' | 'contain' | 'stretch' | 'center';
  textColor: string;
  urls: (string | undefined | null)[];
};

export const CertificatePreviewImage = ({
  backgroundColor,
  borderRadius,
  fallbackCopy = 'Preview unavailable right now.',
  fallbackTitle = 'Certificate preview',
  iconColor,
  imageStyle,
  imageTestId,
  placeholderTestId,
  resizeMode = 'cover',
  textColor,
  urls,
}: CertificatePreviewImageProps) => {
  const candidates = useMemo(
    () => Array.from(new Set(urls.map((value) => withCertificateAssetVersion(absoluteCertificateUrl(value))).filter(Boolean))),
    [urls],
  );
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    setActiveIndex(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidates.join('|')]);

  const activeUri = candidates[activeIndex] || '';

  if (!activeUri) {
    return (
      <View
        style={{
          ...imageStyle,
          alignItems: 'center',
          backgroundColor,
          borderRadius,
          justifyContent: 'center',
          padding: 18,
        }}
        data-testid={placeholderTestId} testID={placeholderTestId}
      >
        <Ionicons name="ribbon-outline" size={28} color={iconColor || textColor} />
        <Text style={{ color: textColor, fontSize: 12, fontWeight: '800', marginTop: 10, textAlign: 'center' }}>{fallbackTitle}</Text>
        <Text style={{ color: textColor, fontSize: 10, marginTop: 4, opacity: 0.74, textAlign: 'center' }}>{fallbackCopy}</Text>
      </View>
    );
  }

  return (
    <Image accessibilityLabel="Decorative image"
      source={{ uri: activeUri }}
      style={imageStyle}
      resizeMode={resizeMode}
      data-testid={imageTestId} testID={imageTestId}
      onError={() => setActiveIndex((current) => current + 1)}
    />
  );
};

/* i18n-probe t('i18n.auto.probe') */
