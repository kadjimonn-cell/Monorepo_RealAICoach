import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView, ActivityIndicator, Platform, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
const PREVIEW_BASE = {
  bg: 'transparent', bgAlt: 'rgba(15,23,42,0.12)', card: 'rgba(15,23,42,0.08)', surface: 'rgba(15,23,42,0.08)', surfaceHover: 'rgba(15,23,42,0.12)', border: 'rgba(148,163,184,0.22)', borderStrong: 'var(--app-border-strong)',
  text: 'var(--app-text)', textSec: 'var(--app-text-sec)', textMuted: 'var(--app-text-muted)', textDim: 'var(--app-text-muted)',
  primary: 'var(--app-primary)', success: 'var(--app-success)' as any, warning: 'var(--app-warning)' as any, error: 'var(--app-error)' as any,
};
type BrandingSettings = {
  brand_name: string;
  primary_color: string;
  secondary_color: string;
  footer_text: string;
  company_info: string;
  show_qr_code: boolean;
  custom_logo: string | null;
};

const tx = (_key: string, fallback: string) => fallback;

const COLOR_PRESETS = [
  { label: 'Core', mainColor: 'var(--app-primary)', supportColor: 'var(--app-primary)' },
  { label: 'Teal Light', mainColor: 'var(--app-primary)', supportColor: 'var(--app-primary)' },
  { label: 'Deep Teal', mainColor: 'var(--app-primary)', supportColor: 'var(--app-primary)' },
  { label: 'Slate', mainColor: PREVIEW_BASE.textDim, supportColor: 'var(--app-primary)' },
  { label: 'Enterprise', mainColor: 'var(--app-primary)', supportColor: 'var(--app-primary)' },
  { label: 'Calm', mainColor: 'var(--app-primary)', supportColor: 'var(--app-primary)' },
];

function hexToRgb(hex: string): string {
  const h = hex.replace('#', '');
  if (h.length !== 6) return '37, 99, 235';
  return `${parseInt(h.substring(0, 2), 16)}, ${parseInt(h.substring(2, 4), 16)}, ${parseInt(h.substring(4, 6), 16)}`;
}

export default function ReceiptBrandingPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const DEFAULTS: BrandingSettings = {
    brand_name: 'RealAICoach',
    primary_color: colors.primary,
    secondary_color: colors.warning,
    footer_text: 'Thank you for your business!',
    company_info: 'support@realaicoach.app',
    show_qr_code: true,
    custom_logo: null,
  };

  const AC = useAdminTheme();
  const [branding, setBranding] = useState<BrandingSettings>(DEFAULTS);
  const [saved, setSaved] = useState<BrandingSettings>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState('');
  const envReactBase = typeof process !== 'undefined' ? (process.env?.['REACT_APP_BACKEND_URL'] || '') : '';
  const envExpoBase = typeof process !== 'undefined' ? (process.env?.['EXPO_PUBLIC_BACKEND_URL'] || '') : '';
  const backendBaseUrl = (envReactBase || envExpoBase || '').replace(/\/$/, '');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hasChanges = JSON.stringify(branding) !== JSON.stringify(saved);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3000);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/api/admin/receipt-branding');
        if (res.data?.branding) {
          setBranding(res.data.branding);
          setSaved(res.data.branding);
        }
      } catch { /* use defaults */ }
      setLoading(false);
    })();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await api.put('/api/admin/receipt-branding', branding);
      if (res.data?.branding) {
        setSaved(res.data.branding);
        setBranding(res.data.branding);
      }
      showToast('Branding settings saved');
    } catch {
      showToast('Failed to save settings');
    }
    setSaving(false);
  };

  const handleReset = async () => {
    setSaving(true);
    try {
      const res = await api.post('/api/admin/receipt-branding/reset');
      if (res.data?.branding) {
        setSaved(res.data.branding);
        setBranding(res.data.branding);
      }
      showToast('Branding reset to defaults');
    } catch {
      showToast('Failed to reset');
    }
    setSaving(false);
  };

  const handlePreview = async () => {
    setPreviewing(true);
    try {
      const res = await api.post('/api/admin/receipt-branding/preview', branding, { responseType: 'blob' });
      if (Platform.OS === 'web') {
        const blob = new Blob([res.data], { type: 'application/pdf' });
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
      }
      showToast('Preview generated');
    } catch {
      showToast('Failed to generate preview');
    }
    setPreviewing(false);
  };

  const handleLogoUpload = async (file: File) => {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('logo', file);
      const res = await api.post('/api/admin/receipt-branding/logo', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      if (res.data?.branding) {
        setBranding(res.data.branding);
        setSaved(res.data.branding);
      }
      showToast('Logo uploaded successfully');
    } catch (e: any) {
      showToast(e?.response?.data?.detail || 'Failed to upload logo');
    }
    setUploading(false);
  };

  const handleLogoDelete = async () => {
    setUploading(true);
    try {
      const res = await api.delete('/api/admin/receipt-branding/logo');
      if (res.data?.branding) {
        setBranding(res.data.branding);
        setSaved(res.data.branding);
      }
      showToast('Logo removed');
    } catch {
      showToast('Failed to remove logo');
    }
    setUploading(false);
  };

  const onFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleLogoUpload(file);
    e.target.value = '';
  };

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }} data-testid="receipt-branding-loading" testID="receipt-branding-loading">
        <ActivityIndicator size="large" color={'var(--app-primary)'} />
      </View>
    );
  }

  const s = {
    card: { backgroundColor: AC.surface, borderRadius: 12, borderWidth: 1, borderColor: AC.border, padding: 20, marginBottom: 16 } as any,
    label: { fontSize: 12, fontWeight: '600' as const, color: AC.textMuted, marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: 0.5 },
    input: { backgroundColor: AC.surfaceHover || AC.surfaceHover, borderWidth: 1, borderColor: AC.border, borderRadius: 8, padding: 12, fontSize: 14, color: AC.text } as any,
    swatch: (hex: string, active: boolean) => ({
      width: 36, height: 36, borderRadius: 8, backgroundColor: hex,
      borderWidth: active ? 3 : 1, borderColor: active ? AC.text : AC.border, /* @theme-ok deliberate-high-contrast outline on selected color swatch */
      justifyContent: 'center' as const, alignItems: 'center' as const,
    }),
  };

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, paddingBottom: 40 }} data-testid="receipt-branding-panel" testID="receipt-branding-panel">
      {/* Toast */}
      {toast ? (
        <View style={{ position: 'absolute', top: 8, right: 16, left: 16, zIndex: 50, backgroundColor: colors.success, borderRadius: 8, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="checkmark-circle" size={18} color={AC.primaryText} />
          <Text style={{ color: AC.primaryText, fontWeight: '600', fontSize: 13 }}>{toast}</Text>
        </View>
      ) : null}

      {/* Header */}
      <View style={{ marginBottom: 20 }}>
        <Text style={{ fontSize: 20, fontWeight: '700', color: AC.text }} data-testid="receipt-branding-title" testID="receipt-branding-title">{tx('admin.receiptBrandingPanel.auto.text.001', 'Receipt Branding')}</Text>
        <Text style={{ fontSize: 13, color: AC.textMuted, marginTop: 4 }}>{tx('admin.receiptBrandingPanel.auto.text.002', 'Customize how your PDF receipts and invoices look.')}</Text>
      </View>

      {/* Brand Name */}
      <View style={s.card}>
        <Text style={{ fontSize: 15, fontWeight: '600', color: AC.text, marginBottom: 14 }}>{tx('admin.receiptBrandingPanel.auto.text.003', 'Brand Identity')}</Text>
        <Text style={s.label}>{tx('admin.receiptBrandingPanel.auto.text.004', 'Brand Name')}</Text>
        <TextInput
          style={s.input}
          value={branding.brand_name}
          onChangeText={v => setBranding(p => ({ ...p, brand_name: v }))}
          placeholder={tx('admin.receiptBrandingPanel.auto.placeholder.001', 'Your brand name')}
          placeholderTextColor={AC.textMuted}
          data-testid="branding-brand-name-input" testID="branding-brand-name-input"
        />
        <View style={{ marginTop: 14 }}>
          <Text style={s.label}>{tx('admin.receiptBrandingPanel.auto.text.005', 'Company Info (footer)')}</Text>
          <TextInput
            style={s.input}
            value={branding.company_info}
            onChangeText={v => setBranding(p => ({ ...p, company_info: v }))}
            placeholder={tx('admin.receiptBrandingPanel.auto.placeholder.002', 'support@company.com')}
            placeholderTextColor={AC.textMuted}
            data-testid="branding-company-info-input" testID="branding-company-info-input"
          />
        </View>
        <View style={{ marginTop: 14 }}>
          <Text style={s.label}>{tx('admin.receiptBrandingPanel.auto.text.006', 'Footer Message')}</Text>
          <TextInput
            style={s.input}
            value={branding.footer_text}
            onChangeText={v => setBranding(p => ({ ...p, footer_text: v }))}
            placeholder={tx('admin.receiptBrandingPanel.auto.placeholder.003', 'Thank you for your business!')}
            placeholderTextColor={AC.textMuted}
            data-testid="branding-footer-text-input" testID="branding-footer-text-input"
          />
        </View>

        {/* Logo Upload */}
        <View style={{ marginTop: 14 }}>
          <Text style={s.label}>{tx('admin.receiptBrandingPanel.auto.text.007', 'Custom Logo')}</Text>
          {Platform.OS === 'web' && (
            <input aria-label="Text input"
              ref={fileInputRef as any}
              type="file"
              accept="image/*"
              onChange={onFileInputChange as any}
              style={{ display: 'none' }}
            />
          )}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            {branding.custom_logo ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <View style={{ width: 56, height: 56, borderRadius: 8, borderWidth: 1, borderColor: AC.border, overflow: 'hidden', backgroundColor: AC.text, justifyContent: 'center', alignItems: 'center' }}>
                  <Image accessibilityLabel={tx('admin.receiptBrandingPanel.auto.accessibility.001', 'Branding logo preview')}
                    source={{ uri: `${backendBaseUrl}${branding.custom_logo}` }}
                    style={{ width: 52, height: 52 }}
                    resizeMode="contain"
                    data-testid="branding-logo-preview" testID="branding-logo-preview"
                  />
                </View>
                <View style={{ gap: 6 }}>
                  <TouchableOpacity
                    onPress={() => fileInputRef.current?.click?.()}
                    disabled={uploading}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: colors.background, borderWidth: 1, borderColor: AC.border }}
                    data-testid="branding-logo-change-btn" testID="branding-logo-change-btn"
                  >
                    {uploading ? <ActivityIndicator size="small" color={AC.text} /> : <Ionicons name="swap-horizontal" size={14} color={AC.text} />}
                    <Text style={{ fontSize: 12, color: AC.text, fontWeight: '600' }}>{tx('admin.receiptBrandingPanel.auto.text.008', 'Change')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={handleLogoDelete}
                    disabled={uploading}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6 }}
                    data-testid="branding-logo-remove-btn" testID="branding-logo-remove-btn"
                  >
                    <Ionicons name="trash" size={14} color={'var(--app-error)'} />
                    <Text style={{ fontSize: 12, color: colors.error, fontWeight: '600' }}>{tx('admin.receiptBrandingPanel.auto.text.009', 'Remove')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ) : (
              <TouchableOpacity aria-label="Upload branding logo"
                onPress={() => fileInputRef.current?.click?.()}
                disabled={uploading}
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 12,
                  borderRadius: 8, borderWidth: 1, borderStyle: 'dashed', borderColor: AC.border,
                  backgroundColor: colors.background, opacity: uploading ? 0.6 : 1,
                }}
                data-testid="branding-logo-upload-btn" testID="branding-logo-upload-btn"
              >
                {uploading ? <ActivityIndicator size="small" color={'var(--app-primary)'} /> : <Ionicons name="cloud-upload" size={18} color={'var(--app-primary)'} />}
                <View>
                  <Text style={{ fontSize: 13, fontWeight: '600', color: AC.text }}>{tx('admin.receiptBrandingPanel.auto.text.010', 'Upload Logo')}</Text>
                  <Text style={{ fontSize: 11, color: AC.textMuted }}>{tx('admin.receiptBrandingPanel.auto.text.011', 'PNG, JPG up to 2MB')}</Text>
                </View>
              </TouchableOpacity>
            )}
          </View>
        </View>
      </View>

      {/* Color Palette */}
      <View style={s.card}>
        <Text style={{ fontSize: 15, fontWeight: '600', color: AC.text, marginBottom: 14 }}>{tx('admin.receiptBrandingPanel.auto.text.012', 'Color Palette')}</Text>

        {/* Presets */}
        <Text style={s.label}>{tx('admin.receiptBrandingPanel.auto.text.013', 'Quick Presets')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {COLOR_PRESETS.map(p => {
            const active = branding.primary_color === p.mainColor && branding.secondary_color === p.supportColor;
            return (
              <TouchableOpacity aria-label={`Apply ${p.label} color preset`}
                key={p.label}
                onPress={() => setBranding(prev => ({ ...prev, primary_color: p.mainColor, secondary_color: p.supportColor }))}
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8,
                  borderRadius: 8, borderWidth: 1, backgroundColor: active ? `rgba(${hexToRgb(p.mainColor)}, 0.1)` : colors.background,
                  borderColor: active ? p.mainColor : AC.border,
                }}
                data-testid={`branding-preset-${p.label.toLowerCase()}`} testID={`branding-preset-${p.label.toLowerCase()}`}
              >
                <View style={{ width: 14, height: 14, borderRadius: 4, backgroundColor: p.mainColor }} />
                <View style={{ width: 14, height: 14, borderRadius: 4, backgroundColor: p.supportColor }} />
                <Text style={{ fontSize: 12, fontWeight: '600', color: active ? p.mainColor : colors.text }}>{p.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Custom colors */}
        <View style={{ flexDirection: 'row', gap: 16 }}>
          <View style={{ flex: 1 }}>
            <Text style={s.label}>{tx('admin.receiptBrandingPanel.auto.text.014', 'Primary Color')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: branding.primary_color, borderWidth: 1, borderColor: AC.border }} />
              <TextInput
                style={[s.input, { flex: 1 }]}
                value={branding.primary_color}
                onChangeText={v => setBranding(p => ({ ...p, primary_color: v }))}
                placeholder={'var(--app-primary)'}
                placeholderTextColor={AC.textMuted}
                maxLength={7}
                data-testid="branding-primary-color-input" testID="branding-primary-color-input"
              />
            </View>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.label}>{tx('admin.receiptBrandingPanel.auto.text.015', 'Secondary Color')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: branding.secondary_color, borderWidth: 1, borderColor: AC.border }} />
              <TextInput
                style={[s.input, { flex: 1 }]}
                value={branding.secondary_color}
                onChangeText={v => setBranding(p => ({ ...p, secondary_color: v }))}
                placeholder={'var(--app-warning)'}
                placeholderTextColor={AC.textMuted}
                maxLength={7}
                data-testid="branding-secondary-color-input" testID="branding-secondary-color-input"
              />
            </View>
          </View>
        </View>
      </View>

      {/* Receipt Preview Mock */}
      <View style={s.card}>
        <Text style={{ fontSize: 15, fontWeight: '600', color: AC.text, marginBottom: 14 }}>{tx('admin.receiptBrandingPanel.auto.text.016', 'Live Preview')}</Text>
        <View style={{ borderRadius: 8, overflow: 'hidden', borderWidth: 1, borderColor: AC.border }}>
          {/* Header */}
          <View style={{ backgroundColor: branding.primary_color, padding: 16 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                {branding.custom_logo ? (
                  <Image accessibilityLabel={tx('admin.receiptBrandingPanel.auto.accessibility.002', 'Branding logo preview')}
                    source={{ uri: `${backendBaseUrl}${branding.custom_logo}` }}
                    style={{ width: 28, height: 28, borderRadius: 4 }}
                    resizeMode="contain"
                  />
                ) : null}
                <Text style={{ color: AC.primaryText, fontSize: 16, fontWeight: '700' }}>{branding.brand_name || 'Brand'}</Text>
              </View>
              <Text style={{ color: AC.primaryText, fontSize: 18, fontWeight: '800', letterSpacing: 1 }}>{tx('admin.receiptBrandingPanel.auto.text.017', 'RECEIPT')}</Text>
            </View>
            <Text style={{ color: 'rgba(255,255,255,0.7)', fontSize: 11, marginTop: 4 }}>{tx('admin.receiptBrandingPanel.auto.text.018', 'Secure Digital Payment Receipt')}</Text>
          </View>
          {/* Accent bar */}
          <View style={{ height: 3, backgroundColor: branding.secondary_color }} />
          {/* Body */}
          <View style={{ backgroundColor: AC.primaryText, padding: 16 }}>
            <View style={{ flexDirection: 'row', gap: 12, marginBottom: 12 }}>
              <View style={{ flex: 1, backgroundColor: AC.text, borderRadius: 6, padding: 10, borderLeftWidth: 3, borderLeftColor: branding.secondary_color }}>
                <Text style={{ fontSize: 9, color: AC.textDim, fontWeight: '600' }}>{tx('admin.receiptBrandingPanel.auto.text.019', 'BILL TO')}</Text>
                <Text style={{ fontSize: 12, color: AC.bgAlt, fontWeight: '700', marginTop: 2 }}>{tx('admin.receiptBrandingPanel.auto.text.020', 'John Doe')}</Text>{/* @theme-ok deliberate-high-contrast inverted receipt preview */}
              </View>
              <View style={{ flex: 1, backgroundColor: AC.text, borderRadius: 6, padding: 10, borderLeftWidth: 3, borderLeftColor: branding.primary_color }}>
                <Text style={{ fontSize: 9, color: AC.textDim, fontWeight: '600' }}>{tx('admin.receiptBrandingPanel.auto.text.021', 'RECEIPT INFO')}</Text>
                <Text style={{ fontSize: 12, color: AC.bgAlt, fontWeight: '700', marginTop: 2 }}>{tx('admin.receiptBrandingPanel.auto.text.022', 'RCT-20260319')}</Text>{/* @theme-ok deliberate-high-contrast inverted receipt preview */}
              </View>
            </View>
            {/* Table */}
            <View style={{ backgroundColor: branding.primary_color, borderRadius: 4, padding: 8, marginBottom: 2 }}>
              <Text style={{ color: AC.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.receiptBrandingPanel.auto.text.023', 'DESCRIPTION')}</Text>
            </View>
            <View style={{ padding: 8, borderBottomWidth: 1, borderBottomColor: AC.textSec }}>
              <Text style={{ fontSize: 11, color: AC.bgAlt, fontWeight: '600' }}>{tx('admin.receiptBrandingPanel.auto.text.024', 'Premium Plan Subscription')}</Text>{/* @theme-ok deliberate-high-contrast inverted receipt preview */}
            </View>
            {/* Total */}
            <View style={{ backgroundColor: AC.bgAlt, borderRadius: 4, padding: 10, marginTop: 8, flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: AC.primaryText, fontSize: 12, fontWeight: '700' }}>{tx('admin.receiptBrandingPanel.auto.text.025', 'TOTAL')}</Text>
              <Text style={{ color: AC.primaryText, fontSize: 14, fontWeight: '800' }}>{tx('admin.receiptBrandingPanel.auto.text.026', '$29.99 USD')}</Text>
            </View>
            {/* Footer */}
            <View style={{ marginTop: 12, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end' }}>
              <View>
                {branding.show_qr_code && (
                  <View style={{ width: 32, height: 32, backgroundColor: AC.text, borderRadius: 4, marginBottom: 4, justifyContent: 'center', alignItems: 'center' }}>
                    <Ionicons name="qr-code" size={20} color="var(--app-text-muted)" />
                  </View>
                )}
                <Text style={{ fontSize: 9, color: AC.textDim }}>{branding.company_info || 'company info'}</Text>
              </View>
              <Text style={{ fontSize: 9, color: branding.primary_color, fontStyle: 'italic' }}>{branding.footer_text || 'footer text'}</Text>
            </View>
          </View>
          {/* Bottom bars */}
          <View style={{ height: 3, backgroundColor: branding.primary_color }} />
          <View style={{ height: 2, backgroundColor: branding.secondary_color }} />
        </View>
      </View>

      {/* Options */}
      <View style={s.card}>
        <Text style={{ fontSize: 15, fontWeight: '600', color: AC.text, marginBottom: 14 }}>{tx('admin.receiptBrandingPanel.auto.text.027', 'Options')}</Text>
        <TouchableOpacity
          onPress={() => setBranding(p => ({ ...p, show_qr_code: !p.show_qr_code }))}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}
          data-testid="branding-toggle-qr" testID="branding-toggle-qr"
        >
          <View style={{
            width: 44, height: 24, borderRadius: 12, justifyContent: 'center',
            backgroundColor: branding.show_qr_code ? 'var(--app-success)' : AC.border,
            paddingHorizontal: 2,
          }}>
            <View style={{
              width: 20, height: 20, borderRadius: 10, backgroundColor: AC.primaryText,
              alignSelf: branding.show_qr_code ? 'flex-end' : 'flex-start',
            }} />
          </View>
          <Text style={{ fontSize: 14, color: AC.text }}>{tx('admin.receiptBrandingPanel.auto.text.028', 'Show QR verification code on receipts')}</Text>
        </TouchableOpacity>
      </View>

      {/* Actions */}
      <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
        <TouchableOpacity aria-label="Save branding changes"
          onPress={handleSave}
          disabled={saving || !hasChanges}
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: hasChanges ? 'var(--app-success)' : AC.border,
            paddingHorizontal: 20, paddingVertical: 12, borderRadius: 8, opacity: saving ? 0.6 : 1,
          }}
          data-testid="branding-save-btn" testID="branding-save-btn"
        >
          {saving ? <ActivityIndicator size="small" color={AC.primaryText} /> : <Ionicons name="checkmark-circle" size={18} color={AC.primaryText} />}
          <Text style={{ color: AC.primaryText, fontWeight: '700', fontSize: 14 }}>{tx('admin.receiptBrandingPanel.auto.text.029', 'Save Changes')}</Text>
        </TouchableOpacity>

        <TouchableOpacity aria-label="Preview branded receipt PDF"
          onPress={handlePreview}
          disabled={previewing}
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: AC.surface,
            paddingHorizontal: 20, paddingVertical: 12, borderRadius: 8, borderWidth: 1, borderColor: AC.border,
            opacity: previewing ? 0.6 : 1,
          }}
          data-testid="branding-preview-btn" testID="branding-preview-btn"
        >
          {previewing ? <ActivityIndicator size="small" color={AC.text} /> : <Ionicons name="eye" size={18} color={AC.text} />}
          <Text style={{ color: AC.text, fontWeight: '600', fontSize: 14 }}>{tx('admin.receiptBrandingPanel.auto.text.030', 'Preview PDF')}</Text>
        </TouchableOpacity>

        <TouchableOpacity aria-label="Reset branding to defaults"
          onPress={handleReset}
          disabled={saving}
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: AC.surface,
            paddingHorizontal: 20, paddingVertical: 12, borderRadius: 8, borderWidth: 1, borderColor: colors.error,
          }}
          data-testid="branding-reset-btn" testID="branding-reset-btn"
        >
          <Ionicons name="refresh" size={18} color={'var(--app-error)'} />
          <Text style={{ color: colors.error, fontWeight: '600', fontSize: 14 }}>{tx('admin.receiptBrandingPanel.auto.text.031', 'Reset to Defaults')}</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}
