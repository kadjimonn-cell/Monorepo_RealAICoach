import React from 'react';
import { StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';

import { NovaAvatarBadge } from '../common/NovaIdentityBadge';

type NovaSurfaceColors = {
  card: string;
  bgSoft: string;
  border: string;
  text: string;
  textMuted: string;
};

interface NovaSurfaceShellProps {
  colors: NovaSurfaceColors;
  title: string;
  shellTestId: string;
  headerTestId: string;
  titleTestId: string;
  avatarWrapTestId: string;
  avatarImageTestId: string;
  metaTestId?: string;
  headerMeta?: React.ReactNode;
  headerActions?: React.ReactNode;
  headerSupplement?: React.ReactNode;
  body: React.ReactNode;
  bodyTestId: string;
  footer?: React.ReactNode;
  footerTestId?: string;
  shellStyle?: StyleProp<ViewStyle>;
  headerStyle?: StyleProp<ViewStyle>;
  bodyStyle?: StyleProp<ViewStyle>;
  footerStyle?: StyleProp<ViewStyle>;
}

export const NovaSurfaceShell = ({
  colors,
  title,
  shellTestId,
  headerTestId,
  titleTestId,
  avatarWrapTestId,
  avatarImageTestId,
  metaTestId,
  headerMeta,
  headerActions,
  headerSupplement,
  body,
  bodyTestId,
  footer,
  footerTestId,
  shellStyle,
  headerStyle,
  bodyStyle,
  footerStyle,
}: NovaSurfaceShellProps) => {
  return (
  <View
    style={[styles.shell, { backgroundColor: colors.card, borderColor: colors.border }, shellStyle]}
    data-testid={shellTestId}
    testID={shellTestId}
  >
    <View
      style={[styles.headerSection, { borderBottomColor: colors.border, backgroundColor: colors.card }, headerStyle]}
      data-testid={headerTestId}
      testID={headerTestId}
    >
      <View style={styles.headerRow}>
        <View style={styles.headerLead}>
          <NovaAvatarBadge
            size={40}
            ringColor={colors.border}
            surfaceColor={colors.card}
            animationPreset="subtle"
            wrapTestId={avatarWrapTestId}
            imageTestId={avatarImageTestId}
          />
          <View style={styles.headerCopy}>
            <Text style={[styles.title, { color: colors.text }]} data-testid={titleTestId} testID={titleTestId}>
              {title}
            </Text>
            {headerMeta ? (
              <View data-testid={metaTestId} testID={metaTestId}>
                {headerMeta}
              </View>
            ) : null}
          </View>
        </View>
        {headerActions ? <View style={styles.headerActions}>{headerActions}</View> : null}
      </View>
      {headerSupplement ? <View style={styles.headerSupplement}>{headerSupplement}</View> : null}
    </View>

    <View style={[styles.body, bodyStyle]} data-testid={bodyTestId} testID={bodyTestId}>
      {body}
    </View>

    {footer ? (
      <View style={[styles.footer, { borderTopColor: colors.border }, footerStyle]} data-testid={footerTestId} testID={footerTestId}>
        {footer}
      </View>
    ) : null}
  </View>
  );
};

const styles = StyleSheet.create({
  shell: {
    flex: 1,
    minHeight: 0,
    borderWidth: 1,
    borderRadius: 22,
    overflow: 'hidden',
  },
  headerSection: {
    borderBottomWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 16,
    gap: 12,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  headerLead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flex: 1,
  },
  headerCopy: {
    flex: 1,
    minWidth: 0,
  },
  title: {
    fontSize: 18,
    fontWeight: '900',
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerSupplement: {
    gap: 12,
  },
  body: {
    flex: 1,
    minHeight: 0,
  },
  footer: {
    borderTopWidth: 1,
    padding: 12,
  },
});
