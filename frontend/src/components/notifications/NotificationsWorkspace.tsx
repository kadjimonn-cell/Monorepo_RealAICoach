import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  ActivityIndicator,
  Image,
  Modal,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  useWindowDimensions,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import AppShell from "../AppShell";
import { NotificationsSkeleton } from "../SkeletonLoaders";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import { useTranslation } from "../../hooks/useTranslation";
import { useGlobalPlatformState } from "../../hooks/useGlobalPlatformState";
import GpsLabelBlocker from "../GpsLabelBlocker";
import { GpsDataStatusCard } from "../GpsDataStatusCard";
import api from "../../services/api";
import { isNotificationSupported, getNotificationPermission, requestNotificationPermission, registerPushNotifications } from "../../utils/pushNotifications";
import { getShadow } from "../../utils/themeShadows";
import { EMPTY_IMAGE, getGroupLabel, getNotificationVisual, timeAgo } from "./notificationsPageConfig";
import { useNotifications } from "../NotificationBell";

const DENSE_VIEW_STORAGE_KEY = "notifications_dense_view_preference";

const SummaryStat = ({ label, value, tone, icon, colors, testId, cardStyle }) => (
  <View style={[styles.summaryCard, { backgroundColor: colors.surface, borderColor: colors.border }, cardStyle]} data-testid={testId} testID={testId}>
    <View style={[styles.summaryIcon, { backgroundColor: tone.bg }]}>
      <Ionicons name={icon} size={18} color={tone.fg} />
    </View>
    <View style={{ flex: 1 }}>
      <Text style={[styles.summaryLabel, { color: colors.textSec }]}>{label}</Text>
      <Text style={[styles.summaryValue, { color: colors.text }]}>{value}</Text>
    </View>
  </View>
);

const FilterPill = ({ active, icon, label, onPress, colors, testId }) => (
  <TouchableOpacity accessibilityLabel="On press in notifications workspace button"
    onPress={onPress}
    style={[
      styles.filterPill,
      { backgroundColor: active ? colors.primarySoft : colors.surface, borderColor: active ? colors.primary : colors.border },
    ]}
    data-testid={testId} testID={testId}
  >
    <Ionicons name={icon} size={14} color={active ? colors.primary : colors.textSec} />
    <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 12, fontWeight: "800" }}>{label}</Text>
  </TouchableOpacity>
);

const NotificationRow = ({ item, colors, isMobile, dense, onOpen, onMarkRead, onDelete, onToggleSelect, isSelected }) => {
  const visual = getNotificationVisual(item);
  const id = item.notification_id || item.id;
  const rowPadding = dense ? 12 : 16;
  const avatarSize = dense ? 36 : 44;
  const contentGap = dense ? 10 : 14;

  return (
    <View
      style={[
        styles.notificationRow,
        {
          backgroundColor: isSelected ? (colors.brand ? `${colors.brand}12` : colors.brandSoft) : item.read ? colors.surface : colors.brandSoft,
          borderColor: (globalThis as any).__alphaColor(isSelected ? colors.brand : item.read ? colors.border : colors.brand, '35'),
          flexWrap: isMobile ? 'wrap' : 'nowrap',
          padding: rowPadding,
          gap: contentGap,
        },
      ]}
      data-testid={`notifications-item-${id}`} testID={`notifications-item-${id}`}
    >
      <TouchableOpacity accessibilityLabel="On toggle select in notifications workspace button"
        onPress={() => onToggleSelect(id)}
        style={[
          styles.selectionButton,
          {
            borderColor: isSelected ? colors.brand : colors.border,
            backgroundColor: isSelected ? colors.brand : colors.surfaceMuted,
            marginTop: dense ? 2 : 4,
          },
        ]}
        data-testid={`notifications-select-${id}`} testID={`notifications-select-${id}`}
      >
        {isSelected ? <Ionicons name="checkmark" size={14} color={colors.primaryText} /> : null}
      </TouchableOpacity>
      <View style={{ width: 4, alignSelf: "stretch", borderRadius: 99, backgroundColor: item.read ? colors.textSec : colors.brand }} />

      {visual.avatarUrl ? (
        <Image source={{ uri: visual.avatarUrl }} style={[styles.avatar, { width: avatarSize, height: avatarSize, borderRadius: dense ? 12 : 14 }]} resizeMode="cover" data-testid={`notifications-item-avatar-${id}`} testID={`notifications-item-avatar-${id}`} accessibilityLabel="Decorative image" />
      ) : (
        <View style={[styles.avatar, { width: avatarSize, height: avatarSize, borderRadius: dense ? 12 : 14, backgroundColor: visual.accent }]} data-testid={`notifications-item-icon-${id}`} testID={`notifications-item-icon-${id}`}>
          <Ionicons name={visual.name} size={dense ? 16 : 18} color={visual.color} />
        </View>
      )}

      <Pressable accessibilityLabel="On open in notifications workspace button"
        onPress={() => onOpen(item)}
        style={({ pressed }) => [
          { flex: 1, minWidth: 0, borderRadius: 18 },
          pressed ? getShadow("sm", false) : null,
        ]}
        data-testid={`notifications-item-open-${id}`} testID={`notifications-item-open-${id}`}
      >
        <View style={{ flexDirection: isMobile ? "column" : "row", gap: 8, alignItems: isMobile ? "flex-start" : "center" }}>
          <Text numberOfLines={1} style={[styles.rowTitle, { color: colors.text, fontSize: dense ? 14 : 15 }]} data-testid={`notifications-item-title-${id}`} testID={`notifications-item-title-${id}`}>
            {item.title || "Notification"}
          </Text>
          {!item.read ? <View style={[styles.unreadDot, { backgroundColor: colors.brand }]} data-testid={`notifications-item-unread-${id}`} testID={`notifications-item-unread-${id}`} /> : null}
        </View>

        <Text style={[styles.rowBody, { color: colors.textSecondary, fontSize: dense ? 12 : 13, lineHeight: dense ? 18 : 20 }]} data-testid={`notifications-item-message-${id}`} testID={`notifications-item-message-${id}`}>
          {item.message || item.body}
        </Text>

        <View style={styles.rowMeta}>
          <View style={[styles.typeChip, { backgroundColor: visual.accent }]}>
            <Text style={{ color: visual.color, fontSize: 10, fontWeight: "800" }}>{String(item.type || "general").replace(/_/g, " ")}</Text>
          </View>
          <Text style={{ color: colors.textSecondary, fontSize: 11 }}>{timeAgo(item.created_at)}</Text>
          {item.action_url ? (
            <Text style={{ color: colors.brand, fontSize: 11, fontWeight: "700" }} data-testid={`notifications-open-hint-${id}`} testID={`notifications-open-hint-${id}`}>
              Open destination
            </Text>
          ) : null}
        </View>
      </Pressable>

      <View style={[styles.rowActions, { alignItems: isMobile ? "flex-start" : "flex-end", flexDirection: isMobile ? 'row' : 'column', flexWrap: isMobile ? 'wrap' : 'nowrap', width: isMobile ? '100%' : undefined, paddingLeft: isMobile ? (dense ? 76 : 88) : 0 }]}>
        {!item.read ? (
          <TouchableOpacity onPress={() => onMarkRead(id)} style={[styles.ghostButton, { borderColor: (globalThis as any).__alphaColor(colors.brand, '35'), backgroundColor: colors.brandSoft }]} data-testid={`notifications-mark-read-${id}`} testID={`notifications-mark-read-${id}`}>
            <Text style={{ color: colors.brand, fontSize: 11, fontWeight: "800" }}>Mark read</Text>
          </TouchableOpacity>
        ) : null}
        <TouchableOpacity onPress={() => onDelete(id)} style={[styles.ghostButton, { borderColor: colors.dangerBorder, backgroundColor: colors.dangerSoft }]} data-testid={`notifications-delete-${id}`} testID={`notifications-delete-${id}`}>
          <Text style={{ color: colors.errorText, fontSize: 11, fontWeight: "800" }}>Delete</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const PreferencesDrawer = ({
  open,
  close,
  colors,
  isMobile,
  preferences,
  preferencesLoading,
  preferencesSaving,
  preferencesMessage,
  updatePreference,
  savePreferences,
  pushPermission,
  preferenceRows,
  labels,
  isAdmin,
  retention,
  retentionLoading,
  updateRetention,
  saveRetention,
  retentionSaving,
}) => (
  <Modal visible={open} transparent animationType="fade" onRequestClose={close}>
    <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" }}>
      <View style={[styles.drawer, { backgroundColor: colors.surface, borderColor: colors.border, width: isMobile ? "100%" : 430, borderBottomLeftRadius: isMobile ? 0 : 28 }]} data-testid="notifications-preferences-drawer" testID="notifications-preferences-drawer">
        <View style={styles.drawerHeader}>
          <View style={{ flex: 1 }}>
            <Text style={[styles.drawerTitle, { color: colors.text }]} data-testid="notifications-preferences-title" testID="notifications-preferences-title">Notification Preferences</Text>
            <Text style={{ color: colors.textSecondary, fontSize: 12, marginTop: 6 }}>
              Manage delivery, digest rhythm, and quiet hours without leaving your inbox.
            </Text>
          </View>
          <TouchableOpacity onPress={close} style={[styles.iconButton, { borderColor: colors.border, backgroundColor: colors.surfaceMuted }]} data-testid="notifications-preferences-close-button" testID="notifications-preferences-close-button">
            <Ionicons name="close" size={18} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>

        <ScrollView style={{ marginTop: 18 }} contentContainerStyle={{ gap: 12, paddingBottom: 24 }} data-testid="notifications-preferences-scroll" testID="notifications-preferences-scroll">
          {preferencesLoading ? (
            <View style={{ paddingVertical: 40, alignItems: "center" }} data-testid="notifications-preferences-loading" testID="notifications-preferences-loading">
              <ActivityIndicator size="small" color={colors.brand} />
            </View>
          ) : (
            <>
              {Boolean(preferencesMessage) ? (
                <View style={[styles.banner, { backgroundColor: preferencesMessage === "Preferences saved." ? colors.successSoft : colors.warningSoft, borderColor: preferencesMessage === "Preferences saved." ? colors.success : colors.warning }]} data-testid="notifications-preferences-message-banner" testID="notifications-preferences-message-banner">
                  <Text style={{ color: preferencesMessage === "Preferences saved." ? colors.successText : colors.warningText, fontSize: 12, fontWeight: "700" }}>{preferencesMessage}</Text>
                </View>
              ) : null}

              <View style={[styles.preferenceCard, { backgroundColor: colors.surfaceMuted, borderColor: colors.border }]} data-testid="notifications-preferences-delivery-section" testID="notifications-preferences-delivery-section">
                <Text style={[styles.preferenceSectionTitle, { color: colors.text }]}>Delivery Channels</Text>
                <Text style={{ color: colors.textSecondary, fontSize: 12, marginBottom: 8 }}>
                  Browser push is currently {pushPermission === "granted" ? "enabled" : "not enabled"} for this device.
                </Text>
                {preferenceRows.slice(0, 2).map((row) => (
                  <TouchableOpacity key={row.key} onPress={() => updatePreference(row.key, !preferences?.[row.key])} style={[styles.preferenceRow, { borderColor: colors.border }]} data-testid={`notifications-setting-${row.key}-toggle`} testID={`notifications-setting-${row.key}-toggle`}>
                    <View style={{ flex: 1, paddingRight: 12 }}>
                      <Text style={{ color: colors.text, fontSize: 13, fontWeight: "700" }}>{row.label}</Text>
                      <Text style={{ color: colors.textSecondary, fontSize: 11, marginTop: 4 }}>{row.description}</Text>
                    </View>
                    <View style={[styles.switchTrack, { backgroundColor: preferences?.[row.key] ? colors.brand : colors.border }]}>
                      <View style={[styles.switchThumb, { alignSelf: preferences?.[row.key] ? "flex-end" : "flex-start" }]} />
                    </View>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={[styles.preferenceCard, { backgroundColor: colors.surfaceMuted, borderColor: colors.border }]} data-testid="notifications-preferences-topics-section" testID="notifications-preferences-topics-section">
                <Text style={[styles.preferenceSectionTitle, { color: colors.text }]}>Topics & Digests</Text>
                {preferenceRows.slice(2).map((row) => (
                  <TouchableOpacity key={row.key} onPress={() => updatePreference(row.key, !preferences?.[row.key])} style={[styles.preferenceRow, { borderColor: colors.border }]} data-testid={`notifications-setting-${row.key}-toggle`} testID={`notifications-setting-${row.key}-toggle`}>
                    <View style={{ flex: 1, paddingRight: 12 }}>
                      <Text style={{ color: colors.text, fontSize: 13, fontWeight: "700" }}>{row.label}</Text>
                      <Text style={{ color: colors.textSecondary, fontSize: 11, marginTop: 4 }}>{row.description}</Text>
                    </View>
                    <View style={[styles.switchTrack, { backgroundColor: preferences?.[row.key] ? colors.brand : colors.border }]}>
                      <View style={[styles.switchThumb, { alignSelf: preferences?.[row.key] ? "flex-end" : "flex-start" }]} />
                    </View>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={[styles.preferenceCard, { backgroundColor: colors.surfaceMuted, borderColor: colors.border }]} data-testid="notifications-preferences-quiet-hours-section" testID="notifications-preferences-quiet-hours-section">
                <TouchableOpacity onPress={() => updatePreference("quiet_hours_enabled", !preferences?.quiet_hours_enabled)} style={[styles.preferenceRow, { borderColor: colors.border }]} data-testid="notifications-setting-quiet-hours-enabled-toggle" testID="notifications-setting-quiet-hours-enabled-toggle">
                  <View style={{ flex: 1, paddingRight: 12 }}>
                    <Text style={{ color: colors.text, fontSize: 13, fontWeight: "700" }}>{labels.quietHoursTitle}</Text>
                    <Text style={{ color: colors.textSecondary, fontSize: 11, marginTop: 4 }}>{labels.quietHoursDescription}</Text>
                  </View>
                  <View style={[styles.switchTrack, { backgroundColor: preferences?.quiet_hours_enabled ? colors.brand : colors.border }]}>
                    <View style={[styles.switchThumb, { alignSelf: preferences?.quiet_hours_enabled ? "flex-end" : "flex-start" }]} />
                  </View>
                </TouchableOpacity>

                <View style={{ flexDirection: isMobile ? "column" : "row", gap: 10, marginTop: 12 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.textSecondary, fontSize: 11, marginBottom: 6 }}>{labels.startTime}</Text>
                    <TextInput value={preferences?.quiet_hours_start || ""} onChangeText={(value) => updatePreference("quiet_hours_start", value)} placeholder="22:00" placeholderTextColor={colors.textSecondary} style={[styles.preferenceInput, { color: colors.text, borderColor: colors.border, backgroundColor: colors.surface }]} data-testid="notifications-setting-quiet-hours-start-input" testID="notifications-setting-quiet-hours-start-input" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.textSecondary, fontSize: 11, marginBottom: 6 }}>{labels.endTime}</Text>
                    <TextInput value={preferences?.quiet_hours_end || ""} onChangeText={(value) => updatePreference("quiet_hours_end", value)} placeholder="07:00" placeholderTextColor={colors.textSecondary} style={[styles.preferenceInput, { color: colors.text, borderColor: colors.border, backgroundColor: colors.surface }]} data-testid="notifications-setting-quiet-hours-end-input" testID="notifications-setting-quiet-hours-end-input" />
                  </View>
                </View>
              </View>

              {isAdmin ? (
                <View style={[styles.preferenceCard, { backgroundColor: colors.surfaceMuted, borderColor: colors.border }]} testID="notifications-retention-settings-section">
                  <Text style={[styles.preferenceSectionTitle, { color: colors.text }]}>Retention Policy (Admin)</Text>
                  <Text style={{ color: colors.textSecondary, fontSize: 11, marginBottom: 10 }}>
                    Notifications older than the configured window are automatically archived nightly at 03:30 UTC.
                  </Text>
                  {retentionLoading ? (
                    <ActivityIndicator size="small" color={colors.brand} />
                  ) : (
                    <>
                      <TouchableOpacity accessibilityLabel="Auto-Archive Enabled" onPress={() => updateRetention("auto_archive_enabled", !retention?.auto_archive_enabled)} style={[styles.preferenceRow, { borderColor: colors.border }]} testID="retention-toggle-enabled">
                        <View style={{ flex: 1, paddingRight: 12 }}>
                          <Text style={{ color: colors.text, fontSize: 13, fontWeight: "700" }}>Auto-Archive Enabled</Text>
                          <Text style={{ color: colors.textSecondary, fontSize: 11, marginTop: 4 }}>Automatically archive old notifications on a nightly schedule.</Text>
                        </View>
                        <View style={[styles.switchTrack, { backgroundColor: retention?.auto_archive_enabled ? colors.brand : colors.border }]}>
                          <View style={[styles.switchThumb, { alignSelf: retention?.auto_archive_enabled ? "flex-end" : "flex-start" }]} />
                        </View>
                      </TouchableOpacity>
                      <View style={{ marginTop: 10 }}>
                        <Text style={{ color: colors.textSecondary, fontSize: 11, marginBottom: 6 }}>Retention Window (days)</Text>
                        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                          {[7, 14, 30, 60, 90].map((d) => (
                            <TouchableOpacity key={d} accessibilityLabel="Update retention in notifications workspace button" onPress={() => updateRetention("retention_days", d)} testID={`retention-days-${d}`} style={{
                              paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
                              backgroundColor: retention?.retention_days === d ? colors.brand : colors.surface,
                              borderWidth: 1, borderColor: retention?.retention_days === d ? colors.brand : colors.border,
                            }}>
                              <Text style={{ fontSize: 12, fontWeight: "700", color: retention?.retention_days === d ? colors.text : colors.textSecondary }}>{d}d</Text>
                            </TouchableOpacity>
                          ))}
                        </View>
                      </View>
                      <TouchableOpacity accessibilityLabel="Retention save button" onPress={() => { void saveRetention(); }} disabled={retentionSaving} testID="retention-save-btn" style={{
                        marginTop: 14, paddingVertical: 10, borderRadius: 10, alignItems: "center",
                        backgroundColor: colors.brand, opacity: retentionSaving ? 0.6 : 1,
                      }}>
                        <Text style={{ color: colors.text, fontSize: 12, fontWeight: "800" }}>{retentionSaving ? "Saving..." : "Save Retention Settings"}</Text>
                      </TouchableOpacity>
                    </>
                  )}
                </View>
              ) : null}
            </>
          )}
        </ScrollView>

        <View style={{ flexDirection: "row", gap: 10 }}>
          <TouchableOpacity onPress={close} style={[styles.footerButton, { backgroundColor: colors.surfaceMuted, borderColor: colors.border }]} data-testid="notifications-preferences-cancel-button" testID="notifications-preferences-cancel-button">
            <Text style={{ color: colors.textSecondary, fontSize: 12, fontWeight: "800" }}>{labels.close}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { void savePreferences(); }} disabled={preferencesLoading || preferencesSaving} style={[styles.footerButton, { backgroundColor: colors.brand, borderColor: colors.brand, opacity: preferencesLoading || preferencesSaving ? 0.7 : 1 }]} data-testid="notifications-preferences-save-button" testID="notifications-preferences-save-button">
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: "800" }}>{preferencesSaving ? labels.saving : labels.savePreferences}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  </Modal>
);

export const NotificationsWorkspace = () => {
  const { colors: C } = useTheme();
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const {
    strictLabel,
    getMissingLabels,
    loading: gpsLoading,
    error: gpsError,
    refetch: gpsRefetch,
    diagnostics: gpsDiagnostics,
  } = useGlobalPlatformState();

  const requiredNotificationLabelKeys = [
    "notifications.pref.push.label",
    "notifications.pref.push.desc",
    "notifications.pref.email.label",
    "notifications.pref.email.desc",
    "notifications.pref.daily.label",
    "notifications.pref.daily.desc",
    "notifications.pref.weekly.label",
    "notifications.pref.weekly.desc",
    "notifications.pref.team.label",
    "notifications.pref.team.desc",
    "notifications.pref.goal.label",
    "notifications.pref.goal.desc",
    "notifications.pref.practice.label",
    "notifications.pref.practice.desc",
    "notifications.pref.achievement.label",
    "notifications.pref.achievement.desc",
    "notifications.pref.coaching.label",
    "notifications.pref.coaching.desc",
    "notifications.pref.quiet_hours.title",
    "notifications.pref.quiet_hours.desc",
    "notifications.pref.quiet_hours.start",
    "notifications.pref.quiet_hours.end",
    "notifications.pref.save",
    "common.close",
    "common.saving",
  ];
  const missingNotificationLabels = getMissingLabels(requiredNotificationLabelKeys);
  const strictOrTx = useCallback((key: string, fallback: string) => {
    const strictValue = strictLabel(key);
    if (strictValue) return strictValue;
    return tx(key, fallback);
  }, [strictLabel, tx]);

  const preferenceRows = useMemo(() => ([
    {
      key: "push_enabled",
      label: strictOrTx("notifications.pref.push.label", "Push notifications"),
      description: strictOrTx("notifications.pref.push.desc", "Receive push updates on this device"),
    },
    {
      key: "email_enabled",
      label: strictOrTx("notifications.pref.email.label", "Email notifications"),
      description: strictOrTx("notifications.pref.email.desc", "Receive notification emails"),
    },
    {
      key: "daily_briefing",
      label: strictOrTx("notifications.pref.daily.label", "Daily briefing"),
      description: strictOrTx("notifications.pref.daily.desc", "One summary every day"),
    },
    {
      key: "weekly_digest",
      label: strictOrTx("notifications.pref.weekly.label", "Weekly digest"),
      description: strictOrTx("notifications.pref.weekly.desc", "Weekly highlights summary"),
    },
    {
      key: "team_updates",
      label: strictOrTx("notifications.pref.team.label", "Team updates"),
      description: strictOrTx("notifications.pref.team.desc", "Updates from your team"),
    },
    {
      key: "goal_reminders",
      label: strictOrTx("notifications.pref.goal.label", "Goal reminders"),
      description: strictOrTx("notifications.pref.goal.desc", "Reminders about your goals"),
    },
    {
      key: "practice_reminders",
      label: strictOrTx("notifications.pref.practice.label", "Practice reminders"),
      description: strictOrTx("notifications.pref.practice.desc", "Prompts to continue practice"),
    },
    {
      key: "achievement_alerts",
      label: strictOrTx("notifications.pref.achievement.label", "Achievement alerts"),
      description: strictOrTx("notifications.pref.achievement.desc", "Celebrate milestones and wins"),
    },
    {
      key: "coaching_nudges",
      label: strictOrTx("notifications.pref.coaching.label", "Coaching nudges"),
      description: strictOrTx("notifications.pref.coaching.desc", "AI coaching nudges and insights"),
    },
  ]), [strictOrTx]);

  const drawerLabels = useMemo(() => ({
    quietHoursTitle: strictOrTx("notifications.pref.quiet_hours.title", "Quiet hours"),
    quietHoursDescription: strictOrTx("notifications.pref.quiet_hours.desc", "Mute non-critical alerts during selected hours"),
    startTime: strictOrTx("notifications.pref.quiet_hours.start", "Start time"),
    endTime: strictOrTx("notifications.pref.quiet_hours.end", "End time"),
    close: strictOrTx("common.close", "Close"),
    savePreferences: strictOrTx("notifications.pref.save", "Save preferences"),
    saving: strictOrTx("common.saving", "Saving..."),
  }), [strictOrTx]);

  const isMobile = width < 768;
  const isNarrowMobile = width < 480;
  const isTablet = width >= 768 && width < 1180;

  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [summary, setSummary] = useState(null);
  const [serverUnreadCount, setServerUnreadCount] = useState(null);
  const [search, setSearch] = useState("");
  const [pushPermission, setPushPermission] = useState("default");
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [preferences, setPreferences] = useState(null);
  const [preferencesLoading, setPreferencesLoading] = useState(false);
  const [preferencesSaving, setPreferencesSaving] = useState(false);
  const [preferencesMessage, setPreferencesMessage] = useState("");
  const [retention, setRetention] = useState({ retention_days: 30, auto_archive_enabled: true });
  const [retentionLoading, setRetentionLoading] = useState(false);
  const [retentionSaving, setRetentionSaving] = useState(false);
  const isAdmin = Boolean(user?.is_admin);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [denseView, setDenseView] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(null);
  const notificationsCountRef = useRef(0);
  const fetchNotificationsRef = useRef(async () => {});
  const notificationCenter = useNotifications();

  const colors = {
    pageBg: Platform.OS === 'web' ? 'transparent' : C.bg,
    surface: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.surface || C.card, 'B0') : (C.surface || C.card),
    surfaceMuted: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.cardMuted || C.bgSoft || C.bgAlt, 'A8') : (C.cardMuted || C.bgSoft || C.bgAlt),
    text: C.text,
    textSec: C.textSec,
    textSecondary: C.textSecondary || C.textSec,
    textMuted: C.textMuted,
    border: C.border,
    brand: C.primary,
    brandSoft: C.primarySoft,
    success: C.success,
    successText: C.successText,
    successSoft: C.successSoft,
    warning: C.warning,
    warningText: C.warningText,
    warningSoft: C.warningSoft,
    progressTrack: C.bgAlt,
    divider: C.borderSoft || C.divider || C.border,
    dangerSoft: C.errorSoft,
    dangerBorder: C.error,
    error: C.error,
    errorText: C.errorText,
    primary: C.primary,
    primarySoft: C.primarySoft,
    indigo: C.info,
    purple: C.accent,
    purpleText: C.purpleText || C.accent,
    info: C.info,
    infoText: C.infoText,
    infoSoft: C.infoSoft,
  };

  useEffect(() => {
    if (Platform.OS === "web" && isNotificationSupported()) {
      setPushPermission(getNotificationPermission());
    }
  }, []);

  useEffect(() => {
    notificationsCountRef.current = notifications.length;
  }, [notifications.length]);

  useEffect(() => {
    AsyncStorage.getItem(DENSE_VIEW_STORAGE_KEY)
      .then((value) => {
        if (value === "dense") {
          setDenseView(true);
        }
      })
      .catch(() => {});
  }, []);

  const handleEnablePush = async () => {
    const result = await requestNotificationPermission();
    setPushPermission(result);
    if (result === "granted") {
      await registerPushNotifications();
    }
  };

  const fetchSummary = useCallback(async () => {
    try {
      const summaryRes = await api.get("/notification-engine/summary");
      if (summaryRes.data) {
        setSummary(summaryRes.data);
      }
    } catch {
      return null;
    }
  }, []);

  const fetchNotifications = useCallback(async () => {
    if (!user?.user_id) {
      setNotifications([]);
      setSummary(null);
      setServerUnreadCount(null);
      setLoading(authLoading);
      return;
    }

    setLoading((prev) => prev && notificationsCountRef.current === 0);
    try {
      const notificationsRes = await api.get(`/notifications/${user.user_id}?limit=24`);
      setNotifications(notificationsRes.data.notifications || []);
      setServerUnreadCount(typeof notificationsRes.data.unread_count === 'number' ? notificationsRes.data.unread_count : null);
      setLastSyncAt(new Date().toISOString());
      void fetchSummary();
    } catch {
      setNotifications([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [authLoading, fetchSummary, user?.user_id]);

  useEffect(() => {
    fetchNotificationsRef.current = fetchNotifications;
  }, [fetchNotifications]);

  useEffect(() => {
    void fetchNotificationsRef.current();
  }, [user?.user_id, authLoading]);

  useEffect(() => {
    if (!user?.user_id) return;

    const scope = String((notificationCenter as any)?.scope || 'user');
    const providerActive = scope === 'user';
    if (providerActive) {
      return;
    }

    const interval = setInterval(() => { void fetchNotificationsRef.current(); }, 120000);
    return () => clearInterval(interval);
  }, [user?.user_id, notificationCenter]);

  useEffect(() => {
    const availableIds = new Set(notifications.map((item) => item.notification_id || item.id).filter(Boolean));
    setSelectedIds((prev) => prev.filter((id) => availableIds.has(id)));
  }, [notifications]);

  const loadPreferences = useCallback(async () => {
    setPreferencesLoading(true);
    setPreferencesMessage("");
    try {
      const res = await api.get("/notifications/settings");
      setPreferences(res.data || null);
    } catch {
      setPreferencesMessage("Unable to load notification preferences right now.");
    } finally {
      setPreferencesLoading(false);
    }
  }, []);

  const openPreferences = async () => {
    setPreferencesOpen(true);
    if (!preferences) {
      await loadPreferences();
    }
    if (isAdmin) {
      setRetentionLoading(true);
      try {
        const res = await api.get("/admin/notification-settings/retention");
        setRetention(res.data || { retention_days: 30, auto_archive_enabled: true });
      } catch { /* silent */ }
      setRetentionLoading(false);
    }
  };

  const updateRetention = (key, value) => {
    setRetention((prev) => ({ ...prev, [key]: value }));
  };

  const saveRetention = async () => {
    setRetentionSaving(true);
    try {
      await api.put("/admin/notification-settings/retention", retention);
    } catch { /* silent */ }
    setRetentionSaving(false);
  };

  const updatePreference = (key, value) => {
    setPreferences((prev) => ({ ...(prev || {}), [key]: value }));
  };

  const savePreferences = async () => {
    if (!preferences) return;
    setPreferencesSaving(true);
    setPreferencesMessage("");
    try {
      const payload = {
        push_enabled: Boolean(preferences.push_enabled),
        email_enabled: Boolean(preferences.email_enabled),
        daily_briefing: Boolean(preferences.daily_briefing),
        practice_reminders: Boolean(preferences.practice_reminders),
        achievement_alerts: Boolean(preferences.achievement_alerts),
        weekly_digest: Boolean(preferences.weekly_digest),
        team_updates: Boolean(preferences.team_updates),
        goal_reminders: Boolean(preferences.goal_reminders),
        coaching_nudges: Boolean(preferences.coaching_nudges),
        quiet_hours_enabled: Boolean(preferences.quiet_hours_enabled),
        quiet_hours_start: preferences.quiet_hours_start || "22:00",
        quiet_hours_end: preferences.quiet_hours_end || "07:00",
      };
      const res = await api.put("/notifications/settings", payload);
      setPreferences(res.data || payload);
      setPreferencesMessage("Preferences saved.");
    } catch {
      setPreferencesMessage("Unable to save preferences right now.");
    } finally {
      setPreferencesSaving(false);
    }
  };

  const markRead = async (id) => {
    try {
      await api.post(`/notifications/${id}/read`);
      setNotifications((prev) => prev.map((item) => (item.notification_id === id || item.id === id ? { ...item, read: true } : item)));
      setServerUnreadCount((prev) => (typeof prev === 'number' ? Math.max(0, prev - 1) : prev));
      void fetchSummary();
    } catch {
      return false;
    }
  };

  const deleteNotification = async (id) => {
    try {
      const target = notifications.find((item) => (item.notification_id || item.id) === id);
      await api.delete(`/notifications/${id}`);
      setNotifications((prev) => prev.filter((item) => (item.notification_id || item.id) !== id));
      if (target && !target.read) {
        setServerUnreadCount((prev) => (typeof prev === 'number' ? Math.max(0, prev - 1) : prev));
      }
      void fetchSummary();
    } catch {
      return false;
    }
  };

  const markAllRead = async () => {
    try {
      await api.post(`/notifications/${user?.user_id || "me"}/read-all`);
      setNotifications((prev) => prev.map((item) => ({ ...item, read: true })));
      setServerUnreadCount(0);
      void fetchSummary();
    } catch {
      return false;
    }
  };

  const clearAllRead = async () => {
    try {
      const res = await api.post("/notifications/clear-read");
      const cleared = res.data?.cleared || 0;
      if (cleared > 0) {
        setNotifications((prev) => prev.filter((item) => !item.read));
        void fetchSummary();
      }
    } catch {
      return false;
    }
  };

  const selectedCount = selectedIds.length;

  const persistDenseView = async (next) => {
    setDenseView(next);
    try {
      await AsyncStorage.setItem(DENSE_VIEW_STORAGE_KEY, next ? "dense" : "comfortable");
    } catch {
      return false;
    }
  };

  const toggleSelectNotification = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((entry) => entry !== id) : [...prev, id]));
  };

  const clearSelection = () => setSelectedIds([]);

  const toggleSelectVisible = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        visibleNotificationIds.forEach((id) => next.delete(id));
      } else {
        visibleNotificationIds.forEach((id) => next.add(id));
      }
      return Array.from(next);
    });
  };

  const bulkMarkRead = async () => {
    if (!selectedIds.length) return;
    const selectedSet = new Set(selectedIds);
    const unreadAffected = notifications.filter((item) => selectedSet.has(item.notification_id || item.id) && !item.read).length;
    setBulkBusy("read");
    try {
      await api.post("/notifications/bulk/read", { notification_ids: selectedIds });
      setNotifications((prev) => prev.map((item) => (selectedSet.has(item.notification_id || item.id) ? { ...item, read: true } : item)));
      setServerUnreadCount((prev) => (typeof prev === 'number' ? Math.max(0, prev - unreadAffected) : prev));
      clearSelection();
      void fetchSummary();
    } catch {
      return false;
    } finally {
      setBulkBusy(null);
    }
  };

  const bulkArchive = async () => {
    if (!selectedIds.length) return;
    const selectedSet = new Set(selectedIds);
    const unreadAffected = notifications.filter((item) => selectedSet.has(item.notification_id || item.id) && !item.read).length;
    setBulkBusy("archive");
    try {
      await api.post("/notifications/bulk/archive", { notification_ids: selectedIds });
      setNotifications((prev) => prev.filter((item) => !selectedSet.has(item.notification_id || item.id)));
      setServerUnreadCount((prev) => (typeof prev === 'number' ? Math.max(0, prev - unreadAffected) : prev));
      clearSelection();
      void fetchSummary();
    } catch {
      return false;
    } finally {
      setBulkBusy(null);
    }
  };

  const unreadCount = useMemo(() => notifications.filter((item) => !item.read).length, [notifications]);
  const visibleUnreadCount = typeof summary?.total_unread === 'number'
    ? summary.total_unread
    : typeof serverUnreadCount === 'number'
      ? serverUnreadCount
      : unreadCount;

  const summaryData = useMemo(() => {
    const byCategory = { meetings: 0, hiring: 0, system: 0, general: 0 };
    notifications.forEach((item) => {
      byCategory[getNotificationVisual(item).category] = (byCategory[getNotificationVisual(item).category] || 0) + 1;
    });
    return {
      total: typeof summary?.total === 'number' ? summary.total : notifications.length,
      total_unread: visibleUnreadCount,
      by_type: summary?.by_type || {},
      by_category: byCategory,
    };
  }, [notifications, summary, visibleUnreadCount]);

  const signalRows = useMemo(() => {
    return Object.entries(summary?.by_type || {})
      .map(([key, value]) => ({ key, unread: value?.unread || 0, count: value?.count || 0 }))
      .sort((a, b) => (b.unread || b.count) - (a.unread || a.count))
      .slice(0, 5);
  }, [summary]);

  const filters = [
    { key: "all", label: t("notifications.filterAll"), icon: "grid-outline" },
    { key: "unread", label: `${t("notifications.filterUnread")}${visibleUnreadCount ? ` (${visibleUnreadCount})` : ""}`, icon: "mail-unread-outline" },
    { key: "meetings", label: t("notifications.filterMeetings"), icon: "calendar-outline" },
    { key: "hiring", label: t("notifications.filterHiring"), icon: "briefcase-outline" },
    { key: "system", label: t("notifications.filterSystem"), icon: "settings-outline" },
  ];

  const filteredNotifications = useMemo(() => {
    let items = [...notifications];
    if (filter === "unread") items = items.filter((item) => !item.read);
    if (filter !== "all" && filter !== "unread") items = items.filter((item) => getNotificationVisual(item).category === filter);
    if (search.trim()) {
      const query = search.trim().toLowerCase();
      items = items.filter((item) => `${item.title || ""} ${item.message || item.body || ""} ${item.type || ""}`.toLowerCase().includes(query));
    }
    return items;
  }, [filter, notifications, search]);

  const visibleNotificationIds = useMemo(
    () => filteredNotifications.map((item) => item.notification_id || item.id).filter(Boolean),
    [filteredNotifications],
  );
  const allVisibleSelected = visibleNotificationIds.length > 0 && visibleNotificationIds.every((id) => selectedIds.includes(id));

  const groupedNotifications = useMemo(() => {
    const groups = {};
    filteredNotifications.forEach((item) => {
      const key = getGroupLabel(item.created_at);
      groups[key] = groups[key] || [];
      groups[key].push(item);
    });
    return ["Today", "Yesterday", "Last 7 Days", "Earlier"].filter((key) => groups[key]?.length).map((key) => ({ key, items: groups[key] }));
  }, [filteredNotifications]);

  const openNotification = (item) => {
    const id = item.notification_id || item.id;
    if (!item.read && id) {
      void markRead(id);
    }
    if (item.action_url) {
      router.push(item.action_url);
    }
  };

  const summaryCardStyle = isNarrowMobile
    ? { minWidth: '100%', width: '100%' }
    : isTablet
      ? { minWidth: '48%', width: '48%' }
      : undefined;

  if (gpsLoading && !gpsError) {
    return (
      <AppShell>
        <View style={{ flex: 1, backgroundColor: colors.pageBg, padding: isMobile ? 16 : 28 }}>
          <GpsDataStatusCard
            surfaceName="notifications"
            loading={gpsLoading}
            error={gpsError}
            onRetry={() => void gpsRefetch()}
            colors={{
              bg: colors.pageBg,
              card: colors.surface,
              text: colors.text,
              textSec: colors.textSec,
              textMuted: colors.textMuted,
              border: colors.border,
              borderSoft: colors.border,
              primary: colors.primary,
              error: C.error,
              success: colors.success,
              warning: colors.warning,
            }}
            diagnostics={gpsDiagnostics}
            testIdPrefix="notifications"
          />
        </View>
      </AppShell>
    );
  }

  if (missingNotificationLabels.length > 0 && !gpsError && gpsDiagnostics?.mode === "live") {
    return (
      <AppShell>
        <GpsLabelBlocker surfaceName="notifications" missingKeys={missingNotificationLabels} colors={colors} />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <View style={{ flex: 1, backgroundColor: colors.pageBg }}>
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={{ padding: isMobile ? 16 : 28, maxWidth: 1240, width: "100%", alignSelf: "center" }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void fetchNotifications(); }} tintColor={colors.brand} />}
          data-testid="notifications-page" testID="notifications-page"
        >
          {gpsError ? (
            <View
              style={{ marginBottom: 16 }}
              data-testid="notifications-inline-gps-status-wrapper"
              testID="notifications-inline-gps-status-wrapper"
            >
              <GpsDataStatusCard
                surfaceName="notifications"
                loading={false}
                error={gpsError}
                onRetry={() => void gpsRefetch()}
                colors={{
                  bg: colors.pageBg,
                  card: colors.surface,
                  text: colors.text,
                  textSec: colors.textSec,
                  textMuted: colors.textMuted,
                  border: colors.border,
                  borderSoft: colors.border,
                  primary: colors.primary,
                  error: C.error,
                  success: colors.success,
                  warning: colors.warning,
                }}
                diagnostics={gpsDiagnostics}
                testIdPrefix="notifications"
              />
            </View>
          ) : null}
          <View>
            <View style={[styles.headerShell, { backgroundColor: colors.surface, borderColor: colors.border, flexDirection: isMobile ? 'column' : 'row', padding: isNarrowMobile ? 18 : 24, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }]}> 
              <View style={{ flex: 1, minWidth: isMobile ? "100%" : 320 }}>
                <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: "800", letterSpacing: 1.2, textTransform: "uppercase" }}>Inbox intelligence</Text>
                <View style={{ flexDirection: isMobile ? "column" : "row", alignItems: isMobile ? "flex-start" : "center", gap: 10, marginTop: 8 }}>
                  <Text style={[styles.pageTitle, { color: colors.text, fontSize: isNarrowMobile ? 24 : 34 }]} data-testid="notifications-title" testID="notifications-title">Notifications</Text>
                  <View style={[styles.unreadBadge, { backgroundColor: colors.brandSoft }]} data-testid="notifications-unread-badge" testID="notifications-unread-badge">
                    <Text style={{ color: colors.brand, fontSize: 12, fontWeight: "800" }}>{visibleUnreadCount} unread</Text>
                  </View>
                </View>
                <Text style={{ color: colors.textSecondary, fontSize: 14, marginTop: 10, maxWidth: 960 }} data-testid="notifications-subtitle" testID="notifications-subtitle">
                  A cleaner command inbox for meetings, hiring, AI nudges, and platform alerts — all accessible from the navigation bar.
                </Text>
              </View>

              <View style={{ flexDirection: isNarrowMobile ? 'column' : "row", flexWrap: "wrap", gap: 10, marginTop: isMobile ? 14 : 0, width: isMobile ? '100%' : undefined, alignItems: isNarrowMobile ? 'stretch' : 'flex-start' }}>
                <TouchableOpacity onPress={() => { setRefreshing(true); void fetchNotifications(); }} style={[styles.headerAction, { backgroundColor: colors.surfaceMuted, borderColor: colors.border, width: isNarrowMobile ? '100%' : undefined, justifyContent: 'center' }]} data-testid="notifications-refresh-button" testID="notifications-refresh-button">
                  <Ionicons name="refresh-outline" size={16} color={colors.textSecondary} />
                  <Text style={{ color: colors.textSecondary, fontSize: 12, fontWeight: "800" }}>Refresh</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => { void openPreferences(); }} style={[styles.headerAction, { backgroundColor: colors.surfaceMuted, borderColor: colors.border, width: isNarrowMobile ? '100%' : undefined, justifyContent: 'center' }]} data-testid="notifications-preferences-button" testID="notifications-preferences-button">
                  <Ionicons name="settings-outline" size={16} color={colors.textSecondary} />
                  <Text style={{ color: colors.textSecondary, fontSize: 12, fontWeight: "800" }}>Preferences</Text>
                </TouchableOpacity>
                {visibleUnreadCount > 0 ? (
                  <TouchableOpacity onPress={markAllRead} style={[styles.headerAction, { backgroundColor: colors.brand, borderColor: colors.brand, width: isNarrowMobile ? '100%' : undefined, justifyContent: 'center' }]} data-testid="mark-all-read-btn" testID="mark-all-read-btn">
                    <Ionicons name="checkmark-done-outline" size={16} color={colors.text} />
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: "800" }}>{t("notifications.markAllRead")}</Text>
                  </TouchableOpacity>
                ) : null}
                {notifications.some((item) => item.read) ? (
                  <TouchableOpacity onPress={clearAllRead} style={[styles.headerAction, { backgroundColor: colors.surfaceMuted, borderColor: colors.border, width: isNarrowMobile ? '100%' : undefined, justifyContent: 'center' }]} data-testid="clear-all-read-btn" testID="clear-all-read-btn">
                    <Ionicons name="trash-outline" size={16} color={colors.textSecondary} />
                    <Text style={{ color: colors.textSecondary, fontSize: 12, fontWeight: "800" }}>Clear Read</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            </View>
          </View>

          <View>
            <View style={{ flexDirection: isTablet || isMobile ? "column" : "row", gap: 14, marginTop: 16 }}>
              <View style={{ flex: 1.6, gap: 14 }}>
                <View style={styles.summaryGrid}>
                  <SummaryStat label="Total" value={summaryData.total || 0} tone={{ bg: colors.primarySoft, fg: colors.indigo }} icon="notifications" colors={colors} testId="notifications-summary-total" cardStyle={summaryCardStyle} />
                  <SummaryStat label="Unread" value={summaryData.total_unread || 0} tone={{ bg: colors.brandSoft, fg: colors.primary }} icon="mail-unread" colors={colors} testId="notifications-summary-unread" cardStyle={summaryCardStyle} />
                  <SummaryStat label="Types" value={Object.keys(summaryData.by_type || {}).length} tone={{ bg: colors.infoSoft, fg: colors.purpleText }} icon="layers" colors={colors} testId="notifications-summary-types" cardStyle={summaryCardStyle} />
                  <SummaryStat label="Meetings" value={summaryData.by_category?.meetings || 0} tone={{ bg: colors.infoSoft, fg: colors.infoText }} icon="calendar" colors={colors} testId="notifications-summary-meetings" cardStyle={summaryCardStyle} />
                </View>

                {Platform.OS === "web" && isNotificationSupported() && pushPermission !== "granted" ? (
                  <TouchableOpacity style={[styles.pushPrompt, { backgroundColor: colors.surface, borderColor: colors.primarySoft, flexDirection: isNarrowMobile ? 'column' : 'row', alignItems: isNarrowMobile ? 'flex-start' : 'center' }]} onPress={handleEnablePush} data-testid="enable-push-btn" testID="enable-push-btn">
                    <View style={[styles.pushPromptIcon, { backgroundColor: colors.brandSoft }]}> 
                      <Ionicons name="notifications-outline" size={18} color={colors.brand} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: colors.text, fontSize: 14, fontWeight: "800" }}>{t("notifications.enablePush")}</Text>
                      <Text style={{ color: colors.textSecondary, fontSize: 12, marginTop: 4 }}>{t("notifications.enablePushDesc")}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={colors.textSecondary} />
                  </TouchableOpacity>
                ) : null}

                <View style={[styles.toolbarShell, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <View style={[styles.searchShell, { backgroundColor: colors.surfaceMuted, borderColor: colors.border }]}>
                    <Ionicons name="search-outline" size={16} color={colors.textSecondary} />
                    <TextInput value={search} onChangeText={setSearch} placeholder="Search title, message, or type" placeholderTextColor={colors.textMuted} style={{ flex: 1, color: colors.text, fontSize: 13 }} data-testid="notifications-search-input" testID="notifications-search-input" />
                  </View>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} data-testid="notifications-filter-scroll" testID="notifications-filter-scroll">
                    <View style={{ flexDirection: "row", gap: 8 }}>
                      {filters.map((item) => (
                        <FilterPill key={item.key} active={filter === item.key} icon={item.icon} label={item.label} onPress={() => setFilter(item.key)} colors={colors} testId={`filter-${item.key}`} />
                      ))}
                    </View>
                  </ScrollView>

                  <View style={{ flexDirection: isMobile ? "column" : "row", justifyContent: "space-between", alignItems: isMobile ? "flex-start" : "center", gap: 10 }}>
                    <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                      <TouchableOpacity onPress={toggleSelectVisible} disabled={visibleNotificationIds.length === 0} style={[styles.compactAction, { borderColor: colors.border, backgroundColor: colors.surfaceMuted, opacity: visibleNotificationIds.length === 0 ? 0.6 : 1 }]} data-testid="notifications-select-visible-button" testID="notifications-select-visible-button">
                        <Ionicons name={allVisibleSelected ? "remove-circle-outline" : "checkmark-circle-outline"} size={15} color={colors.textSecondary} />
                        <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: "800" }}>{allVisibleSelected ? "Clear visible" : "Select visible"}</Text>
                      </TouchableOpacity>
                      {selectedCount > 0 ? (
                        <TouchableOpacity onPress={clearSelection} style={[styles.compactAction, { borderColor: colors.border, backgroundColor: colors.surface }]} data-testid="notifications-clear-selection-button" testID="notifications-clear-selection-button">
                          <Ionicons name="close-circle-outline" size={15} color={colors.textSecondary} />
                          <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: "800" }}>Clear selection</Text>
                        </TouchableOpacity>
                      ) : null}
                      <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: "700" }} data-testid="notifications-view-summary-copy" testID="notifications-view-summary-copy">
                        {denseView ? "Dense view is on" : "Comfortable view is on"}
                      </Text>
                    </View>

                    <View style={[styles.viewToggleShell, { borderColor: colors.border, backgroundColor: colors.surfaceMuted }]} data-testid="notifications-view-toggle-shell" testID="notifications-view-toggle-shell">
                      <TouchableOpacity onPress={() => { void persistDenseView(false); }} style={[styles.viewToggleButton, { backgroundColor: denseView ? "transparent" : colors.surface }]} data-testid="notifications-view-toggle-comfortable-button" testID="notifications-view-toggle-comfortable-button">
                        <Ionicons name="reorder-two-outline" size={15} color={denseView ? colors.textSecondary : colors.text} />
                        <Text style={{ color: denseView ? colors.textSecondary : colors.text, fontSize: 11, fontWeight: "800" }}>Comfortable</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => { void persistDenseView(true); }} style={[styles.viewToggleButton, { backgroundColor: denseView ? colors.surface : "transparent" }]} data-testid="notifications-view-toggle-dense-button" testID="notifications-view-toggle-dense-button">
                        <Ionicons name="menu-outline" size={15} color={denseView ? colors.text : colors.textSecondary} />
                        <Text style={{ color: denseView ? colors.text : colors.textSecondary, fontSize: 11, fontWeight: "800" }}>Dense</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>

                {selectedCount > 0 ? (
                  <View style={[styles.bulkActionBar, { backgroundColor: colors.surface, borderColor: colors.border, flexDirection: isMobile ? "column" : "row", alignItems: isMobile ? "flex-start" : "center" }]} data-testid="notifications-bulk-action-bar" testID="notifications-bulk-action-bar">
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: "800" }} data-testid="notifications-selected-count" testID="notifications-selected-count">
                      {selectedCount} selected
                    </Text>
                    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                      <TouchableOpacity onPress={() => { void bulkMarkRead(); }} disabled={bulkBusy !== null} style={[styles.compactAction, { borderColor: colors.brand, backgroundColor: colors.brandSoft, opacity: bulkBusy !== null ? 0.6 : 1 }]} data-testid="notifications-bulk-mark-read-button" testID="notifications-bulk-mark-read-button">
                        <Ionicons name="checkmark-done-outline" size={15} color={colors.brand} />
                        <Text style={{ color: colors.brand, fontSize: 11, fontWeight: "800" }}>{bulkBusy === "read" ? "Marking…" : "Mark selected read"}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => { void bulkArchive(); }} disabled={bulkBusy !== null} style={[styles.compactAction, { borderColor: colors.border, backgroundColor: colors.surfaceMuted, opacity: bulkBusy !== null ? 0.6 : 1 }]} data-testid="notifications-bulk-archive-button" testID="notifications-bulk-archive-button">
                        <Ionicons name="archive-outline" size={15} color={colors.textSecondary} />
                        <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: "800" }}>{bulkBusy === "archive" ? "Archiving…" : "Archive selected"}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                ) : null}

                {loading ? (
                  <NotificationsSkeleton />
                ) : groupedNotifications.length === 0 ? (
                  <View style={[styles.emptyState, { backgroundColor: colors.surface, borderColor: colors.border }]} data-testid="notifications-empty-state" testID="notifications-empty-state">
                    <Image source={{ uri: EMPTY_IMAGE }} style={{ width: 220, height: 130, borderRadius: 22, marginBottom: 18 }} resizeMode="cover" accessibilityLabel="Decorative image" />
                    <Text style={{ color: colors.text, fontSize: 20, fontWeight: "800" }}>{filter === "unread" ? t("notifications.noUnread") : t("notifications.noNotifications")}</Text>
                    <Text style={{ color: colors.textSecondary, fontSize: 13, marginTop: 6, textAlign: "center", maxWidth: 380 }}>{filter === "unread" ? t("notifications.caughtUp") : t("notifications.willAppear")}</Text>
                  </View>
                ) : (
                  groupedNotifications.map((group) => (
                    <View key={group.key}>
                      <View style={{ marginTop: 16 }} data-testid={`notifications-group-${group.key.toLowerCase().replace(/\s+/g, "-")}`} testID={`notifications-group-${group.key.toLowerCase().replace(/\s+/g, "-")}`}>
                        <Text style={{ color: colors.textSecondary, fontSize: 12, fontWeight: "800", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 10 }}>{group.key}</Text>
                        <View style={{ gap: denseView ? 8 : 10 }} data-testid={`notification-list-${group.key.toLowerCase().replace(/\s+/g, "-")}`} testID={`notification-list-${group.key.toLowerCase().replace(/\s+/g, "-")}`}>
                          {group.items.map((item) => (
                            <NotificationRow
                              key={item.notification_id || item.id}
                              item={item}
                              colors={colors}
                              isMobile={isMobile}
                              dense={denseView}
                              onOpen={openNotification}
                              onMarkRead={markRead}
                              onDelete={deleteNotification}
                              onToggleSelect={toggleSelectNotification}
                              isSelected={selectedIds.includes(item.notification_id || item.id)}
                            />
                          ))}
                        </View>
                      </View>
                    </View>
                  ))
                )}
              </View>

              <View style={{ width: isTablet || isMobile ? "100%" : 320, gap: 14 }} data-testid="notifications-side-rail" testID="notifications-side-rail">
                <View style={[styles.railCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <Text style={[styles.railTitle, { color: colors.text }]}>Delivery & Control</Text>
                  <View style={styles.railMetric} data-testid="notifications-delivery-push-status" testID="notifications-delivery-push-status">
                    <Text style={{ color: colors.textSecondary, fontSize: 12 }}>Push Notifications</Text>
                    <Text style={{ color: pushPermission === "granted" ? colors.success : colors.warning, fontSize: 12, fontWeight: "800" }}>{pushPermission === "granted" ? "Enabled" : "Action needed"}</Text>
                  </View>
                  <View style={styles.railMetric} data-testid="notifications-delivery-unread-status" testID="notifications-delivery-unread-status">
                    <Text style={{ color: colors.textSecondary, fontSize: 12 }}>Unread Queue</Text>
                    <Text style={{ color: visibleUnreadCount > 0 ? colors.warning : colors.success, fontSize: 12, fontWeight: "800" }}>{visibleUnreadCount > 0 ? `${visibleUnreadCount} pending` : "Clear"}</Text>
                  </View>
                  <View style={styles.railMetric} data-testid="notifications-last-sync-status" testID="notifications-last-sync-status">
                    <Text style={{ color: colors.textSecondary, fontSize: 12 }}>Last refresh</Text>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: "800" }}>{lastSyncAt ? timeAgo(lastSyncAt) : "just now"}</Text>
                  </View>
                </View>

                <View style={[styles.railCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <Text style={[styles.railTitle, { color: colors.text }]}>Category Mix</Text>
                  {[
                    { id: "meetings", label: t("notifications.filterMeetings"), value: summaryData.by_category?.meetings || 0, color: colors.primary },
                    { id: "hiring", label: t("notifications.filterHiring"), value: summaryData.by_category?.hiring || 0, color: colors.purpleText },
                    { id: "system", label: t("notifications.filterSystem"), value: summaryData.by_category?.system || 0, color: colors.warningText },
                    { id: "general", label: "General", value: summaryData.by_category?.general || 0, color: colors.successText },
                  ].map((row) => (
                    <View key={row.id} style={{ gap: 6 }} data-testid={`notifications-category-${row.id}`} testID={`notifications-category-${row.id}`}>
                      <View style={styles.railMetric}>
                        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                          <View style={{ width: 8, height: 8, borderRadius: 99, backgroundColor: row.color }} />
                          <Text style={{ color: colors.textSecondary, fontSize: 12 }}>{row.label}</Text>
                        </View>
                        <Text style={{ color: colors.text, fontSize: 12, fontWeight: "800" }}>{row.value}</Text>
                      </View>
                      <View style={{ height: 6, borderRadius: 99, backgroundColor: colors.progressTrack, overflow: "hidden" }}>
                        <View style={{ width: `${Math.min(100, summaryData.total ? (row.value / summaryData.total) * 100 : 0)}%`, height: "100%", backgroundColor: row.color }} />
                      </View>
                    </View>
                  ))}
                </View>

                <View style={[styles.railCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <Text style={[styles.railTitle, { color: colors.text }]}>High-Signal Types</Text>
                  {signalRows.length === 0 ? (
                    <Text style={{ color: colors.textSecondary, fontSize: 12 }}>Signal counts will appear once notification summaries load.</Text>
                  ) : (
                    signalRows.map((signal) => (
                      <View key={signal.key} style={[styles.signalRow, { borderTopColor: colors.divider }]} data-testid={`notifications-signal-${signal.key}`} testID={`notifications-signal-${signal.key}`}>
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: colors.text, fontSize: 12, fontWeight: "700" }}>{signal.key.replace(/_/g, " ")}</Text>
                          <Text style={{ color: colors.textSecondary, fontSize: 11, marginTop: 4 }}>{signal.unread} unread · {signal.count} total</Text>
                        </View>
                        <Ionicons name="chevron-forward" size={14} color={colors.textMuted} />
                      </View>
                    ))
                  )}
                </View>
              </View>
            </View>
          </View>
        </ScrollView>

        <PreferencesDrawer
          open={preferencesOpen}
          close={() => setPreferencesOpen(false)}
          colors={colors}
          isMobile={isMobile}
          preferences={preferences}
          preferencesLoading={preferencesLoading}
          preferencesSaving={preferencesSaving}
          preferencesMessage={preferencesMessage}
          updatePreference={updatePreference}
          savePreferences={savePreferences}
          pushPermission={pushPermission}
          preferenceRows={preferenceRows}
          labels={drawerLabels}
          isAdmin={isAdmin}
          retention={retention}
          retentionLoading={retentionLoading}
          updateRetention={updateRetention}
          saveRetention={saveRetention}
          retentionSaving={retentionSaving}
        />
      </View>
    </AppShell>
  );
};

const styles = StyleSheet.create({
  headerShell: {
    borderWidth: 1,
    borderRadius: 28,
    padding: 24,
    gap: 16,
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
  },
  pageTitle: {
    fontSize: 34,
    fontWeight: "900",
    letterSpacing: -1.2,
  },
  unreadBadge: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 999,
  },
  headerAction: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 11,
    borderRadius: 999,
    borderWidth: 1,
  },
  summaryGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
  },
  summaryCard: {
    flex: 1,
    minWidth: 180,
    borderWidth: 1,
    borderRadius: 20,
    padding: 18,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  summaryIcon: {
    width: 44,
    height: 44,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  summaryLabel: {
    fontSize: 11,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  summaryValue: {
    fontSize: 28,
    fontWeight: "900",
    marginTop: 4,
  },
  pushPrompt: {
    borderWidth: 1,
    borderRadius: 20,
    padding: 18,
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
  },
  pushPromptIcon: {
    width: 44,
    height: 44,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  toolbarShell: {
    borderWidth: 1,
    borderRadius: 22,
    padding: 14,
    gap: 12,
  },
  searchShell: {
    borderWidth: 1,
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  filterPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  compactAction: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  viewToggleShell: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderRadius: 999,
    padding: 4,
    gap: 4,
  },
  viewToggleButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  bulkActionBar: {
    borderWidth: 1,
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 10,
    justifyContent: "space-between",
    marginTop: 14,
  },
  notificationRow: {
    borderWidth: 1,
    borderRadius: 22,
    padding: 16,
    flexDirection: "row",
    gap: 14,
    alignItems: "flex-start",
  },
  selectionButton: {
    width: 24,
    height: 24,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 14,
    overflow: "hidden",
    alignItems: "center",
    justifyContent: "center",
  },
  rowTitle: {
    fontSize: 15,
    fontWeight: "800",
    flexShrink: 1,
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 99,
  },
  rowBody: {
    fontSize: 13,
    lineHeight: 20,
    marginTop: 6,
  },
  rowMeta: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
    marginTop: 10,
  },
  typeChip: {
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  rowActions: {
    gap: 8,
    rowGap: 8,
    columnGap: 8,
  },
  ghostButton: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  railCard: {
    borderWidth: 1,
    borderRadius: 20,
    padding: 18,
    gap: 12,
  },
  railTitle: {
    fontSize: 13,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  railMetric: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
  },
  signalRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: 'transparent',
  },
  emptyState: {
    borderWidth: 1,
    borderRadius: 26,
    padding: 40,
    alignItems: "center",
    marginTop: 16,
  },
  drawer: {
    alignSelf: "flex-end",
    height: "100%",
    maxWidth: "100%",
    borderTopLeftRadius: 28,
    borderBottomLeftRadius: 28,
    borderWidth: 1,
    padding: 20,
  },
  drawerHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
  },
  drawerTitle: {
    fontSize: 22,
    fontWeight: "800",
  },
  iconButton: {
    width: 38,
    height: 38,
    borderRadius: 12,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  banner: {
    borderWidth: 1,
    borderRadius: 14,
    padding: 12,
  },
  preferenceCard: {
    borderWidth: 1,
    borderRadius: 20,
    padding: 16,
    gap: 8,
  },
  preferenceSectionTitle: {
    fontSize: 13,
    fontWeight: "800",
  },
  preferenceRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    borderBottomWidth: 1,
    paddingVertical: 12,
  },
  switchTrack: {
    width: 48,
    height: 28,
    borderRadius: 999,
    padding: 3,
    justifyContent: "center",
  },
  switchThumb: {
    width: 22,
    height: 22,
    borderRadius: 999,
    backgroundColor: 'rgb(255,255,255)', // @theme-ok switch handle (white in both modes)
    borderWidth: 1,
  },
  footerButton: {
    flex: 1,
    borderWidth: 1,
    borderRadius: 14,
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
  },
});
