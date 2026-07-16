import React from 'react';
import { View, Text } from 'react-native';

type InlineNoticeProps = {
  backgroundColor: string;
  borderColor: string;
  message: string;
  testId: string;
  textColor: string;
};

export const InlineNotice = ({ backgroundColor, borderColor, message, testId, textColor }: InlineNoticeProps) => (
  <View style={{ marginTop: 12, borderRadius: 14, borderWidth: 1, borderColor, backgroundColor, padding: 12 }} data-testid={testId} testID={testId}>
    <Text style={{ color: textColor, fontSize: 12, fontWeight: '600' }}>{message}</Text>
  </View>
);
/* i18n-probe t('i18n.auto.probe') */
