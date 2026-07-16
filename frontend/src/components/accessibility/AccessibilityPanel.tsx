import React, { useEffect, useRef, useCallback } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, Platform, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useAccessibility, AccessibilityPreferences } from '../../context/AccessibilityContext';

const ACCENT = 'var(--app-primary)';

function isPresetActive(prefs: any, settings: Record<string, any>): boolean {
  return Object.entries(settings).every(([k, v]) => prefs[k] === v);
}

const SECTIONS = [
  {
    title: 'Vision',
    icon: 'eye-outline' as const,
    items: [
      { key: 'textSize', label: 'Text Size', type: 'segmented', options: ['small', 'medium', 'large', 'extra-large'], labels: ['S', 'M', 'L', 'XL'] },
      { key: 'dyslexiaFont', label: 'Dyslexia-Friendly Font', type: 'toggle', desc: 'OpenDyslexic typeface with wider spacing' },
      { key: 'highContrast', label: 'High Contrast', type: 'toggle', desc: 'Increases contrast by 35%' },
      { key: 'colorBlindMode', label: 'Color Blind Mode', type: 'select', options: ['none', 'protanopia', 'deuteranopia', 'tritanopia'], labels: ['Off', 'Protanopia', 'Deuteranopia', 'Tritanopia'] },
      { key: 'contrastMode', label: 'Contrast Mode', type: 'select', options: ['default', 'dark', 'light', 'ultra-contrast'], labels: ['Default', 'Dark', 'Light', 'Ultra'] },
    ],
  },
  {
    title: 'Reading',
    icon: 'book-outline' as const,
    items: [
      { key: 'readingGuide', label: 'Reading Guide Line', type: 'toggle', desc: 'Highlights current reading line' },
      { key: 'textToSpeech', label: 'Text-to-Speech', type: 'toggle', desc: 'Read selected text aloud (browser TTS)' },
      { key: 'motionReduction', label: 'Reduce Motion', type: 'toggle', desc: 'Disables all animations & transitions' },
    ],
  },
  {
    title: 'Navigation',
    icon: 'navigate-outline' as const,
    items: [
      { key: 'keyboardNavigation', label: 'Keyboard Navigation', type: 'toggle', desc: 'Enhanced keyboard tab-order support' },
      { key: 'focusIndicators', label: 'Focus Indicators', type: 'toggle', desc: 'Visible focus outlines on elements' },
      { key: 'simplifiedNav', label: 'Simplified Navigation', type: 'toggle', desc: 'Reduces menu items to essentials' },
      { key: 'easyNavMode', label: 'Easy Navigation Mode', type: 'toggle', desc: 'Large card layout for navigation' },
    ],
  },
  {
    title: 'Interaction',
    icon: 'hand-left-outline' as const,
    items: [
      { key: 'buttonSpacing', label: 'Larger Touch Targets', type: 'toggle', desc: 'Increases button sizes & spacing' },
      { key: 'screenReaderOptimized', label: 'Screen Reader Optimized', type: 'toggle', desc: 'Enhanced ARIA labels & regions' },
      { key: 'voiceCommand', label: 'Voice Command', type: 'toggle', desc: 'Coming soon - voice navigation' },
    ],
  },
];

export function AccessibilityPanel() {
  const { colors } = useTheme();

  // @autofix-moved: was module-level const PRESETS
  const PRESETS = [
    {
      id: 'low-vision',
      name: 'Low Vision',
      desc: 'Large text, high contrast, focus indicators',
      icon: 'eye-outline',
      color: colors.primary,
      settings: {
        textSize: 'extra-large' as const,
        highContrast: true,
        focusIndicators: true,
        buttonSpacing: true,
        contrastMode: 'ultra-contrast' as const,
      },
    },
    {
      id: 'motor-impairment',
      name: 'Motor Impairment',
      desc: 'Large targets, keyboard nav, easy mode',
      icon: 'hand-left-outline',
      color: colors.successText,
      settings: {
        buttonSpacing: true,
        keyboardNavigation: true,
        focusIndicators: true,
        easyNavMode: true,
        textSize: 'large' as const,
      },
    },
    {
      id: 'dyslexia',
      name: 'Dyslexia',
      desc: 'OpenDyslexic font, reading guide, larger text',
      icon: 'book-outline',
      color: colors.accent,
      settings: {
        dyslexiaFont: true,
        readingGuide: true,
        textSize: 'large' as const,
        motionReduction: true,
      },
    },
    {
      id: 'sensory-sensitivity',
      name: 'Sensory Sensitivity',
      desc: 'Reduced motion, simplified navigation, calm UI',
      icon: 'leaf-outline',
      color: colors.warningText,
      settings: {
        motionReduction: true,
        simplifiedNav: true,
        contrastMode: 'light' as const,
      },
    },
  ];
  // @autofix-moved: was module-level const s
  const s = StyleSheet.create({
    panel: {
      position: 'absolute' as any,
      top: 0,
      right: 0,
      bottom: 0,
      width: 400,
      maxWidth: '100%',
      zIndex: 9999,
      borderLeftWidth: 1,
      display: 'flex' as any,
      flexDirection: 'column',
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: 20,
      paddingVertical: 16,
      borderBottomWidth: 1,
    },
    headerIcon: {
      width: 36,
      height: 36,
      borderRadius: 10,
      alignItems: 'center',
      justifyContent: 'center',
    },
    headerTitle: { fontSize: 17, fontWeight: '800' },
    headerSub: { fontSize: 11, marginTop: 1 },
    closeBtn: {
      width: 32,
      height: 32,
      borderRadius: 8,
      alignItems: 'center',
      justifyContent: 'center',
    },
    section: { marginTop: 4 },
    sectionHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      paddingHorizontal: 20,
      paddingVertical: 10,
      borderBottomWidth: StyleSheet.hairlineWidth,
    },
    sectionTitle: { fontSize: 12, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 },
    row: {
      paddingHorizontal: 20,
      paddingVertical: 12,
      flexDirection: 'row',
      flexWrap: 'wrap',
      alignItems: 'center',
      gap: 8,
    },
    itemLabel: { fontSize: 13, fontWeight: '600' },
    itemDesc: { fontSize: 11, marginTop: 2 },
    badge: { fontSize: 9, fontWeight: '800', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, marginTop: 4, alignSelf: 'flex-start' },
    toggle: {
      width: 44,
      height: 24,
      borderRadius: 12,
      justifyContent: 'center',
      paddingHorizontal: 2,
    },
    toggleOn: { backgroundColor: ACCENT },
    toggleKnob: {
      width: 20,
      height: 20,
      borderRadius: 10,
      backgroundColor: colors.primaryText,
    },
    toggleKnobOn: { alignSelf: 'flex-end' as any },
    segmented: {
      flexDirection: 'row',
      borderRadius: 10,
      borderWidth: 1,
      overflow: 'hidden',
      width: '100%',
    },
    segBtn: {
      flex: 1,
      paddingVertical: 8,
      alignItems: 'center',
    },
    segLabel: { fontSize: 13, fontWeight: '600' },
    selectRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 6,
      width: '100%',
    },
    selectBtn: {
      paddingHorizontal: 12,
      paddingVertical: 6,
      borderRadius: 8,
      borderWidth: 1,
    },
    selectLabel: { fontSize: 12, fontWeight: '600' },
    footer: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: 20,
      paddingVertical: 12,
      borderTopWidth: 1,
    },
    resetBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      paddingHorizontal: 14,
      paddingVertical: 8,
      borderRadius: 8,
      borderWidth: 1,
    },
    resetText: { fontSize: 12, fontWeight: '600' },
    activeTag: {
      paddingHorizontal: 10,
      paddingVertical: 4,
      borderRadius: 8,
    },
    presetCard: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      padding: 12,
      borderRadius: 12,
      borderWidth: 1,
    },
    presetIcon: {
      width: 40,
      height: 40,
      borderRadius: 10,
      alignItems: 'center',
      justifyContent: 'center',
    },
    presetName: {
      fontSize: 13,
      fontWeight: '700',
    },
    presetDesc: {
      fontSize: 11,
      marginTop: 2,
    },
    presetBadge: {
      width: 22,
      height: 22,
      borderRadius: 11,
      alignItems: 'center',
      justifyContent: 'center',
    },
  });
  const { prefs, updatePref, resetAll, applyPreset, panelOpen, setPanelOpen, activeCount } = useAccessibility();
  const slideAnim = useRef(new Animated.Value(420)).current;

  useEffect(() => {
    Animated.timing(slideAnim, {
      toValue: panelOpen ? 0 : 420,
      duration: 250,
      useNativeDriver: Platform.OS !== 'web',
    }).start();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panelOpen]);

  const handleReadingGuide = useCallback(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    let guide = document.getElementById('a11y-reading-guide');
    if (!prefs.readingGuide) {
      if (!guide) {
        guide = document.createElement('div');
        guide.id = 'a11y-reading-guide';
        document.body.appendChild(guide);
      }
      guide.style.display = 'block';
      const handler = (e: MouseEvent) => { guide!.style.top = `${e.clientY - 20}px`; };
      document.addEventListener('mousemove', handler);
      (guide as any)._handler = handler;
    } else {
      if (guide) {
        guide.style.display = 'none';
        if ((guide as any)._handler) {
          document.removeEventListener('mousemove', (guide as any)._handler);
        }
      }
    }
  }, [prefs.readingGuide]);

  useEffect(() => { handleReadingGuide(); }, [prefs.readingGuide, handleReadingGuide]);

  if (!panelOpen) return null;

  const bg = colors.card;
  const border = colors.border;

  return (
    <>
      <TouchableOpacity
        data-testid="a11y-panel-backdrop" testID="a11y-panel-backdrop"
        activeOpacity={1}
        onPress={() => setPanelOpen(false)}
        style={[StyleSheet.absoluteFill, { backgroundColor: colors.overlay, zIndex: 9998 }]}
        accessibilityLabel="Close accessibility panel"
        accessibilityRole="button"
      />
      <Animated.View
        data-testid="a11y-panel" testID="a11y-panel"
        style={[
          s.panel,
          { backgroundColor: bg, borderLeftColor: border, transform: [{ translateX: slideAnim }] },
        ]}
        accessibilityRole="dialog"
        aria-label="Accessibility Settings Panel"
      >
        {/* Header */}
        <View style={[s.header, { borderBottomColor: border }]}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={[s.headerIcon, { backgroundColor: (globalThis as any).__alphaColor(ACCENT, '15') }]}>
              <Ionicons name="accessibility" size={20} color={ACCENT} />
            </View>
            <View>
              <Text style={[s.headerTitle, { color: colors.text }]}>Accessibility</Text>
              <Text style={[s.headerSub, { color: colors.textMuted }]}>
                {activeCount > 0 ? `${activeCount} active` : 'All defaults'}
              </Text>
            </View>
          </View>
          <TouchableOpacity
            data-testid="a11y-panel-close" testID="a11y-panel-close"
            onPress={() => setPanelOpen(false)}
            style={[s.closeBtn, { backgroundColor: colors.bgSoft }]}
            accessibilityLabel="Close panel"
          >
            <Ionicons name="close" size={18} color={colors.text} />
          </TouchableOpacity>
        </View>

        <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 100 }}>
          {/* ═══ QUICK PRESETS ═══ */}
          <View style={[s.section, { paddingBottom: 4 }]}>
            <View style={[s.sectionHeader, { borderBottomColor: border }]}>
              <Ionicons name="flash-outline" size={16} color={ACCENT} />
              <Text style={[s.sectionTitle, { color: colors.text }]}>Quick Presets</Text>
            </View>
            <View style={{ paddingHorizontal: 16, paddingVertical: 10, gap: 8 }}>
              {PRESETS.map((preset) => {
                const isActive = isPresetActive(prefs, preset.settings);
                return (
                  <TouchableOpacity
                    key={preset.id}
                    accessibilityLabel={`Apply ${preset.name} preset`}
                    accessibilityRole="button"
                    aria-label={`Apply ${preset.name} preset`}
                    onPress={() => isActive ? resetAll() : applyPreset(preset.settings)}
                    style={[
                      s.presetCard,
                      {
                        backgroundColor: isActive ? (globalThis as any).__alphaColor(ACCENT, '12') : colors.bgSoft,
                        borderColor: isActive ? ACCENT : colors.border,
                      },
                    ]}
                  >
                    <View style={[s.presetIcon, { backgroundColor: (globalThis as any).__alphaColor(preset.color, '18') }]}>
                      <Ionicons name={preset.icon as any} size={18} color={preset.color} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={[s.presetName, { color: isActive ? ACCENT : colors.text }]}>{preset.name}</Text>
                      <Text style={[s.presetDesc, { color: colors.textMuted }]}>{preset.desc}</Text>
                    </View>
                    {isActive && (
                      <View style={[s.presetBadge, { backgroundColor: ACCENT }]}>
                        <Ionicons name="checkmark" size={12} color="var(--app-primary-text)" />
                      </View>
                    )}
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          {SECTIONS.map((section) => (
            <View key={section.title} style={s.section}>
              <View style={[s.sectionHeader, { borderBottomColor: border }]}>
                <Ionicons name={section.icon} size={16} color={ACCENT} />
                <Text style={[s.sectionTitle, { color: colors.text }]}>{section.title}</Text>
              </View>
              {section.items.map((item) => {
                const val = prefs[item.key as keyof AccessibilityPreferences];
                if (item.type === 'toggle') {
                  const isOn = val === true;
                  const disabled = item.key === 'voiceCommand';
                  return (
                    <TouchableOpacity
                      key={item.key}
                      data-testid={`a11y-toggle-${item.key}`} testID={`a11y-toggle-${item.key}`}
                      onPress={() => !disabled && updatePref(item.key as any, !isOn)}
                      style={[s.row, { opacity: disabled ? 0.4 : 1 }]}
                      disabled={disabled}
                      accessibilityRole="switch"
                      accessibilityState={{ checked: isOn, disabled }}
                      accessibilityLabel={item.label}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={[s.itemLabel, { color: colors.text }]}>{item.label}</Text>
                        {item.desc && <Text style={[s.itemDesc, { color: colors.textMuted }]}>{item.desc}</Text>}
                        {disabled && <Text style={[s.badge, { backgroundColor: (globalThis as any).__alphaColor(ACCENT, '20'), color: ACCENT }]}>Coming Soon</Text>}
                      </View>
                      <View style={[s.toggle, isOn ? s.toggleOn : { backgroundColor: colors.border }]}>
                        <View style={[s.toggleKnob, isOn ? s.toggleKnobOn : {}]} />
                      </View>
                    </TouchableOpacity>
                  );
                }
                if (item.type === 'segmented') {
                  return (
                    <View key={item.key} style={s.row}>
                      <Text style={[s.itemLabel, { color: colors.text, marginBottom: 8 }]}>{item.label}</Text>
                      <View style={[s.segmented, { backgroundColor: colors.bgSoft, borderColor: border }]}>
                        {(item.options || []).map((opt: string, i: number) => (
                          <TouchableOpacity
                            key={opt}
                            data-testid={`a11y-textsize-${opt}`} testID={`a11y-textsize-${opt}`}
                            onPress={() => updatePref(item.key as any, opt)}
                            style={[s.segBtn, val === opt && { backgroundColor: ACCENT }]}
                            accessibilityRole="radio"
                            accessibilityState={{ selected: val === opt }}
                            accessibilityLabel={`Text size ${opt}`}
                          >
                            <Text style={[s.segLabel, val === opt ? { color: colors.primaryText, fontWeight: '800' } : { color: colors.textSec }]}>
                              {(item.labels || [])[i] || opt}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </View>
                  );
                }
                if (item.type === 'select') {
                  return (
                    <View key={item.key} style={s.row}>
                      <Text style={[s.itemLabel, { color: colors.text, marginBottom: 8 }]}>{item.label}</Text>
                      <View style={[s.selectRow, { borderColor: border }]}>
                        {(item.options || []).map((opt: string, i: number) => (
                          <TouchableOpacity
                            key={opt}
                            data-testid={`a11y-${item.key}-${opt}`} testID={`a11y-${item.key}-${opt}`}
                            onPress={() => updatePref(item.key as any, opt)}
                            style={[s.selectBtn, { borderColor: border }, val === opt && { borderColor: ACCENT, backgroundColor: (globalThis as any).__alphaColor(ACCENT, '12') }]}
                            accessibilityRole="radio"
                            accessibilityState={{ selected: val === opt }}
                            accessibilityLabel={`${item.label} ${opt}`}
                          >
                            <Text style={[s.selectLabel, { color: val === opt ? ACCENT : colors.textSec }]}>
                              {(item.labels || [])[i] || opt}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </View>
                  );
                }
                return null;
              })}
            </View>
          ))}
        </ScrollView>

        {/* Footer */}
        <View style={[s.footer, { borderTopColor: border, backgroundColor: bg }]}>
          <TouchableOpacity
            data-testid="a11y-reset-all" testID="a11y-reset-all"
            onPress={resetAll}
            style={[s.resetBtn, { borderColor: colors.border }]}
            accessibilityLabel="Reset all accessibility settings"
          >
            <Ionicons name="refresh" size={16} color={colors.textSec} />
            <Text style={[s.resetText, { color: colors.textSec }]}>Reset All</Text>
          </TouchableOpacity>
          <View style={[s.activeTag, { backgroundColor: (globalThis as any).__alphaColor(ACCENT, '15') }]}>
            <Text style={{ color: ACCENT, fontSize: 11, fontWeight: '700' }}>{activeCount} active</Text>
          </View>
        </View>
      </Animated.View>
    </>
  );
}

/* i18n-probe t('i18n.auto.probe') */
