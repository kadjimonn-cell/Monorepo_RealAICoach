import React from "react";
import { Platform } from "react-native";
import OperationsConsoleView from "../../src/components/OperationsConsoleView";
import { useTranslation } from '../../src/hooks/useTranslation';
import { AdminRouteGate } from '../../src/components/auth/AdminRouteGate';
import { WebOnlyScreen } from '../../src/components/WebOnlyScreen';

// This screen renders the "Operations Console" (as labeled in the sidebar).
// The URL path `/admin-console` is preserved for backward compatibility with
// the ~20 deep-links throughout the app (e.g. /admin-console?category=operations&tab=…).
// Code identifiers live in src/components/OperationsConsoleView.tsx and
// src/components/operations-console/ so developers see the same name the
// user sees in the sidebar.
export default function OperationsConsoleScreen() {
  if (Platform.OS !== 'web') {
    return <WebOnlyScreen featureNameKey="webOnly.operationsConsole" featureNameFallback="Operations Console" />;
  }
  const { t } = useTranslation();
  t('i18n.route.(tabs).admin-console.probe');
  return (
    <AdminRouteGate returnTo="/admin-console">
      <OperationsConsoleView />
    </AdminRouteGate>
  );
}