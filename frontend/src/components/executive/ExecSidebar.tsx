import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from '../admin/ExecDashboardPanels';

interface NavItem {
  id: string;
  label: string;
  icon: string;
  section?: boolean;
  route?: string;
}

interface ExecSidebarProps {
  navItems: NavItem[];
  activeSection: string;
  setActiveSection: (id: string) => void;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  isWide: boolean;
  pinnedTabs: string[];
  togglePin: (id: string) => void;
  hoveredNav: string | null;
  setHoveredNav: (id: string | null) => void;
  onSearchOpen: () => void;
  onNavigateBack: () => void;
  onNavigateToRoute: (route: string) => void;
}

export function ExecSidebar({
  navItems, activeSection, setActiveSection, sidebarOpen, setSidebarOpen,
  isWide, pinnedTabs, togglePin, hoveredNav, setHoveredNav,
  onSearchOpen, onNavigateBack, onNavigateToRoute,
}: ExecSidebarProps) {
  const s = useExecStyles();
  const THEME = useExecTheme();
  const now = new Date();

  return (
    <View style={[s.sidebar, !isWide && sidebarOpen && s.sidebarMobile, { display: 'flex', flexDirection: 'column' } as any]} data-testid="admin-sidebar" testID="admin-sidebar">
      <View style={s.sidebarBrand}>
        <View style={s.brandDot} />
        <View>
          <Text style={s.brandName}>RealAICoach</Text>
          <Text style={s.brandSub}>Executive Console</Text>
        </View>
      </View>
      <View style={s.sidebarDivider} />
      {/* Search shortcut */}
      <TouchableOpacity
        style={[s.navItem, { borderWidth: 1, borderColor: THEME.border, borderRadius: 8, marginHorizontal: 10, marginBottom: 8, justifyContent: 'center' }]}
        onPress={onSearchOpen}
        data-testid="search-tabs-btn" testID="search-tabs-btn"
      >
        <Ionicons name="search" size={15} color={THEME.textMuted} />
        <Text style={[s.navLabel, { flex: 1 }]}>Search tabs...</Text>
        <View style={{ flexDirection: 'row', gap: 3 }}>
          <Text style={{ fontSize: 9, color: THEME.textMuted, backgroundColor: THEME.border, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 3, fontWeight: '700', fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }}>
            {Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.platform?.includes('Mac') ? '\u2318' : 'Ctrl'}
          </Text>
          <Text style={{ fontSize: 9, color: THEME.textMuted, backgroundColor: THEME.border, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 3, fontWeight: '700', fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }}>K</Text>
        </View>
      </TouchableOpacity>
      <ScrollView style={{ flex: 1, overflow: 'auto' } as any} showsVerticalScrollIndicator={true}>
        {/* Pinned tabs section */}
        {pinnedTabs.length > 0 && (
          <>
            <Text style={s.sidebarSectionTitle}>PINNED</Text>
            {pinnedTabs.map(tabId => {
              const item = navItems.find(n => n.id === tabId);
              if (!item || item.section) return null;
              const active = tabId === activeSection;
              return (
                <TouchableOpacity accessibilityLabel="item.label"
                  key={`pin-${tabId}`}
                  style={[s.navItem, active && s.navItemActive, { position: 'relative' } as any]}
                  onPress={() => { setActiveSection(tabId); if (!isWide) setSidebarOpen(false); }}
                  {...(Platform.OS === 'web' ? { onMouseEnter: () => setHoveredNav(`pin-${tabId}`), onMouseLeave: () => setHoveredNav(null) } : {})}
                >
                  <Ionicons name={item.icon as any} size={17} color={active ? THEME.primary : THEME.textMuted} />
                  <Text style={[s.navLabel, active && s.navLabelActive, { flex: 1 }]}>{item.label}</Text>
                  <TouchableOpacity accessibilityLabel="star button" onPress={(e) => { e.stopPropagation(); togglePin(tabId); }} style={{ padding: 4 }}>
                    <Ionicons name="star" size={12} color={THEME.warningText} />
                  </TouchableOpacity>
                  {active && <View style={s.activeIndicator} />}
                </TouchableOpacity>
              );
            })}
            <View style={[s.sidebarDivider, { marginVertical: 8 }]} />
          </>
        )}

        <Text style={s.sidebarSectionTitle}>NAVIGATION</Text>
        {navItems.map(item => {
          if (item.section) {
            return <Text key={item.id} style={[s.sidebarSectionTitle, { marginTop: 16 }]}>{item.label}</Text>;
          }
          const active = item.id === activeSection;
          const isPinned = pinnedTabs.includes(item.id);
          const isHovered = hoveredNav === item.id;
          return (
            <TouchableOpacity accessibilityLabel="Route in exec sidebar button"
              key={item.id}
              style={[s.navItem, active && s.navItemActive]}
              onPress={() => {
                if (item.route) { onNavigateToRoute(item.route); return; }
                setActiveSection(item.id); if (!isWide) setSidebarOpen(false);
              }}
              {...(Platform.OS === 'web' ? { onMouseEnter: () => setHoveredNav(item.id), onMouseLeave: () => setHoveredNav(null) } : {})}
              data-testid={`admin-nav-${item.id}`} testID={`admin-nav-${item.id}`}
            >
              <Ionicons name={item.icon as any} size={17} color={active ? THEME.primary : THEME.textMuted} />
              <Text style={[s.navLabel, active && s.navLabelActive, { flex: 1 }]}>{item.label}</Text>
              {(isHovered || isPinned) && (
                <TouchableOpacity accessibilityLabel="Stop propagation in exec sidebar button" onPress={(e) => { e.stopPropagation(); togglePin(item.id); }} style={{ padding: 4, opacity: isPinned ? 1 : 0.4 }}>
                  <Ionicons name={isPinned ? 'star' : 'star-outline'} size={12} color={isPinned ? THEME.warning : THEME.textMuted} />
                </TouchableOpacity>
              )}
              {active && <View style={s.activeIndicator} />}
            </TouchableOpacity>
          );
        })}
      </ScrollView>
      <View style={s.sidebarDivider} />
      <TouchableOpacity
        style={[s.navItem, { backgroundColor: 'rgba(59,130,246,0.08)', borderRadius: 8, marginHorizontal: 10, marginBottom: 4 }]}
        onPress={() => onNavigateToRoute('/admin-console')}
        data-testid="admin-nav-ops-console" testID="admin-nav-ops-console"
      >
        <Ionicons name="build" size={17} color={THEME.primary} />
        <Text style={[s.navLabel, { color: THEME.primary, fontWeight: '600' }]}>Operations Console</Text>
        <Ionicons name="open-outline" size={13} color={THEME.primary} />
      </TouchableOpacity>
      <TouchableOpacity style={s.navItem} onPress={onNavigateBack} data-testid="admin-nav-user-app" testID="admin-nav-user-app">
        <Ionicons name="arrow-back-circle" size={17} color={THEME.textMuted} />
        <Text style={s.navLabel}>Back to App</Text>
      </TouchableOpacity>
      <View style={s.sidebarFooter}>
        <Text style={s.footerText}>v2.0 Enterprise</Text>
        <Text style={s.footerText}>{now.toLocaleDateString()}</Text>
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
