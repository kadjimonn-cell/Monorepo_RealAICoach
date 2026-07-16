import React from "react";
import DownloadsManagerView from "../../src/components/DownloadsManagerView";
import { DownloadsSkeleton, usePageReady } from '../../src/components/SkeletonLoaders';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function DownloadsScreen() {
  const { t } = useTranslation();
  t('i18n.route.(tabs).downloads.probe');
  const pageReady = usePageReady();
  if (!pageReady) return <DownloadsSkeleton />;

  return <DownloadsManagerView />;
}