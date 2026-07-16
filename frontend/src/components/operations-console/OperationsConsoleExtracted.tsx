import React, { useState, useRef, useEffect, useMemo } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, TouchableOpacity, TextInput, ScrollView, Platform, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { EXEC_NAV_ITEMS } from '../../lib/unified-admin-search';
import { CONSOLE_TAB_DEBUG_VERSIONS } from '../../lib/consoleTabContracts';
import { OPERATIONS_PHASE_B_HUBS } from '../../config/phaseBTabConsolidation';
import type { ThemeColors } from '../../theme/v1';

/* ── Category + Tab definitions ── */
export interface TabDef { id: string; label: string; icon: string; }

/**
 * Keys that categories are allowed to reference from the theme palette.
 * Restricted to the semantic slice of the theme so a category can't ever
 * bind to a structural token like `bgGradientStart`. Widening this union
 * when new categories need additional colors is a deliberate one-line
 * change — that's the point of the compile-time guard.
 */
export type CategoryColorKey =
  | 'primary'
  | 'accent'
  | 'success'
  | 'warning'
  | 'error'
  | 'textMuted';

// Compile-time invariant: every `CategoryColorKey` member must exist on
// `ThemeColors`. If `theme/v1.ts` ever removes one of these keys, this
// line fails type-checking and breaks the build — far better than
// shipping a `colors[key]` lookup that silently resolves to `undefined`
// at runtime.
type _AssertCategoryKeysExistOnTheme =
  Exclude<CategoryColorKey, keyof ThemeColors> extends never ? true : never;
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const __assertCategoryKeys: _AssertCategoryKeysExistOnTheme = true;

/**
 * `colorKey` is a semantic token name resolved against the live theme at
 * render time via `useTheme().colors[cat.colorKey]`. Typed as a strict
 * union (not `string`) so the TypeScript compiler catches typos like
 * `colorKey: 'primrayText'` at build time instead of at runtime.
 */
export interface CategoryDef {
  id: string;
  label: string;
  icon: string;
  colorKey: CategoryColorKey;
  tabs: TabDef[];
}

/**
 * Resolve a category's theme color from the live colors palette.
 * Falls back to `colors.textMuted` if the key doesn't exist (defensive —
 * keeps the UI rendering even if a category uses a non-standard token).
 */
export function getCategoryColor(
  cat: { colorKey?: CategoryColorKey },
  colors: ThemeColors | any,
): string {
  const key = (cat?.colorKey || 'primary') as CategoryColorKey;
  return (colors && (colors as any)[key]) || (colors && colors.textMuted) || 'var(--app-text-muted)';
}

const toRgb = (hexLike: string): { r: number; g: number; b: number } | null => {
  const raw = String(hexLike || '').trim();
  const m = raw.match(/^#([\da-fA-F]{3}|[\da-fA-F]{6})$/);
  if (!m) return null;
  const v = m[1].length === 3
    ? m[1].split('').map((c) => c + c).join('')
    : m[1];
  const n = parseInt(v, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
};

const relLum = ({ r, g, b }: { r: number; g: number; b: number }): number => {
  const ch = [r, g, b].map((v) => {
    const n = v / 255;
    return n <= 0.03928 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
};

const contrastRatio = (fg: string, bg: string): number | null => {
  const a = toRgb(fg);
  const b = toRgb(bg);
  if (!a || !b) return null;
  const l1 = relLum(a);
  const l2 = relLum(b);
  const max = Math.max(l1, l2);
  const min = Math.min(l1, l2);
  return (max + 0.05) / (min + 0.05);
};

const blendHex = (fg: string, bg: string, alpha: number): string | null => {
  const a = toRgb(fg);
  const b = toRgb(bg);
  if (!a || !b) return null;
  const mix = (f: number, d: number) => Math.round((f * alpha) + (d * (1 - alpha)));
  const r = mix(a.r, b.r);
  const g = mix(a.g, b.g);
  const b2 = mix(a.b, b.b);
  return `#${[r, g, b2].map((x) => x.toString(16).padStart(2, '0')).join('')}`;
};

const getHubTab = (hubId: string): TabDef => {
  const hub = OPERATIONS_PHASE_B_HUBS.find((item) => item.id === hubId);
  if (!hub) {
    return { id: hubId, label: hubId, icon: 'ellipse' };
  }
  return { id: hub.id, label: hub.label, icon: hub.icon };
};

export const CATEGORIES: CategoryDef[] = [
  {
    id: 'overview',
    label: 'Overview',
    icon: 'grid',
    colorKey: 'primary',
    tabs: [
      { id: 'assigned-host', label: 'Assigned Host', icon: 'git-network' },
      getHubTab('ops-command-center'),
      getHubTab('platform-health-observability-hub'),
    ],
  },
  {
    id: 'growth',
    label: 'Growth',
    icon: 'trending-up',
    colorKey: 'warning',
    tabs: [
      getHubTab('growth-experimentation-hub'),
      getHubTab('ai-operations-hub'),
      getHubTab('mobile-distribution-hub'),
    ],
  },
  {
    id: 'hiring',
    label: 'Hiring',
    icon: 'briefcase',
    colorKey: 'accent',
    tabs: [
      getHubTab('hiring-careers-hub'),
      getHubTab('support-ticketing-hub'),
    ],
  },
  {
    id: 'revenue',
    label: 'Revenue',
    icon: 'cash',
    colorKey: 'success',
    tabs: [
      getHubTab('revenue-billing-hub'),
      { id: 'provider-incidents', label: 'Provider Incidents', icon: 'pulse' },
      getHubTab('notifications-messaging-hub'),
    ],
  },
  {
    id: 'security',
    label: 'Security',
    icon: 'shield',
    colorKey: 'error',
    tabs: [
      getHubTab('security-trust-hub'),
      getHubTab('identity-access-hub'),
    ],
  },
  {
    id: 'platform',
    label: 'Platform',
    icon: 'settings',
    colorKey: 'accent',
    tabs: [
      getHubTab('automation-reliability-hub'),
      getHubTab('integrations-webhooks-hub'),
      getHubTab('content-knowledge-hub'),
      getHubTab('policy-compliance-hub'),
      getHubTab('theme-brand-localization-hub'),
      { id: 'sports-source-health', label: 'Sports Source Health', icon: 'pulse' },
      { id: 'matchday-reminders', label: 'Matchday Reminders', icon: 'alarm' },
      { id: 'content-integrity', label: 'Content Integrity', icon: 'shield-checkmark' },
      { id: 'blog-editorial', label: 'Blog Editorial', icon: 'newspaper' },
    ],
  },
];

/* ── Command Palette ── */
interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onSelect: (item: { catId: string; id: string }) => void;
  onSelectExec?: (tabId: string) => void;
  colors: any;
}

export function OperationsCommandPalette({ open, onClose, onSelect, onSelectExec, colors }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const inputRef = useRef<TextInput>(null);
  const CP = {
    panelBg: colors?.card,
    panelBorder: colors?.border,
    text: colors?.text,
    textSec: colors?.textSec || colors?.text,
    textMuted: colors?.textMuted,
    textDim: colors?.textDim || colors?.textMuted,
    chipBg: colors?.bgSoft || colors?.surfaceHover,
  };

  const allItems = CATEGORIES.flatMap(cat =>
    cat.tabs.map(tab => ({ catId: cat.id, catLabel: cat.label, catColor: getCategoryColor(cat, colors), ...tab }))
  );

  const execItems = useMemo(() => EXEC_NAV_ITEMS, []);

  const filtered = query.trim()
    ? allItems.filter(item => item.label.toLowerCase().includes(query.toLowerCase()) || item.catLabel.toLowerCase().includes(query.toLowerCase()))
    : allItems;

  const filteredExec = query.trim()
    ? execItems.filter((item: any) => item.label.toLowerCase().includes(query.toLowerCase()))
    : [];

  useEffect(() => { setIndex(0); }, [query]);
  useEffect(() => {
    if (open && inputRef.current) setTimeout(() => inputRef.current?.focus(), 100);
    if (open) { setQuery(''); setIndex(0); }
  }, [open]);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) { onClose(); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999, alignItems: 'center', paddingTop: 80 }}>
      <TouchableOpacity activeOpacity={1} onPress={onClose}
        style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)' }}
        data-testid="cmd-palette-backdrop" testID="cmd-palette-backdrop" />
      <View style={{
        width: '100%', maxWidth: 520, backgroundColor: CP.panelBg,
        borderRadius: 16, borderWidth: 1, borderColor: CP.panelBorder, overflow: 'hidden',
        ...(Platform.OS === 'web' ? { boxShadow: '0 16px 64px rgba(0,0,0,0.5)' } : {}),
      }} data-testid="cmd-palette-modal" testID="cmd-palette-modal">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14, borderBottomWidth: 1, borderBottomColor: CP.panelBorder }}>
          <Ionicons name="search" size={18} color={CP.textMuted} />
          <TextInput ref={inputRef} value={query} onChangeText={setQuery}
            placeholder="Search across all admin panels..." placeholderTextColor={CP.textDim}
            style={{ flex: 1, color: CP.text, fontSize: 15, padding: 0, outlineStyle: 'none' } as any}
            autoFocus
            onKeyPress={(e: any) => {
              const key = e.nativeEvent?.key;
              if (key === 'ArrowDown') { e.preventDefault?.(); setIndex(i => Math.min(i + 1, filtered.length - 1)); }
              if (key === 'ArrowUp') { e.preventDefault?.(); setIndex(i => Math.max(i - 1, 0)); }
              if (key === 'Enter' && filtered[index]) { onSelect(filtered[index]); }
              if (key === 'Escape') { onClose(); }
            }}
            data-testid="cmd-palette-input" testID="cmd-palette-input" />
          <View style={{ backgroundColor: CP.chipBg, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
            <Text style={{ color: CP.textDim, fontSize: 10, fontWeight: '600' }}>ESC</Text>
          </View>
        </View>
        <ScrollView style={{ maxHeight: 360 }} contentContainerStyle={{ paddingVertical: 4 }} data-testid="cmd-palette-results" testID="cmd-palette-results">
          {filtered.length === 0 && filteredExec.length === 0 ? (
            <View style={{ padding: 24, alignItems: 'center' }}>
              <Text style={{ color: CP.textDim, fontSize: 13 }}>No matching panels found</Text>
            </View>
          ) : (
            <>
              {filtered.length > 0 && query.trim() ? (
                <View style={{ paddingHorizontal: 14, paddingTop: 6, paddingBottom: 2 }}>
                  <Text style={{ fontSize: 10, color: colors?.primary || CP.textSec, fontWeight: '700', letterSpacing: 0.5 }}>OPERATIONS CONSOLE</Text>
                </View>
              ) : null}
              {filtered.map((item, idx) => {
                const isSelected = idx === index;
                return (
                  <TouchableOpacity key={`${item.catId}-${item.id}`} onPress={() => onSelect(item)}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, paddingHorizontal: 14, marginHorizontal: 4, borderRadius: 8, backgroundColor: isSelected ? CP.chipBg : 'transparent' }}
                    data-testid={`cmd-item-${item.id}`} testID={`cmd-item-${item.id}`}>
                    <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: `${item.catColor}20`, alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name={item.icon as any} size={13} color={item.catColor} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: isSelected ? CP.text : CP.textSec, fontSize: 13, fontWeight: '600' }}>{item.label}</Text>
                      <Text style={{ color: CP.textDim, fontSize: 10, marginTop: 1 }}>{item.catLabel}</Text>
                    </View>
                    {isSelected && (
                      <View style={{ backgroundColor: CP.card, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                        <Text style={{ color: CP.textMuted, fontSize: 9, fontWeight: '600' }}>Enter</Text>
                      </View>
                    )}
                  </TouchableOpacity>
                );
              })}
              {filteredExec.length > 0 && (
                <>
                  <View style={{ paddingHorizontal: 14, paddingTop: 10, paddingBottom: 2 }}>
                    <Text style={{ fontSize: 10, color: colors?.successText || CP.textSec, fontWeight: '700', letterSpacing: 0.5 }}>EXECUTIVE DASHBOARD</Text>
                  </View>
                  {filteredExec.map((item: any) => (
                    <TouchableOpacity key={`exec-${item.id}`} onPress={() => onSelectExec?.(item.id)}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, paddingHorizontal: 14, marginHorizontal: 4, borderRadius: 8 }}
                      data-testid={`cmd-item-exec-${item.id}`} testID={`cmd-item-exec-${item.id}`}>
                      <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: 'rgba(16,185,129,0.12)', alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={item.icon as any} size={13} color={colors?.successText || CP.textSec} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: CP.textSec, fontSize: 13, fontWeight: '600' }}>{item.label}</Text>
                        <Text style={{ color: CP.textDim, fontSize: 10, marginTop: 1 }}>Executive Dashboard</Text>
                      </View>
                      <Ionicons name="open-outline" size={12} color={colors?.successText || CP.textSec} />
                    </TouchableOpacity>
                  ))}
                </>
              )}
            </>
          )}
        </ScrollView>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 16, padding: 10, borderTopWidth: 1, borderTopColor: CP.panelBorder }}>
          {[{ keys: 'Up/Down', label: 'Navigate' }, { keys: 'Enter', label: 'Select' }, { keys: 'Esc', label: 'Close' }].map(h => (
            <View key={h.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <Text style={{ color: CP.textMuted, fontSize: 10 }}>{h.label}</Text>
              <Text style={{ color: CP.textDim, fontSize: 9, backgroundColor: CP.chipBg, paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3 }}>{h.keys}</Text>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

/* ── Toast Alerts ── */
interface OperationsToastAlertsProps {
  toasts: any[];
  onDismiss: (id: number) => void;
}

export function OperationsToastAlerts({ toasts, onDismiss }: OperationsToastAlertsProps) {
  if (toasts.length === 0) return null;
  // Theme-reactive severity palette — was previously hardcoded to dark bg
  // (`var(--app-primary)`/`var(--app-primary)`/`var(--app-primary)`) with off-white text (`var(--app-primary)`), which
  // rendered as nearly-invisible light-grey toasts on light-theme admin
  // surfaces (user-reported "Integrity Engine WARNING — 88/100" faint toast).
  // Switched to CSS-var tokens so bg softens/darkens with the active theme
  // and text stays readable in both.
  const sev: Record<string, { bg: string; border: string; icon: string; iconName: string }> = {
    critical: { bg: 'var(--app-error-soft)' as any,   border: 'var(--app-error)' as any,   icon: 'var(--app-error)' as any,   iconName: 'alert-circle' },
    warning:  { bg: 'var(--app-warning-soft)' as any, border: 'var(--app-warning)' as any, icon: 'var(--app-warning)' as any, iconName: 'warning' },
    info:     { bg: 'var(--app-success-soft)' as any, border: 'var(--app-success)' as any, icon: 'var(--app-success)' as any, iconName: 'information-circle' },
  };
  return (
    <View style={{ position: 'absolute', top: 16, right: 16, zIndex: 9999, gap: 8, width: 360 }} data-testid="admin-toast-container" testID="admin-toast-container">
      {toasts.map((toast) => {
        const st = sev[toast.severity] || sev.info;
        return (
          <Animated.View key={toast.id} style={{
            backgroundColor: st.bg, borderWidth: 1, borderColor: st.border, borderRadius: 12,
            padding: 12, flexDirection: 'row', alignItems: 'flex-start', gap: 10,
            ...(Platform.OS === 'web' ? { boxShadow: `0 4px 16px rgba(15,23,42,0.12)` } : {}),
          }} data-testid={`admin-toast-${toast.alert_type}`} testID={`admin-toast-${toast.alert_type}`}>
            <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: st.icon, opacity: 0.9, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={st.iconName as any} size={16} color={'var(--app-primary-text)'} />
            </View>
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <Text style={{ color: 'var(--app-text)' as any, fontSize: 12, fontWeight: '700' }}>{toast.title}</Text>
                <TouchableOpacity onPress={() => onDismiss(toast.id)} data-testid="dismiss-toast" testID="dismiss-toast">
                  <Ionicons name="close" size={14} color={'var(--app-text-muted)' as any} />
                </TouchableOpacity>
              </View>
              <Text style={{ color: 'var(--app-text-sec)' as any, fontSize: 11, marginTop: 2 }}>{toast.message}</Text>
            </View>
          </Animated.View>
        );
      })}
    </View>
  );
}

/* ── Category Bar ── */
interface OperationsCategoryBarProps {
  activeCategory: string;
  onCategoryPress: (id: string) => void;
  activeTab: string;
  onTabPress: (id: string) => void;
  colors: any;
  width: number;
  showDebugAdvanced: boolean;
}

export function OperationsCategoryBar({ activeCategory, onCategoryPress, activeTab, onTabPress, colors, width, showDebugAdvanced }: OperationsCategoryBarProps) {
  const activeCat = CATEGORIES.find(c => c.id === activeCategory);
  const compact = width < 600;
  const activeCatColor = activeCat ? getCategoryColor(activeCat, colors) : (colors?.primary || 'var(--app-primary)');

  return (
    <>
      <View style={{ marginBottom: 6 }} data-testid="category-bar-wrapper" testID="category-bar-wrapper">
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: compact ? 4 : 6 }}>
          {CATEGORIES.map(cat => {
            const isActive = activeCategory === cat.id;
            const catColor = getCategoryColor(cat, colors);
            return (
              <TouchableOpacity accessibilityLabel="On category press in operations console extracted button"
                key={cat.id}
                onPress={() => onCategoryPress(cat.id)}
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: compact ? 4 : 6,
                  paddingVertical: compact ? 6 : 8,
                  paddingHorizontal: compact ? 10 : 14,
                  borderRadius: 10,
                  backgroundColor: isActive ? catColor : (colors?.card || colors?.surface),
                  borderWidth: 1,
                  borderColor: isActive ? catColor : colors?.border,
                  minHeight: compact ? 32 : 36,
                }}
                data-testid={`admin-category-${cat.id}`}
                testID={`admin-category-${cat.id}`}
              >
                <Ionicons name={cat.icon as any} size={compact ? 12 : 14} color={isActive ? (colors?.primaryText || 'var(--app-primary-text)') : (colors?.textMuted)} />
                <Text style={{ color: isActive ? (colors?.primaryText || 'var(--app-primary-text)') : (colors?.textMuted), fontSize: compact ? 10 : 12, fontWeight: '700' }}>{cat.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      {activeCat && activeCat.tabs.length > 1 && (
        <View style={{ marginBottom: 16 }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, paddingVertical: 6 }} data-testid="admin-subtab-wrap" testID="admin-subtab-wrap">
            {activeCat.tabs.map(tab => {
              const isActive = activeTab === tab.id;
              const debugVersion = CONSOLE_TAB_DEBUG_VERSIONS[tab.id];
              const tabBg = isActive
                ? (blendHex(activeCatColor, colors?.bg || 'var(--app-primary-text)', 0.18) || colors?.bg || 'var(--app-primary-text)')
                : (colors?.bg || 'var(--app-primary-text)');
              const tabFg = isActive ? activeCatColor : (colors?.textMuted || 'var(--app-text-muted)');
              const tabContrastScore = contrastRatio(tabFg, tabBg);
              const isContrastAA = (tabContrastScore || 0) >= 4.5;
              return (
                <TouchableOpacity accessibilityLabel="On tab press in operations console extracted"
                  key={tab.id}
                  onPress={() => onTabPress(tab.id)}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 5,
                    paddingVertical: compact ? 6 : 7,
                    paddingHorizontal: compact ? 10 : 12,
                    borderRadius: 8,
                    backgroundColor: isActive ? `${activeCatColor}18` : 'transparent',
                    borderWidth: 1,
                    borderColor: isActive ? `${activeCatColor}35` : (colors?.border),
                    minHeight: compact ? 30 : 34,
                    maxWidth: width >= 1280 ? 260 : width >= 768 ? 220 : width - 44,
                  }}
                  data-testid={`admin-tab-${tab.id}`}
                  testID={`admin-tab-${tab.id}`}
                >
                  <Ionicons name={tab.icon as any} size={12} color={isActive ? activeCatColor : (colors?.textMuted)} />
                  <Text
                    numberOfLines={1}
                    style={{ color: isActive ? activeCatColor : (colors?.textMuted), fontSize: 12, fontWeight: isActive ? '700' : '500' }}
                  >
                    {tab.label}
                  </Text>
                  {showDebugAdvanced && debugVersion ? (
                    <View
                      style={{
                        borderRadius: 999,
                        paddingHorizontal: 6,
                        paddingVertical: 2,
                        borderWidth: 1,
                        borderColor: isContrastAA ? colors.success : colors.warning,
                        backgroundColor: isContrastAA ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.12)',
                      }}
                      data-testid={`admin-tab-version-badge-${tab.id}`}
                      testID={`admin-tab-version-badge-${tab.id}`}
                    >
                      <Text style={{ color: isContrastAA ? colors.success : colors.warning, fontSize: 9, fontWeight: '800' }}>
                        {debugVersion}
                      </Text>
                    </View>
                  ) : null}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      )}
      {activeCat && activeCat.tabs.length === 1 && <View style={{ height: 12 }} />}
    </>
  );
}

/* i18n-probe t('i18n.auto.probe') */
