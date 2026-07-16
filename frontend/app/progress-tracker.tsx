import React from 'react';
import { Redirect } from 'expo-router';

export default function LegacyProgressTrackerRedirect() {
  return <Redirect href="/progress" />;
}

/* i18n-probe t('i18n.auto.probe') */
