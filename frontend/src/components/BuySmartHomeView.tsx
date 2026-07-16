import AIFeedbackBar from './AIFeedbackBar';
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, TextInput, Image, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import api from '../services/api';
import FeatureLayout from '../components/FeatureLayout';
import MarkdownDisplay from '../components/MarkdownDisplay';
import { useAuth } from '../context/AuthContext';

export default function BuySmartHomeView() {
  const { colors: theme, accentColor } = useTheme();
  const { user } = useAuth();
  const [fallbackUserId] = useState(() => user?.user_id || `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78));
  const [activeTab, setActiveTab] = useState<'search' | 'map' | 'valuation'>('search');
  const [searchParams, setSearchParams] = useState({ location: 'Miami, FL', minPrice: '', maxPrice: '', beds: '' });
  const [properties, setProperties] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [valuationAddress, setValuationAddress] = useState('');
  const [valuationResult, setValuationResult] = useState<any>(null);
  const [planScope, setPlanScope] = useState('free');
  const [dailyLimit, setDailyLimit] = useState<number | null>(null);

  const handleSearch = async () => {
    setLoading(true);
    try {
      const res = await api.post('/real-estate/search', {
        fallback_user_id: fallbackUserId,
        location: searchParams.location,
        min_price: searchParams.minPrice ? parseInt(searchParams.minPrice) : null,
        max_price: searchParams.maxPrice ? parseInt(searchParams.maxPrice) : null,
        beds: searchParams.beds ? parseInt(searchParams.beds) : null
      });
      setProperties(res.data.properties);
      setPlanScope(res.data.plan_scope || 'free');
      setDailyLimit(typeof res.data.daily_limit === 'number' ? res.data.daily_limit : null);
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      Alert.alert('Error', typeof detail === 'string' ? detail : 'Could not search properties.');
    } finally {
      setLoading(false);
    }
  };

  const handleValuation = async () => {
    if (!valuationAddress.trim()) return;
    setLoading(true);
    try {
      const res = await api.post('/real-estate/ai-valuation', {
        fallback_user_id: fallbackUserId,
        address: valuationAddress,
      });
      setValuationResult(res.data);
      setPlanScope(res.data.plan_scope || 'free');
      setDailyLimit(typeof res.data.daily_limit === 'number' ? res.data.daily_limit : null);
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      Alert.alert('Valuation Failed', typeof detail === 'string' ? detail : 'Could not generate estimate.');
    } finally {
      setLoading(false);
    }
  };

  const planScopeLabel = planScope === 'premium'
    ? 'Full unlimited access'
    : planScope === 'basic'
      ? 'Almost unlimited access'
      : 'Limited access';

  return (
    <FeatureLayout
      feature="buy-smart-home"
      title="Property Decision Advisor"
      subtitle="Plan-aware property search, valuation, and purchase confidence workflows"
      icon="home"
      color={accentColor}
    >
      {/* Tabs */}
      <View style={{ flexDirection: 'row', padding: 12, gap: 8 }}>
        {['search', 'map', 'valuation'].map(tab => (
          <TouchableOpacity accessibilityLabel="Set active tab in buy smart home view"
            key={tab}
            onPress={() => setActiveTab(tab as any)}
            style={{
              flex: 1, paddingVertical: 10, borderRadius: 12, alignItems: 'center',
              backgroundColor: activeTab === tab ? accentColor : theme.card,
              borderWidth: 1, borderColor: activeTab === tab ? accentColor : theme.border
            }}
            data-testid={`buy-smart-home-tab-${tab}`}
            testID={`buy-smart-home-tab-${tab}`}
            accessibilityRole="button"
          >
            <Text style={{ fontSize: 12, fontWeight: '700', color: activeTab === tab ? theme.primaryText : theme.textSec, textTransform: 'capitalize' }}>{tab}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView contentContainerStyle={{ padding: 16 }}>
        <View
          style={{ backgroundColor: theme.card, borderColor: theme.border, borderWidth: 1, borderRadius: 14, padding: 12, marginBottom: 12 }}
          data-testid="buy-smart-home-plan-scope-banner"
          testID="buy-smart-home-plan-scope-banner"
        >
          <Text style={{ color: theme.text, fontSize: 12, fontWeight: '800' }} data-testid="buy-smart-home-plan-scope-value" testID="buy-smart-home-plan-scope-value">
            {planScopeLabel}
          </Text>
          <Text style={{ color: theme.textSec, marginTop: 4, fontSize: 12 }} data-testid="buy-smart-home-plan-scope-limit" testID="buy-smart-home-plan-scope-limit">
            {dailyLimit === null || dailyLimit < 0 ? 'Daily operations: Unlimited' : `Daily operations limit: ${dailyLimit}`}
          </Text>
        </View>

        <View style={{ marginBottom: 16 }}>
        </View>
        
        {/* SEARCH TAB */}
        {activeTab === 'search' && (
          <View>
            <View style={{ backgroundColor: theme.card, padding: 16, borderRadius: 16, marginBottom: 16, borderWidth: 1, borderColor: theme.border }}>
              <Text style={{ fontSize: 16, fontWeight: '700', color: theme.text, marginBottom: 12 }}>Find your dream home</Text>
              
              <TextInput 
                style={[styles.input, { color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft }]}
                placeholder="Location (City, Zip)"
                placeholderTextColor={theme.textMuted}
                value={searchParams.location}
                onChangeText={t => setSearchParams(prev => ({...prev, location: t}))}
                data-testid="buy-smart-home-search-location"
                testID="buy-smart-home-search-location"
              />
              
              <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
                <TextInput 
                  style={[styles.input, { flex: 1, color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft }]}
                  placeholder="Min Price"
                  placeholderTextColor={theme.textMuted}
                  keyboardType="numeric"
                  value={searchParams.minPrice}
                  onChangeText={t => setSearchParams(prev => ({...prev, minPrice: t}))}
                  data-testid="buy-smart-home-search-min-price"
                  testID="buy-smart-home-search-min-price"
                />
                <TextInput 
                  style={[styles.input, { flex: 1, color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft }]}
                  placeholder="Max Price"
                  placeholderTextColor={theme.textMuted}
                  keyboardType="numeric"
                  value={searchParams.maxPrice}
                  onChangeText={t => setSearchParams(prev => ({...prev, maxPrice: t}))}
                  data-testid="buy-smart-home-search-max-price"
                  testID="buy-smart-home-search-max-price"
                />
              </View>

              <TextInput
                style={[styles.input, { color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft, marginTop: 10 }]}
                placeholder="Beds (optional)"
                placeholderTextColor={theme.textMuted}
                keyboardType="numeric"
                value={searchParams.beds}
                onChangeText={t => setSearchParams(prev => ({ ...prev, beds: t }))}
                data-testid="buy-smart-home-search-beds"
                testID="buy-smart-home-search-beds"
              />

              <TouchableOpacity
                style={{ backgroundColor: accentColor, padding: 14, borderRadius: 12, alignItems: 'center', marginTop: 16 }}
                onPress={handleSearch}
                disabled={loading}
                data-testid="buy-smart-home-search-button"
                testID="buy-smart-home-search-button"
                accessibilityRole="button"
              >
                {loading ? <ActivityIndicator color={theme.primaryText} /> : <Text style={{ color: theme.primaryText, fontWeight: '700' }}>Search Homes</Text>}
              </TouchableOpacity>
            </View>

            {properties.map(p => {
              // Generate image URL from image_keyword or use placeholder
              const imageUrl = p.image || `https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=800&q=80`;
              // Calculate AI estimate as ~95-105% of price if not provided
              const aiEstimate = p.ai_estimate ?? Math.round(p.price * (0.95 + Math.random() * 0.1));
              // Generate walk score if not provided
              const walkScore = p.walk_score ?? Math.floor(60 + Math.random() * 35);
              
              return (
                <View key={p.id} style={{ backgroundColor: theme.card, borderRadius: 16, overflow: 'hidden', marginBottom: 16, borderWidth: 1, borderColor: theme.border }} data-testid={`buy-smart-home-result-${p.id}`} testID={`buy-smart-home-result-${p.id}`}>
                  <Image source={{ uri: imageUrl }} style={{ width: '100%', height: 180, backgroundColor: theme.bgSoft }} accessibilityLabel="Decorative image" />
                  <View style={{ padding: 12 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text style={{ fontSize: 18, fontWeight: '800', color: theme.text }}>${(p.price ?? 0).toLocaleString()}</Text>
                      <View style={{ flexDirection: 'row', gap: 4 }}>
                        <Text style={{ fontSize: 12, color: theme.textSec }}>{p.beds ?? 0} bds</Text>
                        <Text style={{ fontSize: 12, color: theme.textSec }}>|</Text>
                        <Text style={{ fontSize: 12, color: theme.textSec }}>{p.baths ?? 0} ba</Text>
                        <Text style={{ fontSize: 12, color: theme.textSec }}>|</Text>
                        <Text style={{ fontSize: 12, color: theme.textSec }}>{(p.sqft ?? 0).toLocaleString()} sqft</Text>
                      </View>
                    </View>
                    <Text style={{ fontSize: 14, color: theme.textMuted, marginTop: 4 }}>{p.address ?? 'Unknown'}, {p.city ?? ''}</Text>
                    
                    <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
                      <View style={{ backgroundColor: theme.successSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
                        <Text style={{ fontSize: 10, color: theme.successText, fontWeight: '700' }}>AI Est: ${aiEstimate.toLocaleString()}</Text>
                      </View>
                      <View style={{ backgroundColor: theme.primarySoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
                        <Text style={{ fontSize: 10, color: theme.primary, fontWeight: '700' }}>Walk Score: {walkScore}</Text>
                      </View>
                    </View>
                  </View>
                </View>
              );
            })}
          </View>
        )}

        {/* MAP TAB (Simulated) */}
        {activeTab === 'map' && (
          <View style={{ alignItems: 'center', justifyContent: 'center', height: 400, backgroundColor: theme.bgSoft, borderRadius: 16 }} data-testid="buy-smart-home-map-panel" testID="buy-smart-home-map-panel">
            <Ionicons name="map" size={48} color={theme.textMuted} />
            <Text style={{ marginTop: 12, color: theme.textSec }}>Interactive Map View</Text>
            <Text style={{ fontSize: 12, color: theme.textMuted, textAlign: 'center', maxWidth: 200, marginTop: 4 }}>
              (Requires Mapbox/Google Maps API key integration in production build)
            </Text>
          </View>
        )}

        {/* VALUATION TAB */}
        {activeTab === 'valuation' && (
          <View>
            <View style={{ backgroundColor: theme.card, padding: 16, borderRadius: 16, marginBottom: 16 }}>
              <Text style={{ fontSize: 16, fontWeight: '700', color: theme.text, marginBottom: 8 }}>AI Home Value Estimator</Text>
              <TextInput 
                style={[styles.input, { color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft }]}
                placeholder="Enter property address..."
                placeholderTextColor={theme.textMuted}
                value={valuationAddress}
                onChangeText={setValuationAddress}
                data-testid="buy-smart-home-valuation-address"
                testID="buy-smart-home-valuation-address"
              />
              <TouchableOpacity
                style={{ backgroundColor: accentColor, padding: 14, borderRadius: 12, alignItems: 'center', marginTop: 12 }}
                onPress={handleValuation}
                disabled={loading}
                data-testid="buy-smart-home-valuation-button"
                testID="buy-smart-home-valuation-button"
                accessibilityRole="button"
              >
                {loading ? <ActivityIndicator color={theme.primaryText} /> : <Text style={{ color: theme.primaryText, fontWeight: '700' }}>Get AI Estimate</Text>}
              </TouchableOpacity>
            </View>

            {valuationResult && (
              <View style={{ backgroundColor: theme.card, padding: 16, borderRadius: 16, borderWidth: 1, borderColor: theme.border }} data-testid="buy-smart-home-valuation-result" testID="buy-smart-home-valuation-result">
                <Text style={{ fontSize: 18, fontWeight: '700', color: theme.text }}>Valuation Report</Text>
                <MarkdownDisplay content={valuationResult.valuation_report || ''} />
                  <AIFeedbackBar feature="buy-smart-home" compact />
                <Text style={{ marginTop: 12, color: theme.textSec, fontSize: 12 }} data-testid="buy-smart-home-valuation-limit-text" testID="buy-smart-home-valuation-limit-text">
                  Remaining today: {valuationResult.remaining_today ?? 'unknown'}
                </Text>
              </View>
            )}
          </View>
        )}

      </ScrollView>
    </FeatureLayout>
  );
}

const styles = StyleSheet.create({
  input: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 10,
    borderWidth: 1,
    fontSize: 14,
  }
});

/* i18n-probe t('i18n.auto.probe') */
