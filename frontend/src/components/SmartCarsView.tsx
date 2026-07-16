import AIFeedbackBar from './AIFeedbackBar';
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, TextInput, Image, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import api from '../services/api';
import FeatureLayout from '../components/FeatureLayout';
import { useAuth } from '../context/AuthContext';

export default function SmartCarsView() {
  const { colors: theme, accentColor } = useTheme();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<'search' | 'sell' | 'finance'>('search');
  const [searchParams, setSearchParams] = useState({ make: '', minPrice: '', maxPrice: '' });
  const [cars, setCars] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [planScope, setPlanScope] = useState('free');
  const [dailyLimit, setDailyLimit] = useState<number | null>(null);

  const [tradeIn, setTradeIn] = useState({ make: '', model: '', year: '', mileage: '', condition: 'Good' });
  const [tradeInResult, setTradeInResult] = useState<any>(null);

  const handleSearch = async () => {
    setLoading(true);
    try {
      const res = await api.post('/cars/search', {
        user_id: user?.user_id || 'guest',
        make: searchParams.make,
        min_price: searchParams.minPrice ? parseInt(searchParams.minPrice) : null,
        max_price: searchParams.maxPrice ? parseInt(searchParams.maxPrice) : null
      });
      setCars(res.data.cars);
      setPlanScope(res.data.plan_scope || 'free');
      setDailyLimit(typeof res.data.daily_limit === 'number' ? res.data.daily_limit : null);
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      Alert.alert('Error', typeof detail === 'string' ? detail : 'Could not search cars.');
    } finally {
      setLoading(false);
    }
  };

  const handleTradeIn = async () => {
    if (!tradeIn.make || !tradeIn.model) return;
    setLoading(true);
    try {
      const res = await api.post('/cars/trade-in', {
        user_id: user?.user_id || 'guest',
        make: tradeIn.make,
        model: tradeIn.model,
        year: parseInt(tradeIn.year) || 2020,
        mileage: parseInt(tradeIn.mileage) || 50000,
        condition: tradeIn.condition
      });
      setTradeInResult(res.data);
      setPlanScope(res.data.plan_scope || 'free');
      setDailyLimit(typeof res.data.daily_limit === 'number' ? res.data.daily_limit : null);
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      Alert.alert('Error', typeof detail === 'string' ? detail : 'Valuation failed.');
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
      feature="smart-cars"
      title="Mobility Assistant"
      subtitle="Smart driving, trade-in, and mobility decisions with plan-aware guidance"
      icon="car"
      color={accentColor}
    >
      <View style={{ flexDirection: 'row', padding: 12, gap: 8 }}>
        {['search', 'sell', 'finance'].map(tab => (
          <TouchableOpacity accessibilityLabel="Set active tab in smart cars view"
            key={tab}
            onPress={() => setActiveTab(tab as any)}
            style={{
              flex: 1, paddingVertical: 10, borderRadius: 12, alignItems: 'center',
              backgroundColor: activeTab === tab ? accentColor : theme.card,
              borderWidth: 1, borderColor: activeTab === tab ? accentColor : theme.border
            }}
            data-testid={`smart-cars-tab-${tab}`}
            testID={`smart-cars-tab-${tab}`}
            accessibilityRole="button"
          >
            <Text style={{ fontSize: 12, fontWeight: '700', color: activeTab === tab ? theme.primaryText : theme.textSec, textTransform: 'capitalize' }}>{tab}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView contentContainerStyle={{ padding: 16 }}>
        <View
          style={{ backgroundColor: theme.card, borderColor: theme.border, borderWidth: 1, borderRadius: 14, padding: 12, marginBottom: 12 }}
          data-testid="smart-cars-plan-scope-banner"
          testID="smart-cars-plan-scope-banner"
        >
          <Text style={{ color: theme.text, fontSize: 12, fontWeight: '800' }} data-testid="smart-cars-plan-scope-value" testID="smart-cars-plan-scope-value">
            {planScopeLabel}
          </Text>
          <Text style={{ color: theme.textSec, marginTop: 4, fontSize: 12 }} data-testid="smart-cars-plan-scope-limit" testID="smart-cars-plan-scope-limit">
            {dailyLimit === null || dailyLimit < 0 ? 'Daily operations: Unlimited' : `Daily operations limit: ${dailyLimit}`}
          </Text>
        </View>

        {activeTab === 'search' && (
          <View>
            <View style={{ backgroundColor: theme.card, padding: 16, borderRadius: 16, marginBottom: 16, borderWidth: 1, borderColor: theme.border }}>
              <Text style={{ fontSize: 16, fontWeight: '700', color: theme.text, marginBottom: 12 }}>Find your next ride</Text>

              <TextInput
                style={[styles.input, { color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft }]}
                placeholder="Make (e.g. Toyota, BMW)"
                placeholderTextColor={theme.textMuted}
                value={searchParams.make}
                onChangeText={t => setSearchParams(prev => ({ ...prev, make: t }))}
                data-testid="smart-cars-search-make"
                testID="smart-cars-search-make"
              />

              <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
                <TextInput
                  style={[styles.input, { flex: 1, color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft }]}
                  placeholder="Min Price"
                  placeholderTextColor={theme.textMuted}
                  keyboardType="numeric"
                  value={searchParams.minPrice}
                  onChangeText={t => setSearchParams(prev => ({ ...prev, minPrice: t }))}
                  data-testid="smart-cars-search-min-price"
                  testID="smart-cars-search-min-price"
                />
                <TextInput
                  style={[styles.input, { flex: 1, color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft }]}
                  placeholder="Max Price"
                  placeholderTextColor={theme.textMuted}
                  keyboardType="numeric"
                  value={searchParams.maxPrice}
                  onChangeText={t => setSearchParams(prev => ({ ...prev, maxPrice: t }))}
                  data-testid="smart-cars-search-max-price"
                  testID="smart-cars-search-max-price"
                />
              </View>

              <TouchableOpacity
                style={{ backgroundColor: accentColor, padding: 14, borderRadius: 12, alignItems: 'center', marginTop: 16 }}
                onPress={handleSearch}
                disabled={loading}
                data-testid="smart-cars-search-button"
                testID="smart-cars-search-button"
                accessibilityRole="button"
              >
                {loading ? <ActivityIndicator color={theme.primaryText} /> : <Text style={{ color: theme.primaryText, fontWeight: '700' }}>Search Cars</Text>}
              </TouchableOpacity>
            </View>

            {cars.map(c => (
              <View
                key={c.id}
                style={{ backgroundColor: theme.card, borderRadius: 16, overflow: 'hidden', marginBottom: 16, borderWidth: 1, borderColor: theme.border }}
                data-testid={`smart-cars-result-${c.id}`}
                testID={`smart-cars-result-${c.id}`}
                accessibilityLabel={String(c?.deal_rating || 'Deal rating')}
              >
                <Image source={{ uri: c.image }} style={{ width: '100%', height: 180, backgroundColor: theme.bgSoft }} accessibilityLabel={c.deal_rating.toUpperCase()} />
                <View style={{ position: 'absolute', top: 12, left: 12, backgroundColor: c.deal_rating === 'Great Deal' ? theme.success : theme.warning, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
                  <Text style={{ fontSize: 10, fontWeight: '800', color: theme.primaryText }}>{c.deal_rating.toUpperCase()}</Text>
                </View>

                <View style={{ padding: 12 }}>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: theme.text }}>{c.year} {c.make} {c.model}</Text>
                  <Text style={{ fontSize: 12, color: theme.textMuted, marginTop: 2 }}>{c.trim} • {c.mileage.toLocaleString()} miles</Text>

                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
                    <Text style={{ fontSize: 20, fontWeight: '800', color: theme.text }}>${c.price.toLocaleString()}</Text>
                    <TouchableOpacity
                      style={{ backgroundColor: theme.bgSoft, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 }}
                      data-testid={`smart-cars-availability-${c.id}`}
                      testID={`smart-cars-availability-${c.id}`}
                      accessibilityRole="button"
                    >
                      <Text style={{ fontSize: 12, fontWeight: '600', color: theme.text }}>Check Availability</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            ))}
          </View>
        )}

        {activeTab === 'sell' && (
          <View>
            <View style={{ backgroundColor: theme.card, padding: 16, borderRadius: 16, marginBottom: 16 }}>
              <Text style={{ fontSize: 16, fontWeight: '700', color: theme.text, marginBottom: 8 }}>AI Trade-In Estimator</Text>

              <View style={{ gap: 10 }}>
                <TextInput
                  style={[styles.input, { color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft }]}
                  placeholder="Make"
                  placeholderTextColor={theme.textMuted}
                  value={tradeIn.make}
                  onChangeText={t => setTradeIn(p => ({ ...p, make: t }))}
                  data-testid="smart-cars-tradein-make"
                  testID="smart-cars-tradein-make"
                />
                <TextInput
                  style={[styles.input, { color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft }]}
                  placeholder="Model"
                  placeholderTextColor={theme.textMuted}
                  value={tradeIn.model}
                  onChangeText={t => setTradeIn(p => ({ ...p, model: t }))}
                  data-testid="smart-cars-tradein-model"
                  testID="smart-cars-tradein-model"
                />
                <View style={{ flexDirection: 'row', gap: 10 }}>
                  <TextInput
                    style={[styles.input, { flex: 1, color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft }]}
                    placeholder="Year"
                    placeholderTextColor={theme.textMuted}
                    keyboardType="numeric"
                    value={tradeIn.year}
                    onChangeText={t => setTradeIn(p => ({ ...p, year: t }))}
                    data-testid="smart-cars-tradein-year"
                    testID="smart-cars-tradein-year"
                  />
                  <TextInput
                    style={[styles.input, { flex: 1, color: theme.text, borderColor: theme.border, backgroundColor: theme.bgSoft }]}
                    placeholder="Mileage"
                    placeholderTextColor={theme.textMuted}
                    keyboardType="numeric"
                    value={tradeIn.mileage}
                    onChangeText={t => setTradeIn(p => ({ ...p, mileage: t }))}
                    data-testid="smart-cars-tradein-mileage"
                    testID="smart-cars-tradein-mileage"
                  />
                </View>
              </View>

              <TouchableOpacity
                style={{ backgroundColor: accentColor, padding: 14, borderRadius: 12, alignItems: 'center', marginTop: 16 }}
                onPress={handleTradeIn}
                disabled={loading}
                data-testid="smart-cars-tradein-button"
                testID="smart-cars-tradein-button"
                accessibilityRole="button"
              >
                {loading ? <ActivityIndicator color={theme.primaryText} /> : <Text style={{ color: theme.primaryText, fontWeight: '700' }}>Get Instant Offer</Text>}
              </TouchableOpacity>
            </View>

            {tradeInResult && (
              <View style={{ backgroundColor: theme.card, padding: 16, borderRadius: 16, borderWidth: 1, borderColor: theme.border }} data-testid="smart-cars-tradein-result" testID="smart-cars-tradein-result">
                <Text style={{ fontSize: 18, fontWeight: '700', color: theme.text }}>Your Offer</Text>
                <Text style={{ fontSize: 32, fontWeight: '800', color: theme.successText, marginVertical: 8 }}>${tradeInResult.estimated_value.toLocaleString()}</Text>
                <AIFeedbackBar feature="smart-cars" compact />
                <Text style={{ fontSize: 14, color: theme.textSec, lineHeight: 20 }}>{tradeInResult.market_notes}</Text>
              </View>
            )}
          </View>
        )}

        {activeTab === 'finance' && (
          <View style={{ alignItems: 'center', justifyContent: 'center', height: 300, backgroundColor: theme.bgSoft, borderRadius: 16, padding: 20 }} data-testid="smart-cars-finance-panel" testID="smart-cars-finance-panel">
            <Ionicons name="card" size={48} color={theme.textMuted} />
            <Text style={{ marginTop: 12, fontSize: 16, fontWeight: '700', color: theme.text }} data-testid="smart-cars-finance-title" testID="smart-cars-finance-title">Instant Financing</Text>
            <Text style={{ fontSize: 13, color: theme.textSec, textAlign: 'center', marginTop: 8 }} data-testid="smart-cars-finance-note" testID="smart-cars-finance-note">
              Get pre-qualified in seconds without impacting your credit score. (Basic/Premium feature)
            </Text>
            <TouchableOpacity
              style={{ marginTop: 16, backgroundColor: theme.success, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 10 }}
              data-testid="smart-cars-finance-check"
              testID="smart-cars-finance-check"
              accessibilityRole="button"
            >
              <Text style={{ color: theme.primaryText, fontWeight: '700' }}>Check Rates</Text>
            </TouchableOpacity>
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
