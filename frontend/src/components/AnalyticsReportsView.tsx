import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator, Platform, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import api from '../services/api';
import PremiumGuard from './PremiumGuard';

interface ReportType {
  name: string;
  description: string;
}

interface Schedule {
  schedule_id: string;
  report_type: string;
  frequency: string;
  email: string;
  active: boolean;
}

interface ExportHistoryItem {
  export_id: string;
  report_type: string;
  format: string;
  start_date: string;
  end_date: string;
  rows: number;
  created_at: string;
}

export default function AnalyticsReportsView() {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { _user } = useAuth();
  const { colors: C, accentColor } = useTheme();

  // @autofix-moved: was module-level const styles
  const styles = StyleSheet.create({
    container: { flex: 1 },
    tabRow: { flexDirection: 'row', paddingHorizontal: 16, paddingTop: 12, gap: 10 },
    tab: {
      flexDirection: 'row', alignItems: 'center', gap: 6,
      paddingVertical: 8, paddingHorizontal: 16, borderRadius: 20, borderWidth: 1, borderColor: 'transparent',
    },
    tabText: { fontWeight: '600', fontSize: 14 },
    scroll: { flex: 1, paddingHorizontal: 16 },
    section: { marginTop: 16 },
    sectionTitle: { fontSize: 16, fontWeight: '700', marginBottom: 10 },
    sectionDesc: { fontSize: 13, marginBottom: 14, lineHeight: 19 },
    typeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 },
    typeCard: {
      width: Platform.OS === 'web' ? 'calc(50% - 5px)' as any : '48%',
      padding: 14, borderRadius: 14, borderWidth: 1, gap: 6,
    },
    typeIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
    typeName: { fontSize: 14, fontWeight: '600' },
    typeDesc: { fontSize: 11, lineHeight: 16 },
    dateRow: { flexDirection: 'row', gap: 8, marginBottom: 16 },
    dateChip: {
      paddingVertical: 8, paddingHorizontal: 16, borderRadius: 20,
      borderWidth: 1, borderColor: C.border,
    },
    dateText: { fontSize: 13, fontWeight: '500', color: C.textMuted },
    actionRow: { flexDirection: 'row', gap: 10, marginBottom: 20 },
    actionBtn: {
      flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
      paddingVertical: 14, borderRadius: 12, borderWidth: 1, borderColor: 'transparent',
    },
    actionBtnText: { fontWeight: '600', fontSize: 14 },
    previewCard: { borderRadius: 14, borderWidth: 1, overflow: 'hidden' },
    previewHeader: { padding: 14, borderBottomWidth: 1, borderColor: C.borderSoft || C.border },
    previewTitle: { fontSize: 15, fontWeight: '700' },
    previewMeta: { fontSize: 12, marginTop: 2 },
    tableWrap: { overflow: 'scroll' as any },
    tableRow: { flexDirection: 'row', borderBottomWidth: 1 },
    tableCell: { flex: 1, paddingVertical: 8, paddingHorizontal: 10, fontSize: 12, minWidth: 100 },
    tableHeaderCell: { fontWeight: '700', fontSize: 11, textTransform: 'uppercase' },
    moreText: { padding: 10, fontSize: 12, textAlign: 'center' },
    mobileRow: { padding: 12, borderBottomWidth: 1, gap: 6 },
    mobileField: { flexDirection: 'row', justifyContent: 'space-between' },
    mobileLabel: { fontSize: 12, fontWeight: '600' },
    mobileValue: { fontSize: 12 },
    scheduleBtn: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
      paddingVertical: 14, borderRadius: 12,
    },
    scheduleBtnText: { color: C.primaryText, fontWeight: '700', fontSize: 14 },
    scheduleCard: {
      flexDirection: 'row', alignItems: 'center', gap: 12,
      padding: 14, borderRadius: 14, borderWidth: 1, marginBottom: 10,
    },
    scheduleIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
    scheduleName: { fontSize: 14, fontWeight: '600' },
    scheduleMeta: { fontSize: 12, marginTop: 2 },
    historyCard: {
      flexDirection: 'row', alignItems: 'center', gap: 12,
      padding: 14, borderRadius: 14, borderWidth: 1, marginBottom: 10,
    },
    historyIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
    historyName: { fontSize: 14, fontWeight: '600' },
    historyMeta: { fontSize: 12, marginTop: 2 },
    formatBadge: { paddingVertical: 4, paddingHorizontal: 10, borderRadius: 8 },
    formatText: { fontSize: 11, fontWeight: '700' },
    emptyState: { alignItems: 'center', paddingTop: 40, gap: 8 },
    emptyText: { fontSize: 14 },
  });

  const [activeTab, setActiveTab] = useState<'export' | 'schedule' | 'history'>('export');
  const [reportTypes, setReportTypes] = useState<Record<string, ReportType>>({});
  const [selectedType, setSelectedType] = useState<string>('usage');
  const [dateRange, setDateRange] = useState<'7d' | '30d' | '90d' | 'all'>('30d');
  const [exporting, setExporting] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [schedulesLoading, setSchedulesLoading] = useState(false);
  const [scheduleFreq, setScheduleFreq] = useState<'weekly' | 'monthly'>('weekly');
  const [scheduling, setScheduling] = useState(false);

  const [history, setHistory] = useState<ExportHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const TYPE_ICONS: Record<string, { icon: keyof typeof Ionicons.glyphMap; color: string }> = {
    usage: { icon: 'bar-chart', color: C.primary },
    conversations: { icon: 'chatbubbles', color: C.successText },
    features: { icon: 'grid', color: C.purpleText },
    subscription: { icon: 'card', color: C.warningText },
  };

  useEffect(() => {
    fetchReportTypes();
  }, []);

  const fetchReportTypes = async () => {
    try {
      const res = await api.get('/reports/types');
      setReportTypes(res.data.report_types || {});
    } catch { /* silent */ }
  };

  const getDateParams = () => {
    const now = new Date();
    let start: string;
    const end = now.toISOString().split('T')[0];
    switch (dateRange) {
      case '7d': start = new Date(now.getTime() - 7 * 86400000).toISOString().split('T')[0]; break;
      case '30d': start = new Date(now.getTime() - 30 * 86400000).toISOString().split('T')[0]; break;
      case '90d': start = new Date(now.getTime() - 90 * 86400000).toISOString().split('T')[0]; break;
      default: start = '2020-01-01';
    }
    return { start, end };
  };

  const handlePreview = async () => {
    setPreviewLoading(true);
    setPreviewData(null);
    try {
      const { start, end } = getDateParams();
      const res = await api.get(`/reports/export/${selectedType}/json?start_date=${start}&end_date=${end}`);
      setPreviewData(res.data);
    } catch { /* error */ }
    finally { setPreviewLoading(false); }
  };

  const handleExportCSV = async () => {
    setExporting(true);
    try {
      const { start, end } = getDateParams();
      const baseUrl = (api.defaults.baseURL || '').replace(/\/api\/?$/, '');
      const token = api.defaults.headers?.common?.['Authorization']?.toString().replace('Bearer ', '') || '';
      const url = `${baseUrl}/api/reports/export/${selectedType}?start_date=${start}&end_date=${end}&token=${token}`;
      if (Platform.OS === 'web') {
        window.open(url, '_blank');
      } else {
        await Linking.openURL(url);
      }
    } catch { /* error */ }
    finally { setExporting(false); }
  };

  const fetchSchedules = useCallback(async () => {
    setSchedulesLoading(true);
    try {
      const res = await api.get('/reports/schedules');
      setSchedules(res.data.schedules || []);
    } catch { /* silent */ }
    finally { setSchedulesLoading(false); }
  }, []);

  const handleSchedule = async () => {
    setScheduling(true);
    try {
      await api.post('/reports/schedule', {
        report_type: selectedType,
        frequency: scheduleFreq,
      });
      await fetchSchedules();
    } catch { /* error */ }
    finally { setScheduling(false); }
  };

  const handleCancelSchedule = async (reportType: string) => {
    try {
      await api.delete(`/reports/schedule/${reportType}`);
      setSchedules(s => s.filter(sc => sc.report_type !== reportType));
    } catch { /* error */ }
  };

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await api.get('/reports/history');
      setHistory(res.data.exports || []);
    } catch { /* silent */ }
    finally { setHistoryLoading(false); }
  }, []);

  useEffect(() => {
    if (activeTab === 'schedule') fetchSchedules();
    if (activeTab === 'history') fetchHistory();
  }, [activeTab, fetchSchedules, fetchHistory]);

  return (
    <PremiumGuard featureName="Analytics Reports">
      <View style={[styles.container, { backgroundColor: C.bg }]} data-testid="analytics-reports-view" testID="analytics-reports-view">
        {/* Tabs */}
        <View style={styles.tabRow}>
          {(['export', 'schedule', 'history'] as const).map(tab => (
            <TouchableOpacity
              key={tab}
              data-testid={`reports-tab-${tab}`} testID={`reports-tab-${tab}`}
              style={[styles.tab, activeTab === tab && { backgroundColor: (globalThis as any).__alphaColor(accentColor, '18'), borderColor: accentColor }]}
              onPress={() => setActiveTab(tab)}
            >
              <Ionicons
                name={tab === 'export' ? 'download' : tab === 'schedule' ? 'calendar' : 'time'}
                size={16}
                color={activeTab === tab ? accentColor : C.textMuted}
              />
              <Text style={[styles.tabText, { color: activeTab === tab ? accentColor : C.textMuted }]}>
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <ScrollView style={styles.scroll} contentContainerStyle={{ paddingBottom: 60 }}>
          {/* Report Type Selector - shown on export & schedule tabs */}
          {(activeTab === 'export' || activeTab === 'schedule') && (
            <View style={styles.section}>
              <Text style={[styles.sectionTitle, { color: C.text }]}>Report Type</Text>
              <View style={styles.typeGrid}>
                {Object.entries(reportTypes).map(([key, rt]) => {
                  const ti = TYPE_ICONS[key] || { icon: 'analytics' as any, color: C.textDim };
                  const selected = selectedType === key;
                  return (
                    <TouchableOpacity
                      key={key}
                      data-testid={`report-type-${key}`} testID={`report-type-${key}`}
                      style={[
                        styles.typeCard,
                        { backgroundColor: C.card, borderColor: selected ? ti.color : C.border },
                        selected && { borderWidth: 2 },
                      ]}
                      onPress={() => { setSelectedType(key); setPreviewData(null); }}
                    >
                      <View style={[styles.typeIcon, { backgroundColor: (globalThis as any).__alphaColor(ti.color, '18') }]}>
                        <Ionicons name={ti.icon} size={20} color={ti.color} />
                      </View>
                      <Text style={[styles.typeName, { color: C.text }]}>{rt.name}</Text>
                      <Text style={[styles.typeDesc, { color: C.textMuted }]} numberOfLines={2}>{rt.description}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          )}

          {/* Export Tab */}
          {activeTab === 'export' && (
            <View style={styles.section}>
              {/* Date Range */}
              <Text style={[styles.sectionTitle, { color: C.text }]}>Date Range</Text>
              <View style={styles.dateRow}>
                {(['7d', '30d', '90d', 'all'] as const).map(d => (
                  <TouchableOpacity
                    key={d}
                    data-testid={`date-range-${d}`} testID={`date-range-${d}`}
                    style={[styles.dateChip, dateRange === d && { backgroundColor: accentColor, borderColor: accentColor }]}
                    onPress={() => { setDateRange(d); setPreviewData(null); }}
                  >
                    <Text style={[styles.dateText, dateRange === d && { color: C.primaryText }]}>
                      {d === '7d' ? '7 Days' : d === '30d' ? '30 Days' : d === '90d' ? '90 Days' : 'All Time'}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Action Buttons */}
              <View style={styles.actionRow}>
                <TouchableOpacity
                  data-testid="preview-report-btn" testID="preview-report-btn"
                  style={[styles.actionBtn, { backgroundColor: C.card, borderColor: accentColor }]}
                  onPress={handlePreview}
                  disabled={previewLoading}
                >
                  {previewLoading ? (
                    <ActivityIndicator color={accentColor} size="small" />
                  ) : (
                    <>
                      <Ionicons name="eye" size={16} color={accentColor} />
                      <Text style={[styles.actionBtnText, { color: accentColor }]}>Preview</Text>
                    </>
                  )}
                </TouchableOpacity>
                <TouchableOpacity
                  data-testid="export-csv-btn" testID="export-csv-btn"
                  style={[styles.actionBtn, { backgroundColor: accentColor }]}
                  onPress={handleExportCSV}
                  disabled={exporting}
                >
                  {exporting ? (
                    <ActivityIndicator color="var(--app-primary-text)" size="small" />
                  ) : (
                    <>
                      <Ionicons name="download" size={16} color="var(--app-primary-text)" />
                      <Text style={[styles.actionBtnText, { color: C.primaryText }]}>Export CSV</Text>
                    </>
                  )}
                </TouchableOpacity>
              </View>

              {/* Preview Table */}
              {previewData && (
                <View style={[styles.previewCard, { backgroundColor: C.card, borderColor: C.border }]} data-testid="report-preview" testID="report-preview">
                  <View style={styles.previewHeader}>
                    <Text style={[styles.previewTitle, { color: C.text }]}>{previewData.report_name}</Text>
                    <Text style={[styles.previewMeta, { color: C.textMuted }]}>
                      {previewData.row_count} rows &middot; {previewData.start_date} to {previewData.end_date}
                    </Text>
                  </View>
                  {Platform.OS === 'web' ? (
                    <View style={styles.tableWrap}>
                      {previewData.rows?.length > 0 && (
                        <>
                          {/* Table Header */}
                          <View style={[styles.tableRow, { backgroundColor: C.cardMuted }]}>
                            {Object.keys(previewData.rows[0]).map((col: string) => (
                              <Text key={col} style={[styles.tableCell, styles.tableHeaderCell, { color: C.textSec }]}>
                                {col}
                              </Text>
                            ))}
                          </View>
                          {/* Table Body */}
                          {previewData.rows.slice(0, 10).map((row: Record<string, any>, i: number) => (
                            <View key={i} style={[styles.tableRow, { borderColor: C.border }]}>
                              {Object.values(row).map((val: any, j: number) => (
                                <Text key={j} style={[styles.tableCell, { color: C.text }]} numberOfLines={1}>
                                  {String(val)}
                                </Text>
                              ))}
                            </View>
                          ))}
                          {previewData.rows.length > 10 && (
                            <Text style={[styles.moreText, { color: C.textMuted }]}>
                              + {previewData.rows.length - 10} more rows in CSV export
                            </Text>
                          )}
                        </>
                      )}
                    </View>
                  ) : (
                    <View>
                      {previewData.rows?.slice(0, 5).map((row: Record<string, any>, i: number) => (
                        <View key={i} style={[styles.mobileRow, { borderColor: C.border }]}>
                          {Object.entries(row).map(([k, v]) => (
                            <View key={k} style={styles.mobileField}>
                              <Text style={[styles.mobileLabel, { color: C.textMuted }]}>{k}</Text>
                              <Text style={[styles.mobileValue, { color: C.text }]}>{String(v)}</Text>
                            </View>
                          ))}
                        </View>
                      ))}
                    </View>
                  )}
                </View>
              )}
            </View>
          )}

          {/* Schedule Tab */}
          {activeTab === 'schedule' && (
            <View style={styles.section}>
              <Text style={[styles.sectionTitle, { color: C.text }]}>Schedule Delivery</Text>
              <Text style={[styles.sectionDesc, { color: C.textMuted }]}>
                Automatically receive reports via email on a recurring schedule.
              </Text>

              {/* Frequency */}
              <View style={styles.dateRow}>
                {(['weekly', 'monthly'] as const).map(f => (
                  <TouchableOpacity
                    key={f}
                    data-testid={`freq-${f}`} testID={`freq-${f}`}
                    style={[styles.dateChip, scheduleFreq === f && { backgroundColor: accentColor, borderColor: accentColor }]}
                    onPress={() => setScheduleFreq(f)}
                  >
                    <Text style={[styles.dateText, scheduleFreq === f && { color: C.primaryText }]}>
                      {f.charAt(0).toUpperCase() + f.slice(1)}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <TouchableOpacity
                data-testid="schedule-report-btn" testID="schedule-report-btn"
                style={[styles.scheduleBtn, { backgroundColor: accentColor }]}
                onPress={handleSchedule}
                disabled={scheduling}
              >
                {scheduling ? (
                  <ActivityIndicator color="var(--app-primary-text)" />
                ) : (
                  <>
                    <Ionicons name="calendar" size={16} color="var(--app-primary-text)" />
                    <Text style={styles.scheduleBtnText}>Schedule {reportTypes[selectedType]?.name || 'Report'}</Text>
                  </>
                )}
              </TouchableOpacity>

              {/* Active Schedules */}
              <Text style={[styles.sectionTitle, { color: C.text, marginTop: 24 }]}>Active Schedules</Text>
              {schedulesLoading ? (
                <ActivityIndicator color={accentColor} style={{ marginTop: 20 }} />
              ) : schedules.length === 0 ? (
                <View style={styles.emptyState}>
                  <Ionicons name="calendar-outline" size={36} color={C.textMuted} />
                  <Text style={[styles.emptyText, { color: C.textMuted }]}>No scheduled reports</Text>
                </View>
              ) : (
                schedules.map(s => {
                  const ti = TYPE_ICONS[s.report_type] || { icon: 'analytics' as any, color: C.textDim };
                  return (
                    <View key={s.schedule_id} style={[styles.scheduleCard, { backgroundColor: C.card, borderColor: C.border }]} data-testid={`schedule-${s.report_type}`} testID={`schedule-${s.report_type}`}>
                      <View style={[styles.scheduleIcon, { backgroundColor: (globalThis as any).__alphaColor(ti.color, '18') }]}>
                        <Ionicons name={ti.icon} size={18} color={ti.color} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.scheduleName, { color: C.text }]}>
                          {reportTypes[s.report_type]?.name || s.report_type}
                        </Text>
                        <Text style={[styles.scheduleMeta, { color: C.textMuted }]}>
                          {s.frequency} &middot; {s.email}
                        </Text>
                      </View>
                      <TouchableOpacity
                        data-testid={`cancel-schedule-${s.report_type}`} testID={`cancel-schedule-${s.report_type}`}
                        onPress={() => handleCancelSchedule(s.report_type)}
                      >
                        <Ionicons name="close-circle" size={22} color={C.error} />
                      </TouchableOpacity>
                    </View>
                  );
                })
              )}
            </View>
          )}

          {/* History Tab */}
          {activeTab === 'history' && (
            <View style={styles.section}>
              <Text style={[styles.sectionTitle, { color: C.text }]}>Export History</Text>
              {historyLoading ? (
                <ActivityIndicator color={accentColor} style={{ marginTop: 20 }} />
              ) : history.length === 0 ? (
                <View style={styles.emptyState} data-testid="history-empty" testID="history-empty">
                  <Ionicons name="document-text-outline" size={36} color={C.textMuted} />
                  <Text style={[styles.emptyText, { color: C.textMuted }]}>No exports yet</Text>
                </View>
              ) : (
                history.map(h => {
                  const ti = TYPE_ICONS[h.report_type] || { icon: 'analytics' as any, color: C.textDim };
                  return (
                    <View key={h.export_id} style={[styles.historyCard, { backgroundColor: C.card, borderColor: C.border }]} data-testid={`export-${h.export_id}`} testID={`export-${h.export_id}`}>
                      <View style={[styles.historyIcon, { backgroundColor: (globalThis as any).__alphaColor(ti.color, '18') }]}>
                        <Ionicons name={ti.icon} size={18} color={ti.color} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.historyName, { color: C.text }]}>
                          {reportTypes[h.report_type]?.name || h.report_type}
                        </Text>
                        <Text style={[styles.historyMeta, { color: C.textMuted }]}>
                          {h.rows} rows &middot; {h.format.toUpperCase()} &middot; {new Date(h.created_at).toLocaleDateString()}
                        </Text>
                      </View>
                      <View style={[styles.formatBadge, { backgroundColor: (globalThis as any).__alphaColor(ti.color, '18') }]}>
                        <Text style={[styles.formatText, { color: ti.color }]}>{h.format.toUpperCase()}</Text>
                      </View>
                    </View>
                  );
                })
              )}
            </View>
          )}
        </ScrollView>
      </View>
    </PremiumGuard>
  );
}

/* i18n-probe t('i18n.auto.probe') */
