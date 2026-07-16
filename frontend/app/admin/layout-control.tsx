/**
 * Admin → Layout & UI Control
 *
 * Allows administrators to configure Global Layout System (GLS) parameters
 * that propagate across ALL platform pages. Changes are GPS-governed and
 * logged via the GPS event system.
 */
import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, Platform, useWindowDimensions, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../src/context/ThemeContext';
import { useLanguage } from '../../src/i18n/LanguageContext';
import api from '../../src/services/api';

interface LayoutConfig {
  max_width: number;
  max_width_wide: number;
  max_width_narrow: number;
  padding_mobile: number;
  padding_tablet: number;
  padding_desktop: number;
  padding_large: number;
  section_padding_mobile: number;
  section_padding_tablet: number;
  section_padding_desktop: number;
  breakpoint_tablet: number;
  breakpoint_desktop: number;
  breakpoint_large: number;
  layout_mode: string;
  responsive_enabled: boolean;
}

const FIELD_GROUPS = [
  {
    label: 'Container Widths',
    icon: 'resize-outline' as const,
    fields: [
      { key: 'max_width', label: 'Default Max Width', unit: 'px', min: 800, max: 1920 },
      { key: 'max_width_wide', label: 'Wide Max Width', unit: 'px', min: 1200, max: 2560 },
      { key: 'max_width_narrow', label: 'Narrow Max Width', unit: 'px', min: 600, max: 1200 },
    ],
  },
  {
    label: 'Horizontal Padding',
    icon: 'swap-horizontal-outline' as const,
    fields: [
      { key: 'padding_mobile', label: 'Mobile', unit: 'px', min: 8, max: 40 },
      { key: 'padding_tablet', label: 'Tablet', unit: 'px', min: 16, max: 60 },
      { key: 'padding_desktop', label: 'Desktop', unit: 'px', min: 20, max: 80 },
      { key: 'padding_large', label: 'Large Screen', unit: 'px', min: 24, max: 120 },
    ],
  },
  {
    label: 'Section Vertical Spacing',
    icon: 'swap-vertical-outline' as const,
    fields: [
      { key: 'section_padding_mobile', label: 'Mobile', unit: 'px', min: 24, max: 120 },
      { key: 'section_padding_tablet', label: 'Tablet', unit: 'px', min: 32, max: 160 },
      { key: 'section_padding_desktop', label: 'Desktop', unit: 'px', min: 48, max: 200 },
    ],
  },
  {
    label: 'Breakpoints',
    icon: 'phone-landscape-outline' as const,
    fields: [
      { key: 'breakpoint_tablet', label: 'Tablet', unit: 'px', min: 600, max: 900 },
      { key: 'breakpoint_desktop', label: 'Desktop', unit: 'px', min: 900, max: 1200 },
      { key: 'breakpoint_large', label: 'Large Screen', unit: 'px', min: 1200, max: 1920 },
    ],
  },
];

export default function AdminLayoutControl() {
  const { colors, darkMode } = useTheme();
  const { t } = useLanguage();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  const [config, setConfig] = useState<LayoutConfig | null>(null);
  const [original, setOriginal] = useState<LayoutConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await api.get('/gps/admin/layout-config');
      setConfig(data);
      setOriginal(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to load layout config');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  const hasChanges = useMemo(() => {
    if (!config || !original) return false;
    return JSON.stringify(config) !== JSON.stringify(original);
  }, [config, original]);

  const handleSave = async () => {
    if (!config || !hasChanges) return;
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const { data } = await api.put('/gps/admin/layout-config', config);
      setOriginal(data.config || config);
      setSuccess('Layout configuration saved. Changes propagate globally.');
      setTimeout(() => setSuccess(''), 5000);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to save layout config');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (original) setConfig({ ...original });
  };

  const updateField = (key: string, value: number) => {
    if (!config) return;
    setConfig({ ...config, [key]: value });
  };

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ marginTop: 12, color: colors.textMuted, fontSize: 14 }}>Loading layout config...</Text>
      </View>
    );
  }

  if (!config) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }}>
        <Ionicons name="warning-outline" size={40} color={colors.error} />
        <Text style={{ marginTop: 12, color: colors.error, fontSize: 14 }}>{error || 'Failed to load'}</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={{ padding: isDesktop ? 32 : 18, maxWidth: 960, width: '100%', alignSelf: 'center' }}
      data-testid="admin-layout-control"
    >
      {/* Header */}
      <View style={{ marginBottom: 28 }} data-testid="admin-layout-header">
        <Text style={{ fontSize: 22, fontWeight: '800', color: colors.text, letterSpacing: -0.5 }}>
          {t('admin.layout.title', 'Layout & UI Control')}
        </Text>
        <Text style={{ fontSize: 14, color: colors.textMuted, marginTop: 6, lineHeight: 22 }}>
          {t('admin.layout.subtitle', 'Configure the Global Layout System (GLS). Changes propagate across all platform pages via GPS.')}
        </Text>
      </View>

      {/* Status banners */}
      {error ? (
        <View style={{ padding: 14, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.error, '15'), marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '30') }}>
          <Text style={{ color: colors.error, fontSize: 13, fontWeight: '600' }}>{error}</Text>
        </View>
      ) : null}
      {success ? (
        <View style={{ padding: 14, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15'), marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '30') }}>
          <Text style={{ color: colors.primary, fontSize: 13, fontWeight: '600' }}>{success}</Text>
        </View>
      ) : null}

      {/* Layout Mode */}
      <View style={{
        backgroundColor: colors.card, borderRadius: 14, padding: 20, marginBottom: 16,
        borderWidth: 1, borderColor: colors.border,
      }} data-testid="layout-mode-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <Ionicons name="grid-outline" size={18} color={colors.primary} />
          <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>Layout Mode</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 10 }}>
          {['centered', 'full-width', 'compact'].map((mode) => (
            <TouchableOpacity
              key={mode}
              data-testid={`layout-mode-${mode}`}
              onPress={() => setConfig({ ...config, layout_mode: mode })}
              style={{
                flex: 1,
                paddingVertical: 12, paddingHorizontal: 14,
                borderRadius: 10, alignItems: 'center',
                borderWidth: 1.5,
                borderColor: config.layout_mode === mode ? colors.primary : colors.border,
                backgroundColor: config.layout_mode === mode ? (globalThis as any).__alphaColor(colors.primary, '10') : 'transparent',
              }}
            >
              <Text style={{
                fontSize: 12, fontWeight: '700',
                color: config.layout_mode === mode ? colors.primary : colors.textMuted,
                textTransform: 'capitalize',
              }}>{mode}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Responsive Toggle */}
      <View style={{
        backgroundColor: colors.card, borderRadius: 14, padding: 20, marginBottom: 16,
        borderWidth: 1, borderColor: colors.border,
        flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
      }} data-testid="responsive-toggle-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Ionicons name="phone-portrait-outline" size={18} color={colors.primary} />
          <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>Responsive Design</Text>
        </View>
        <TouchableOpacity
          data-testid="responsive-toggle-btn"
          onPress={() => setConfig({ ...config, responsive_enabled: !config.responsive_enabled })}
          style={{
            width: 52, height: 28, borderRadius: 14,
            backgroundColor: config.responsive_enabled ? colors.primary : colors.border,
            justifyContent: 'center', padding: 3,
          }}
        >
          <View style={{
            width: 22, height: 22, borderRadius: 11, backgroundColor: colors.primaryText,
            alignSelf: config.responsive_enabled ? 'flex-end' : 'flex-start',
            ...(Platform.OS === 'web' ? { transition: 'all 0.2s ease' } as any : {}),
          }} />
        </TouchableOpacity>
      </View>

      {/* Field Groups */}
      {FIELD_GROUPS.map((group) => (
        <View key={group.label} style={{
          backgroundColor: colors.card, borderRadius: 14, padding: 20, marginBottom: 16,
          borderWidth: 1, borderColor: colors.border,
        }} data-testid={`layout-group-${group.label.toLowerCase().replace(/\s/g, '-')}`}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
            <Ionicons name={group.icon} size={18} color={colors.primary} />
            <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>{group.label}</Text>
          </View>
          {group.fields.map((field) => (
            <View key={field.key} style={{ marginBottom: 14 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
                <Text style={{ fontSize: 13, color: colors.textMuted, fontWeight: '500' }}>{field.label}</Text>
                <Text style={{ fontSize: 13, color: colors.text, fontWeight: '700' }}>
                  {(config as any)[field.key]}{field.unit}
                </Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                <Text style={{ fontSize: 11, color: colors.textMuted, width: 40 }}>{field.min}</Text>
                <View style={{ flex: 1, height: 4, backgroundColor: colors.border, borderRadius: 2 }}>
                  <View style={{
                    height: '100%', borderRadius: 2, backgroundColor: colors.primary,
                    width: `${(((config as any)[field.key] - field.min) / (field.max - field.min)) * 100}%`,
                  }} />
                </View>
                <Text style={{ fontSize: 11, color: colors.textMuted, width: 40, textAlign: 'right' }}>{field.max}</Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                <TouchableOpacity
                  data-testid={`layout-field-${field.key}-minus`}
                  onPress={() => updateField(field.key, Math.max(field.min, (config as any)[field.key] - (field.min >= 100 ? 10 : 2)))}
                  style={{ width: 32, height: 32, borderRadius: 8, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }}
                >
                  <Ionicons name="remove" size={16} color={colors.text} />
                </TouchableOpacity>
                <TextInput
                  data-testid={`layout-field-${field.key}-input`}
                  style={{
                    flex: 1, height: 32, borderRadius: 8, borderWidth: 1, borderColor: colors.border,
                    paddingHorizontal: 10, fontSize: 13, fontWeight: '600', color: colors.text,
                    textAlign: 'center', backgroundColor: colors.card,
                  }}
                  value={String((config as any)[field.key])}
                  onChangeText={(txt) => {
                    const num = parseInt(txt, 10);
                    if (!isNaN(num)) updateField(field.key, Math.max(field.min, Math.min(field.max, num)));
                  }}
                  keyboardType="numeric"
                />
                <TouchableOpacity
                  data-testid={`layout-field-${field.key}-plus`}
                  onPress={() => updateField(field.key, Math.min(field.max, (config as any)[field.key] + (field.min >= 100 ? 10 : 2)))}
                  style={{ width: 32, height: 32, borderRadius: 8, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }}
                >
                  <Ionicons name="add" size={16} color={colors.text} />
                </TouchableOpacity>
              </View>
            </View>
          ))}
        </View>
      ))}

      {/* Breakpoint Preview */}
      <View style={{
        backgroundColor: colors.card, borderRadius: 14, padding: 20, marginBottom: 16,
        borderWidth: 1, borderColor: colors.border,
      }} data-testid="breakpoint-preview">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <Ionicons name="desktop-outline" size={18} color={colors.primary} />
          <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>Breakpoint Preview</Text>
        </View>
        <View style={{ height: 40, backgroundColor: (globalThis as any).__alphaColor(colors.border, '40'), borderRadius: 8, overflow: 'hidden', flexDirection: 'row' }}>
          <View style={{ width: `${(config.breakpoint_tablet / config.breakpoint_large) * 100}%`, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '20'), justifyContent: 'center', alignItems: 'center', borderRightWidth: 1, borderRightColor: colors.primary }}>
            <Text style={{ fontSize: 9, fontWeight: '700', color: colors.primary }}>Mobile</Text>
          </View>
          <View style={{ width: `${((config.breakpoint_desktop - config.breakpoint_tablet) / config.breakpoint_large) * 100}%`, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '10'), justifyContent: 'center', alignItems: 'center', borderRightWidth: 1, borderRightColor: colors.primary }}>
            <Text style={{ fontSize: 9, fontWeight: '700', color: colors.primary }}>Tablet</Text>
          </View>
          <View style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '08'), justifyContent: 'center', alignItems: 'center' }}>
            <Text style={{ fontSize: 9, fontWeight: '700', color: colors.primary }}>Desktop+</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
          <Text style={{ fontSize: 10, color: colors.textMuted }}>0px</Text>
          <Text style={{ fontSize: 10, color: colors.textMuted }}>{config.breakpoint_tablet}px</Text>
          <Text style={{ fontSize: 10, color: colors.textMuted }}>{config.breakpoint_desktop}px</Text>
          <Text style={{ fontSize: 10, color: colors.textMuted }}>{config.breakpoint_large}px+</Text>
        </View>
      </View>

      {/* Action Buttons */}
      <View style={{ flexDirection: 'row', gap: 12, marginBottom: 40, marginTop: 8 }}>
        <TouchableOpacity
          data-testid="layout-save-btn"
          disabled={!hasChanges || saving}
          onPress={handleSave}
          style={{
            flex: 1, paddingVertical: 14, borderRadius: 12, alignItems: 'center',
            backgroundColor: hasChanges ? colors.primary : colors.border,
            opacity: saving ? 0.6 : 1,
          }}
        >
          {saving ? (
            <ActivityIndicator size="small" color={colors.primaryText} />
          ) : (
            <Text style={{ fontSize: 14, fontWeight: '700', color: hasChanges ? colors.primaryText : colors.textMuted }}>
              Save Configuration
            </Text>
          )}
        </TouchableOpacity>
        <TouchableOpacity
          data-testid="layout-reset-btn"
          disabled={!hasChanges}
          onPress={handleReset}
          style={{
            paddingVertical: 14, paddingHorizontal: 24, borderRadius: 12, alignItems: 'center',
            borderWidth: 1, borderColor: colors.border,
            opacity: hasChanges ? 1 : 0.5,
          }}
        >
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.textMuted }}>Reset</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}
