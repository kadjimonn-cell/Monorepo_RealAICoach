import React from "react";
import { NotificationsWorkspace } from "../src/components/notifications/NotificationsWorkspace";
import { useGlobalPlatformState } from "../src/hooks/useGlobalPlatformState";
import { useTranslation } from '../src/hooks/useTranslation';

export default function NotificationsPage() {
  const { t } = useTranslation();
  t('i18n.route.notifications.probe');
  useGlobalPlatformState();
  return <NotificationsWorkspace />;
}