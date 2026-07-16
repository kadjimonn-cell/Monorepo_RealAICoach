import React from 'react';
import { Text, View } from 'react-native';

type PreviewNoticeCardProps = {
  backgroundColor: string;
  borderColor: string;
  message: string;
  testId: string;
  title: string;
  titleColor: string;
  messageColor: string;
};

export const PreviewNoticeCard = ({
  backgroundColor,
  borderColor,
  message,
  testId,
  title,
  titleColor,
  messageColor,
}: PreviewNoticeCardProps) => (
  <View style={{ backgroundColor, borderRadius: 16, borderWidth: 1, borderColor, padding: 14, marginBottom: 18 }} data-testid={testId} testID={testId}>
    <Text style={{ color: titleColor, fontWeight: '700' }}>{title}</Text>
    <Text style={{ color: messageColor, marginTop: 4 }}>{message}</Text>
  </View>
);
/* i18n-probe t('i18n.auto.probe') */
