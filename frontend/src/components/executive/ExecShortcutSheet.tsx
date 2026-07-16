import React from 'react';
import { View, Text, TouchableOpacity, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';

interface ExecShortcutSheetProps {
  visible: boolean;
  onClose: () => void;
  pinnedCount: number;
}

export function ExecShortcutSheet({ visible, onClose, pinnedCount }: ExecShortcutSheetProps) {
  const { colors, darkMode } = useTheme();

  // @autofix-moved: was module-level const SHORTCUT_GROUPS
  const SHORTCUT_GROUPS = [
    {
      title: 'Navigation',
      icon: 'compass' as const,
      color: colors.primary,
      shortcuts: [
        { keys: ['Ctrl', 'K'], label: 'Search / Jump to any panel', mac: ['\u2318', 'K'] },
        { keys: ['1-9'], label: 'Jump to pinned tab by number' },
        { keys: ['Esc'], label: 'Close sidebar (mobile) / Close modal' },
      ],
    },
    {
      title: 'Search Modal',
      icon: 'search' as const,
      color: colors.accent,
      shortcuts: [
        { keys: ['\u2191', '\u2193'], label: 'Navigate through results' },
        { keys: ['Enter'], label: 'Select highlighted result' },
        { keys: ['Esc'], label: 'Close search' },
        { keys: ['1-9'], label: 'Quick access to pinned tabs' },
      ],
    },
    {
      title: 'General',
      icon: 'settings' as const,
      color: colors.successText,
      shortcuts: [
        { keys: ['?'], label: 'Toggle this shortcut sheet' },
        { keys: ['R'], label: 'Refresh dashboard data (coming soon)' },
      ],
    },
    {
      title: 'Tips',
      icon: 'bulb' as const,
      color: colors.warningText,
      shortcuts: [
        { keys: ['\u2605'], label: 'Pin/unpin tabs by hovering and clicking the star' },
        { keys: ['\u21e7'], label: 'Drag pinned tabs to reorder (coming soon)' },
      ],
    },
  ];
  if (!visible) return null;

  const isMac = Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.platform?.includes('Mac');
  const C = {
    overlay: `${colors.overlay}${darkMode ? 'A6' : '73'}`,
    modalBg: colors.card,
    modalBorder: colors.borderStrong || colors.border,
    headerBg: colors.primarySoft,
    text: colors.text,
    textSecondary: colors.textSec,
    textMuted: colors.textMuted,
    closeBg: colors.bgSoft,
    rowBg: colors.cardMuted,
    keyBg: colors.bgSoft,
    keyBorder: colors.border,
    keyText: colors.text,
    footerBg: colors.cardMuted,
  };

  return (
    <View
      style={{
        position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: C.overlay, zIndex: 998,
        justifyContent: 'center', alignItems: 'center',
        ...(Platform.OS === 'web' ? { backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)' } : {}),
      } as any}
      data-testid="shortcut-sheet-overlay" testID="shortcut-sheet-overlay"
    >
      <TouchableOpacity accessibilityLabel="On close in exec shortcut sheet button"
        style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
        onPress={onClose} activeOpacity={1}
      />
      <View style={{
        width: 480, maxWidth: '92vw', backgroundColor: C.modalBg,
        borderRadius: 20, borderWidth: 1, borderColor: C.modalBorder, overflow: 'hidden',
        ...(Platform.OS === 'web' ? { boxShadow: '0 32px 64px rgba(0,0,0,0.6)' } : {}),
      } as any} data-testid="shortcut-sheet-modal" testID="shortcut-sheet-modal">
        {/* Header */}
        <View style={{
          flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
          paddingHorizontal: 24, paddingVertical: 18,
          borderBottomWidth: 1, borderBottomColor: C.modalBorder,
          backgroundColor: C.headerBg,
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <View style={{
              width: 36, height: 36, borderRadius: 10,
              backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center',
            }}>
              <Ionicons name="flash" size={18} color={colors.primary} />
            </View>
            <View>
              <Text style={{ fontSize: 16, fontWeight: '800', color: C.text, letterSpacing: -0.3 }} data-testid="shortcut-sheet-title" testID="shortcut-sheet-title">Keyboard Shortcuts</Text>
              <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 1 }} data-testid="shortcut-sheet-subtitle" testID="shortcut-sheet-subtitle">
                {pinnedCount > 0 ? `${pinnedCount} pinned tab${pinnedCount > 1 ? 's' : ''} active` : 'Pin tabs for quick 1-9 access'}
              </Text>
            </View>
          </View>
          <TouchableOpacity onPress={onClose} style={{
            width: 30, height: 30, borderRadius: 8,
            backgroundColor: C.closeBg, alignItems: 'center', justifyContent: 'center',
          }} data-testid="shortcut-sheet-close" testID="shortcut-sheet-close">
            <Ionicons name="close" size={16} color={C.textMuted} />
          </TouchableOpacity>
        </View>

        {/* Shortcut Groups */}
        <View style={{ padding: 20, gap: 20, maxHeight: 420, overflow: 'auto' } as any}>
          {SHORTCUT_GROUPS.map((group) => (
            <View key={group.title}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <View style={{
                  width: 22, height: 22, borderRadius: 6,
                  backgroundColor: (globalThis as any).__alphaColor(group.color, '15'), alignItems: 'center', justifyContent: 'center',
                }}>
                  <Ionicons name={group.icon} size={11} color={group.color} />
                </View>
                <Text style={{ fontSize: 11, fontWeight: '700', color: group.color, letterSpacing: 0.8, textTransform: 'uppercase' }}>{group.title}</Text>
              </View>
              <View style={{ gap: 6 }}>
                {group.shortcuts.map((sc, i) => {
                  const displayKeys = isMac && sc.mac ? sc.mac : sc.keys;
                  return (
                    <View key={i} style={{
                      flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                      paddingVertical: 7, paddingHorizontal: 12, borderRadius: 8,
                      backgroundColor: C.rowBg,
                    }} data-testid={`shortcut-row-${group.title.toLowerCase()}-${i}`} testID={`shortcut-row-${group.title.toLowerCase()}-${i}`}>
                      <Text style={{ fontSize: 12, color: C.textSecondary, flex: 1, fontWeight: '600' }}>{sc.label}</Text>
                      <View style={{ flexDirection: 'row', gap: 4, alignItems: 'center' }}>
                        {displayKeys.map((key, ki) => (
                          <React.Fragment key={ki}>
                            {ki > 0 && <Text style={{ fontSize: 9, color: C.textMuted }}>+</Text>}
                            <View style={{
                              paddingHorizontal: 8, paddingVertical: 3, borderRadius: 5,
                              backgroundColor: C.keyBg, borderWidth: 1, borderColor: C.keyBorder,
                              minWidth: 26, alignItems: 'center',
                              ...(Platform.OS === 'web' ? { boxShadow: '0 1px 2px rgba(0,0,0,0.3)' } : {}),
                            } as any}>
                              <Text style={{
                                fontSize: 10, fontWeight: '700', color: C.keyText,
                                fontFamily: Platform.OS === 'web' ? 'monospace' : undefined,
                              }}>{key}</Text>
                            </View>
                          </React.Fragment>
                        ))}
                      </View>
                    </View>
                  );
                })}
              </View>
            </View>
          ))}
        </View>

        {/* Footer */}
        <View style={{
          flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
          paddingVertical: 12, borderTopWidth: 1, borderTopColor: C.modalBorder,
          backgroundColor: C.footerBg,
        }}>
          <Text style={{ fontSize: 10, color: C.textMuted }}>Press</Text>
          <View style={{
            paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4,
            backgroundColor: C.keyBg, borderWidth: 1, borderColor: C.keyBorder,
          }}>
            <Text style={{ fontSize: 9, fontWeight: '700', color: C.keyText, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }}>?</Text>
          </View>
          <Text style={{ fontSize: 10, color: C.textMuted }}>or</Text>
          <View style={{
            paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4,
            backgroundColor: C.keyBg, borderWidth: 1, borderColor: C.keyBorder,
          }}>
            <Text style={{ fontSize: 9, fontWeight: '700', color: C.keyText, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }}>Esc</Text>
          </View>
          <Text style={{ fontSize: 10, color: C.textMuted }}>to dismiss</Text>
        </View>
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
