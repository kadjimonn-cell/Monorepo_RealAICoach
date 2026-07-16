import React from 'react';
import { View, useWindowDimensions } from 'react-native';
import { useLanguage } from '../../i18n/LanguageContext';

type ResponsiveDataGridProps = {
  compactBreakpoint?: number;
  compactTestId: string;
  desktopTestId: string;
  renderCompact: () => React.ReactNode;
  renderDesktop: () => React.ReactNode;
};

export const ResponsiveDataGrid = ({
  compactBreakpoint = 900,
  compactTestId,
  desktopTestId,
  renderCompact,
  renderDesktop,
}: ResponsiveDataGridProps) => {
  const { t } = useLanguage();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { width } = useWindowDimensions();
  const isCompact = width < compactBreakpoint;
  const layoutLabel = isCompact
    ? tx('admin.responsiveDataGrid.layout.compact', 'Compact data grid layout')
    : tx('admin.responsiveDataGrid.layout.desktop', 'Desktop data grid layout');

  return (
    <View
      data-testid={isCompact ? compactTestId : desktopTestId}
      testID={isCompact ? compactTestId : desktopTestId}
      accessibilityLabel={layoutLabel}
    >
      {isCompact ? renderCompact() : renderDesktop()}
    </View>
  );
};
