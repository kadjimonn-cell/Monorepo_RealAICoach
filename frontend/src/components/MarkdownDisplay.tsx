import React, { Suspense } from 'react';
import { View, ActivityIndicator } from 'react-native';

interface MarkdownDisplayProps {
  content: string;
}

// Lazy-load the heavy markdown rendering (markdown-it + entities = ~235KB)
const LazyMarkdownInner = React.lazy(() => import('./MarkdownDisplayInner'));

function MarkdownFallback() {
  return (
    <View style={{ padding: 12, alignItems: 'center' }}>
      <ActivityIndicator size="small" />
    </View>
  );
}

export default function MarkdownDisplay({ content }: MarkdownDisplayProps) {
  if (!content) return null;

  return (
    <Suspense fallback={<MarkdownFallback />}>
      <LazyMarkdownInner content={content} />
    </Suspense>
  );
}

/* i18n-probe t('i18n.auto.probe') */
