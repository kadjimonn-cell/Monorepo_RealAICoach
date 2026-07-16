import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, TextInput, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme } from '../admin/ExecDashboardPanels';
import type { UnifiedSearchItem } from '../../lib/unified-admin-search';
import { CATEGORIES, getCategoryColor } from '../operations-console/OperationsConsoleExtracted';

interface NavItem {
  id: string;
  label: string;
  icon: string;
  section?: boolean;
}

interface ExecSearchModalProps {
  searchOpen: boolean;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  searchIndex: number;
  setSearchIndex: (i: number) => void;
  filteredNavItems: NavItem[];
  pinnedTabs: string[];
  recentlyViewed: string[];
  clearRecentlyViewed: () => void;
  tabFrequency: Record<string, number>;
  setActiveSection: (id: string) => void;
  onClose: () => void;
  navItems: NavItem[];
  width: number;
  searchInputRef: React.RefObject<any>;
  onNavigateToDashboard?: (route: string, tabId?: string) => void;
}

export function ExecSearchModal({
  searchOpen, searchQuery, setSearchQuery, searchIndex, setSearchIndex,
  filteredNavItems, pinnedTabs, recentlyViewed, clearRecentlyViewed,
  tabFrequency, setActiveSection, onClose, navItems, width, searchInputRef,
  onNavigateToDashboard,
}: ExecSearchModalProps) {
  const THEME = useExecTheme();
  const opsAccent = THEME.success;
  const opsItems = React.useMemo(() =>
    CATEGORIES.flatMap(cat =>
      cat.tabs.map(tab => ({
        id: tab.id,
        label: tab.label,
        icon: tab.icon,
        source: 'operations' as const,
        sourceLabel: 'Operations',
        catLabel: cat.label,
        catColor: getCategoryColor(cat, THEME),
        catId: cat.id,
      }))
    ), [THEME]
  );
  const filteredOpsItems = React.useMemo(
    () => searchQuery.trim()
      ? opsItems.filter(item =>
          item.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (item.catLabel && item.catLabel.toLowerCase().includes(searchQuery.toLowerCase()))
        )
      : [],
    [searchQuery, opsItems]
  );

  if (!searchOpen) return null;

  const selectAndClose = (id: string) => {
    setActiveSection(id);
    onClose();
  };

  const selectOpsItem = (item: UnifiedSearchItem) => {
    onClose();
    if (onNavigateToDashboard) {
      onNavigateToDashboard('/admin-console', item.id);
    }
  };

  return (
    <View
      style={{
        position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.6)', zIndex: 999,
        justifyContent: 'flex-start', alignItems: 'center', paddingTop: 120,
        ...(Platform.OS === 'web' ? { backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)' } : {}),
      } as any}
      data-testid="search-modal-overlay" testID="search-modal-overlay"
      role="dialog"
      aria-modal={true}
      aria-label="Command palette search"
    >
      <TouchableOpacity accessibilityLabel="Close search" accessibilityRole="button"
        style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
        onPress={onClose}
        activeOpacity={1}
      />
      <View style={{
        width: Math.min(520, width - 40), backgroundColor: THEME.card,
        borderRadius: 16, borderWidth: 1, borderColor: THEME.border, overflow: 'hidden',
        ...(Platform.OS === 'web' ? { boxShadow: '0 25px 50px rgba(0,0,0,0.5)' } : {}),
      } as any} data-testid="search-modal" testID="search-modal">
        {/* Search Input */}
        <View style={{ flexDirection: 'row', alignItems: 'center', padding: 16, borderBottomWidth: 1, borderBottomColor: THEME.border, gap: 12 }}>
          <Ionicons name="search" size={20} color={THEME.primary} />
          <TextInput
            ref={searchInputRef}
            style={{ flex: 1, fontSize: 16, color: THEME.text, fontWeight: '500', ...(Platform.OS === 'web' ? { outline: 'none', boxShadow: '0 0 0 2px transparent' } : {}) } as any}
            placeholder="Search tabs..."
            placeholderTextColor={THEME.textMuted}
            value={searchQuery}
            onChangeText={setSearchQuery}
            autoFocus
            data-testid="search-input" testID="search-input"
          />
          <View style={{ flexDirection: 'row', gap: 3 }}>
            <Text style={{ fontSize: 9, color: THEME.textMuted, backgroundColor: THEME.border, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 3, fontWeight: '700' }}>ESC</Text>
          </View>
        </View>

        {/* Pinned tabs shortcut hint */}
        {pinnedTabs.length > 0 && !searchQuery && (
          <View style={{ paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: THEME.border }}>
            <Text style={{ fontSize: 10, color: THEME.textMuted, fontWeight: '700', marginBottom: 6 }}>QUICK ACCESS (Press 1-{Math.min(pinnedTabs.length, 9)})</Text>
            {pinnedTabs.slice(0, 9).map((tabId, i) => {
              const item = navItems.find(n => n.id === tabId);
              if (!item) return null;
              return (
                <TouchableOpacity accessibilityLabel="i + 1"
                  key={tabId}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6 }}
                  onPress={() => selectAndClose(tabId)}
                >
                  <Text style={{ fontSize: 11, color: THEME.textMuted, backgroundColor: THEME.border, width: 20, height: 20, textAlign: 'center', lineHeight: 20, borderRadius: 4, fontWeight: '800' }}>{i + 1}</Text>
                  <Ionicons name={item.icon as any} size={14} color={THEME.primary} />
                  <Text style={{ fontSize: 13, color: THEME.text, fontWeight: '600' }}>{item.label}</Text>
                  <Ionicons name="star" size={10} color={THEME.warningText} />
                </TouchableOpacity>
              );
            })}
          </View>
        )}

        {/* Search Results */}
        <ScrollView style={{ maxHeight: 360 }}>
          {searchQuery ? (
            <>
              {/* Executive Dashboard results */}
              {filteredNavItems.length > 0 && (
                <View>
                  <View style={{ paddingHorizontal: 16, paddingTop: 10, paddingBottom: 4 }}>
                    <Text style={{ fontSize: 10, color: THEME.primary, fontWeight: '700', letterSpacing: 0.5 }}>EXECUTIVE DASHBOARD</Text>
                  </View>
                  {filteredNavItems.map((item, idx) => (
                    <TouchableOpacity
                      key={item.id}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(30,45,74,0.25)', backgroundColor: idx === searchIndex ? (globalThis as any).__alphaColor(THEME.primary, '15') : 'transparent' }}
                      onPress={() => selectAndClose(item.id)}
                      data-testid={`search-result-${item.id}`} testID={`search-result-${item.id}`}
                    >
                      <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: idx === searchIndex ? (globalThis as any).__alphaColor(THEME.primary, '25') : THEME.primary + '15', alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={item.icon as any} size={16} color={THEME.primary} />
                      </View>
                      <Text style={{ fontSize: 14, color: THEME.text, fontWeight: idx === searchIndex ? '700' : '600', flex: 1 }}>{item.label}</Text>
                      {pinnedTabs.includes(item.id) && <Ionicons name="star" size={12} color={THEME.warningText} />}
                      {idx === searchIndex ? (
                        <View style={{ flexDirection: 'row', gap: 3 }}>
                          <Text style={{ fontSize: 9, color: THEME.textMuted, backgroundColor: THEME.border, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 3, fontWeight: '700' }}>Enter</Text>
                        </View>
                      ) : (
                        <Ionicons name="return-down-back" size={14} color={THEME.textMuted} />
                      )}
                    </TouchableOpacity>
                  ))}
                </View>
              )}
              {/* Operations Console results (cross-dashboard) */}
              {filteredOpsItems.length > 0 && (
                <View>
                  <View style={{ paddingHorizontal: 16, paddingTop: 10, paddingBottom: 4 }}>
                    <Text style={{ fontSize: 10, color: opsAccent, fontWeight: '700', letterSpacing: 0.5 }}>OPERATIONS CONSOLE</Text>
                  </View>
                  {filteredOpsItems.map((item) => (
                    <TouchableOpacity
                      key={`ops-${item.id}`}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(30,45,74,0.25)' }}
                      onPress={() => selectOpsItem(item)}
                      data-testid={`search-result-ops-${item.id}`} testID={`search-result-ops-${item.id}`}
                    >
                      <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(opsAccent, '20'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={item.icon as any} size={16} color={opsAccent} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 14, color: THEME.text, fontWeight: '600' }}>{item.label}</Text>
                        {item.catLabel && <Text style={{ fontSize: 10, color: THEME.textMuted }}>{item.catLabel}</Text>}
                      </View>
                      <Ionicons name="open-outline" size={13} color={opsAccent} />
                    </TouchableOpacity>
                  ))}
                </View>
              )}
              {filteredNavItems.length === 0 && filteredOpsItems.length === 0 && (
                <View style={{ padding: 24, alignItems: 'center' }}>
                  <Ionicons name="search-outline" size={32} color={THEME.textMuted} />
                  <Text style={{ fontSize: 13, color: THEME.textMuted, marginTop: 8 }}>No tabs match "{searchQuery}"</Text>
                </View>
              )}
            </>
          ) : (
            <View>
              {/* Recently Viewed */}
              {recentlyViewed.length > 0 && (
                <View style={{ paddingHorizontal: 16, paddingTop: 12, paddingBottom: 4 }} data-testid="recently-viewed-section" testID="recently-viewed-section">
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                    <Text style={{ fontSize: 10, color: THEME.textMuted, fontWeight: '700', letterSpacing: 0.5 }}>RECENTLY VIEWED</Text>
                    <TouchableOpacity onPress={clearRecentlyViewed} style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4, backgroundColor: 'rgba(30,45,74,0.38)' }} data-testid="clear-recently-viewed-btn" testID="clear-recently-viewed-btn">
                      <Text style={{ fontSize: 9, color: THEME.textMuted, fontWeight: '600' }}>Clear</Text>
                    </TouchableOpacity>
                  </View>
                  {recentlyViewed.map(tabId => {
                    const item = navItems.find(n => n.id === tabId);
                    if (!item || item.section) return null;
                    return (
                      <TouchableOpacity key={`recent-${tabId}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8, paddingHorizontal: 4, borderRadius: 8 }} onPress={() => selectAndClose(tabId)} data-testid={`recent-item-${tabId}`} testID={`recent-item-${tabId}`}>
                        <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(THEME.primary, '12'), alignItems: 'center', justifyContent: 'center' }}>
                          <Ionicons name={item.icon as any} size={14} color={THEME.primary} />
                        </View>
                        <Text style={{ fontSize: 13, color: THEME.text, fontWeight: '500', flex: 1 }}>{item.label}</Text>
                        <Ionicons name="time-outline" size={12} color={THEME.textMuted} />
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}
              {/* Suggested */}
              {Object.keys(tabFrequency).length > 0 && (() => {
                const suggested = Object.entries(tabFrequency)
                  .filter(([id]) => !recentlyViewed.includes(id) && id !== 'overview')
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 4)
                  .map(([id, count]) => ({ id, count, item: navItems.find(n => n.id === id) }))
                  .filter(sg => sg.item && !sg.item.section);
                if (suggested.length === 0) return null;
                return (
                  <View style={{ paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4 }} data-testid="suggested-section" testID="suggested-section">
                    <Text style={{ fontSize: 10, color: THEME.textMuted, fontWeight: '700', marginBottom: 8, letterSpacing: 0.5 }}>SUGGESTED FOR YOU</Text>
                    {suggested.map(({ id, count, item }) => (
                      <TouchableOpacity key={`suggest-${id}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8, paddingHorizontal: 4, borderRadius: 8 }} onPress={() => selectAndClose(id)} data-testid={`suggested-item-${id}`} testID={`suggested-item-${id}`}>
                        <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(THEME.success, '12'), alignItems: 'center', justifyContent: 'center' }}>
                          <Ionicons name={item!.icon as any} size={14} color={THEME.successText} />
                        </View>
                        <Text style={{ fontSize: 13, color: THEME.text, fontWeight: '500', flex: 1 }}>{item!.label}</Text>
                        <Text style={{ fontSize: 9, color: THEME.textMuted, fontWeight: '600' }}>{count}x</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                );
              })()}
              <View style={{ paddingHorizontal: 16, paddingVertical: 12 }}>
                <Text style={{ fontSize: 10, color: THEME.textMuted, fontWeight: '700', marginBottom: 8 }}>ALL TABS ({navItems.filter(n => !n.section).length + opsItems.length} across both dashboards)</Text>
                <Text style={{ fontSize: 11, color: THEME.textMuted, lineHeight: 18 }}>Start typing to search across Executive Dashboard and Operations Console.</Text>
              </View>
            </View>
          )}
        </ScrollView>

        {/* Footer hints */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 16, padding: 10, borderTopWidth: 1, borderTopColor: THEME.border, backgroundColor: 'rgba(11,17,33,0.5)' }}>
          {[
            { keys: ['Up', 'Down'], label: 'navigate' },
            { keys: ['Enter'], label: 'select' },
            { keys: ['Esc'], label: 'close' },
            { keys: ['1-9'], label: 'pinned' },
          ].map(hint => (
            <View key={hint.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              {hint.keys.map(k => (
                <Text key={k} style={{ fontSize: 9, color: THEME.textMuted, backgroundColor: THEME.border, paddingHorizontal: 4, paddingVertical: 2, borderRadius: 3, fontWeight: '700' }}>{k}</Text>
              ))}
              <Text style={{ fontSize: 9, color: THEME.textMuted }}>{hint.label}</Text>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
