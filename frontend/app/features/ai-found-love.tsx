/**
 * Feature 12: Relationship Coach — Enterprise Workspace
 *
 * 12 fully functional tabs:
 * 1. Dashboard      — KPI strip, upcoming reminders preview, quick actions
 * 2. AI Advisor     — Free-text relationship question → AI response
 * 3. Date Ideas     — Generate AI date ideas + history grid
 * 4. Gift Finder    — Occasion + budget → AI gift recommendations + history
 * 5. Important Dates— Full CRUD for anniversaries, birthdays, milestones
 * 6. Reminders      — 30-day rolling calendar of upcoming dates
 * 7. Conversation Lab — AI conversation starters by mood / stage / topic
 * 8. Comm Coach     — Scenario-based communication coaching + history
 * 9. Assessment     — 5-dimension relationship health assessment
 * 10. Assess History — Past assessments + trend scores
 * 11. Session Journal— All past AI advice sessions
 * 12. Analytics      — Usage breakdown & progress metrics
 */

import React, { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  StyleSheet,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useTheme } from "../../src/context/ThemeContext";
import { Ionicons } from "@expo/vector-icons";
import { handleAppRecoverableError } from "../../src/utils/appRecoverableError";
import { useTranslation } from "../../src/hooks/useTranslation";
import api from "../../src/services/api";

const API = process.env.REACT_APP_BACKEND_URL || "";
const FALLBACK_ID = "user_rc_guest_workspace_2026v1";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Bootstrap {
  owner_id: string;
  tier: string;
  limits: { ai_sessions_per_month: number; important_dates: number; assessments_per_month: number };
  usage: { ai_sessions_this_month: number; important_dates: number };
  profile_exists: boolean;
}

interface Profile {
  relationship_status: string;
  partner_name?: string;
  anniversary_date?: string;
  challenges: string[];
  goals: string[];
}

interface ImportantDateItem {
  date_id: string;
  title: string;
  date: string;
  category: string;
  reminder_days: number;
  notes?: string;
  created_at: string;
}

interface AdviceSession {
  session_id: string;
  situation: string;
  created_at: string;
}

interface DateIdea {
  idea_id: string;
  ideas: string;
  parameters: Record<string, unknown>;
  created_at: string;
}

interface GiftIdea {
  gift_id: string;
  recommendations: string;
  occasion: string;
  created_at: string;
}

interface Assessment {
  assessment_id: string;
  health_score: number;
  scores: Record<string, number>;
  strengths: string[];
  improvement_areas: string[];
  created_at: string;
}

interface CommTip {
  tip_id: string;
  scenario: string;
  tips: string;
  created_at: string;
}

interface Analytics {
  total_advice_sessions: number;
  total_date_ideas_generated: number;
  total_assessments: number;
  important_dates_tracked: number;
  latest_health_score: number | null;
}

type TabKey =
  | "dashboard"
  | "advisor"
  | "date-ideas"
  | "gift-finder"
  | "important-dates"
  | "reminders"
  | "conv-lab"
  | "comm-coach"
  | "assessment"
  | "assess-history"
  | "journal"
  | "analytics";

const TABS: { key: TabKey; icon: string; label: string }[] = [
  { key: "dashboard", icon: "heart", label: "Dashboard" },
  { key: "advisor", icon: "chatbubble-ellipses", label: "AI Advisor" },
  { key: "date-ideas", icon: "star", label: "Date Ideas" },
  { key: "gift-finder", icon: "gift", label: "Gift Finder" },
  { key: "important-dates", icon: "calendar", label: "Important Dates" },
  { key: "reminders", icon: "notifications", label: "Reminders" },
  { key: "conv-lab", icon: "bulb", label: "Conversation Lab" },
  { key: "comm-coach", icon: "megaphone", label: "Comm Coach" },
  { key: "assessment", icon: "fitness", label: "Assessment" },
  { key: "assess-history", icon: "bar-chart", label: "Assess History" },
  { key: "journal", icon: "book", label: "Session Journal" },
  { key: "analytics", icon: "analytics", label: "Analytics" },
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function RelationshipCoach() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  t('i18n.route.features.ai-found-love.probe');

  // Core
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>("dashboard");
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);

  // Per-tab data
  const [upcomingDates, setUpcomingDates] = useState<ImportantDateItem[]>([]);
  const [importantDates, setImportantDates] = useState<ImportantDateItem[]>([]);
  const [sessions, setSessions] = useState<AdviceSession[]>([]);
  const [dateIdeasHistory, setDateIdeasHistory] = useState<DateIdea[]>([]);
  const [giftHistory, setGiftHistory] = useState<GiftIdea[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [commHistory, setCommHistory] = useState<CommTip[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);

  // AI results
  const [adviceResult, setAdviceResult] = useState("");
  const [dateIdeasResult, setDateIdeasResult] = useState("");
  const [giftResult, setGiftResult] = useState("");
  const [convResult, setConvResult] = useState("");
  const [commResult, setCommResult] = useState("");
  const [assessResult, setAssessResult] = useState<Assessment | null>(null);

  // AI loading states
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [dateIdeaLoading, setDateIdeaLoading] = useState(false);
  const [giftLoading, setGiftLoading] = useState(false);
  const [convLoading, setConvLoading] = useState(false);
  const [commLoading, setCommLoading] = useState(false);
  const [assessLoading, setAssessLoading] = useState(false);

  // Forms
  const [adviceForm, setAdviceForm] = useState({ situation: "", context: "", relationship_stage: "committed" });
  const [dateIdeasForm, setDateIdeasForm] = useState({ budget: "moderate", mood: "romantic", preferences: "", location: "" });
  const [giftForm, setGiftForm] = useState({ occasion: "anniversary", budget: "moderate", partner_interests: "", personality: "" });
  const [importantDateForm, setImportantDateForm] = useState({ title: "", date: "", category: "anniversary", reminder_days: "7", notes: "" });
  const [showImportantDateForm, setShowImportantDateForm] = useState(false);
  const [editingDate, setEditingDate] = useState<ImportantDateItem | null>(null);
  const [convForm, setConvForm] = useState({ relationship_stage: "committed", mood: "neutral", topic_preference: "" });
  const [commForm, setCommForm] = useState({ scenario: "", context: "" });
  const [assessForm, setAssessForm] = useState({
    communication_score: "7",
    trust_score: "7",
    intimacy_score: "7",
    conflict_resolution_score: "7",
    shared_goals_score: "7",
    notes: "",
  });

  // ── API helpers ─────────────────────────────────────────────────────────────

  const q = (extra = "") => `?fallback_user_id=${FALLBACK_ID}${extra}`;

  const apiRequest = useCallback(async (url: string, opts: any = {}) => {
    try {
      const target = String(url || "");
      const urlObj = target.startsWith("http")
        ? new URL(target)
        : new URL(target, "http://localhost");
      const endpoint = urlObj.pathname.startsWith("/api/") ? urlObj.pathname.slice(4) : urlObj.pathname;
      const params = Object.fromEntries(urlObj.searchParams.entries());
      const method = String(opts?.method || "GET").toUpperCase();

      let payload: any = undefined;
      if (opts?.body != null) {
        if (typeof opts.body === "string") {
          try {
            payload = JSON.parse(opts.body);
          } catch {
            payload = opts.body;
          }
        } else {
          payload = opts.body;
        }
      }

      const config: any = { params };
      let response: any;

      if (method === "GET") response = await api.get(endpoint, config);
      else if (method === "POST") response = await api.post(endpoint, payload, config);
      else if (method === "PUT") response = await api.put(endpoint, payload, config);
      else if (method === "PATCH") response = await api.patch(endpoint, payload, config);
      else if (method === "DELETE") response = await api.delete(endpoint, config);
      else throw new Error(`Unsupported method: ${method}`);

      return {
        ok: true,
        status: response.status,
        json: async () => response.data,
      };
    } catch (error: any) {
      const data = error?.response?.data || { detail: error?.message || "Request failed" };
      return {
        ok: false,
        status: Number(error?.response?.status || 500),
        json: async () => data,
      };
    }
  }, []);

  const apiFetch = useCallback(async (path: string, opts?: RequestInit) => {
    const res = await apiRequest(`${API}${path}`, { headers: { "Content-Type": "application/json" }, ...opts });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || "Request failed");
    return json;
  }, [apiRequest]);

  // ── Bootstrap ───────────────────────────────────────────────────────────────

  const init = useCallback(async () => {
    try {
      setLoading(true);
      const [bs, upcoming] = await Promise.all([
        apiFetch(`/api/relationship-coach/bootstrap${q()}`),
        apiFetch(`/api/relationship-coach/upcoming-reminders${q()}`),
      ]);
      setBootstrap(bs);
      setUpcomingDates(upcoming.upcoming_dates || []);
    } catch (e) {
      handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#init',
        error: e,
        message: 'Failed to load Relationship Coach',
        notifyMode: 'silent',
      });
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => { init(); }, []);

  // Tab-change data loaders
  useEffect(() => {
    if (activeTab === "important-dates") loadImportantDates();
    else if (activeTab === "date-ideas") loadDateIdeasHistory();
    else if (activeTab === "gift-finder") loadGiftHistory();
    else if (activeTab === "journal") loadSessions();
    else if (activeTab === "assess-history") loadAssessments();
    else if (activeTab === "comm-coach") loadCommHistory();
    else if (activeTab === "analytics") loadAnalytics();
    else if (activeTab === "reminders") loadUpcoming();
  }, [activeTab]);

  const loadImportantDates = async () => {
    try {
      const d = await apiFetch(`/api/relationship-coach/important-dates${q()}`);
      setImportantDates(d.dates || []);
    } catch (e) {
      handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#loadImportantDates',
        error: e,
        message: 'Could not load important dates.',
        notifyMode: 'silent',
      });
    }
  };

  const loadDateIdeasHistory = async () => {
    try {
      const d = await apiFetch(`/api/relationship-coach/date-ideas/history${q()}`);
      setDateIdeasHistory(d.history || []);
    } catch (e) {
      handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#loadDateIdeasHistory',
        error: e,
        message: 'Could not load date idea history.',
        notifyMode: 'silent',
      });
    }
  };

  const loadGiftHistory = async () => {
    try {
      const d = await apiFetch(`/api/relationship-coach/gift-ideas/history${q()}`);
      setGiftHistory(d.history || []);
    } catch (e) {
      handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#loadGiftHistory',
        error: e,
        message: 'Could not load gift history.',
        notifyMode: 'silent',
      });
    }
  };

  const loadSessions = async () => {
    try {
      const d = await apiFetch(`/api/relationship-coach/sessions${q()}`);
      setSessions(d.sessions || []);
    } catch (e) {
      handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#loadSessions',
        error: e,
        message: 'Could not load session history.',
        notifyMode: 'silent',
      });
    }
  };

  const loadAssessments = async () => {
    try {
      const d = await apiFetch(`/api/relationship-coach/assessments/history${q()}`);
      setAssessments(d.assessments || []);
    } catch (e) {
      handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#loadAssessments',
        error: e,
        message: 'Could not load assessment history.',
        notifyMode: 'silent',
      });
    }
  };

  const loadCommHistory = async () => {
    try {
      const d = await apiFetch(`/api/relationship-coach/communication-tips/history${q()}`);
      setCommHistory(d.history || []);
    } catch (e) {
      handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#loadCommHistory',
        error: e,
        message: 'Could not load communication tips history.',
        notifyMode: 'silent',
      });
    }
  };

  const loadAnalytics = async () => {
    try {
      const d = await apiFetch(`/api/relationship-coach/analytics${q()}`);
      setAnalytics(d);
    } catch (e) {
      handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#loadAnalytics',
        error: e,
        message: 'Could not load analytics.',
        notifyMode: 'silent',
      });
    }
  };

  const loadUpcoming = async () => {
    try {
      const d = await apiFetch(`/api/relationship-coach/upcoming-reminders${q()}`);
      setUpcomingDates(d.upcoming_dates || []);
    } catch (e) {
      handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#loadUpcoming',
        error: e,
        message: 'Could not load upcoming reminders.',
        notifyMode: 'silent',
      });
    }
  };

  // ── Actions ─────────────────────────────────────────────────────────────────

  const getAdvice = async () => {
    if (!adviceForm.situation.trim()) { Alert.alert("Please describe your situation"); return; }
    setAdviceLoading(true); setAdviceResult("");
    try {
      const d = await apiFetch(`/api/relationship-coach/advice${q()}`, {
        method: "POST",
        body: JSON.stringify({ ...adviceForm, fallback_user_id: FALLBACK_ID }),
      });
      setAdviceResult(d.advice || "");
      await init();
    } catch (e: any) {
      if (e.message?.includes("limit")) Alert.alert("Tier Limit Reached", "Upgrade to get more AI sessions.");
      else handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#getAdvice',
        error: e,
        message: 'Advice generation failed',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void getAdvice(); },
      });
    } finally { setAdviceLoading(false); }
  };

  const generateDateIdeas = async () => {
    setDateIdeaLoading(true); setDateIdeasResult("");
    try {
      const d = await apiFetch(`/api/relationship-coach/date-ideas${q()}`, {
        method: "POST",
        body: JSON.stringify({
          ...dateIdeasForm,
          preferences: dateIdeasForm.preferences.split(",").map(s => s.trim()).filter(Boolean),
          fallback_user_id: FALLBACK_ID,
        }),
      });
      setDateIdeasResult(d.date_ideas || "");
      loadDateIdeasHistory();
    } catch (e: any) {
      if (e.message?.includes("limit")) Alert.alert("Tier Limit Reached", "Upgrade for more date ideas.");
      else handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#generateDateIdeas',
        error: e,
        message: 'Date idea generation failed',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void generateDateIdeas(); },
      });
    } finally { setDateIdeaLoading(false); }
  };

  const generateGiftIdeas = async () => {
    if (!giftForm.occasion.trim()) { Alert.alert("Please enter an occasion"); return; }
    setGiftLoading(true); setGiftResult("");
    try {
      const d = await apiFetch(`/api/relationship-coach/gift-ideas${q()}`, {
        method: "POST",
        body: JSON.stringify({
          ...giftForm,
          partner_interests: giftForm.partner_interests.split(",").map(s => s.trim()).filter(Boolean),
          fallback_user_id: FALLBACK_ID,
        }),
      });
      setGiftResult(d.gift_ideas || "");
      loadGiftHistory();
    } catch (e: any) {
      if (e.message?.includes("limit")) Alert.alert("Tier Limit Reached", "Upgrade for more gift searches.");
      else handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#generateGiftIdeas',
        error: e,
        message: 'Gift idea generation failed',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void generateGiftIdeas(); },
      });
    } finally { setGiftLoading(false); }
  };

  const generateConversationStarters = async () => {
    setConvLoading(true); setConvResult("");
    try {
      const d = await apiFetch(`/api/relationship-coach/conversation-starters${q()}`, {
        method: "POST",
        body: JSON.stringify({ ...convForm, fallback_user_id: FALLBACK_ID }),
      });
      setConvResult(d.conversation_starters || "");
    } catch (e: any) {
      if (e.message?.includes("limit")) Alert.alert("Tier Limit Reached", "Upgrade for more starters.");
      else handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#generateConversationStarters',
        error: e,
        message: 'Conversation starters failed',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void generateConversationStarters(); },
      });
    } finally { setConvLoading(false); }
  };

  const getCommTips = async () => {
    if (!commForm.scenario.trim()) { Alert.alert("Please describe the scenario"); return; }
    setCommLoading(true); setCommResult("");
    try {
      const d = await apiFetch(`/api/relationship-coach/communication-tips${q()}`, {
        method: "POST",
        body: JSON.stringify({ ...commForm, fallback_user_id: FALLBACK_ID }),
      });
      setCommResult(d.tips || "");
      loadCommHistory();
    } catch (e: any) {
      if (e.message?.includes("limit")) Alert.alert("Tier Limit Reached", "Upgrade for more coaching.");
      else handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#getCommTips',
        error: e,
        message: 'Communication tips failed',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void getCommTips(); },
      });
    } finally { setCommLoading(false); }
  };

  const submitAssessment = async () => {
    setAssessLoading(true); setAssessResult(null);
    try {
      const d = await apiFetch(`/api/relationship-coach/assessment${q()}`, {
        method: "POST",
        body: JSON.stringify({
          communication_score: parseInt(assessForm.communication_score),
          trust_score: parseInt(assessForm.trust_score),
          intimacy_score: parseInt(assessForm.intimacy_score),
          conflict_resolution_score: parseInt(assessForm.conflict_resolution_score),
          shared_goals_score: parseInt(assessForm.shared_goals_score),
          notes: assessForm.notes,
          fallback_user_id: FALLBACK_ID,
        }),
      });
      setAssessResult(d);
      await init();
    } catch (e: any) {
      if (e.message?.includes("limit")) Alert.alert("Assessment Limit", "You've reached your monthly assessment limit.");
      else handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#submitAssessment',
        error: e,
        message: 'Assessment failed',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void submitAssessment(); },
      });
    } finally { setAssessLoading(false); }
  };

  const addImportantDate = async () => {
    if (!importantDateForm.title.trim() || !importantDateForm.date.trim()) {
      Alert.alert("Please enter title and date");
      return;
    }
    try {
      if (editingDate) {
        await apiFetch(`/api/relationship-coach/important-dates/${editingDate.date_id}${q()}`, {
          method: "PUT",
          body: JSON.stringify({ ...importantDateForm, reminder_days: parseInt(importantDateForm.reminder_days), fallback_user_id: FALLBACK_ID }),
        });
        Alert.alert("Updated!");
      } else {
        await apiFetch(`/api/relationship-coach/important-dates${q()}`, {
          method: "POST",
          body: JSON.stringify({ ...importantDateForm, reminder_days: parseInt(importantDateForm.reminder_days), fallback_user_id: FALLBACK_ID }),
        });
        Alert.alert("Date added!");
      }
      setImportantDateForm({ title: "", date: "", category: "anniversary", reminder_days: "7", notes: "" });
      setShowImportantDateForm(false);
      setEditingDate(null);
      loadImportantDates();
      await init();
    } catch (e: any) {
      if (e.message?.includes("limit")) Alert.alert("Limit Reached", "Upgrade to track more important dates.");
      else handleAppRecoverableError({
        scope: 'features/ai-found-love.tsx#addImportantDate',
        error: e,
        message: 'Failed to save date',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void addImportantDate(); },
      });
    }
  };

  const deleteImportantDate = async (dateId: string) => {
    Alert.alert("Delete", "Remove this date?", [
      { text: "Cancel" },
      {
        text: "Delete", style: "destructive", onPress: async () => {
          try {
            await apiFetch(`/api/relationship-coach/important-dates/${dateId}${q()}`, { method: "DELETE" });
            loadImportantDates();
            await init();
          } catch (e) {
            handleAppRecoverableError({
              scope: 'features/ai-found-love.tsx#deleteImportantDate',
              error: e,
              message: 'Delete failed',
              notifyMode: 'dialog',
              userInitiated: true,
              onRetry: () => { void deleteImportantDate(dateId); },
            });
          }
        },
      },
    ]);
  };

  // ── Renders ──────────────────────────────────────────────────────────────────

  const renderKPI = () => (
    <View testID="rc-kpi-strip" style={[S.kpiWrap, { backgroundColor: colors.card }]}>
      {[
        { icon: "chatbubble-ellipses" as const, value: bootstrap?.usage.ai_sessions_this_month ?? 0, label: "AI Sessions", color: colors.info },
        { icon: "calendar" as const, value: bootstrap?.usage.important_dates ?? 0, label: "Dates Tracked", color: colors.warning },
        { icon: "notifications" as const, value: upcomingDates.length, label: "Upcoming", color: colors.primary },
        { icon: "heart" as const, value: bootstrap?.tier ?? "free", label: "Plan", color: colors.error },
      ].map((k, i) => (
        <View key={i} style={S.kpiCard}>
          <Ionicons name={k.icon} size={22} color={k.color} />
          <Text style={[S.kpiVal, { color: colors.text }]}>{k.value}</Text>
          <Text style={[S.kpiLbl, { color: colors.textSecondary }]}>{k.label}</Text>
        </View>
      ))}
    </View>
  );

  const renderTabBar = () => (
    <View style={[S.tabBar, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        {TABS.map(t => (
          <TouchableOpacity
            key={t.key}
            testID={`rc-tab-${t.key}`}
            style={[S.tab, activeTab === t.key && { borderBottomColor: colors.primary, borderBottomWidth: 2 }]}
            onPress={() => setActiveTab(t.key)}
          >
            <Ionicons name={t.icon as any} size={18} color={activeTab === t.key ? colors.primary : colors.textSecondary} />
            <Text style={[S.tabLbl, { color: activeTab === t.key ? colors.primary : colors.textSecondary }]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );

  // Tab 1: Dashboard
  const renderDashboard = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-dashboard">
      <Text style={[S.sectionTitle, { color: colors.text }]}>Welcome to Relationship Coach</Text>
      <Text style={[S.bodyText, { color: colors.textSecondary }]}>
        {bootstrap?.profile_exists
          ? "Your workspace is active. Use the tabs above to navigate all features."
          : "Set up your profile to personalise your coaching experience."}
      </Text>

      {upcomingDates.length > 0 && (
        <View style={{ marginTop: 16 }}>
          <Text style={[S.subsectionTitle, { color: colors.text }]}>Upcoming Reminders</Text>
          {upcomingDates.slice(0, 3).map(d => {
            const daysLeft = Math.ceil((new Date(d.date).getTime() - Date.now()) / 86400000);
            return (
              <View key={d.date_id} style={[S.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
                <View style={S.row}>
                  <Ionicons name="alarm" size={18} color={colors.warning} />
                  <Text style={[S.cardTitle, { color: colors.text, flex: 1, marginLeft: 8 }]}>{d.title}</Text>
                  <View style={[S.chip, { backgroundColor: daysLeft <= 7 ? colors.error : colors.primary }]}> 
                    <Text style={S.chipText}>{daysLeft}d</Text>
                  </View>
                </View>
                <Text style={[S.smallText, { color: colors.textSecondary, marginTop: 4 }]}>{d.date} · {d.category}</Text>
              </View>
            );
          })}
        </View>
      )}

      <View style={{ marginTop: 20 }}>
        <Text style={[S.subsectionTitle, { color: colors.text }]}>Quick Actions</Text>
        {[
          { label: "Get AI Relationship Advice", tab: "advisor" as TabKey, icon: "chatbubble-ellipses", color: colors.info },
          { label: "Generate Date Ideas", tab: "date-ideas" as TabKey, icon: "star", color: colors.warning },
          { label: "Find Gift Ideas", tab: "gift-finder" as TabKey, icon: "gift", color: colors.success },
          { label: "Add Important Date", tab: "important-dates" as TabKey, icon: "calendar", color: colors.primary },
          { label: "Take Health Assessment", tab: "assessment" as TabKey, icon: "fitness", color: colors.primary },
        ].map((q, i) => (
          <TouchableOpacity
            key={i}
            testID={`rc-quick-${q.tab}`}
            style={[S.quickAction, { backgroundColor: colors.card, borderColor: colors.border }]}
            onPress={() => setActiveTab(q.tab)}
          >
            <Ionicons name={q.icon as any} size={20} color={q.color} />
            <Text style={[S.quickActionText, { color: colors.text }]}>{q.label}</Text>
            <Ionicons name="chevron-forward" size={16} color={colors.textSecondary} />
          </TouchableOpacity>
        ))}
      </View>
    </ScrollView>
  );

  // Tab 2: AI Advisor
  const renderAdvisor = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-advisor">
      <Text style={[S.sectionTitle, { color: colors.text }]}>AI Relationship Advisor</Text>
      <Text style={[S.bodyText, { color: colors.textSecondary }]}>Describe your situation for empathetic, actionable guidance.</Text>

      <TextInput
        testID="rc-advice-situation"
        style={[S.textarea, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]}
        placeholder="Describe your situation or concern..."
        placeholderTextColor={colors.textSecondary}
        multiline
        numberOfLines={4}
        value={adviceForm.situation}
        onChangeText={t => setAdviceForm(p => ({ ...p, situation: t }))}
      />

      <TextInput
        testID="rc-advice-context"
        style={[S.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]}
        placeholder="Additional context (optional)"
        placeholderTextColor={colors.textSecondary}
        value={adviceForm.context}
        onChangeText={t => setAdviceForm(p => ({ ...p, context: t }))}
      />

      <Text style={[S.label, { color: colors.textSecondary }]}>Relationship Stage</Text>
      <View style={S.chipRow}>
        {["dating", "committed", "married", "long-distance", "complicated"].map(s => (
          <TouchableOpacity
            key={s}
            testID={`rc-stage-${s}`}
            style={[S.chip, { backgroundColor: adviceForm.relationship_stage === s ? colors.primary : colors.card, borderColor: colors.border, borderWidth: 1 }]}
            onPress={() => setAdviceForm(p => ({ ...p, relationship_stage: s }))}
          >
            <Text style={[S.chipText, { color: adviceForm.relationship_stage === s ? colors.primaryText : colors.text }]}>{s}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity
        testID="rc-advice-submit"
        style={[S.aiBtn, { backgroundColor: colors.primary }]}
        onPress={getAdvice}
        disabled={adviceLoading}
      >
        {adviceLoading ? <ActivityIndicator color={colors.primaryText} /> : <>
          <Ionicons name="sparkles" size={18} color={colors.primaryText} />
          <Text style={S.aiBtnText}>Get AI Advice</Text>
        </>}
      </TouchableOpacity>

      {adviceResult ? (
        <View style={[S.resultCard, { backgroundColor: colors.card, borderColor: colors.border }]} testID="rc-advice-result">
          <Text style={[S.resultText, { color: colors.text }]}>{adviceResult}</Text>
        </View>
      ) : null}
    </ScrollView>
  );

  // Tab 3: Date Ideas
  const renderDateIdeas = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-date-ideas">
      <Text style={[S.sectionTitle, { color: colors.text }]}>Date Ideas Generator</Text>

      <Text style={[S.label, { color: colors.textSecondary }]}>Budget</Text>
      <View style={S.chipRow}>
        {["budget-friendly", "moderate", "splurge"].map(b => (
          <TouchableOpacity key={b} testID={`rc-budget-${b}`} style={[S.chip, { backgroundColor: dateIdeasForm.budget === b ? colors.primary : colors.card, borderColor: colors.border, borderWidth: 1 }]} onPress={() => setDateIdeasForm(p => ({ ...p, budget: b }))}>
            <Text style={[S.chipText, { color: dateIdeasForm.budget === b ? colors.primaryText : colors.text }]}>{b}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={[S.label, { color: colors.textSecondary }]}>Mood</Text>
      <View style={S.chipRow}>
        {["romantic", "adventurous", "relaxed", "fun", "cultural"].map(m => (
          <TouchableOpacity key={m} testID={`rc-mood-${m}`} style={[S.chip, { backgroundColor: dateIdeasForm.mood === m ? colors.primary : colors.card, borderColor: colors.border, borderWidth: 1 }]} onPress={() => setDateIdeasForm(p => ({ ...p, mood: m }))}>
            <Text style={[S.chipText, { color: dateIdeasForm.mood === m ? colors.primaryText : colors.text }]}>{m}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TextInput testID="rc-dateideas-prefs" style={[S.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]} placeholder="Preferences (comma-separated, optional)" placeholderTextColor={colors.textSecondary} value={dateIdeasForm.preferences} onChangeText={t => setDateIdeasForm(p => ({ ...p, preferences: t }))} />
      <TextInput testID="rc-dateideas-location" style={[S.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]} placeholder="Location (optional)" placeholderTextColor={colors.textSecondary} value={dateIdeasForm.location} onChangeText={t => setDateIdeasForm(p => ({ ...p, location: t }))} />

      <TouchableOpacity testID="rc-dateideas-submit" style={[S.aiBtn, { backgroundColor: colors.warning }]} onPress={generateDateIdeas} disabled={dateIdeaLoading}>
        {dateIdeaLoading ? <ActivityIndicator color={colors.primaryText} /> : <><Ionicons name="star" size={18} color={colors.primaryText} /><Text style={S.aiBtnText}>Generate Date Ideas</Text></>}
      </TouchableOpacity>

      {dateIdeasResult ? (
        <View style={[S.resultCard, { backgroundColor: colors.card, borderColor: colors.border }]} testID="rc-dateideas-result">
          <Text style={[S.resultText, { color: colors.text }]}>{dateIdeasResult}</Text>
        </View>
      ) : null}

      {dateIdeasHistory.length > 0 && (
        <View style={{ marginTop: 24 }}>
          <Text style={[S.subsectionTitle, { color: colors.text }]}>Past Date Ideas</Text>
          {dateIdeasHistory.map(d => (
            <View key={d.idea_id} style={[S.histCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[S.smallText, { color: colors.textSecondary }]}>{new Date(d.created_at).toLocaleDateString()}</Text>
              <Text style={[S.bodyText, { color: colors.text }]} numberOfLines={3}>{d.ideas}</Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );

  // Tab 4: Gift Finder
  const renderGiftFinder = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-gift-finder">
      <Text style={[S.sectionTitle, { color: colors.text }]}>Gift Finder</Text>

      <TextInput testID="rc-gift-occasion" style={[S.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]} placeholder="Occasion (e.g. anniversary, birthday)" placeholderTextColor={colors.textSecondary} value={giftForm.occasion} onChangeText={t => setGiftForm(p => ({ ...p, occasion: t }))} />
      <TextInput testID="rc-gift-interests" style={[S.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]} placeholder="Partner's interests (comma-separated)" placeholderTextColor={colors.textSecondary} value={giftForm.partner_interests} onChangeText={t => setGiftForm(p => ({ ...p, partner_interests: t }))} />
      <TextInput testID="rc-gift-personality" style={[S.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]} placeholder="Personality traits (optional)" placeholderTextColor={colors.textSecondary} value={giftForm.personality} onChangeText={t => setGiftForm(p => ({ ...p, personality: t }))} />

      <Text style={[S.label, { color: colors.textSecondary }]}>Budget Range</Text>
      <View style={S.chipRow}>
        {["budget-friendly", "moderate", "premium", "luxury"].map(b => (
          <TouchableOpacity key={b} testID={`rc-gift-budget-${b}`} style={[S.chip, { backgroundColor: giftForm.budget === b ? colors.success : colors.card, borderColor: colors.border, borderWidth: 1 }]} onPress={() => setGiftForm(p => ({ ...p, budget: b }))}>
            <Text style={[S.chipText, { color: giftForm.budget === b ? colors.primaryText : colors.text }]}>{b}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity testID="rc-gift-submit" style={[S.aiBtn, { backgroundColor: colors.success }]} onPress={generateGiftIdeas} disabled={giftLoading}>
        {giftLoading ? <ActivityIndicator color={colors.primaryText} /> : <><Ionicons name="gift" size={18} color={colors.primaryText} /><Text style={S.aiBtnText}>Find Gift Ideas</Text></>}
      </TouchableOpacity>

      {giftResult ? (
        <View style={[S.resultCard, { backgroundColor: colors.card, borderColor: colors.border }]} testID="rc-gift-result">
          <Text style={[S.resultText, { color: colors.text }]}>{giftResult}</Text>
        </View>
      ) : null}

      {giftHistory.length > 0 && (
        <View style={{ marginTop: 24 }}>
          <Text style={[S.subsectionTitle, { color: colors.text }]}>Past Gift Searches</Text>
          {giftHistory.map(g => (
            <View key={g.gift_id} style={[S.histCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <View style={S.row}>
                <Text style={[S.cardTitle, { color: colors.text, flex: 1 }]}>{g.occasion}</Text>
                <Text style={[S.smallText, { color: colors.textSecondary }]}>{new Date(g.created_at).toLocaleDateString()}</Text>
              </View>
              <Text style={[S.bodyText, { color: colors.text }]} numberOfLines={3}>{g.recommendations}</Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );

  // Tab 5: Important Dates
  const renderImportantDates = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-important-dates">
      <View style={S.sectionHeader}>
        <Text style={[S.sectionTitle, { color: colors.text }]}>Important Dates</Text>
        <TouchableOpacity testID="rc-add-date-btn" style={[S.addBtn, { backgroundColor: colors.primary }]} onPress={() => { setEditingDate(null); setShowImportantDateForm(true); }}>
          <Ionicons name="add" size={18} color={colors.primaryText} />
          <Text style={S.addBtnText}>Add Date</Text>
        </TouchableOpacity>
      </View>

      {importantDates.length === 0 ? (
        <View style={S.empty}>
          <Ionicons name="calendar-outline" size={56} color={colors.textSecondary} />
          <Text style={[S.emptyText, { color: colors.textSecondary }]}>No important dates yet. Add anniversaries, birthdays, and milestones.</Text>
        </View>
      ) : importantDates.map(d => (
        <View key={d.date_id} testID={`rc-date-item-${d.date_id}`} style={[S.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <View style={S.row}>
            <View style={[S.catBadge, { backgroundColor: getCatColor(d.category) }]}>
              <Text style={S.chipText}>{d.category}</Text>
            </View>
            <Text style={[S.cardTitle, { color: colors.text, flex: 1, marginLeft: 8 }]}>{d.title}</Text>
            <TouchableOpacity testID={`rc-edit-date-${d.date_id}`} onPress={() => { setEditingDate(d); setImportantDateForm({ title: d.title, date: d.date, category: d.category, reminder_days: String(d.reminder_days), notes: d.notes || "" }); setShowImportantDateForm(true); }}>
              <Ionicons name="pencil" size={18} color={colors.primary} />
            </TouchableOpacity>
            <TouchableOpacity testID={`rc-delete-date-${d.date_id}`} onPress={() => deleteImportantDate(d.date_id)} style={{ marginLeft: 12 }}>
              <Ionicons name="trash" size={18} color={colors.error} />
            </TouchableOpacity>
          </View>
          <Text style={[S.bodyText, { color: colors.textSecondary, marginTop: 6 }]}>{d.date} · Remind {d.reminder_days}d before</Text>
          {d.notes ? <Text style={[S.smallText, { color: colors.textSecondary, marginTop: 4 }]}>{d.notes}</Text> : null}
        </View>
      ))}

      {showImportantDateForm && (
        <View style={[S.modalOverlay, { backgroundColor: "rgba(0,0,0,0.5)" }]}>
          <View style={[S.modal, { backgroundColor: colors.card }]}>
            <Text style={[S.modalTitle, { color: colors.text }]}>{editingDate ? "Edit Date" : "Add Important Date"}</Text>
            <TextInput testID="rc-date-title" style={[S.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]} placeholder="Title (e.g. Our Anniversary)" placeholderTextColor={colors.textSecondary} value={importantDateForm.title} onChangeText={t => setImportantDateForm(p => ({ ...p, title: t }))} />
            <TextInput testID="rc-date-date" style={[S.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]} placeholder="Date (YYYY-MM-DD)" placeholderTextColor={colors.textSecondary} value={importantDateForm.date} onChangeText={t => setImportantDateForm(p => ({ ...p, date: t }))} />
            <TextInput testID="rc-date-reminder" style={[S.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]} placeholder="Remind X days before" keyboardType="number-pad" placeholderTextColor={colors.textSecondary} value={importantDateForm.reminder_days} onChangeText={t => setImportantDateForm(p => ({ ...p, reminder_days: t }))} />
            <TextInput testID="rc-date-notes" style={[S.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]} placeholder="Notes (optional)" placeholderTextColor={colors.textSecondary} value={importantDateForm.notes} onChangeText={t => setImportantDateForm(p => ({ ...p, notes: t }))} />

            <Text style={[S.label, { color: colors.textSecondary }]}>Category</Text>
            <View style={S.chipRow}>
              {["anniversary", "birthday", "milestone", "holiday", "other"].map(c => (
                <TouchableOpacity key={c} testID={`rc-cat-${c}`} style={[S.chip, { backgroundColor: importantDateForm.category === c ? colors.primary : colors.background, borderColor: colors.border, borderWidth: 1 }]} onPress={() => setImportantDateForm(p => ({ ...p, category: c }))}>
                  <Text style={[S.chipText, { color: importantDateForm.category === c ? colors.primaryText : colors.text }]}>{c}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <View style={S.modalActions}>
              <TouchableOpacity testID="rc-date-cancel" style={[S.modalBtn, { backgroundColor: colors.border }]} onPress={() => { setShowImportantDateForm(false); setEditingDate(null); }}>
                <Text style={[S.modalBtnText, { color: colors.text }]}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="rc-date-save" style={[S.modalBtn, { backgroundColor: colors.primary }]} onPress={addImportantDate}>
                <Text style={S.modalBtnText}>{editingDate ? "Update" : "Add"}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}
    </ScrollView>
  );

  // Tab 6: Reminders
  const renderReminders = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-reminders">
      <Text style={[S.sectionTitle, { color: colors.text }]}>Upcoming Reminders</Text>
      <Text style={[S.bodyText, { color: colors.textSecondary }]}>Important dates in the next 30 days.</Text>

      {upcomingDates.length === 0 ? (
        <View style={S.empty}>
          <Ionicons name="notifications-outline" size={56} color={colors.textSecondary} />
          <Text style={[S.emptyText, { color: colors.textSecondary }]}>No upcoming dates in the next 30 days.</Text>
        </View>
      ) : upcomingDates.map(d => {
        const daysLeft = Math.ceil((new Date(d.date).getTime() - Date.now()) / 86400000);
        return (
          <View key={d.date_id} testID={`rc-reminder-${d.date_id}`} style={[S.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <View style={S.row}>
              <Ionicons name="alarm" size={20} color={daysLeft <= 3 ? colors.error : daysLeft <= 7 ? colors.warning : colors.primary} />
              <Text style={[S.cardTitle, { color: colors.text, flex: 1, marginLeft: 8 }]}>{d.title}</Text>
              <View style={[S.chip, { backgroundColor: daysLeft <= 3 ? colors.error : daysLeft <= 7 ? colors.warning : colors.primary }]}> 
                <Text style={S.chipText}>{daysLeft === 0 ? "Today!" : `${daysLeft}d`}</Text>
              </View>
            </View>
            <Text style={[S.smallText, { color: colors.textSecondary, marginTop: 6 }]}>{d.date} · {d.category}</Text>
          </View>
        );
      })}
    </ScrollView>
  );

  // Tab 7: Conversation Lab
  const renderConvLab = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-conv-lab">
      <Text style={[S.sectionTitle, { color: colors.text }]}>Conversation Lab</Text>
      <Text style={[S.bodyText, { color: colors.textSecondary }]}>Generate meaningful conversation starters tailored to your relationship.</Text>

      <Text style={[S.label, { color: colors.textSecondary }]}>Relationship Stage</Text>
      <View style={S.chipRow}>
        {["dating", "committed", "married", "long-distance"].map(s => (
          <TouchableOpacity key={s} testID={`rc-conv-stage-${s}`} style={[S.chip, { backgroundColor: convForm.relationship_stage === s ? colors.primary : colors.card, borderColor: colors.border, borderWidth: 1 }]} onPress={() => setConvForm(p => ({ ...p, relationship_stage: s }))}>
            <Text style={[S.chipText, { color: convForm.relationship_stage === s ? colors.primaryText : colors.text }]}>{s}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={[S.label, { color: colors.textSecondary }]}>Current Mood</Text>
      <View style={S.chipRow}>
        {["neutral", "curious", "playful", "deep", "nostalgic"].map(m => (
          <TouchableOpacity key={m} testID={`rc-conv-mood-${m}`} style={[S.chip, { backgroundColor: convForm.mood === m ? colors.primary : colors.card, borderColor: colors.border, borderWidth: 1 }]} onPress={() => setConvForm(p => ({ ...p, mood: m }))}>
            <Text style={[S.chipText, { color: convForm.mood === m ? colors.primaryText : colors.text }]}>{m}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TextInput testID="rc-conv-topic" style={[S.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]} placeholder="Topic preference (optional)" placeholderTextColor={colors.textSecondary} value={convForm.topic_preference} onChangeText={t => setConvForm(p => ({ ...p, topic_preference: t }))} />

      <TouchableOpacity testID="rc-conv-submit" style={[S.aiBtn, { backgroundColor: colors.primary }]} onPress={generateConversationStarters} disabled={convLoading}>
        {convLoading ? <ActivityIndicator color={colors.primaryText} /> : <><Ionicons name="bulb" size={18} color={colors.primaryText} /><Text style={S.aiBtnText}>Generate Starters</Text></>}
      </TouchableOpacity>

      {convResult ? (
        <View style={[S.resultCard, { backgroundColor: colors.card, borderColor: colors.border }]} testID="rc-conv-result">
          <Text style={[S.resultText, { color: colors.text }]}>{convResult}</Text>
        </View>
      ) : null}
    </ScrollView>
  );

  // Tab 8: Communication Coach
  const renderCommCoach = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-comm-coach">
      <Text style={[S.sectionTitle, { color: colors.text }]}>Communication Coach</Text>
      <Text style={[S.bodyText, { color: colors.textSecondary }]}>Describe a communication challenge to get expert coaching.</Text>

      <TextInput testID="rc-comm-scenario" style={[S.textarea, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]} placeholder="Describe your communication challenge..." placeholderTextColor={colors.textSecondary} multiline numberOfLines={4} value={commForm.scenario} onChangeText={t => setCommForm(p => ({ ...p, scenario: t }))} />
      <TextInput testID="rc-comm-context" style={[S.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]} placeholder="Context (optional)" placeholderTextColor={colors.textSecondary} value={commForm.context} onChangeText={t => setCommForm(p => ({ ...p, context: t }))} />

      <TouchableOpacity testID="rc-comm-submit" style={[S.aiBtn, { backgroundColor: colors.primary }]} onPress={getCommTips} disabled={commLoading}>
        {commLoading ? <ActivityIndicator color={colors.primaryText} /> : <><Ionicons name="megaphone" size={18} color={colors.primaryText} /><Text style={S.aiBtnText}>Get Communication Tips</Text></>}
      </TouchableOpacity>

      {commResult ? (
        <View style={[S.resultCard, { backgroundColor: colors.card, borderColor: colors.border }]} testID="rc-comm-result">
          <Text style={[S.resultText, { color: colors.text }]}>{commResult}</Text>
        </View>
      ) : null}

      {commHistory.length > 0 && (
        <View style={{ marginTop: 24 }}>
          <Text style={[S.subsectionTitle, { color: colors.text }]}>Past Coaching Sessions</Text>
          {commHistory.map(c => (
            <View key={c.tip_id} style={[S.histCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[S.cardTitle, { color: colors.text }]}>{c.scenario}</Text>
              <Text style={[S.smallText, { color: colors.textSecondary }]}>{new Date(c.created_at).toLocaleDateString()}</Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );

  // Tab 9: Health Assessment
  const renderAssessment = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-assessment">
      <Text style={[S.sectionTitle, { color: colors.text }]}>Relationship Health Assessment</Text>
      <Text style={[S.bodyText, { color: colors.textSecondary }]}>Rate each dimension from 1 (low) to 10 (high).</Text>

      {[
        { key: "communication_score", label: "Communication", icon: "chatbubbles", color: colors.primary },
        { key: "trust_score", label: "Trust", icon: "shield-checkmark", color: colors.success },
        { key: "intimacy_score", label: "Intimacy", icon: "heart", color: colors.error },
        { key: "conflict_resolution_score", label: "Conflict Resolution", icon: "git-merge", color: colors.warning },
        { key: "shared_goals_score", label: "Shared Goals", icon: "flag", color: colors.primary },
      ].map(({ key, label, icon, color }) => (
        <View key={key} style={[S.assessRow, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <View style={S.row}>
            <Ionicons name={icon as any} size={20} color={color} />
            <Text style={[S.cardTitle, { color: colors.text, flex: 1, marginLeft: 8 }]}>{label}</Text>
            <Text style={[S.kpiVal, { color: color }]}>{(assessForm as any)[key]}/10</Text>
          </View>
          <View style={S.sliderRow}>
            {[1,2,3,4,5,6,7,8,9,10].map(v => (
              <TouchableOpacity
                key={v}
                testID={`rc-assess-${key}-${v}`}
                style={[S.scoreBtn, { backgroundColor: parseInt((assessForm as any)[key]) >= v ? color : colors.background, borderColor: colors.border }]}
                onPress={() => setAssessForm(p => ({ ...p, [key]: String(v) }))}
              >
                <Text style={[S.scoreBtnText, { color: parseInt((assessForm as any)[key]) >= v ? colors.primaryText : colors.textSecondary }]}>{v}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      ))}

      <TextInput testID="rc-assess-notes" style={[S.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border, marginTop: 12 }]} placeholder="Notes (optional)" placeholderTextColor={colors.textSecondary} value={assessForm.notes} onChangeText={t => setAssessForm(p => ({ ...p, notes: t }))} />

      <TouchableOpacity testID="rc-assess-submit" style={[S.aiBtn, { backgroundColor: colors.primary }]} onPress={submitAssessment} disabled={assessLoading}>
        {assessLoading ? <ActivityIndicator color={colors.primaryText} /> : <><Ionicons name="fitness" size={18} color={colors.primaryText} /><Text style={S.aiBtnText}>Submit Assessment</Text></>}
      </TouchableOpacity>

      {assessResult && (
        <View style={[S.resultCard, { backgroundColor: colors.card, borderColor: colors.border }]} testID="rc-assess-result">
          <Text style={[S.sectionTitle, { color: colors.primary }]}>Health Score: {assessResult.health_score}%</Text>
          {assessResult.strengths.length > 0 && (
            <>
              <Text style={[S.label, { color: colors.success, marginTop: 8 }]}>Strengths</Text>
              {assessResult.strengths.map(s => <Text key={s} style={[S.bodyText, { color: colors.text }]}>• {s}</Text>)}
            </>
          )}
          {assessResult.improvement_areas.length > 0 && (
            <>
              <Text style={[S.label, { color: colors.warning, marginTop: 8 }]}>Areas to Improve</Text>
              {assessResult.improvement_areas.map(a => <Text key={a} style={[S.bodyText, { color: colors.text }]}>• {a}</Text>)}
            </>
          )}
        </View>
      )}
    </ScrollView>
  );

  // Tab 10: Assessment History
  const renderAssessHistory = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-assess-history">
      <Text style={[S.sectionTitle, { color: colors.text }]}>Assessment History</Text>
      {assessments.length === 0 ? (
        <View style={S.empty}>
          <Ionicons name="bar-chart-outline" size={56} color={colors.textSecondary} />
          <Text style={[S.emptyText, { color: colors.textSecondary }]}>No assessments yet. Take your first assessment to track progress.</Text>
        </View>
      ) : assessments.map((a, i) => (
        <View key={a.assessment_id} testID={`rc-assess-hist-${a.assessment_id}`} style={[S.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <View style={S.row}>
            <Text style={[S.cardTitle, { color: colors.text, flex: 1 }]}>Assessment #{assessments.length - i}</Text>
            <View style={[S.chip, { backgroundColor: a.health_score >= 70 ? colors.success : a.health_score >= 50 ? colors.warning : colors.error }]}> 
              <Text style={S.chipText}>{a.health_score}%</Text>
            </View>
          </View>
          <Text style={[S.smallText, { color: colors.textSecondary, marginTop: 4 }]}>{new Date(a.created_at).toLocaleDateString()}</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {Object.entries(a.scores).map(([k, v]) => (
              <View key={k} style={[S.chip, { backgroundColor: colors.background, borderColor: colors.border, borderWidth: 1 }]}>
                <Text style={[S.chipText, { color: colors.text }]}>{k.replace("_", " ")}: {v}</Text>
              </View>
            ))}
          </View>
        </View>
      ))}
    </ScrollView>
  );

  // Tab 11: Session Journal
  const renderJournal = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-journal">
      <Text style={[S.sectionTitle, { color: colors.text }]}>Session Journal</Text>
      {sessions.length === 0 ? (
        <View style={S.empty}>
          <Ionicons name="book-outline" size={56} color={colors.textSecondary} />
          <Text style={[S.emptyText, { color: colors.textSecondary }]}>No advice sessions yet. Use the AI Advisor tab to get started.</Text>
        </View>
      ) : sessions.map((s, i) => (
        <View key={s.session_id} testID={`rc-journal-${s.session_id}`} style={[S.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <View style={S.row}>
            <View style={[S.chip, { backgroundColor: colors.info }]}> 
              <Text style={S.chipText}>#{sessions.length - i}</Text>
            </View>
            <Text style={[S.bodyText, { color: colors.text, flex: 1, marginLeft: 8 }]} numberOfLines={2}>{s.situation}</Text>
          </View>
          <Text style={[S.smallText, { color: colors.textSecondary, marginTop: 6 }]}>{new Date(s.created_at).toLocaleDateString()}</Text>
        </View>
      ))}
    </ScrollView>
  );

  // Tab 12: Analytics
  const renderAnalytics = () => (
    <ScrollView style={S.tabContent} testID="rc-tab-content-analytics">
      <Text style={[S.sectionTitle, { color: colors.text }]}>Analytics & Insights</Text>
      {!analytics ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 32 }} />
      ) : (
        <>
          <View style={[S.kpiWrap, { backgroundColor: colors.card }]}>
            {[
              { label: "AI Sessions", value: analytics.total_advice_sessions, icon: "chatbubble-ellipses", color: colors.info },
              { label: "Date Ideas", value: analytics.total_date_ideas_generated, icon: "star", color: colors.warning },
              { label: "Assessments", value: analytics.total_assessments, icon: "fitness", color: colors.primary },
              { label: "Dates Tracked", value: analytics.important_dates_tracked, icon: "calendar", color: colors.primary },
            ].map((k, i) => (
              <View key={i} style={S.kpiCard}>
                <Ionicons name={k.icon as any} size={22} color={k.color} />
                <Text style={[S.kpiVal, { color: colors.text }]}>{k.value}</Text>
                <Text style={[S.kpiLbl, { color: colors.textSecondary }]}>{k.label}</Text>
              </View>
            ))}
          </View>

          {analytics.latest_health_score !== null && (
            <View style={[S.card, { backgroundColor: colors.card, borderColor: colors.border, marginTop: 16, alignItems: "center" }]}>
              <Ionicons name="heart" size={32} color={colors.error} />
              <Text style={[S.sectionTitle, { color: colors.primary, marginTop: 8 }]}>{analytics.latest_health_score}%</Text>
              <Text style={[S.bodyText, { color: colors.textSecondary }]}>Latest Health Score</Text>
            </View>
          )}

          <View style={[S.card, { backgroundColor: colors.card, borderColor: colors.border, marginTop: 16 }]}>
            <Text style={[S.subsectionTitle, { color: colors.text }]}>Tier: {bootstrap?.tier?.toUpperCase()}</Text>
            {bootstrap && (
              <>
                <Text style={[S.bodyText, { color: colors.textSecondary }]}>AI Sessions this month: {bootstrap.usage.ai_sessions_this_month} / {bootstrap.limits.ai_sessions_per_month}</Text>
                <Text style={[S.bodyText, { color: colors.textSecondary }]}>Important dates: {bootstrap.usage.important_dates} / {bootstrap.limits.important_dates === -1 ? "Unlimited" : bootstrap.limits.important_dates}</Text>
                <Text style={[S.bodyText, { color: colors.textSecondary }]}>Assessments per month: {bootstrap.limits.assessments_per_month === -1 ? "Unlimited" : bootstrap.limits.assessments_per_month}</Text>
              </>
            )}
          </View>
        </>
      )}
    </ScrollView>
  );

  // ── Helpers ──────────────────────────────────────────────────────────────────

  const getCatColor = (cat: string) => {
    switch (cat) {
      case "anniversary": return colors.error;
      case "birthday": return colors.warning;
      case "milestone": return colors.primary;
      case "holiday": return colors.primary;
      default: return colors.textMuted;
    }
  };

  const renderTab = () => {
    switch (activeTab) {
      case "dashboard": return renderDashboard();
      case "advisor": return renderAdvisor();
      case "date-ideas": return renderDateIdeas();
      case "gift-finder": return renderGiftFinder();
      case "important-dates": return renderImportantDates();
      case "reminders": return renderReminders();
      case "conv-lab": return renderConvLab();
      case "comm-coach": return renderCommCoach();
      case "assessment": return renderAssessment();
      case "assess-history": return renderAssessHistory();
      case "journal": return renderJournal();
      case "analytics": return renderAnalytics();
    }
  };

  // ── Loading screen ────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <SafeAreaView style={[S.container, { backgroundColor: colors.background }]}>
        <View style={S.loadingWrap}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[S.bodyText, { color: colors.textSecondary, marginTop: 12 }]}>Loading Relationship Coach…</Text>
        </View>
      </SafeAreaView>
    );
  }

  // ── Main render ───────────────────────────────────────────────────────────────

  return (
    <SafeAreaView testID="rc-workspace" style={[S.container, { backgroundColor: colors.background }]}>
      {/* Header */}
      <View style={[S.header, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
        <Ionicons name="heart" size={28} color={colors.error} />
        <View style={{ marginLeft: 12 }}>
          <Text style={[S.headerTitle, { color: colors.text }]}>Relationship Coach</Text>
          <Text style={[S.headerSub, { color: colors.textSecondary }]}>AI-powered relationship support · {bootstrap?.tier} plan</Text>
        </View>
      </View>

      {renderKPI()}
      {renderTabBar()}

      <View style={{ flex: 1 }}>
        {renderTab()}
      </View>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const S = StyleSheet.create({
  container: { flex: 1 },
  loadingWrap: { flex: 1, justifyContent: "center", alignItems: "center" },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1 },
  headerTitle: { fontSize: 18, fontWeight: "700" },
  headerSub: { fontSize: 12, marginTop: 2 },
  kpiWrap: { flexDirection: "row", paddingVertical: 12, paddingHorizontal: 8, marginHorizontal: 12, marginTop: 12, borderRadius: 12 },
  kpiCard: { flex: 1, alignItems: "center" },
  kpiVal: { fontSize: 20, fontWeight: "700", marginTop: 4 },
  kpiLbl: { fontSize: 10, marginTop: 2, textAlign: "center" },
  tabBar: { borderBottomWidth: 1, marginTop: 8 },
  tab: { flexDirection: "row", alignItems: "center", paddingHorizontal: 14, paddingVertical: 10, gap: 6 },
  tabLbl: { fontSize: 12, fontWeight: "500" },
  tabContent: { flex: 1, padding: 16 },
  sectionTitle: { fontSize: 20, fontWeight: "700", marginBottom: 8 },
  subsectionTitle: { fontSize: 16, fontWeight: "600", marginBottom: 10 },
  bodyText: { fontSize: 14, lineHeight: 20, marginBottom: 4 },
  smallText: { fontSize: 12 },
  label: { fontSize: 12, fontWeight: "600", marginBottom: 6, marginTop: 10 },
  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 },
  addBtn: { flexDirection: "row", alignItems: "center", paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, gap: 6 },
  addBtnText: { color: "var(--app-primary-text)", fontSize: 14, fontWeight: "600" },
  row: { flexDirection: "row", alignItems: "center" },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 8 },
  chip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20 },
  chipText: { color: "var(--app-primary-text)", fontSize: 11, fontWeight: "600" },
  catBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  card: { padding: 14, borderRadius: 12, borderWidth: 1, marginBottom: 10 },
  cardTitle: { fontSize: 15, fontWeight: "600" },
  histCard: { padding: 12, borderRadius: 10, borderWidth: 1, marginBottom: 8 },
  input: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, marginBottom: 10 },
  textarea: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, marginBottom: 10, minHeight: 90, textAlignVertical: "top" },
  aiBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", paddingVertical: 14, borderRadius: 10, gap: 8, marginTop: 4, marginBottom: 8 },
  aiBtnText: { color: "var(--app-primary-text)", fontSize: 15, fontWeight: "700" },
  resultCard: { marginTop: 12, padding: 16, borderRadius: 12, borderWidth: 1 },
  resultText: { fontSize: 14, lineHeight: 22 },
  empty: { alignItems: "center", paddingVertical: 48 },
  emptyText: { marginTop: 12, fontSize: 14, textAlign: "center", paddingHorizontal: 24 },
  quickAction: { flexDirection: "row", alignItems: "center", padding: 14, borderRadius: 10, borderWidth: 1, marginBottom: 8, gap: 12 },
  quickActionText: { flex: 1, fontSize: 14, fontWeight: "500" },
  modalOverlay: { position: "absolute", top: 0, left: -16, right: -16, bottom: 0, justifyContent: "center", alignItems: "center", zIndex: 100 },
  modal: { width: "90%", maxWidth: 420, padding: 20, borderRadius: 16, maxHeight: "85%" },
  modalTitle: { fontSize: 18, fontWeight: "700", marginBottom: 14 },
  modalActions: { flexDirection: "row", justifyContent: "flex-end", gap: 10, marginTop: 14 },
  modalBtn: { paddingHorizontal: 20, paddingVertical: 10, borderRadius: 8 },
  modalBtnText: { color: "var(--app-primary-text)", fontSize: 14, fontWeight: "600" },
  assessRow: { padding: 14, borderRadius: 12, borderWidth: 1, marginBottom: 10 },
  sliderRow: { flexDirection: "row", gap: 4, marginTop: 10, flexWrap: "wrap" },
  scoreBtn: { width: 28, height: 28, borderRadius: 6, borderWidth: 1, justifyContent: "center", alignItems: "center" },
  scoreBtnText: { fontSize: 11, fontWeight: "600" },
});
