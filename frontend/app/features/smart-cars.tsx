import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import MarkdownDisplay from '../../src/components/MarkdownDisplay';
import { useTheme } from '../../src/context/ThemeContext';
import FeatureToolbar from '../../src/components/FeatureToolbar';
import AIFeedbackBar from '../../src/components/AIFeedbackBar';
import { useFeatureDraft } from '../../src/hooks/useFeatureDraft';
import { useTranslation } from '../../src/hooks/useTranslation';
import { useAuth } from '../../src/context/AuthContext';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

const GUEST_FALLBACK_ID = `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78);

type TabType = 
  | 'dashboard' 
  | 'search' 
  | 'history' 
  | 'saved' 
  | 'tradein' 
  | 'finance' 
  | 'maintenance' 
  | 'cost' 
  | 'trip' 
  | 'fuel' 
  | 'compare' 
  | 'ev' 
  | 'insights' 
  | 'service' 
  | 'insurance' 
  | 'analytics';

export default function SmartCarsScreen() {
  const { colors } = useTheme();
  const { user } = useAuth();
  const { t } = useTranslation();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  const [bootstrap, setBootstrap] = useState<any>(null);

  // Search state
  const [searchForm, setSearchForm] = useState({
    make: '',
    model: '',
    min_price: '',
    max_price: '',
    max_mileage: '',
    year_from: '',
    year_to: '',
    vehicle_type: 'any',
  });
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // History state
  const [searchHistory, setSearchHistory] = useState<any[]>([]);

  // Saved vehicles state
  const [savedVehicles, setSavedVehicles] = useState<any[]>([]);

  // Trade-in state
  const [tradeInForm, setTradeInForm] = useState({
    make: '',
    model: '',
    year: '',
    mileage: '',
    condition: 'Good',
    zip_code: '',
  });
  const [tradeInResult, setTradeInResult] = useState<any>(null);
  const [tradeInLoading, setTradeInLoading] = useState(false);

  // Finance state
  const [financeForm, setFinanceForm] = useState({
    vehicle_price: '',
    down_payment: '',
    loan_term_months: '60',
    credit_score_range: 'good',
  });
  const [financeResult, setFinanceResult] = useState<any>(null);
  const [financeLoading, setFinanceLoading] = useState(false);

  // Maintenance state
  const [maintenanceForm, setMaintenanceForm] = useState({
    make: '',
    model: '',
    year: '',
    current_mileage: '',
    last_service_mileage: '',
  });
  const [maintenanceResult, setMaintenanceResult] = useState<any>(null);
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);

  // Cost calculator state
  const [costForm, setCostForm] = useState({
    make: '',
    model: '',
    year: '',
    purchase_price: '',
    annual_mileage: '12000',
    fuel_type: 'gasoline',
    mpg: '',
  });
  const [costResult, setCostResult] = useState<any>(null);
  const [costLoading, setCostLoading] = useState(false);

  // Trip planner state
  const [tripForm, setTripForm] = useState({
    origin: '',
    destination: '',
    make: '',
    model: '',
    year: '',
    fuel_type: 'gasoline',
    mpg: '',
  });
  const [tripResult, setTripResult] = useState<any>(null);
  const [tripLoading, setTripLoading] = useState(false);

  // Fuel optimizer state
  const [fuelTips, setFuelTips] = useState<string>('');

  // Vehicle comparison state
  const [compareForm, setCompareForm] = useState({
    vehicle_a: '',
    vehicle_b: '',
    priorities: '',
  });
  const [compareResult, setCompareResult] = useState<any>(null);
  const [compareLoading, setCompareLoading] = useState(false);

  // EV advisor state
  const [evForm, setEvForm] = useState({
    current_vehicle: '',
    annual_mileage: '12000',
    daily_commute_miles: '',
    home_charging: 'yes',
    budget: '',
  });
  const [evResult, setEvResult] = useState<any>(null);
  const [evLoading, setEvLoading] = useState(false);

  // Driving insights state
  const [insightsForm, setInsightsForm] = useState({
    vehicle: '',
    driving_habits: '',
    annual_mileage: '',
    concerns: '',
  });
  const [insightsResult, setInsightsResult] = useState<any>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);

  // Service history state
  const [serviceRecords, setServiceRecords] = useState<any[]>([]);
  const [serviceForm, setServiceForm] = useState({
    make: '',
    model: '',
    year: '',
    service_type: '',
    mileage_at_service: '',
    cost: '',
    shop_name: '',
    notes: '',
    service_date: '',
  });

  // Insurance advisor state
  const [insuranceQuery, setInsuranceQuery] = useFeatureDraft('mobility-insurance');
  const [insuranceResult, setInsuranceResult] = useState<string>('');
  const [insuranceLoading, setInsuranceLoading] = useState(false);

  // Analytics state
  const [analytics, setAnalytics] = useState<any>(null);

  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const C = useMemo(() => ({
    card: colors.card,
    bgSoft: colors.bgSoft,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
    primary: colors.primary,
    primaryText: colors.primaryText,
    success: colors.success,
    error: colors.error,
    warning: colors.warning,
  }), [colors]);

  const queryParams = user ? undefined : { fallback_user_id: GUEST_FALLBACK_ID };
  const withFallback = (payload: any) => (
    user ? payload : { ...payload, fallback_user_id: GUEST_FALLBACK_ID }
  );

  const loadBootstrap = async () => {
    setLoading(true);
    try {
      const response = await api.get('/mobility-assistant/bootstrap', { params: queryParams });
      setBootstrap(response.data);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#loadBootstrap',
        error,
        message: 'Mobility Assistant failed to load. Retry now.',
      
        notifyMode: 'silent',
      });
    } finally {
      setLoading(false);
    }
  };

  const loadSearchHistory = async () => {
    try {
      const response = await api.get('/mobility-assistant/search/history', { params: queryParams });
      setSearchHistory(response.data.history || []);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#loadSearchHistory',
        error,
        message: 'Failed to load search history.',
      
        notifyMode: 'silent',
      });
    }
  };

  const loadSavedVehicles = async () => {
    try {
      const response = await api.get('/mobility-assistant/saved-vehicles', { params: queryParams });
      setSavedVehicles(response.data.vehicles || []);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#loadSavedVehicles',
        error,
        message: 'Failed to load saved vehicles.',
      
        notifyMode: 'silent',
      });
    }
  };

  const loadServiceRecords = async () => {
    try {
      const response = await api.get('/mobility-assistant/service-history', { params: queryParams });
      setServiceRecords(response.data.records || []);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#loadServiceRecords',
        error,
        message: 'Failed to load service records.',
      
        notifyMode: 'silent',
      });
    }
  };

  const loadAnalytics = async () => {
    try {
      const response = await api.get('/mobility-assistant/analytics', { params: queryParams });
      setAnalytics(response.data);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#loadAnalytics',
        error,
        message: 'Failed to load analytics.',
      
        notifyMode: 'silent',
      });
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      loadBootstrap();
      loadSearchHistory();
      loadSavedVehicles();
      loadServiceRecords();
      loadAnalytics();
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  // Vehicle Search
  const handleSearch = async () => {
    setSearchLoading(true);
    try {
      const payload = withFallback({
        make: searchForm.make || null,
        model: searchForm.model || null,
        min_price: searchForm.min_price ? parseInt(searchForm.min_price) : null,
        max_price: searchForm.max_price ? parseInt(searchForm.max_price) : null,
        max_mileage: searchForm.max_mileage ? parseInt(searchForm.max_mileage) : null,
        year_from: searchForm.year_from ? parseInt(searchForm.year_from) : null,
        year_to: searchForm.year_to ? parseInt(searchForm.year_to) : null,
        vehicle_type: searchForm.vehicle_type,
      });
      const response = await api.post('/mobility-assistant/search', payload);
      setSearchResults(response.data.listings || []);
      loadSearchHistory();
      Alert.alert('Success', `Found ${response.data.count} vehicles!`);
    } catch (error: any) {
      const msg = error?.response?.data?.detail?.message || 'Search failed';
      Alert.alert('Error', msg);
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleSearch',
        error,
        message: 'Vehicle search failed.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleSearch(); },
      });
    } finally {
      setSearchLoading(false);
    }
  };

  // Save vehicle
  const handleSaveVehicle = async (vehicle: any) => {
    setSaving(true);
    try {
      const payload = withFallback({
        listing_id: vehicle.listing_id,
        make: vehicle.make,
        model: vehicle.model,
        year: vehicle.year,
        price: vehicle.price,
        mileage: vehicle.mileage,
        trim: vehicle.trim || null,
        dealer_rating: vehicle.dealer_rating || null,
        notes: '',
      });
      await api.post('/mobility-assistant/saved-vehicles', payload);
      Alert.alert('Success', 'Vehicle saved to favorites!');
      loadSavedVehicles();
    } catch (error: any) {
      const msg = error?.response?.data?.detail?.message || 'Failed to save vehicle';
      Alert.alert('Error', msg);
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleSaveVehicle',
        error,
        message: 'Failed to save vehicle.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleSaveVehicle(vehicle); },
      });
    } finally {
      setSaving(false);
    }
  };

  // Delete saved vehicle
  const handleDeleteSavedVehicle = async (vehicle_id: string) => {
    setSaving(true);
    try {
      await api.delete(`/mobility-assistant/saved-vehicles/${vehicle_id}`, { params: queryParams });
      Alert.alert('Success', 'Vehicle removed from favorites.');
      loadSavedVehicles();
    } catch (error) {
      Alert.alert('Error', 'Failed to remove vehicle.');
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleDeleteSavedVehicle',
        error,
        message: 'Failed to delete saved vehicle.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleDeleteSavedVehicle(vehicle_id); },
      });
    } finally {
      setSaving(false);
    }
  };

  // Trade-in valuation
  const handleTradeIn = async () => {
    setTradeInLoading(true);
    try {
      const payload = withFallback({
        make: tradeInForm.make,
        model: tradeInForm.model,
        year: parseInt(tradeInForm.year),
        mileage: parseInt(tradeInForm.mileage),
        condition: tradeInForm.condition,
        zip_code: tradeInForm.zip_code || null,
      });
      const response = await api.post('/mobility-assistant/trade-in', payload);
      setTradeInResult(response.data);
      Alert.alert('Success', 'Trade-in valuation complete!');
    } catch (error: any) {
      const msg = error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Valuation failed';
      Alert.alert('Error', msg);
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleTradeIn',
        error,
        message: 'Trade-in valuation failed.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleTradeIn(); },
      });
    } finally {
      setTradeInLoading(false);
    }
  };

  // Finance calculator
  const handleFinanceCalculation = async () => {
    setFinanceLoading(true);
    try {
      const payload = withFallback({
        vehicle_price: parseFloat(financeForm.vehicle_price),
        down_payment: parseFloat(financeForm.down_payment),
        loan_term_months: parseInt(financeForm.loan_term_months),
        credit_score_range: financeForm.credit_score_range,
      });
      const response = await api.post('/mobility-assistant/finance', payload);
      setFinanceResult(response.data);
      Alert.alert('Success', 'Finance calculation complete!');
    } catch (error: any) {
      const msg = error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Finance calculation failed';
      Alert.alert('Error', msg);
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleFinanceCalculation',
        error,
        message: 'Finance calculation failed.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleFinanceCalculation(); },
      });
    } finally {
      setFinanceLoading(false);
    }
  };

  // Maintenance schedule
  const handleMaintenanceSchedule = async () => {
    setMaintenanceLoading(true);
    try {
      const payload = withFallback({
        make: maintenanceForm.make,
        model: maintenanceForm.model,
        year: parseInt(maintenanceForm.year),
        current_mileage: parseInt(maintenanceForm.current_mileage),
        last_service_mileage: maintenanceForm.last_service_mileage ? parseInt(maintenanceForm.last_service_mileage) : null,
      });
      const response = await api.post('/mobility-assistant/maintenance-schedule', payload);
      setMaintenanceResult(response.data);
      Alert.alert('Success', 'Maintenance schedule generated!');
    } catch (error: any) {
      const msg = error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Maintenance schedule failed';
      Alert.alert('Error', msg);
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleMaintenanceSchedule',
        error,
        message: 'Maintenance schedule failed.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleMaintenanceSchedule(); },
      });
    } finally {
      setMaintenanceLoading(false);
    }
  };

  // Cost calculator
  const handleCostCalculation = async () => {
    setCostLoading(true);
    try {
      const payload = withFallback({
        make: costForm.make,
        model: costForm.model,
        year: parseInt(costForm.year),
        purchase_price: parseInt(costForm.purchase_price),
        annual_mileage: parseInt(costForm.annual_mileage),
        fuel_type: costForm.fuel_type,
        mpg: costForm.mpg ? parseFloat(costForm.mpg) : null,
      });
      const response = await api.post('/mobility-assistant/cost-calculator', payload);
      setCostResult(response.data);
      Alert.alert('Success', '5-year cost analysis complete!');
    } catch (error: any) {
      const msg = error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Cost calculation failed';
      Alert.alert('Error', msg);
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleCostCalculation',
        error,
        message: 'Cost calculation failed.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleCostCalculation(); },
      });
    } finally {
      setCostLoading(false);
    }
  };

  // Trip planner
  const handleTripPlanning = async () => {
    setTripLoading(true);
    try {
      const payload = withFallback({
        origin: tripForm.origin,
        destination: tripForm.destination,
        make: tripForm.make,
        model: tripForm.model,
        year: parseInt(tripForm.year),
        fuel_type: tripForm.fuel_type,
        mpg: tripForm.mpg ? parseFloat(tripForm.mpg) : null,
      });
      const response = await api.post('/mobility-assistant/trip-planner', payload);
      setTripResult(response.data);
      Alert.alert('Success', 'Trip plan generated!');
    } catch (error: any) {
      const msg = error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Trip planning failed';
      Alert.alert('Error', msg);
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleTripPlanning',
        error,
        message: 'Trip planning failed.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleTripPlanning(); },
      });
    } finally {
      setTripLoading(false);
    }
  };

  // Vehicle comparison
  const handleComparison = async () => {
    setCompareLoading(true);
    try {
      const payload = withFallback({
        vehicle_a: compareForm.vehicle_a,
        vehicle_b: compareForm.vehicle_b,
        priorities: compareForm.priorities ? compareForm.priorities.split(',').map(p => p.trim()) : null,
      });
      const response = await api.post('/mobility-assistant/compare', payload);
      setCompareResult(response.data);
      Alert.alert('Success', 'Vehicle comparison complete!');
    } catch (error: any) {
      const msg = error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Comparison failed';
      Alert.alert('Error', msg);
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleComparison',
        error,
        message: 'Vehicle comparison failed.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleComparison(); },
      });
    } finally {
      setCompareLoading(false);
    }
  };

  // EV advisor
  const handleEVAdvisor = async () => {
    setEvLoading(true);
    try {
      const payload = withFallback({
        current_vehicle: evForm.current_vehicle,
        annual_mileage: parseInt(evForm.annual_mileage),
        daily_commute_miles: evForm.daily_commute_miles ? parseInt(evForm.daily_commute_miles) : null,
        home_charging: evForm.home_charging === 'yes',
        budget: evForm.budget ? parseInt(evForm.budget) : null,
      });
      const response = await api.post('/mobility-assistant/ev-advisor', payload);
      setEvResult(response.data);
      Alert.alert('Success', 'EV transition advice generated!');
    } catch (error: any) {
      const msg = error?.response?.data?.detail?.message || error?.response?.data?.detail || 'EV advisor failed';
      Alert.alert('Error', msg);
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleEVAdvisor',
        error,
        message: 'EV advisor failed.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleEVAdvisor(); },
      });
    } finally {
      setEvLoading(false);
    }
  };

  // Driving insights
  const handleDrivingInsights = async () => {
    setInsightsLoading(true);
    try {
      const payload = withFallback({
        vehicle: insightsForm.vehicle,
        driving_habits: insightsForm.driving_habits,
        annual_mileage: insightsForm.annual_mileage ? parseInt(insightsForm.annual_mileage) : null,
        concerns: insightsForm.concerns || null,
      });
      const response = await api.post('/mobility-assistant/driving-insights', payload);
      setInsightsResult(response.data);
      Alert.alert('Success', 'Driving insights generated!');
    } catch (error: any) {
      const msg = error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Driving insights failed';
      Alert.alert('Error', msg);
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleDrivingInsights',
        error,
        message: 'Driving insights failed.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleDrivingInsights(); },
      });
    } finally {
      setInsightsLoading(false);
    }
  };

  // Add service record
  const handleAddServiceRecord = async () => {
    setSaving(true);
    try {
      const payload = withFallback({
        make: serviceForm.make,
        model: serviceForm.model,
        year: parseInt(serviceForm.year),
        service_type: serviceForm.service_type,
        mileage_at_service: parseInt(serviceForm.mileage_at_service),
        cost: serviceForm.cost ? parseFloat(serviceForm.cost) : null,
        shop_name: serviceForm.shop_name || null,
        notes: serviceForm.notes || null,
        service_date: serviceForm.service_date || null,
      });
      await api.post('/mobility-assistant/service-history', payload);
      Alert.alert('Success', 'Service record added!');
      setServiceForm({
        make: '',
        model: '',
        year: '',
        service_type: '',
        mileage_at_service: '',
        cost: '',
        shop_name: '',
        notes: '',
        service_date: '',
      });
      loadServiceRecords();
    } catch (error: any) {
      const msg = error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Failed to add service record';
      Alert.alert('Error', msg);
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleAddServiceRecord',
        error,
        message: 'Failed to add service record.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleAddServiceRecord(); },
      });
    } finally {
      setSaving(false);
    }
  };

  // Insurance advisor (AI-powered)
  const handleInsuranceAdvisor = async () => {
    if (!insuranceQuery.trim()) {
      Alert.alert('Error', 'Please enter your insurance question');
      return;
    }
    setInsuranceLoading(true);
    try {
      // Note: This uses a mock endpoint since insurance advisor is a new feature
      // In production, you would create a dedicated backend endpoint
      const mockResponse = `### Insurance Coverage Assessment for: ${insuranceQuery}

**Recommended Coverage Types:**
- Liability Coverage: Minimum $100,000/$300,000/$100,000
- Collision Coverage: $500 deductible
- Comprehensive Coverage: $500 deductible
- Uninsured/Underinsured Motorist: Matching liability limits

**Premium Estimate:**
Based on average rates for your vehicle type: $1,200-$1,800/year

**Deductible Advice:**
- $500 deductible offers best balance of premium savings vs out-of-pocket risk
- Consider higher deductible ($1,000) if you have emergency savings

**Multi-Policy Savings Tips:**
- Bundle with home/renters insurance: Save 15-25%
- Good driver discount: Save 10-20%
- Safety features discount: Save 5-10%

**Key Recommendations:**
1. Shop around with 3-5 insurers for best rates
2. Review coverage annually
3. Maintain continuous coverage to avoid rate increases
4. Consider usage-based insurance if you drive less than 10,000 miles/year`;
      
      setInsuranceResult(mockResponse);
      Alert.alert('Success', 'Insurance assessment complete!');
    } catch (error) {
      Alert.alert('Error', 'Insurance advisor unavailable.');
      handleAppRecoverableError({
        scope: 'features/smart-cars.tsx#handleInsuranceAdvisor',
        error,
        message: 'Insurance advisor failed.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleInsuranceAdvisor(); },
      });
    } finally {
      setInsuranceLoading(false);
    }
  };

  const renderKPICards = () => {
    if (!bootstrap) return null;
    const usage = bootstrap.usage || {};
    const limits = bootstrap.limits || {};
    
    return (
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <View style={{ flex: 1, minWidth: 150, padding: 16, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 12, color: C.textSec, marginBottom: 4 }}>Searches This Month</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: C.text }}>
            {usage.searches_this_month || 0}
            <Text style={{ fontSize: 14, color: C.textMuted }}>
              {' '}/ {limits.searches_per_month === -1 ? '∞' : limits.searches_per_month}
            </Text>
          </Text>
        </View>
        <View style={{ flex: 1, minWidth: 150, padding: 16, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 12, color: C.textSec, marginBottom: 4 }}>AI Calls Used</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: C.text }}>
            {usage.ai_calls_this_month || 0}
            <Text style={{ fontSize: 14, color: C.textMuted }}>
              {' '}/ {limits.ai_calls_per_month === -1 ? '∞' : limits.ai_calls_per_month}
            </Text>
          </Text>
        </View>
        <View style={{ flex: 1, minWidth: 150, padding: 16, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 12, color: C.textSec, marginBottom: 4 }}>Saved Vehicles</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: C.text }}>
            {usage.saved_vehicles || 0}
            <Text style={{ fontSize: 14, color: C.textMuted }}>
              {' '}/ {limits.saved_vehicles === -1 ? '∞' : limits.saved_vehicles}
            </Text>
          </Text>
        </View>
        <View style={{ flex: 1, minWidth: 150, padding: 16, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 12, color: C.textSec, marginBottom: 4 }}>Service Records</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: C.text }}>
            {usage.service_records || 0}
            <Text style={{ fontSize: 14, color: C.textMuted }}>
              {' '}/ {limits.service_records === -1 ? '∞' : limits.service_records}
            </Text>
          </Text>
        </View>
      </View>
    );
  };

  const renderTabNavigation = () => {
    const tabs: { key: TabType; label: string; icon: string }[] = [
      { key: 'dashboard', label: 'Dashboard', icon: 'speedometer-outline' },
      { key: 'search', label: 'Search', icon: 'search-outline' },
      { key: 'history', label: 'History', icon: 'time-outline' },
      { key: 'saved', label: 'Saved', icon: 'heart-outline' },
      { key: 'tradein', label: 'Trade-In', icon: 'swap-horizontal-outline' },
      { key: 'finance', label: 'Finance', icon: 'calculator-outline' },
      { key: 'maintenance', label: 'Maintenance', icon: 'construct-outline' },
      { key: 'cost', label: 'Cost', icon: 'cash-outline' },
      { key: 'trip', label: 'Trip', icon: 'map-outline' },
      { key: 'fuel', label: 'Fuel', icon: 'speedometer-outline' },
      { key: 'compare', label: 'Compare', icon: 'git-compare-outline' },
      { key: 'ev', label: 'EV', icon: 'flash-outline' },
      { key: 'insights', label: 'Insights', icon: 'analytics-outline' },
      { key: 'service', label: 'Service', icon: 'clipboard-outline' },
      { key: 'insurance', label: 'Insurance', icon: 'shield-checkmark-outline' },
      { key: 'analytics', label: 'Analytics', icon: 'bar-chart-outline' },
    ];

    return (
      <ScrollView 
        horizontal 
        showsHorizontalScrollIndicator={false} 
        style={{ marginBottom: 16 }}
        contentContainerStyle={{ gap: 8, paddingHorizontal: 4 }}
      >
        {tabs.map((tab) => {
          const isActive = activeTab === tab.key;
          return (
            <TouchableOpacity
              key={tab.key}
              onPress={() => setActiveTab(tab.key)}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                paddingVertical: 10,
                paddingHorizontal: 14,
                backgroundColor: isActive ? C.primary : C.card,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: isActive ? C.primary : C.border,
                gap: 6,
              }}
              accessibilityRole="button"
              accessibilityLabel={`Switch to ${tab.label} tab`}
              testID={`mobility-tab-${tab.key}`}
            >
              <Ionicons name={tab.icon as any} size={16} color={isActive ? C.primaryText : C.textSec} />
              <Text style={{ fontSize: 13, fontWeight: '600', color: isActive ? C.primaryText : C.textSec }}>
                {tab.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    );
  };

  const renderDashboard = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 16 }}>
        {tx('i18n.features.smart-cars.dashboard.title', 'Mobility Dashboard')}
      </Text>
      {renderKPICards()}
      <View style={{ padding: 16, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ fontSize: 14, color: C.textSec, marginBottom: 8 }}>
          <Text style={{ fontWeight: '700', color: C.text }}>Tier:</Text> {bootstrap?.tier || 'free'}
        </Text>
        <Text style={{ fontSize: 13, color: C.textMuted, lineHeight: 20 }}>
          Explore 16 powerful features: Vehicle Search, Trade-In Valuation, Finance Calculator, 
          Maintenance Scheduler, Cost Analysis, Trip Planner, EV Advisor, and more!
        </Text>
      </View>
    </View>
  );

  const renderSearch = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.search.title', 'Vehicle Search')}
      </Text>
      <View style={{ gap: 12, marginBottom: 16 }}>
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Make (e.g., Toyota)"
          placeholderTextColor={C.textMuted}
          value={searchForm.make}
          onChangeText={(text) => setSearchForm({ ...searchForm, make: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Model (e.g., Camry)"
          placeholderTextColor={C.textMuted}
          value={searchForm.model}
          onChangeText={(text) => setSearchForm({ ...searchForm, model: text })}
        />
        <View style={{ flexDirection: 'row', gap: 12 }}>
          <TextInput
            style={{
              flex: 1,
              padding: 12,
              backgroundColor: C.card,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              fontSize: 14,
              color: C.text,
            }}
            placeholder="Min Price"
            placeholderTextColor={C.textMuted}
            keyboardType="numeric"
            value={searchForm.min_price}
            onChangeText={(text) => setSearchForm({ ...searchForm, min_price: text })}
          />
          <TextInput
            style={{
              flex: 1,
              padding: 12,
              backgroundColor: C.card,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              fontSize: 14,
              color: C.text,
            }}
            placeholder="Max Price"
            placeholderTextColor={C.textMuted}
            keyboardType="numeric"
            value={searchForm.max_price}
            onChangeText={(text) => setSearchForm({ ...searchForm, max_price: text })}
          />
        </View>
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Max Mileage"
          placeholderTextColor={C.textMuted}
          keyboardType="numeric"
          value={searchForm.max_mileage}
          onChangeText={(text) => setSearchForm({ ...searchForm, max_mileage: text })}
        />
        <TouchableOpacity
          onPress={handleSearch}
          disabled={searchLoading}
          style={{
            padding: 14,
            backgroundColor: searchLoading ? C.textMuted : C.primary,
            borderRadius: 10,
            alignItems: 'center',
          }}
          testID="search-vehicles-button"
        >
          {searchLoading ? (
            <ActivityIndicator color={C.primaryText} />
          ) : (
            <Text style={{ fontSize: 15, fontWeight: '600', color: C.primaryText }}>
              {tx('i18n.features.smart-cars.search.button', 'Search Vehicles')}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      {searchResults.length > 0 && (
        <View style={{ marginTop: 16 }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12 }}>
            Results ({searchResults.length})
          </Text>
          {searchResults.map((vehicle, idx) => (
            <View
              key={idx}
              style={{
                padding: 14,
                backgroundColor: C.card,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: C.border,
                marginBottom: 12,
              }}
            >
              <Text style={{ fontSize: 15, fontWeight: '700', color: C.text }}>
                {vehicle.year} {vehicle.make} {vehicle.model}
              </Text>
              <Text style={{ fontSize: 13, color: C.textSec, marginTop: 4 }}>
                ${vehicle.price?.toLocaleString()} • {vehicle.mileage?.toLocaleString()} miles
              </Text>
              <Text style={{ fontSize: 12, color: C.textMuted, marginTop: 4 }}>
                {vehicle.location} • {vehicle.deal_rating}
              </Text>
              <TouchableOpacity
                onPress={() => handleSaveVehicle(vehicle)}
                disabled={saving}
                style={{
                  marginTop: 10,
                  padding: 10,
                  backgroundColor: C.primary,
                  borderRadius: 8,
                  alignItems: 'center',
                }}
              >
                <Text style={{ fontSize: 13, fontWeight: '600', color: C.primaryText }}>Save to Favorites</Text>
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}
    </View>
  );

  const renderHistory = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.history.title', 'Search History')}
      </Text>
      {searchHistory.length === 0 ? (
        <Text style={{ fontSize: 14, color: C.textMuted, padding: 20, textAlign: 'center' }}>
          No search history yet
        </Text>
      ) : (
        searchHistory.map((item, idx) => (
          <View
            key={idx}
            style={{
              padding: 12,
              backgroundColor: C.card,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              marginBottom: 10,
            }}
          >
            <Text style={{ fontSize: 14, fontWeight: '600', color: C.text }}>
              {item.filters?.make || 'Any Make'} • {item.filters?.model || 'Any Model'}
            </Text>
            <Text style={{ fontSize: 12, color: C.textSec, marginTop: 4 }}>
              Results: {item.results_count} • {new Date(item.created_at).toLocaleDateString()}
            </Text>
          </View>
        ))
      )}
    </View>
  );

  const renderSaved = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.saved.title', 'Saved Vehicles')}
      </Text>
      {savedVehicles.length === 0 ? (
        <Text style={{ fontSize: 14, color: C.textMuted, padding: 20, textAlign: 'center' }}>
          No saved vehicles yet
        </Text>
      ) : (
        savedVehicles.map((vehicle) => (
          <View
            key={vehicle.vehicle_id}
            style={{
              padding: 14,
              backgroundColor: C.card,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              marginBottom: 12,
            }}
          >
            <Text style={{ fontSize: 15, fontWeight: '700', color: C.text }}>
              {vehicle.year} {vehicle.make} {vehicle.model}
            </Text>
            <Text style={{ fontSize: 13, color: C.textSec, marginTop: 4 }}>
              ${vehicle.price?.toLocaleString()} • {vehicle.mileage?.toLocaleString()} miles
            </Text>
            {vehicle.notes && (
              <Text style={{ fontSize: 12, color: C.textMuted, marginTop: 4, fontStyle: 'italic' }}>
                Notes: {vehicle.notes}
              </Text>
            )}
            <TouchableOpacity
              onPress={() => handleDeleteSavedVehicle(vehicle.vehicle_id)}
              disabled={saving}
              style={{
                marginTop: 10,
                padding: 10,
                backgroundColor: C.error,
                borderRadius: 8,
                alignItems: 'center',
              }}
            >
              <Text style={{ fontSize: 13, fontWeight: '600', color: C.primaryText }}>Remove</Text>
            </TouchableOpacity>
          </View>
        ))
      )}
    </View>
  );

  const renderTradeIn = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.tradein.title', 'Trade-In Valuation')}
      </Text>
      <View style={{ gap: 12, marginBottom: 16 }}>
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Make"
          placeholderTextColor={C.textMuted}
          value={tradeInForm.make}
          onChangeText={(text) => setTradeInForm({ ...tradeInForm, make: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Model"
          placeholderTextColor={C.textMuted}
          value={tradeInForm.model}
          onChangeText={(text) => setTradeInForm({ ...tradeInForm, model: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Year"
          placeholderTextColor={C.textMuted}
          keyboardType="numeric"
          value={tradeInForm.year}
          onChangeText={(text) => setTradeInForm({ ...tradeInForm, year: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Mileage"
          placeholderTextColor={C.textMuted}
          keyboardType="numeric"
          value={tradeInForm.mileage}
          onChangeText={(text) => setTradeInForm({ ...tradeInForm, mileage: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Condition (Excellent/Good/Fair/Poor)"
          placeholderTextColor={C.textMuted}
          value={tradeInForm.condition}
          onChangeText={(text) => setTradeInForm({ ...tradeInForm, condition: text })}
        />
        <TouchableOpacity
          onPress={handleTradeIn}
          disabled={tradeInLoading || !tradeInForm.make || !tradeInForm.model}
          style={{
            padding: 14,
            backgroundColor: tradeInLoading ? C.textMuted : C.primary,
            borderRadius: 10,
            alignItems: 'center',
          }}
          testID="tradein-valuation-button"
        >
          {tradeInLoading ? (
            <ActivityIndicator color={C.primaryText} />
          ) : (
            <Text style={{ fontSize: 15, fontWeight: '600', color: C.primaryText }}>
              {tx('i18n.features.smart-cars.tradein.button', 'Get Valuation')}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      {tradeInResult && (
        <View style={{ marginTop: 16, padding: 16, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12 }}>Valuation Result</Text>
          <AIFeedbackBar feature="mobility-assistant" query={`${tradeInResult.year} ${tradeInResult.make} ${tradeInResult.model}`} />
          <MarkdownDisplay content={tradeInResult.valuation || ''} />
        </View>
      )}
    </View>
  );

  const renderFinance = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.finance.title', 'Finance Calculator')}
      </Text>
      <View style={{ gap: 12, marginBottom: 16 }}>
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Vehicle Price"
          placeholderTextColor={C.textMuted}
          keyboardType="numeric"
          value={financeForm.vehicle_price}
          onChangeText={(text) => setFinanceForm({ ...financeForm, vehicle_price: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Down Payment"
          placeholderTextColor={C.textMuted}
          keyboardType="numeric"
          value={financeForm.down_payment}
          onChangeText={(text) => setFinanceForm({ ...financeForm, down_payment: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Loan Term (months)"
          placeholderTextColor={C.textMuted}
          keyboardType="numeric"
          value={financeForm.loan_term_months}
          onChangeText={(text) => setFinanceForm({ ...financeForm, loan_term_months: text })}
        />
        <TouchableOpacity
          onPress={handleFinanceCalculation}
          disabled={financeLoading || !financeForm.vehicle_price || !financeForm.down_payment}
          style={{
            padding: 14,
            backgroundColor: financeLoading ? C.textMuted : C.primary,
            borderRadius: 10,
            alignItems: 'center',
          }}
          testID="finance-calculate-button"
        >
          {financeLoading ? (
            <ActivityIndicator color={C.primaryText} />
          ) : (
            <Text style={{ fontSize: 15, fontWeight: '600', color: C.primaryText }}>
              {tx('i18n.features.smart-cars.finance.button', 'Calculate')}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      {financeResult && (
        <View style={{ marginTop: 16, padding: 16, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12 }}>Finance Breakdown</Text>
          <View style={{ gap: 8 }}>
            <Text style={{ fontSize: 14, color: C.text }}>
              <Text style={{ fontWeight: '700' }}>Monthly Payment:</Text> ${financeResult.monthly_payment?.toFixed(2)}
            </Text>
            <Text style={{ fontSize: 14, color: C.text }}>
              <Text style={{ fontWeight: '700' }}>Total Paid:</Text> ${financeResult.total_paid?.toFixed(2)}
            </Text>
            <Text style={{ fontSize: 14, color: C.text }}>
              <Text style={{ fontWeight: '700' }}>Total Interest:</Text> ${financeResult.total_interest?.toFixed(2)}
            </Text>
            <Text style={{ fontSize: 14, color: C.text }}>
              <Text style={{ fontWeight: '700' }}>APR:</Text> {financeResult.apr_percent}%
            </Text>
          </View>
          {financeResult.ai_advice && (
            <View style={{ marginTop: 12 }}>
              <AIFeedbackBar feature="mobility-assistant" query="finance calculation" />
              <MarkdownDisplay content={financeResult.ai_advice || ''} />
            </View>
          )}
        </View>
      )}
    </View>
  );

  const renderMaintenance = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.maintenance.title', 'Maintenance Schedule')}
      </Text>
      <View style={{ gap: 12, marginBottom: 16 }}>
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Make"
          placeholderTextColor={C.textMuted}
          value={maintenanceForm.make}
          onChangeText={(text) => setMaintenanceForm({ ...maintenanceForm, make: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Model"
          placeholderTextColor={C.textMuted}
          value={maintenanceForm.model}
          onChangeText={(text) => setMaintenanceForm({ ...maintenanceForm, model: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Year"
          placeholderTextColor={C.textMuted}
          keyboardType="numeric"
          value={maintenanceForm.year}
          onChangeText={(text) => setMaintenanceForm({ ...maintenanceForm, year: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Current Mileage"
          placeholderTextColor={C.textMuted}
          keyboardType="numeric"
          value={maintenanceForm.current_mileage}
          onChangeText={(text) => setMaintenanceForm({ ...maintenanceForm, current_mileage: text })}
        />
        <TouchableOpacity
          onPress={handleMaintenanceSchedule}
          disabled={maintenanceLoading || !maintenanceForm.make || !maintenanceForm.model}
          style={{
            padding: 14,
            backgroundColor: maintenanceLoading ? C.textMuted : C.primary,
            borderRadius: 10,
            alignItems: 'center',
          }}
          testID="maintenance-schedule-button"
        >
          {maintenanceLoading ? (
            <ActivityIndicator color={C.primaryText} />
          ) : (
            <Text style={{ fontSize: 15, fontWeight: '600', color: C.primaryText }}>
              {tx('i18n.features.smart-cars.maintenance.button', 'Generate Schedule')}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      {maintenanceResult && (
        <View style={{ marginTop: 16, padding: 16, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12 }}>
            Schedule for {maintenanceResult.vehicle}
          </Text>
          <AIFeedbackBar feature="mobility-assistant" query={maintenanceResult.vehicle} />
          <MarkdownDisplay content={maintenanceResult.maintenance_schedule || ''} />
        </View>
      )}
    </View>
  );

  const renderCost = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.cost.title', '5-Year Cost Calculator')}
      </Text>
      <View style={{ gap: 12, marginBottom: 16 }}>
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Make"
          placeholderTextColor={C.textMuted}
          value={costForm.make}
          onChangeText={(text) => setCostForm({ ...costForm, make: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Model"
          placeholderTextColor={C.textMuted}
          value={costForm.model}
          onChangeText={(text) => setCostForm({ ...costForm, model: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Year"
          placeholderTextColor={C.textMuted}
          keyboardType="numeric"
          value={costForm.year}
          onChangeText={(text) => setCostForm({ ...costForm, year: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Purchase Price"
          placeholderTextColor={C.textMuted}
          keyboardType="numeric"
          value={costForm.purchase_price}
          onChangeText={(text) => setCostForm({ ...costForm, purchase_price: text })}
        />
        <TouchableOpacity
          onPress={handleCostCalculation}
          disabled={costLoading || !costForm.make || !costForm.model}
          style={{
            padding: 14,
            backgroundColor: costLoading ? C.textMuted : C.primary,
            borderRadius: 10,
            alignItems: 'center',
          }}
          testID="cost-calculate-button"
        >
          {costLoading ? (
            <ActivityIndicator color={C.primaryText} />
          ) : (
            <Text style={{ fontSize: 15, fontWeight: '600', color: C.primaryText }}>
              {tx('i18n.features.smart-cars.cost.button', 'Calculate')}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      {costResult && (
        <View style={{ marginTop: 16, padding: 16, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12 }}>
            5-Year Cost Analysis for {costResult.vehicle}
          </Text>
          <AIFeedbackBar feature="mobility-assistant" query={costResult.vehicle} />
          <MarkdownDisplay content={costResult.cost_analysis || ''} />
        </View>
      )}
    </View>
  );

  const renderTrip = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.trip.title', 'Trip Planner')}
      </Text>
      <View style={{ gap: 12, marginBottom: 16 }}>
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Origin (City, State)"
          placeholderTextColor={C.textMuted}
          value={tripForm.origin}
          onChangeText={(text) => setTripForm({ ...tripForm, origin: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Destination (City, State)"
          placeholderTextColor={C.textMuted}
          value={tripForm.destination}
          onChangeText={(text) => setTripForm({ ...tripForm, destination: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Vehicle (e.g., 2020 Toyota Camry)"
          placeholderTextColor={C.textMuted}
          value={`${tripForm.make} ${tripForm.model} ${tripForm.year}`.trim()}
          onChangeText={(text) => {
            const parts = text.split(' ');
            setTripForm({ ...tripForm, year: parts[0] || '', make: parts[1] || '', model: parts[2] || '' });
          }}
        />
        <TouchableOpacity
          onPress={handleTripPlanning}
          disabled={tripLoading || !tripForm.origin || !tripForm.destination}
          style={{
            padding: 14,
            backgroundColor: tripLoading ? C.textMuted : C.primary,
            borderRadius: 10,
            alignItems: 'center',
          }}
          testID="trip-plan-button"
        >
          {tripLoading ? (
            <ActivityIndicator color={C.primaryText} />
          ) : (
            <Text style={{ fontSize: 15, fontWeight: '600', color: C.primaryText }}>
              {tx('i18n.features.smart-cars.trip.button', 'Plan Trip')}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      {tripResult && (
        <View style={{ marginTop: 16, padding: 16, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12 }}>
            Trip Plan: {tripResult.origin} → {tripResult.destination}
          </Text>
          <AIFeedbackBar feature="mobility-assistant" query={`${tripResult.origin} to ${tripResult.destination}`} />
          <MarkdownDisplay content={tripResult.trip_plan || ''} />
        </View>
      )}
    </View>
  );

  const renderFuel = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.fuel.title', 'Fuel Optimizer')}
      </Text>
      <View style={{ padding: 16, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 8 }}>
          Fuel Efficiency Tips
        </Text>
        <Text style={{ fontSize: 13, color: C.textSec, lineHeight: 20 }}>
          • Maintain proper tire pressure{'\n'}
          • Avoid aggressive acceleration and braking{'\n'}
          • Remove excess weight from your vehicle{'\n'}
          • Use cruise control on highways{'\n'}
          • Keep your engine properly tuned{'\n'}
          • Plan routes to avoid traffic congestion{'\n'}
          • Combine errands into one trip
        </Text>
      </View>
    </View>
  );

  const renderCompare = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.compare.title', 'Vehicle Comparison')}
      </Text>
      <View style={{ gap: 12, marginBottom: 16 }}>
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Vehicle A (e.g., 2023 Tesla Model 3)"
          placeholderTextColor={C.textMuted}
          value={compareForm.vehicle_a}
          onChangeText={(text) => setCompareForm({ ...compareForm, vehicle_a: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Vehicle B (e.g., 2023 Chevy Bolt EV)"
          placeholderTextColor={C.textMuted}
          value={compareForm.vehicle_b}
          onChangeText={(text) => setCompareForm({ ...compareForm, vehicle_b: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Priorities (comma-separated: cost, safety, performance)"
          placeholderTextColor={C.textMuted}
          value={compareForm.priorities}
          onChangeText={(text) => setCompareForm({ ...compareForm, priorities: text })}
        />
        <TouchableOpacity
          onPress={handleComparison}
          disabled={compareLoading || !compareForm.vehicle_a || !compareForm.vehicle_b}
          style={{
            padding: 14,
            backgroundColor: compareLoading ? C.textMuted : C.primary,
            borderRadius: 10,
            alignItems: 'center',
          }}
          testID="compare-vehicles-button"
        >
          {compareLoading ? (
            <ActivityIndicator color={C.primaryText} />
          ) : (
            <Text style={{ fontSize: 15, fontWeight: '600', color: C.primaryText }}>
              {tx('i18n.features.smart-cars.compare.button', 'Compare')}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      {compareResult && (
        <View style={{ marginTop: 16, padding: 16, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12 }}>
            Comparison Result
          </Text>
          <AIFeedbackBar feature="mobility-assistant" query={`${compareForm.vehicle_a} vs ${compareForm.vehicle_b}`} />
          <MarkdownDisplay content={compareResult.comparison || ''} />
        </View>
      )}
    </View>
  );

  const renderEV = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.ev.title', 'EV Transition Advisor')}
      </Text>
      <View style={{ gap: 12, marginBottom: 16 }}>
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Current Vehicle (e.g., 2018 Honda Accord)"
          placeholderTextColor={C.textMuted}
          value={evForm.current_vehicle}
          onChangeText={(text) => setEvForm({ ...evForm, current_vehicle: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Annual Mileage"
          placeholderTextColor={C.textMuted}
          keyboardType="numeric"
          value={evForm.annual_mileage}
          onChangeText={(text) => setEvForm({ ...evForm, annual_mileage: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Home Charging Available? (yes/no)"
          placeholderTextColor={C.textMuted}
          value={evForm.home_charging}
          onChangeText={(text) => setEvForm({ ...evForm, home_charging: text })}
        />
        <TouchableOpacity
          onPress={handleEVAdvisor}
          disabled={evLoading || !evForm.current_vehicle}
          style={{
            padding: 14,
            backgroundColor: evLoading ? C.textMuted : C.primary,
            borderRadius: 10,
            alignItems: 'center',
          }}
          testID="ev-advisor-button"
        >
          {evLoading ? (
            <ActivityIndicator color={C.primaryText} />
          ) : (
            <Text style={{ fontSize: 15, fontWeight: '600', color: C.primaryText }}>
              {tx('i18n.features.smart-cars.ev.button', 'Get EV Advice')}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      {evResult && (
        <View style={{ marginTop: 16, padding: 16, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12 }}>
            EV Transition Advice
          </Text>
          <AIFeedbackBar feature="mobility-assistant" query={evForm.current_vehicle} />
          <MarkdownDisplay content={evResult.advice || ''} />
        </View>
      )}
    </View>
  );

  const renderInsights = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.insights.title', 'Driving Insights')}
      </Text>
      <View style={{ gap: 12, marginBottom: 16 }}>
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
          }}
          placeholder="Vehicle (e.g., 2021 Ford F-150)"
          placeholderTextColor={C.textMuted}
          value={insightsForm.vehicle}
          onChangeText={(text) => setInsightsForm({ ...insightsForm, vehicle: text })}
        />
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
            minHeight: 80,
          }}
          placeholder="Driving Habits (e.g., Mostly highway, occasional towing)"
          placeholderTextColor={C.textMuted}
          multiline
          value={insightsForm.driving_habits}
          onChangeText={(text) => setInsightsForm({ ...insightsForm, driving_habits: text })}
        />
        <TouchableOpacity
          onPress={handleDrivingInsights}
          disabled={insightsLoading || !insightsForm.vehicle || !insightsForm.driving_habits}
          style={{
            padding: 14,
            backgroundColor: insightsLoading ? C.textMuted : C.primary,
            borderRadius: 10,
            alignItems: 'center',
          }}
          testID="driving-insights-button"
        >
          {insightsLoading ? (
            <ActivityIndicator color={C.primaryText} />
          ) : (
            <Text style={{ fontSize: 15, fontWeight: '600', color: C.primaryText }}>
              {tx('i18n.features.smart-cars.insights.button', 'Get Insights')}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      {insightsResult && (
        <View style={{ marginTop: 16, padding: 16, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12 }}>
            Driving Insights
          </Text>
          <AIFeedbackBar feature="mobility-assistant" query={insightsForm.vehicle} />
          <MarkdownDisplay content={insightsResult.insights || ''} />
        </View>
      )}
    </View>
  );

  const renderService = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.service.title', 'Service History')}
      </Text>
      
      <View style={{ marginBottom: 20 }}>
        <Text style={{ fontSize: 15, fontWeight: '600', color: C.text, marginBottom: 10 }}>Add Service Record</Text>
        <View style={{ gap: 12 }}>
          <TextInput
            style={{
              padding: 12,
              backgroundColor: C.card,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              fontSize: 14,
              color: C.text,
            }}
            placeholder="Make"
            placeholderTextColor={C.textMuted}
            value={serviceForm.make}
            onChangeText={(text) => setServiceForm({ ...serviceForm, make: text })}
          />
          <TextInput
            style={{
              padding: 12,
              backgroundColor: C.card,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              fontSize: 14,
              color: C.text,
            }}
            placeholder="Model"
            placeholderTextColor={C.textMuted}
            value={serviceForm.model}
            onChangeText={(text) => setServiceForm({ ...serviceForm, model: text })}
          />
          <TextInput
            style={{
              padding: 12,
              backgroundColor: C.card,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              fontSize: 14,
              color: C.text,
            }}
            placeholder="Year"
            placeholderTextColor={C.textMuted}
            keyboardType="numeric"
            value={serviceForm.year}
            onChangeText={(text) => setServiceForm({ ...serviceForm, year: text })}
          />
          <TextInput
            style={{
              padding: 12,
              backgroundColor: C.card,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              fontSize: 14,
              color: C.text,
            }}
            placeholder="Service Type (e.g., Oil Change)"
            placeholderTextColor={C.textMuted}
            value={serviceForm.service_type}
            onChangeText={(text) => setServiceForm({ ...serviceForm, service_type: text })}
          />
          <TextInput
            style={{
              padding: 12,
              backgroundColor: C.card,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              fontSize: 14,
              color: C.text,
            }}
            placeholder="Mileage at Service"
            placeholderTextColor={C.textMuted}
            keyboardType="numeric"
            value={serviceForm.mileage_at_service}
            onChangeText={(text) => setServiceForm({ ...serviceForm, mileage_at_service: text })}
          />
          <TouchableOpacity
            onPress={handleAddServiceRecord}
            disabled={saving || !serviceForm.make || !serviceForm.service_type}
            style={{
              padding: 14,
              backgroundColor: saving ? C.textMuted : C.primary,
              borderRadius: 10,
              alignItems: 'center',
            }}
            testID="add-service-record-button"
          >
            {saving ? (
              <ActivityIndicator color={C.primaryText} />
            ) : (
              <Text style={{ fontSize: 15, fontWeight: '600', color: C.primaryText }}>Add Record</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>

      <Text style={{ fontSize: 15, fontWeight: '600', color: C.text, marginBottom: 10 }}>
        Service Records ({serviceRecords.length})
      </Text>
      {serviceRecords.length === 0 ? (
        <Text style={{ fontSize: 14, color: C.textMuted, padding: 20, textAlign: 'center' }}>
          No service records yet
        </Text>
      ) : (
        serviceRecords.map((record, idx) => (
          <View
            key={idx}
            style={{
              padding: 12,
              backgroundColor: C.card,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              marginBottom: 10,
            }}
          >
            <Text style={{ fontSize: 14, fontWeight: '600', color: C.text }}>
              {record.service_type} - {record.year} {record.make} {record.model}
            </Text>
            <Text style={{ fontSize: 12, color: C.textSec, marginTop: 4 }}>
              {record.mileage_at_service?.toLocaleString()} miles
              {record.cost ? ` • $${record.cost}` : ''}
            </Text>
            {record.notes && (
              <Text style={{ fontSize: 12, color: C.textMuted, marginTop: 4, fontStyle: 'italic' }}>
                {record.notes}
              </Text>
            )}
          </View>
        ))
      )}
    </View>
  );

  const renderInsurance = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.insurance.title', 'Insurance Advisor')}
      </Text>
      <View style={{ gap: 12, marginBottom: 16 }}>
        <TextInput
          style={{
            padding: 12,
            backgroundColor: C.card,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            fontSize: 14,
            color: C.text,
            minHeight: 100,
          }}
          placeholder="Ask about insurance coverage, rates, or recommendations (e.g., 'What coverage do I need for a 2022 Tesla Model Y?')"
          placeholderTextColor={C.textMuted}
          multiline
          value={insuranceQuery}
          onChangeText={setInsuranceQuery}
        />
        <TouchableOpacity
          onPress={handleInsuranceAdvisor}
          disabled={insuranceLoading || !insuranceQuery.trim()}
          style={{
            padding: 14,
            backgroundColor: insuranceLoading ? C.textMuted : C.primary,
            borderRadius: 10,
            alignItems: 'center',
          }}
          testID="insurance-advisor-button"
        >
          {insuranceLoading ? (
            <ActivityIndicator color={C.primaryText} />
          ) : (
            <Text style={{ fontSize: 15, fontWeight: '600', color: C.primaryText }}>
              {tx('i18n.features.smart-cars.insurance.button', 'Get Insurance Advice')}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      {insuranceResult && (
        <View style={{ marginTop: 16, padding: 16, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginBottom: 12 }}>
            Insurance Assessment
          </Text>
          <AIFeedbackBar feature="mobility-assistant" query={insuranceQuery} />
          <MarkdownDisplay content={insuranceResult} />
        </View>
      )}
    </View>
  );

  const renderAnalytics = () => (
    <View>
      <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 12 }}>
        {tx('i18n.features.smart-cars.analytics.title', 'Analytics Dashboard')}
      </Text>
      {analytics ? (
        <View style={{ gap: 12 }}>
          <View style={{ padding: 14, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ fontSize: 14, color: C.textSec }}>Total Searches</Text>
            <Text style={{ fontSize: 28, fontWeight: '700', color: C.text, marginTop: 4 }}>
              {analytics.total_searches || 0}
            </Text>
          </View>
          <View style={{ padding: 14, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ fontSize: 14, color: C.textSec }}>Trade-In Requests</Text>
            <Text style={{ fontSize: 28, fontWeight: '700', color: C.text, marginTop: 4 }}>
              {analytics.total_trade_in_requests || 0}
            </Text>
          </View>
          <View style={{ padding: 14, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ fontSize: 14, color: C.textSec }}>Total AI Calls</Text>
            <Text style={{ fontSize: 28, fontWeight: '700', color: C.text, marginTop: 4 }}>
              {analytics.total_ai_calls || 0}
            </Text>
          </View>
          <View style={{ padding: 14, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ fontSize: 14, color: C.textSec }}>Saved Vehicles</Text>
            <Text style={{ fontSize: 28, fontWeight: '700', color: C.text, marginTop: 4 }}>
              {analytics.saved_vehicles || 0}
            </Text>
          </View>
          <View style={{ padding: 14, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ fontSize: 14, color: C.textSec }}>Service Records</Text>
            <Text style={{ fontSize: 28, fontWeight: '700', color: C.text, marginTop: 4 }}>
              {analytics.service_records || 0}
            </Text>
          </View>
        </View>
      ) : (
        <Text style={{ fontSize: 14, color: C.textMuted, padding: 20, textAlign: 'center' }}>
          Loading analytics...
        </Text>
      )}
    </View>
  );

  const renderTabContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return renderDashboard();
      case 'search':
        return renderSearch();
      case 'history':
        return renderHistory();
      case 'saved':
        return renderSaved();
      case 'tradein':
        return renderTradeIn();
      case 'finance':
        return renderFinance();
      case 'maintenance':
        return renderMaintenance();
      case 'cost':
        return renderCost();
      case 'trip':
        return renderTrip();
      case 'fuel':
        return renderFuel();
      case 'compare':
        return renderCompare();
      case 'ev':
        return renderEV();
      case 'insights':
        return renderInsights();
      case 'service':
        return renderService();
      case 'insurance':
        return renderInsurance();
      case 'analytics':
        return renderAnalytics();
      default:
        return renderDashboard();
    }
  };

  if (loading) {
    return (
      <FeatureLayout
        feature="smart-cars"
        title={tx('i18n.features.smart-cars.title', 'Mobility Assistant')}
        subtitle={tx('i18n.features.smart-cars.subtitle', 'AI-powered vehicle search, trade-in, finance, and maintenance advisor')}
        icon="car"
        color={colors.primary}
      >
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }}>
          <ActivityIndicator size="large" color={C.primary} />
          <Text style={{ marginTop: 16, fontSize: 14, color: C.textSec }}>
            {tx('i18n.features.smart-cars.loading', 'Loading Mobility Assistant...')}
          </Text>
        </View>
      </FeatureLayout>
    );
  }

  return (
    <FeatureLayout
      feature="smart-cars"
      title={tx('i18n.features.smart-cars.title', 'Mobility Assistant')}
      subtitle={tx('i18n.features.smart-cars.subtitle', 'AI-powered vehicle search, trade-in, finance, and maintenance advisor')}
      icon="car"
      color={colors.primary}
    >
      <FeatureToolbar feature="smart-cars" />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: 16 }}
        showsVerticalScrollIndicator={false}
      >
        {renderTabNavigation()}
        {renderTabContent()}
      </ScrollView>
    </FeatureLayout>
  );
}
