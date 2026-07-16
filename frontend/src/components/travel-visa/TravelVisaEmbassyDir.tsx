import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, ScrollView, TextInput, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import CountryFlag from '../CountryFlag';
import api from '../../services/api';

const WEB_TRANSITION = Platform.OS === 'web' ? ({ transition: 'all 0.2s ease' } as any) : {};

export default function TravelVisaEmbassyDir({ countries }: { countries: any[] }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [embassies, setEmbassies] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState('');
  const [search, setSearch] = useState('');
  const [filterCountry, setFilterCountry] = useState('');

  useEffect(() => {
    (async () => {
      setLoading(true);
      setPageError('');
      try {
        const params = new URLSearchParams();
        if (filterCountry) params.append('country_code', filterCountry);
        if (search) params.append('search', search);
        const res = await api.get(`/travel-visa/embassies?${params.toString()}`);
        setEmbassies(res.data?.embassies || []);
      } catch (e: any) {
        setPageError(e?.response?.data?.detail || tx('travelVisa.embassy.errors.loadFailed', 'Unable to load embassy directory.'));
        setEmbassies([]);
      }
      setLoading(false);
    })();
  }, [filterCountry, search]);

  return (
    <View data-testid="tv-embassy-dir">
      <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 12 }}>{tx('travelVisa.embassy.header.title', 'Embassy & Consulate Directory')}</Text>

      {/* Search */}
      <View style={{
        flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12,
        backgroundColor: colors.input, borderWidth: 1, borderColor: colors.inputBorder,
        borderRadius: 10, paddingHorizontal: 12, height: 40,
      }}>
        <Ionicons name="search" size={16} color={colors.textMuted} />
        <TextInput data-testid="tv-embassy-search"
          placeholder={tx('travelVisa.embassy.search.placeholder', 'Search embassies by name or city...')}
          placeholderTextColor={colors.placeholder}
          value={search} onChangeText={setSearch}
          style={{
            flex: 1, fontSize: 13, color: colors.inputText,
            ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}),
          }} />
      </View>

      {/* Country Filter */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, marginBottom: 16 }}>
        <TouchableOpacity data-testid="tv-embassy-country-all" onPress={() => setFilterCountry('')}
          style={{
            paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8,
            backgroundColor: !filterCountry ? colors.primary : colors.surfaceHover,
            borderWidth: 1, borderColor: !filterCountry ? colors.primary : colors.border,
          }}>
          <Text style={{ fontSize: 12, fontWeight: '600', color: !filterCountry ? colors.primaryText : colors.text }}>{tx('common.all', 'All')}</Text>
        </TouchableOpacity>
        {countries.slice(0, 12).map((c: any) => (
          <TouchableOpacity data-testid={`tv-embassy-country-${String(c.code || '').toLowerCase()}`} key={c.code}
            onPress={() => setFilterCountry(filterCountry === c.code ? '' : c.code)}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 4,
              paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8,
              backgroundColor: filterCountry === c.code ? colors.primary : colors.surfaceHover,
              borderWidth: 1, borderColor: filterCountry === c.code ? colors.primary : colors.border,
              ...WEB_TRANSITION,
            }}>
            <CountryFlag code={c.code} emoji={c.flag} size={12} />
            <Text style={{ fontSize: 12, fontWeight: '500', color: filterCountry === c.code ? colors.primaryText : colors.text }}>{c.code}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {!!pageError && (
        <View data-testid="tv-embassy-load-error" style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), backgroundColor: colors.errorSoft, padding: 10, marginBottom: 12 }}>
          <Text style={{ fontSize: 11, color: colors.errorText, fontWeight: '700' }}>{pageError}</Text>
        </View>
      )}

      {loading ? (
        <View style={{ padding: 40, alignItems: 'center' }}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : embassies.length === 0 ? (
        <View style={{ padding: 30, alignItems: 'center' }}>
          <Ionicons name="business-outline" size={40} color={colors.textMuted} />
          <Text style={{ fontSize: 14, color: colors.textMuted, marginTop: 10 }}>{tx('travelVisa.embassy.states.noneFound', 'No embassies found')}</Text>
        </View>
      ) : (
        embassies.map((emb, i) => (
          <View data-testid={`tv-embassy-card-${i}`} key={emb.embassy_id || i} style={{
            padding: 16, borderRadius: 14, backgroundColor: colors.card,
            borderWidth: 1, borderColor: colors.border, marginBottom: 10,
            ...(Platform.OS === 'web' ? { boxShadow: `0 1px 4px ${colors.shadowColor}` } as any : {}),
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12 }}>
              <View style={{
                width: 44, height: 44, borderRadius: 12, backgroundColor: colors.primarySoft,
                alignItems: 'center', justifyContent: 'center',
              }}>
                <Ionicons name="business" size={20} color={colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }}>{emb.name}</Text>
                <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>{emb.city}, {emb.country_name}</Text>
                <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 4 }}>{emb.address}</Text>
                {emb.phone && (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 }}>
                    <Ionicons name="call-outline" size={12} color={colors.primary} />
                    <Text style={{ fontSize: 11, color: colors.primary }}>{emb.phone}</Text>
                  </View>
                )}
                {emb.services && emb.services.length > 0 && (
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
                    {emb.services.map((s: string, j: number) => (
                      <View key={j} style={{
                        paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
                        backgroundColor: colors.surfaceHover,
                      }}>
                        <Text style={{ fontSize: 10, color: colors.textMuted }}>{s}</Text>
                      </View>
                    ))}
                  </View>
                )}
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                  {emb.appointment_required && (
                    <View style={{
                      flexDirection: 'row', alignItems: 'center', gap: 4,
                      paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
                      backgroundColor: colors.warningSoft,
                    }}>
                      <Ionicons name="calendar" size={10} color={colors.warning} />
                      <Text style={{ fontSize: 10, fontWeight: '600', color: colors.warningText }}>{tx('travelVisa.embassy.labels.appointmentRequired', 'Appointment Required')}</Text>
                    </View>
                  )}
                  {emb.website && (
                    <TouchableOpacity accessibilityLabel="globe outline button" style={{
                      flexDirection: 'row', alignItems: 'center', gap: 4,
                      paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
                      backgroundColor: colors.primarySoft,
                    }}>
                      <Ionicons name="globe-outline" size={10} color={colors.primary} />
                      <Text style={{ fontSize: 10, fontWeight: '600', color: colors.primary }}>{tx('travelVisa.embassy.labels.website', 'Website')}</Text>
                    </TouchableOpacity>
                  )}
                </View>
              </View>
            </View>
          </View>
        ))
      )}
    </View>
  );
}
