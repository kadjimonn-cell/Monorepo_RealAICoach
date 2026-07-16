import React, { useState, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Alert, Image, useWindowDimensions, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import api from '../services/api';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { clientLogger } from '../utils/clientLogger';

interface AIScannerProps {
  feature: string;
  themeColors?: any;
}

export default function AIScanner({ feature, themeColors }: AIScannerProps) {
  const { width: sw } = useWindowDimensions();
  const { colors } = useTheme();
  const activeColors = themeColors || colors;

  // @autofix-moved: was module-level const SCAN_CONFIG
  const SCAN_CONFIG = {
    medimate: { title: 'Health Scanner', icon: 'medkit', color: activeColors.error, desc: 'Scan skin conditions, injuries, or symptoms for AI health guidance' },
    mindease: { title: 'Wellness Scanner', icon: 'sparkles', color: activeColors.pink, desc: 'Scan your environment for stress assessment and calming suggestions' },
    pennypilot: { title: 'Receipt Scanner', icon: 'receipt', color: activeColors.warningText, desc: 'Scan receipts and bills to track expenses automatically' },
    assetpilot: { title: 'Investment Scanner', icon: 'trending-up', color: activeColors.successText, desc: 'Scan property or documents for investment analysis' },
    assistant: { title: 'Note Scanner', icon: 'document-text', color: activeColors.primary, desc: 'Scan handwritten notes and lists to digitize them' },
    school: { title: 'Study Scanner', icon: 'school', color: activeColors.accent, desc: 'Scan textbook pages or homework for instant explanations' },
    jobhelp: { title: 'Resume Scanner', icon: 'briefcase', color: activeColors.accent, desc: 'Scan your resume or business cards for AI career advice' },
    globecoach: { title: 'Culture Scanner', icon: 'globe', color: activeColors.successText, desc: 'Scan landmarks or items for cultural identification' },
    smartbuy: { title: 'Product Scanner', icon: 'barcode', color: activeColors.warningText, desc: 'Scan products for price comparison and quality assessment' },
    homemate: { title: 'Property Scanner', icon: 'business', color: activeColors.primary, desc: 'Scan rooms or properties for real estate analysis' },
    autogenie: { title: 'Vehicle Scanner', icon: 'car', color: activeColors.error, desc: 'Scan vehicles for condition assessment and value estimate' },
    translate: { title: 'Text Scanner', icon: 'language', color: activeColors.accent, desc: 'Scan signs, menus, or documents for instant translation' },
    ecosync: { title: 'Eco Scanner', icon: 'leaf', color: activeColors.successText, desc: 'Scan items to check recyclability and environmental impact' },
    climateguide: { title: 'Sky Scanner', icon: 'cloudy', color: activeColors.primary, desc: 'Scan the sky for weather assessment and activity tips' },
    lifepulse: { title: 'Routine Scanner', icon: 'pulse', color: activeColors.pink, desc: 'Scan your workspace for productivity optimization' },
    homemind: { title: 'Appliance Scanner', icon: 'home', color: activeColors.warningText, desc: 'Scan appliances for smart home setup and energy tips' },
    disasterguard: { title: 'Safety Scanner', icon: 'shield-checkmark', color: activeColors.error, desc: 'Scan your environment for safety hazards' },
    travelpal: { title: 'Travel Scanner', icon: 'airplane', color: activeColors.accent, desc: 'Scan landmarks and signs for travel information' },
    aidlink: { title: 'Aid Scanner', icon: 'heart-circle', color: activeColors.pink, desc: 'Scan situations to identify humanitarian needs' },
    fitness: { title: 'Body Scanner', icon: 'body', color: activeColors.successText, desc: 'Scan your body for fitness assessment and workout suggestions' },
    nutritrack: { title: 'Meal Scanner', icon: 'nutrition', color: activeColors.warningText, desc: 'Scan meals for instant nutrition analysis and health tips' },
    lifegame: { title: 'Quest Scanner', icon: 'rocket', color: activeColors.accent, desc: 'Scan achievements or items for XP and quest completion' },
  };
  // @autofix-moved: was module-level const createStyles
  const createStyles = (C: any) => StyleSheet.create({
    container: { flex: 1, backgroundColor: C.bg },
    content: { padding: 16 },
    hero: { alignItems: 'center', paddingVertical: 16, marginBottom: 16 },
    iconBox: { width: 72, height: 72, borderRadius: 36, alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
    title: { fontWeight: '800', color: C.text },
    desc: { color: C.textMuted, textAlign: 'center', marginTop: 6, lineHeight: 20, paddingHorizontal: 10 },
    btnRow: { flexDirection: 'row', gap: 12, marginBottom: 16 },
    cameraBtn: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: 14,
      paddingVertical: 16,
      gap: 8,
      ...(Platform.OS === 'web'
        ? { boxShadow: `0 4px 8px ${C.shadowColor}` }
        : Platform.select({ ios: { shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.25, shadowRadius: 8 }, android: { elevation: 4 } })),
    },
    cameraTxt: { fontWeight: '700', color: activeColors.primaryText },
    galleryBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderRadius: 14, paddingVertical: 16, gap: 8, borderWidth: 1.5, backgroundColor: C.card },
    galleryTxt: { fontWeight: '700' },
    preview: { borderRadius: 16, overflow: 'hidden', marginBottom: 16, borderWidth: 1, borderColor: C.border },
    previewImg: { width: '100%', height: 250, borderRadius: 16 },
    overlay: { ...StyleSheet.absoluteFillObject, backgroundColor: C.overlay, alignItems: 'center', justifyContent: 'center', borderRadius: 16 },
    scanText: { color: activeColors.primaryText, fontWeight: '600', marginTop: 12 },
    resultCard: { borderRadius: 16, padding: 18, borderWidth: 1, backgroundColor: C.card, marginBottom: 16 },
    resultHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 },
    resultTitle: { fontWeight: '700', color: C.text },
    resultSection: { marginBottom: 14, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '60') },
    sectionLabel: { fontWeight: '700', marginBottom: 4, letterSpacing: 0.5 },
    val: { color: C.textSec, lineHeight: 20 },
    listItem: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, marginBottom: 3 },
    bullet: { fontSize: 16, marginTop: -2 },
    listText: { flex: 1, color: C.textSec, lineHeight: 18 },
    nestedRow: { marginBottom: 6 },
    nestedLabel: { fontWeight: '600', color: C.textMuted, marginBottom: 2 },
    rescan: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 14, borderRadius: 12, borderWidth: 1, gap: 6, marginTop: 8 },
    rescanTxt: { fontWeight: '600' },
  });
  const { isAuthenticated } = useAuth();
  const [scanning, setScanning] = useState(false);
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  // Theme-aware colors
  const C = useMemo(() => ({
    ...activeColors,
    bg: activeColors.bg,
    bgSoft: activeColors.bgSoft,
    card: activeColors.card,
    text: activeColors.text,
    textSec: activeColors.textSec,
    textMuted: activeColors.textMuted,
    border: activeColors.border,
    success: activeColors.success,
    shadowColor: activeColors.shadowColor,
    overlay: activeColors.overlay,
  }), [activeColors]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const st = useMemo(() => createStyles(C), [C]);

  const config = SCAN_CONFIG[feature] || { title: 'AI Scanner', icon: 'scan', color: activeColors.primary, desc: 'Scan anything for AI analysis' };
  const fs = (b: number) => sw < 360 ? b - 1 : sw >= 414 ? b + 1 : b;

  const extractSummary = (data: any) => {
    if (!data) return 'Scan completed.';
    const skipKeys = new Set(['scan_type', 'scanner_title', 'error']);
    for (const [key, value] of Object.entries(data)) {
      if (skipKeys.has(key)) continue;
      if (typeof value === 'string' && value.trim().length > 0) return value;
      if (value && typeof value === 'object' && typeof (value as any).summary === 'string') {
        return (value as any).summary;
      }
    }
    return 'Scan completed.';
  };

  const saveScan = async (data: any) => {
    if (!isAuthenticated || !data || data.error) return;
    try {
      await api.post('/scans', {
        scan_type: data.scan_type || feature,
        scanner_title: data.scanner_title || config.title,
        summary: extractSummary(data),
        analysis: data,
      });
    } catch (error) {
      console.error('Save scan error:', error);
    }
  };

  const pickImage = async (useCamera: boolean) => {
    try {
      const perm = useCamera
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('Permission Required', `Allow ${useCamera ? 'camera' : 'photo library'} access to scan.`);
        return;
      }
      const res = useCamera
        ? await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.6, base64: true, allowsEditing: true })
        : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.6, base64: true, allowsEditing: true });

      if (!res.canceled && res.assets[0]) {
        setImageUri(res.assets[0].uri);
        setResult(null);
        if (res.assets[0].base64) {
          analyze(res.assets[0].base64);
        }
      }
    } catch (e) { 
      console.error('Image picker error:', e);
      Alert.alert('Error', 'Failed to capture image'); 
    }
  };

  const analyze = async (base64: string) => {
    setScanning(true);
    try {
      const res = await api.post('/ai-scan', { 
        user_id: 'guest', 
        image_base64: base64, 
        scan_type: feature,
        notes: ''
      });
      clientLogger.log('Scan result:', res.data);
      setResult(res.data);
      saveScan(res.data);
    } catch (e) { 
      console.error('Scan API error:', e);
      Alert.alert('Error', 'Failed to analyze. Try again.'); 
    }
    finally { setScanning(false); }
  };

  const renderValue = (val: any, depth = 0): React.ReactNode => {
    if (val === null || val === undefined) return null;
    if (typeof val === 'boolean') return <Text style={[st.val, { fontSize: fs(13) }]}>{val ? '✅ Yes' : '❌ No'}</Text>;
    if (typeof val === 'number') return <Text style={[st.val, { fontSize: fs(13), fontWeight: '700' }]}>{val}</Text>;
    if (typeof val === 'string') return <Text style={[st.val, { fontSize: fs(13) }]}>{val}</Text>;
    if (Array.isArray(val)) return (
      <View style={{ marginTop: 4 }}>
        {val.map((item, i) => (
          <View key={i} style={st.listItem}>
            <Text style={[st.bullet, { color: config.color }]}>•</Text>
            <Text style={[st.listText, { fontSize: fs(12) }]}>{typeof item === 'object' ? JSON.stringify(item) : String(item)}</Text>
          </View>
        ))}
      </View>
    );
    if (typeof val === 'object') return (
      <View style={{ marginTop: 4, marginLeft: depth > 0 ? 12 : 0 }}>
        {Object.entries(val).map(([k, v]) => (
          <View key={k} style={st.nestedRow}>
            <Text style={[st.nestedLabel, { fontSize: fs(11) }]}>{k.replace(/_/g, ' ').toUpperCase()}</Text>
            {renderValue(v, depth + 1)}
          </View>
        ))}
      </View>
    );
    return null;
  };

  return (
    <ScrollView style={st.container} contentContainerStyle={st.content} showsVerticalScrollIndicator={false} data-testid={`scanner-scroll-${feature}`} testID={`scanner-scroll-${feature}`}>
      {/* Hero */}
      <View style={st.hero} data-testid={`scanner-hero-${feature}`} testID={`scanner-hero-${feature}`}>
        <View style={[st.iconBox, { backgroundColor: (globalThis as any).__alphaColor(config.color, '15') }]}>
          <Ionicons name={config.icon as any} size={36} color={config.color} />
        </View>
        <Text style={[st.title, { fontSize: fs(20) }]} data-testid={`scanner-title-${feature}`} testID={`scanner-title-${feature}`}>{config.title}</Text>
        <Text style={[st.desc, { fontSize: fs(13) }]} data-testid={`scanner-description-${feature}`} testID={`scanner-description-${feature}`}>{config.desc}</Text>
      </View>

      {/* Buttons */}
      <View style={st.btnRow} data-testid={`scanner-actions-${feature}`} testID={`scanner-actions-${feature}`}>
        <TouchableOpacity style={[st.cameraBtn, { backgroundColor: config.color }]} onPress={() => pickImage(true)} disabled={scanning} data-testid={`scanner-camera-button-${feature}`} testID={`scanner-camera-button-${feature}`}>
          <Ionicons name="camera" size={22} color={activeColors.primaryText} />
          <Text style={[st.cameraTxt, { fontSize: fs(14) }]} data-testid={`scanner-camera-label-${feature}`} testID={`scanner-camera-label-${feature}`}>Scan Now</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[st.galleryBtn, { borderColor: config.color }]} onPress={() => pickImage(false)} disabled={scanning} data-testid={`scanner-gallery-button-${feature}`} testID={`scanner-gallery-button-${feature}`}>
          <Ionicons name="images" size={22} color={config.color} />
          <Text style={[st.galleryTxt, { color: config.color, fontSize: fs(14) }]} data-testid={`scanner-gallery-label-${feature}`} testID={`scanner-gallery-label-${feature}`}>Gallery</Text>
        </TouchableOpacity>
      </View>

      {/* Preview */}
      {imageUri && (
        <View style={st.preview} data-testid={`scanner-preview-${feature}`} testID={`scanner-preview-${feature}`}>
          <Image source={{ uri: imageUri }} style={st.previewImg} resizeMode="cover" data-testid={`scanner-preview-image-${feature}`} testID={`scanner-preview-image-${feature}`} accessibilityLabel="AI is analyzing..." />
          {scanning && (
            <View style={st.overlay} data-testid={`scanner-loading-${feature}`} testID={`scanner-loading-${feature}`}>
              <ActivityIndicator size="large" color={config.color} />
              <Text style={[st.scanText, { fontSize: fs(14) }]} data-testid={`scanner-loading-text-${feature}`} testID={`scanner-loading-text-${feature}`}>AI is analyzing...</Text>
            </View>
          )}
        </View>
      )}

      {/* Results */}
      {result && !result.error && (
        <View style={[st.resultCard, { borderColor: (globalThis as any).__alphaColor(config.color, '30') }]} data-testid={`scanner-result-${feature}`} testID={`scanner-result-${feature}`}>
          <View style={st.resultHeader} data-testid={`scanner-result-header-${feature}`} testID={`scanner-result-header-${feature}`}>
            <Ionicons name="checkmark-circle" size={20} color={C.successText} />
            <Text style={[st.resultTitle, { fontSize: fs(16) }]} data-testid={`scanner-result-title-${feature}`} testID={`scanner-result-title-${feature}`}>Analysis Complete</Text>
          </View>

          {Object.entries(result).filter(([k]) => !['scan_type', 'scanner_title', 'error'].includes(k)).map(([key, value]) => (
            <View key={key} style={st.resultSection} data-testid={`scanner-result-section-${feature}-${key}`} testID={`scanner-result-section-${feature}-${key}`}>
              <Text style={[st.sectionLabel, { color: config.color, fontSize: fs(12) }]} data-testid={`scanner-result-label-${feature}-${key}`} testID={`scanner-result-label-${feature}-${key}`}>
                {key.replace(/_/g, ' ').toUpperCase()}
              </Text>
              {renderValue(value)}
            </View>
          ))}

          <TouchableOpacity style={[st.rescan, { borderColor: config.color }]} onPress={() => { setImageUri(null); setResult(null); }} data-testid={`scanner-rescan-button-${feature}`} testID={`scanner-rescan-button-${feature}`}>
            <Ionicons name="refresh" size={16} color={config.color} />
            <Text style={[st.rescanTxt, { color: config.color, fontSize: fs(13) }]} data-testid={`scanner-rescan-label-${feature}`} testID={`scanner-rescan-label-${feature}`}>Scan Again</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Error state */}
      {result?.error && (
        <View style={[st.resultCard, { borderColor: (globalThis as any).__alphaColor(activeColors.error, '30') }]} data-testid={`scanner-error-${feature}`} testID={`scanner-error-${feature}`}>
          <View style={st.resultHeader} data-testid={`scanner-error-header-${feature}`} testID={`scanner-error-header-${feature}`}>
            <Ionicons name="alert-circle" size={20} color={activeColors.error} />
            <Text style={[st.resultTitle, { fontSize: fs(16), color: activeColors.error }]} data-testid={`scanner-error-title-${feature}`} testID={`scanner-error-title-${feature}`}>Analysis Issue</Text>
          </View>
          <Text style={[st.val, { fontSize: fs(13) }]} data-testid={`scanner-error-message-${feature}`} testID={`scanner-error-message-${feature}`}>{result.analysis || 'Something went wrong. Please try again.'}</Text>
          <TouchableOpacity style={[st.rescan, { borderColor: config.color, marginTop: 14 }]} onPress={() => { setImageUri(null); setResult(null); }} data-testid={`scanner-retry-button-${feature}`} testID={`scanner-retry-button-${feature}`}>
            <Ionicons name="refresh" size={16} color={config.color} />
            <Text style={[st.rescanTxt, { color: config.color, fontSize: fs(13) }]} data-testid={`scanner-retry-label-${feature}`} testID={`scanner-retry-label-${feature}`}>Try Again</Text>
          </TouchableOpacity>
        </View>
      )}

      <View style={{ height: 30 }} />
    </ScrollView>
  );
}

/* i18n-probe t('i18n.auto.probe') */
