/**
 * Feature 11: Travel Planner Pro - Enterprise Workspace
 * 
 * AI-powered travel planning platform with:
 * - Trip management (create, organize, track)
 * - Multi-day itinerary builder with activities
 * - Budget planning and expense tracking
 * - Travel checklist automation
 * - AI itinerary generation
 * - AI destination recommendations
 * - AI packing list generator
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
import { useTranslation } from "../../src/hooks/useTranslation";
import { handleAppRecoverableError } from "../../src/utils/appRecoverableError";
import api from "../../src/services/api";

const API_BASE = process.env.REACT_APP_BACKEND_URL || "";

interface Trip {
  id: string;
  user_id: string;
  name: string;
  destination: string;
  start_date: string;
  end_date: string;
  traveler_count: number;
  trip_type: string;
  status: string;
  budget_total?: number;
  currency: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

interface Activity {
  activity_id: string;
  time_slot: string;
  start_time?: string;
  end_time?: string;
  title: string;
  location?: string;
  description?: string;
  estimated_cost?: number;
  category: string;
  booking_status: string;
  notes?: string;
  created_at: string;
}

interface ItineraryDay {
  id: string;
  trip_id: string;
  day_number: number;
  date: string;
  title: string;
  activities: Activity[];
  created_at: string;
  updated_at: string;
}

interface Budget {
  id: string;
  trip_id: string;
  user_id: string;
  total_budget: number;
  currency: string;
  category_budgets: Record<string, number>;
  spent_total: number;
  remaining: number;
  created_at: string;
  updated_at: string;
}

interface Expense {
  id: string;
  trip_id: string;
  amount: number;
  currency: string;
  category: string;
  description: string;
  date: string;
  merchant?: string;
  created_at: string;
}

interface ChecklistItem {
  item_id: string;
  category: string;
  title: string;
  description?: string;
  completed: boolean;
  priority: string;
  due_date?: string;
  created_at: string;
}

interface Checklist {
  id: string;
  trip_id: string;
  user_id: string;
  items: ChecklistItem[];
  created_at: string;
  updated_at: string;
}

interface BootstrapData {
  user_id: string;
  tier: string;
  limits: {
    trips_max: number;
    activities_per_trip: number;
    budgets_max: number;
    checklist_items: number;
    ai_generations_per_month: number;
  };
  usage: {
    trips_count: number;
    budgets_count: number;
    ai_queries_this_month: number;
  };
  features_available: string[];
}

export default function TravelPlannerPro() {
  const { colors } = useTheme();
  const { t } = useTranslation();

  // Core state
  const [loading, setLoading] = useState(true);
  const [bootstrap, setBootstrap] = useState<BootstrapData | null>(null);
  const [activeTab, setActiveTab] = useState<
    "trips" | "itinerary" | "budget" | "ai" | "checklist"
  >("trips");

  // Trip state
  const [trips, setTrips] = useState<Trip[]>([]);
  const [selectedTrip, setSelectedTrip] = useState<Trip | null>(null);
  const [showTripForm, setShowTripForm] = useState(false);
  const [tripForm, setTripForm] = useState({
    name: "",
    destination: "",
    start_date: "",
    end_date: "",
    traveler_count: "1",
    trip_type: "vacation",
    budget_total: "",
  });

  // Itinerary state
  const [itinerary, setItinerary] = useState<ItineraryDay[]>([]);
  const [showDayForm, setShowDayForm] = useState(false);
  const [showActivityForm, setShowActivityForm] = useState(false);
  const [selectedDay, setSelectedDay] = useState<ItineraryDay | null>(null);
  const [dayForm, setDayForm] = useState({
    day_number: "",
    date: "",
    title: "",
  });
  const [activityForm, setActivityForm] = useState({
    time_slot: "morning",
    title: "",
    location: "",
    estimated_cost: "",
    category: "activity",
  });

  // Budget state
  const [budget, setBudget] = useState<Budget | null>(null);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [showBudgetForm, setShowBudgetForm] = useState(false);
  const [showExpenseForm, setShowExpenseForm] = useState(false);
  const [budgetForm, setBudgetForm] = useState({
    total_budget: "",
    currency: "USD",
  });
  const [expenseForm, setExpenseForm] = useState({
    amount: "",
    category: "food",
    description: "",
    merchant: "",
  });

  // Checklist state
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [showChecklistForm, setShowChecklistForm] = useState(false);
  const [checklistForm, setChecklistForm] = useState({
    category: "packing",
    title: "",
    priority: "medium",
  });

  // AI state
  const [aiMode, setAiMode] = useState<"itinerary" | "destination" | "packing">("itinerary");
  const [aiInput, setAiInput] = useState({
    destination: "",
    num_days: "",
    budget: "",
    interests: "",
  });
  const [aiResult, setAiResult] = useState<string>("");
  const [aiLoading, setAiLoading] = useState(false);

  const fallbackUserId = `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78);

  const apiRequest = useCallback(async (url: string, opts: any = {}) => {
    try {
      const target = String(url || "");
      const withoutOrigin = target.startsWith("http")
        ? target.replace(/^https?:\/\/[^/]+/i, "")
        : target;
      const [pathPart, queryString = ""] = withoutOrigin.split("?");
      const endpoint = pathPart.startsWith("/api/") ? pathPart.slice(4) : pathPart;
      const params = Object.fromEntries(new URLSearchParams(queryString).entries());
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

  // Initialize workspace
  useEffect(() => {
    initializeWorkspace();
  }, []);

  const initializeWorkspace = async () => {
    try {
      setLoading(true);
      
      const [bootstrapRes, tripsRes] = await Promise.all([
        apiRequest(`${API_BASE}/api/travel-planner-pro/bootstrap?fallback_user_id=${fallbackUserId}`),
        apiRequest(`${API_BASE}/api/travel-planner-pro/trips?fallback_user_id=${fallbackUserId}`),
      ]);

      if (bootstrapRes.ok) {
        const data = await bootstrapRes.json();
        setBootstrap(data);
      }

      if (tripsRes.ok) {
        const data = await tripsRes.json();
        setTrips(data.trips || []);
      }

    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/travelpal.tsx#initializeWorkspace',
        error,
        message: 'Failed to initialize Travel Planner Pro',
        notifyMode: 'silent',
      });
    } finally {
      setLoading(false);
    }
  };

  // Load trip details when selected
  useEffect(() => {
    if (selectedTrip) {
      loadTripDetails(selectedTrip.id);
    }
  }, [selectedTrip]);

  const loadTripDetails = async (tripId: string) => {
    try {
      const [itineraryRes, budgetRes, expensesRes, checklistRes] = await Promise.all([
        apiRequest(`${API_BASE}/api/travel-planner-pro/trips/${tripId}/itinerary?fallback_user_id=${fallbackUserId}`),
        apiRequest(`${API_BASE}/api/travel-planner-pro/trips/${tripId}/budget?fallback_user_id=${fallbackUserId}`),
        apiRequest(`${API_BASE}/api/travel-planner-pro/trips/${tripId}/expenses?fallback_user_id=${fallbackUserId}`),
        apiRequest(`${API_BASE}/api/travel-planner-pro/trips/${tripId}/checklist?fallback_user_id=${fallbackUserId}`),
      ]);

      if (itineraryRes.ok) {
        const data = await itineraryRes.json();
        setItinerary(data.itinerary || []);
      }

      if (budgetRes.ok) {
        const data = await budgetRes.json();
        setBudget(data.budget);
      }

      if (expensesRes.ok) {
        const data = await expensesRes.json();
        setExpenses(data.expenses || []);
      }

      if (checklistRes.ok) {
        const data = await checklistRes.json();
        setChecklist(data.checklist);
      }

    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/travelpal.tsx#loadTripDetails',
        error,
        message: 'Failed to load trip details',
        notifyMode: 'silent',
      });
    }
  };

  // Trip operations
  const createTrip = async () => {
    if (!tripForm.name.trim() || !tripForm.destination.trim()) {
      Alert.alert("Error", "Please enter trip name and destination");
      return;
    }

    try {
      const response = await apiRequest(`${API_BASE}/api/travel-planner-pro/trips?fallback_user_id=${fallbackUserId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: tripForm.name,
          destination: tripForm.destination,
          start_date: tripForm.start_date || new Date().toISOString().split("T")[0],
          end_date: tripForm.end_date || new Date().toISOString().split("T")[0],
          traveler_count: parseInt(tripForm.traveler_count) || 1,
          trip_type: tripForm.trip_type,
          budget_total: tripForm.budget_total ? parseFloat(tripForm.budget_total) : null,
          currency: "USD",
        }),
      });

      if (response.ok) {
        Alert.alert("Success", "Trip created!");
        setTripForm({
          name: "",
          destination: "",
          start_date: "",
          end_date: "",
          traveler_count: "1",
          trip_type: "vacation",
          budget_total: "",
        });
        setShowTripForm(false);
        
        // Refresh trips
        const tripsRes = await apiRequest(`${API_BASE}/api/travel-planner-pro/trips?fallback_user_id=${fallbackUserId}`);
        if (tripsRes.ok) {
          const data = await tripsRes.json();
          setTrips(data.trips || []);
        }
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "Failed to create trip");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/travelpal.tsx#createTrip',
        error,
        message: 'Failed to create trip',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void createTrip(); },
      });
    }
  };

  // Itinerary operations
  const createDay = async () => {
    if (!selectedTrip || !dayForm.title.trim()) {
      Alert.alert("Error", "Please enter day title");
      return;
    }

    try {
      const response = await apiRequest(
        `${API_BASE}/api/travel-planner-pro/trips/${selectedTrip.id}/itinerary?fallback_user_id=${fallbackUserId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            day_number: parseInt(dayForm.day_number) || (itinerary.length + 1),
            date: dayForm.date || new Date().toISOString().split("T")[0],
            title: dayForm.title,
            activities: [],
          }),
        }
      );

      if (response.ok) {
        Alert.alert("Success", "Day added to itinerary!");
        setDayForm({ day_number: "", date: "", title: "" });
        setShowDayForm(false);
        loadTripDetails(selectedTrip.id);
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "Failed to create day");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/travelpal.tsx#createDay',
        error,
        message: 'Failed to create day',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void createDay(); },
      });
    }
  };

  const addActivity = async () => {
    if (!selectedTrip || !selectedDay || !activityForm.title.trim()) {
      Alert.alert("Error", "Please enter activity title");
      return;
    }

    try {
      const response = await apiRequest(
        `${API_BASE}/api/travel-planner-pro/trips/${selectedTrip.id}/itinerary/${selectedDay.id}/activities?fallback_user_id=${fallbackUserId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            time_slot: activityForm.time_slot,
            title: activityForm.title,
            location: activityForm.location,
            estimated_cost: activityForm.estimated_cost ? parseFloat(activityForm.estimated_cost) : null,
            category: activityForm.category,
            booking_status: "planned",
          }),
        }
      );

      if (response.ok) {
        Alert.alert("Success", "Activity added!");
        setActivityForm({
          time_slot: "morning",
          title: "",
          location: "",
          estimated_cost: "",
          category: "activity",
        });
        setShowActivityForm(false);
        loadTripDetails(selectedTrip.id);
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "Failed to add activity");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/travelpal.tsx#addActivity',
        error,
        message: 'Failed to add activity',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void addActivity(); },
      });
    }
  };

  // Budget operations
  const createBudget = async () => {
    if (!selectedTrip || !budgetForm.total_budget) {
      Alert.alert("Error", "Please enter total budget");
      return;
    }

    try {
      const response = await apiRequest(
        `${API_BASE}/api/travel-planner-pro/trips/${selectedTrip.id}/budget?fallback_user_id=${fallbackUserId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            total_budget: parseFloat(budgetForm.total_budget),
            currency: budgetForm.currency,
          }),
        }
      );

      if (response.ok) {
        Alert.alert("Success", "Budget created!");
        setBudgetForm({ total_budget: "", currency: "USD" });
        setShowBudgetForm(false);
        loadTripDetails(selectedTrip.id);
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "Failed to create budget");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/travelpal.tsx#createBudget',
        error,
        message: 'Failed to create budget',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void createBudget(); },
      });
    }
  };

  const logExpense = async () => {
    if (!selectedTrip || !expenseForm.amount || !expenseForm.description.trim()) {
      Alert.alert("Error", "Please fill in all expense fields");
      return;
    }

    try {
      const response = await apiRequest(
        `${API_BASE}/api/travel-planner-pro/trips/${selectedTrip.id}/expenses?fallback_user_id=${fallbackUserId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            amount: parseFloat(expenseForm.amount),
            currency: "USD",
            category: expenseForm.category,
            description: expenseForm.description,
            merchant: expenseForm.merchant,
          }),
        }
      );

      if (response.ok) {
        Alert.alert("Success", "Expense logged!");
        setExpenseForm({
          amount: "",
          category: "food",
          description: "",
          merchant: "",
        });
        setShowExpenseForm(false);
        loadTripDetails(selectedTrip.id);
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "Failed to log expense");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/travelpal.tsx#logExpense',
        error,
        message: 'Failed to log expense',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void logExpense(); },
      });
    }
  };

  // Checklist operations
  const addChecklistItem = async () => {
    if (!selectedTrip || !checklistForm.title.trim()) {
      Alert.alert("Error", "Please enter item title");
      return;
    }

    try {
      const response = await apiRequest(
        `${API_BASE}/api/travel-planner-pro/trips/${selectedTrip.id}/checklist?fallback_user_id=${fallbackUserId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            items: [
              {
                category: checklistForm.category,
                title: checklistForm.title,
                priority: checklistForm.priority,
              },
            ],
          }),
        }
      );

      if (response.ok) {
        Alert.alert("Success", "Item added to checklist!");
        setChecklistForm({
          category: "packing",
          title: "",
          priority: "medium",
        });
        setShowChecklistForm(false);
        loadTripDetails(selectedTrip.id);
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "Failed to add item");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/travelpal.tsx#addChecklistItem',
        error,
        message: 'Failed to add item',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void addChecklistItem(); },
      });
    }
  };

  const toggleChecklistItem = async (itemId: string) => {
    if (!selectedTrip) return;

    try {
      await apiRequest(
        `${API_BASE}/api/travel-planner-pro/trips/${selectedTrip.id}/checklist/${itemId}?fallback_user_id=${fallbackUserId}`,
        { method: "PUT" }
      );
      loadTripDetails(selectedTrip.id);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/travelpal.tsx#toggleChecklistItem',
        error,
        message: 'Failed to toggle item',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void toggleChecklistItem(itemId); },
      });
    }
  };

  // AI operations
  const runAI = async () => {
    if (aiMode === "itinerary" && (!aiInput.destination.trim() || !aiInput.num_days)) {
      Alert.alert("Error", "Please enter destination and number of days");
      return;
    }

    setAiLoading(true);
    setAiResult("");

    try {
      let endpoint = "";
      let body: any = {};

      if (aiMode === "itinerary") {
        endpoint = "/api/travel-planner-pro/ai/generate-itinerary";
        body = {
          destination: aiInput.destination,
          num_days: parseInt(aiInput.num_days) || 7,
          traveler_count: 1,
          budget: aiInput.budget ? parseFloat(aiInput.budget) : null,
          interests: aiInput.interests ? aiInput.interests.split(",").map((s) => s.trim()) : [],
          trip_type: "vacation",
        };
      } else if (aiMode === "destination") {
        endpoint = "/api/travel-planner-pro/ai/destination-recommend";
        body = {
          budget: aiInput.budget ? parseFloat(aiInput.budget) : null,
          interests: aiInput.interests ? aiInput.interests.split(",").map((s) => s.trim()) : [],
        };
      } else if (aiMode === "packing") {
        endpoint = "/api/travel-planner-pro/ai/packing-list";
        body = {
          destination: aiInput.destination,
          num_days: parseInt(aiInput.num_days) || 7,
          season: "summer",
          activities: aiInput.interests ? aiInput.interests.split(",").map((s) => s.trim()) : [],
        };
      }

      const response = await apiRequest(`${API_BASE}${endpoint}?fallback_user_id=${fallbackUserId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (response.ok) {
        const data = await response.json();
        const result = data.itinerary || data.recommendations || data.packing_list || "No result";
        setAiResult(result);
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "AI query failed");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/travelpal.tsx#runAI',
        error,
        message: 'AI query failed',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void runAI(); },
      });
    } finally {
      setAiLoading(false);
    }
  };

  // Render functions
  const renderKPIDashboard = () => (
    <View style={[styles.kpiContainer, { backgroundColor: colors.card }]}>
      <View style={styles.kpiGrid}>
        <View style={styles.kpiCard}>
          <Ionicons name="airplane" size={24} color={colors.primary} />
          <Text style={[styles.kpiValue, { color: colors.text }]}>
            {trips.length}
          </Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>Trips</Text>
        </View>

        <View style={styles.kpiCard}>
          <Ionicons name="calendar" size={24} color={colors.accent} />
          <Text style={[styles.kpiValue, { color: colors.text }]}>
            {trips.filter((t) => t.status === "planning").length}
          </Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>Planning</Text>
        </View>

        <View style={styles.kpiCard}>
          <Ionicons name="cash" size={24} color={colors.success} />
          <Text style={[styles.kpiValue, { color: colors.text }]}>
            {budget ? `$${budget.remaining.toFixed(0)}` : "-"}
          </Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>Budget Left</Text>
        </View>

        <View style={styles.kpiCard}>
          <Ionicons name="sparkles" size={24} color={colors.primary} />
          <Text style={[styles.kpiValue, { color: colors.text }]}>
            {bootstrap?.usage.ai_queries_this_month || 0}
          </Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>AI Used</Text>
        </View>
      </View>
    </View>
  );

  const renderTabBar = () => (
    <View style={[styles.tabBar, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        {[
          { key: "trips", icon: "airplane", label: "My Trips" },
          { key: "itinerary", icon: "calendar", label: "Itinerary" },
          { key: "budget", icon: "wallet", label: "Budget" },
          { key: "ai", icon: "sparkles", label: "AI Planner" },
          { key: "checklist", icon: "checkmark-circle", label: "Checklist" },
        ].map((tab) => (
          <TouchableOpacity
            key={tab.key}
            style={[
              styles.tab,
              activeTab === tab.key && { borderBottomColor: colors.primary, borderBottomWidth: 2 },
            ]}
            onPress={() => setActiveTab(tab.key as any)}
          >
            <Ionicons
              name={tab.icon as any}
              size={20}
              color={activeTab === tab.key ? colors.primary : colors.textSecondary}
            />
            <Text
              style={[
                styles.tabLabel,
                {
                  color: activeTab === tab.key ? colors.primary : colors.textSecondary,
                },
              ]}
            >
              {tab.label}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );

  const renderTripsTab = () => (
    <View style={styles.tabContent}>
      <View style={styles.sectionHeader}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>My Trips</Text>
        <TouchableOpacity
          style={[styles.addButton, { backgroundColor: colors.primary }]}
          onPress={() => setShowTripForm(true)}
        >
          <Ionicons name="add" size={20} color={colors.primaryText} />
          <Text style={styles.addButtonText}>New Trip</Text>
        </TouchableOpacity>
      </View>

      {trips.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="airplane-outline" size={64} color={colors.textSecondary} />
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            No trips yet. Start planning your next adventure!
          </Text>
        </View>
      ) : (
        <ScrollView>
          {trips.map((trip) => (
            <TouchableOpacity
              key={trip.id}
              style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}
              onPress={() => setSelectedTrip(trip)}
            >
              <View style={styles.cardHeader}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>{trip.name}</Text>
                <View style={[styles.badge, { backgroundColor: getStatusColor(trip.status) }]}>
                  <Text style={styles.badgeText}>{trip.status}</Text>
                </View>
              </View>
              <View style={styles.tripDetails}>
                <Ionicons name="location" size={16} color={colors.textSecondary} />
                <Text style={[styles.tripText, { color: colors.text }]}>{trip.destination}</Text>
              </View>
              <View style={styles.tripDetails}>
                <Ionicons name="calendar" size={16} color={colors.textSecondary} />
                <Text style={[styles.tripText, { color: colors.text }]}>
                  {trip.start_date} to {trip.end_date}
                </Text>
              </View>
              <View style={styles.tripDetails}>
                <Ionicons name="people" size={16} color={colors.textSecondary} />
                <Text style={[styles.tripText, { color: colors.text }]}>
                  {trip.traveler_count} traveler(s)
                </Text>
              </View>
            </TouchableOpacity>
          ))}
        </ScrollView>
      )}

      {/* Trip Form Modal */}
      {showTripForm && (
        <View style={[styles.modal, { backgroundColor: colors.background }]}>
          <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
            <Text style={[styles.modalTitle, { color: colors.text }]}>Create New Trip</Text>
            
            <TextInput
              style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
              placeholder="Trip name"
              placeholderTextColor={colors.textSecondary}
              value={tripForm.name}
              onChangeText={(text) => setTripForm((prev) => ({ ...prev, name: text }))}
            />

            <TextInput
              style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
              placeholder="Destination"
              placeholderTextColor={colors.textSecondary}
              value={tripForm.destination}
              onChangeText={(text) => setTripForm((prev) => ({ ...prev, destination: text }))}
            />

            <TextInput
              style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
              placeholder="Start date (YYYY-MM-DD)"
              placeholderTextColor={colors.textSecondary}
              value={tripForm.start_date}
              onChangeText={(text) => setTripForm((prev) => ({ ...prev, start_date: text }))}
            />

            <TextInput
              style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
              placeholder="End date (YYYY-MM-DD)"
              placeholderTextColor={colors.textSecondary}
              value={tripForm.end_date}
              onChangeText={(text) => setTripForm((prev) => ({ ...prev, end_date: text }))}
            />

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={[styles.modalButton, { backgroundColor: colors.border }]}
                onPress={() => setShowTripForm(false)}
              >
                <Text style={[styles.modalButtonText, { color: colors.text }]}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalButton, { backgroundColor: colors.primary }]}
                onPress={createTrip}
              >
                <Text style={styles.modalButtonText}>Create</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}
    </View>
  );

  const renderItineraryTab = () => {
    if (!selectedTrip) {
      return (
        <View style={styles.emptyState}>
          <Ionicons name="calendar-outline" size={64} color={colors.textSecondary} />
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            Select a trip first to view itinerary
          </Text>
        </View>
      );
    }

    return (
      <View style={styles.tabContent}>
        <View style={styles.sectionHeader}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>
            {selectedTrip.name} - Itinerary
          </Text>
          <TouchableOpacity
            style={[styles.addButton, { backgroundColor: colors.primary }]}
            onPress={() => setShowDayForm(true)}
          >
            <Ionicons name="add" size={20} color={colors.primaryText} />
            <Text style={styles.addButtonText}>Add Day</Text>
          </TouchableOpacity>
        </View>

        <ScrollView>
          {itinerary.map((day) => (
            <View
              key={day.id}
              style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}
            >
              <View style={styles.dayHeader}>
                <Text style={[styles.dayTitle, { color: colors.text }]}>
                  Day {day.day_number}: {day.title}
                </Text>
                <Text style={[styles.dayDate, { color: colors.textSecondary }]}>{day.date}</Text>
              </View>

              {day.activities.map((activity) => (
                <View key={activity.activity_id} style={styles.activityCard}>
                  <View style={[styles.timeSlotBadge, { backgroundColor: getTimeSlotColor(activity.time_slot) }]}>
                    <Text style={styles.timeSlotText}>{activity.time_slot}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.activityTitle, { color: colors.text }]}>{activity.title}</Text>
                    {activity.location && (
                      <Text style={[styles.activityLocation, { color: colors.textSecondary }]}>
                        📍 {activity.location}
                      </Text>
                    )}
                    {activity.estimated_cost && (
                      <Text style={[styles.activityCost, { color: colors.success }]}>
                        ${activity.estimated_cost}
                      </Text>
                    )}
                  </View>
                </View>
              ))}

              <TouchableOpacity
                style={[styles.miniButton, { backgroundColor: colors.primary }]}
                onPress={() => {
                  setSelectedDay(day);
                  setShowActivityForm(true);
                }}
              >
                <Ionicons name="add" size={16} color={colors.primaryText} />
                <Text style={styles.miniButtonText}>Add Activity</Text>
              </TouchableOpacity>
            </View>
          ))}
        </ScrollView>

        {/* Day Form Modal */}
        {showDayForm && (
          <View style={[styles.modal, { backgroundColor: colors.background }]}>
            <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>Add Day</Text>
              
              <TextInput
                style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                placeholder="Day title"
                placeholderTextColor={colors.textSecondary}
                value={dayForm.title}
                onChangeText={(text) => setDayForm((prev) => ({ ...prev, title: text }))}
              />

              <TextInput
                style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                placeholder="Date (YYYY-MM-DD)"
                placeholderTextColor={colors.textSecondary}
                value={dayForm.date}
                onChangeText={(text) => setDayForm((prev) => ({ ...prev, date: text }))}
              />

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={[styles.modalButton, { backgroundColor: colors.border }]}
                  onPress={() => setShowDayForm(false)}
                >
                  <Text style={[styles.modalButtonText, { color: colors.text }]}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.modalButton, { backgroundColor: colors.primary }]}
                  onPress={createDay}
                >
                  <Text style={styles.modalButtonText}>Add</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        )}

        {/* Activity Form Modal */}
        {showActivityForm && (
          <View style={[styles.modal, { backgroundColor: colors.background }]}>
            <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>Add Activity</Text>
              
              <TextInput
                style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                placeholder="Activity title"
                placeholderTextColor={colors.textSecondary}
                value={activityForm.title}
                onChangeText={(text) => setActivityForm((prev) => ({ ...prev, title: text }))}
              />

              <TextInput
                style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                placeholder="Location"
                placeholderTextColor={colors.textSecondary}
                value={activityForm.location}
                onChangeText={(text) => setActivityForm((prev) => ({ ...prev, location: text }))}
              />

              <TextInput
                style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                placeholder="Estimated cost"
                placeholderTextColor={colors.textSecondary}
                keyboardType="decimal-pad"
                value={activityForm.estimated_cost}
                onChangeText={(text) => setActivityForm((prev) => ({ ...prev, estimated_cost: text }))}
              />

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={[styles.modalButton, { backgroundColor: colors.border }]}
                  onPress={() => setShowActivityForm(false)}
                >
                  <Text style={[styles.modalButtonText, { color: colors.text }]}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.modalButton, { backgroundColor: colors.primary }]}
                  onPress={addActivity}
                >
                  <Text style={styles.modalButtonText}>Add</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        )}
      </View>
    );
  };

  const renderBudgetTab = () => {
    if (!selectedTrip) {
      return (
        <View style={styles.emptyState}>
          <Ionicons name="wallet-outline" size={64} color={colors.textSecondary} />
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            Select a trip first to manage budget
          </Text>
        </View>
      );
    }

    return (
      <View style={styles.tabContent}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>
          {selectedTrip.name} - Budget
        </Text>

        {!budget ? (
          <View>
            <Text style={[styles.infoText, { color: colors.textSecondary, marginBottom: 16 }]}>
              No budget created yet
            </Text>
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: colors.primary }]}
              onPress={() => setShowBudgetForm(true)}
            >
              <Ionicons name="add" size={20} color={colors.primaryText} />
              <Text style={styles.actionButtonText}>Create Budget</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View>
            <View style={[styles.budgetCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.budgetAmount, { color: colors.text }]}>
                ${budget.spent_total.toFixed(2)} / ${budget.total_budget.toFixed(2)}
              </Text>
              <Text style={[styles.budgetRemaining, { color: colors.success }]}>
                ${budget.remaining.toFixed(2)} remaining
              </Text>
              <View style={[styles.progressBar, { backgroundColor: colors.background }]}>
                <View
                  style={[
                    styles.progressFill,
                    {
                      width: `${Math.min((budget.spent_total / budget.total_budget) * 100, 100)}%`,
                      backgroundColor: getProgressColor((budget.spent_total / budget.total_budget) * 100),
                    },
                  ]}
                />
              </View>
            </View>

            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: colors.primary, marginVertical: 16 }]}
              onPress={() => setShowExpenseForm(true)}
            >
              <Ionicons name="add" size={20} color={colors.primaryText} />
              <Text style={styles.actionButtonText}>Log Expense</Text>
            </TouchableOpacity>

            <Text style={[styles.subsectionTitle, { color: colors.text }]}>Recent Expenses</Text>
            <ScrollView>
              {expenses.map((expense) => (
                <View
                  key={expense.id}
                  style={[styles.expenseCard, { backgroundColor: colors.card, borderColor: colors.border }]}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.expenseDesc, { color: colors.text }]}>{expense.description}</Text>
                    <Text style={[styles.expenseCat, { color: colors.textSecondary }]}>{expense.category}</Text>
                  </View>
                  <Text style={[styles.expenseAmount, { color: colors.text }]}>
                    ${expense.amount.toFixed(2)}
                  </Text>
                </View>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Budget Form Modal */}
        {showBudgetForm && (
          <View style={[styles.modal, { backgroundColor: colors.background }]}>
            <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>Create Budget</Text>
              
              <TextInput
                style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                placeholder="Total budget"
                placeholderTextColor={colors.textSecondary}
                keyboardType="decimal-pad"
                value={budgetForm.total_budget}
                onChangeText={(text) => setBudgetForm((prev) => ({ ...prev, total_budget: text }))}
              />

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={[styles.modalButton, { backgroundColor: colors.border }]}
                  onPress={() => setShowBudgetForm(false)}
                >
                  <Text style={[styles.modalButtonText, { color: colors.text }]}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.modalButton, { backgroundColor: colors.primary }]}
                  onPress={createBudget}
                >
                  <Text style={styles.modalButtonText}>Create</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        )}

        {/* Expense Form Modal */}
        {showExpenseForm && (
          <View style={[styles.modal, { backgroundColor: colors.background }]}>
            <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>Log Expense</Text>
              
              <TextInput
                style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                placeholder="Description"
                placeholderTextColor={colors.textSecondary}
                value={expenseForm.description}
                onChangeText={(text) => setExpenseForm((prev) => ({ ...prev, description: text }))}
              />

              <TextInput
                style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                placeholder="Amount"
                placeholderTextColor={colors.textSecondary}
                keyboardType="decimal-pad"
                value={expenseForm.amount}
                onChangeText={(text) => setExpenseForm((prev) => ({ ...prev, amount: text }))}
              />

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={[styles.modalButton, { backgroundColor: colors.border }]}
                  onPress={() => setShowExpenseForm(false)}
                >
                  <Text style={[styles.modalButtonText, { color: colors.text }]}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.modalButton, { backgroundColor: colors.primary }]}
                  onPress={logExpense}
                >
                  <Text style={styles.modalButtonText}>Log</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        )}
      </View>
    );
  };

  const renderAITab = () => (
    <View style={styles.tabContent}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>AI Trip Planner</Text>

      <View style={styles.aiModeSelector}>
        {[
          { key: "itinerary", label: "Generate Trip", icon: "calendar" },
          { key: "destination", label: "Find Destinations", icon: "location" },
          { key: "packing", label: "Packing List", icon: "briefcase" },
        ].map((mode) => (
          <TouchableOpacity
            key={mode.key}
            style={[
              styles.modeButton,
              {
                backgroundColor: aiMode === mode.key ? colors.primary : colors.card,
                borderColor: colors.border,
              },
            ]}
            onPress={() => setAiMode(mode.key as any)}
          >
            <Ionicons
              name={mode.icon as any}
              size={20}
              color={aiMode === mode.key ? colors.primaryText : colors.text}
            />
            <Text
              style={[
                styles.modeLabel,
                { color: aiMode === mode.key ? colors.primaryText : colors.text },
              ]}
            >
              {mode.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <TextInput
        style={[styles.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]}
        placeholder="Destination"
        placeholderTextColor={colors.textSecondary}
        value={aiInput.destination}
        onChangeText={(text) => setAiInput((prev) => ({ ...prev, destination: text }))}
      />

      {(aiMode === "itinerary" || aiMode === "packing") && (
        <TextInput
          style={[styles.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]}
          placeholder="Number of days"
          placeholderTextColor={colors.textSecondary}
          keyboardType="number-pad"
          value={aiInput.num_days}
          onChangeText={(text) => setAiInput((prev) => ({ ...prev, num_days: text }))}
        />
      )}

      <TextInput
        style={[styles.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]}
        placeholder="Budget (optional)"
        placeholderTextColor={colors.textSecondary}
        keyboardType="decimal-pad"
        value={aiInput.budget}
        onChangeText={(text) => setAiInput((prev) => ({ ...prev, budget: text }))}
      />

      <TextInput
        style={[styles.input, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]}
        placeholder="Interests (comma-separated)"
        placeholderTextColor={colors.textSecondary}
        value={aiInput.interests}
        onChangeText={(text) => setAiInput((prev) => ({ ...prev, interests: text }))}
      />

      <TouchableOpacity
        style={[styles.aiButton, { backgroundColor: colors.primary }]}
        onPress={runAI}
        disabled={aiLoading}
      >
        {aiLoading ? (
          <ActivityIndicator color={colors.primaryText} />
        ) : (
          <>
            <Ionicons name="sparkles" size={20} color={colors.primaryText} />
            <Text style={styles.aiButtonText}>Generate with AI</Text>
          </>
        )}
      </TouchableOpacity>

      {aiResult && (
        <ScrollView style={[styles.aiResultCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.aiResultText, { color: colors.text }]}>{aiResult}</Text>
        </ScrollView>
      )}
    </View>
  );

  const renderChecklistTab = () => {
    if (!selectedTrip) {
      return (
        <View style={styles.emptyState}>
          <Ionicons name="checkmark-circle-outline" size={64} color={colors.textSecondary} />
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            Select a trip first to view checklist
          </Text>
        </View>
      );
    }

    return (
      <View style={styles.tabContent}>
        <View style={styles.sectionHeader}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>
            {selectedTrip.name} - Checklist
          </Text>
          <TouchableOpacity
            style={[styles.addButton, { backgroundColor: colors.primary }]}
            onPress={() => setShowChecklistForm(true)}
          >
            <Ionicons name="add" size={20} color={colors.primaryText} />
            <Text style={styles.addButtonText}>Add Item</Text>
          </TouchableOpacity>
        </View>

        {checklist && checklist.items.length > 0 ? (
          <ScrollView>
            {checklist.items.map((item) => (
              <TouchableOpacity
                key={item.item_id}
                style={[styles.checklistItem, { backgroundColor: colors.card, borderColor: colors.border }]}
                onPress={() => toggleChecklistItem(item.item_id)}
              >
                <Ionicons
                  name={item.completed ? "checkmark-circle" : "ellipse-outline"}
                  size={24}
                  color={item.completed ? colors.success : colors.textSecondary}
                />
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text
                    style={[
                      styles.checklistTitle,
                      { color: colors.text, textDecorationLine: item.completed ? "line-through" : "none" },
                    ]}
                  >
                    {item.title}
                  </Text>
                  <Text style={[styles.checklistCat, { color: colors.textSecondary }]}>
                    {item.category} • {item.priority} priority
                  </Text>
                </View>
              </TouchableOpacity>
            ))}
          </ScrollView>
        ) : (
          <View style={styles.emptyState}>
            <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
              No checklist items yet
            </Text>
          </View>
        )}

        {/* Checklist Form Modal */}
        {showChecklistForm && (
          <View style={[styles.modal, { backgroundColor: colors.background }]}>
            <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>Add Checklist Item</Text>
              
              <TextInput
                style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                placeholder="Item title"
                placeholderTextColor={colors.textSecondary}
                value={checklistForm.title}
                onChangeText={(text) => setChecklistForm((prev) => ({ ...prev, title: text }))}
              />

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={[styles.modalButton, { backgroundColor: colors.border }]}
                  onPress={() => setShowChecklistForm(false)}
                >
                  <Text style={[styles.modalButtonText, { color: colors.text }]}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.modalButton, { backgroundColor: colors.primary }]}
                  onPress={addChecklistItem}
                >
                  <Text style={styles.modalButtonText}>Add</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        )}
      </View>
    );
  };

  // Helper functions
  const getStatusColor = (status: string) => {
    switch (status) {
      case "planning":
        return colors.warning;
      case "ongoing":
        return colors.primary;
      case "completed":
        return colors.success;
      default:
        return colors.textMuted;
    }
  };

  const getTimeSlotColor = (slot: string) => {
    switch (slot) {
      case "morning":
        return colors.warning;
      case "afternoon":
        return colors.info;
      case "evening":
        return colors.primary;
      default:
        return colors.textMuted;
    }
  };

  const getProgressColor = (percent: number) => {
    if (percent >= 90) return colors.error;
    if (percent >= 75) return colors.warning;
    return colors.success;
  };

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[styles.loadingText, { color: colors.text }]}>
            Loading Travel Planner Pro...
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={[styles.header, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
        <View style={styles.headerContent}>
          <Ionicons name="airplane" size={32} color={colors.primary} />
          <View style={styles.headerText}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>Travel Planner Pro</Text>
            <Text style={[styles.headerSubtitle, { color: colors.textSecondary }]}>
              AI-Powered Trip Planning
            </Text>
          </View>
        </View>
        {selectedTrip && (
          <TouchableOpacity onPress={() => setSelectedTrip(null)}>
            <Text style={[styles.clearSelection, { color: colors.primary }]}>Clear</Text>
          </TouchableOpacity>
        )}
      </View>

      {renderKPIDashboard()}
      {renderTabBar()}

      <ScrollView style={styles.content}>
        {activeTab === "trips" && renderTripsTab()}
        {activeTab === "itinerary" && renderItineraryTab()}
        {activeTab === "budget" && renderBudgetTab()}
        {activeTab === "ai" && renderAITab()}
        {activeTab === "checklist" && renderChecklistTab()}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
  },
  loadingText: {
    marginTop: 16,
    fontSize: 16,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  headerContent: {
    flexDirection: "row",
    alignItems: "center",
  },
  headerText: {
    marginLeft: 12,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: "bold",
  },
  headerSubtitle: {
    fontSize: 14,
  },
  clearSelection: {
    fontSize: 14,
    fontWeight: "600",
  },
  kpiContainer: {
    padding: 16,
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
  },
  kpiGrid: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  kpiCard: {
    alignItems: "center",
    flex: 1,
  },
  kpiValue: {
    fontSize: 24,
    fontWeight: "bold",
    marginTop: 8,
  },
  kpiLabel: {
    fontSize: 12,
    marginTop: 4,
  },
  tabBar: {
    borderBottomWidth: 1,
    marginTop: 16,
  },
  tab: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 8,
  },
  tabLabel: {
    fontSize: 14,
    fontWeight: "500",
  },
  content: {
    flex: 1,
  },
  tabContent: {
    padding: 16,
  },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: "bold",
  },
  subsectionTitle: {
    fontSize: 16,
    fontWeight: "600",
    marginBottom: 12,
  },
  addButton: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    gap: 8,
  },
  addButtonText: {
    color: "var(--app-primary-text)",
    fontSize: 14,
    fontWeight: "600",
  },
  emptyState: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 48,
  },
  emptyText: {
    marginTop: 16,
    fontSize: 16,
    textAlign: "center",
    paddingHorizontal: 32,
  },
  infoText: {
    fontSize: 14,
  },
  card: {
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
  },
  cardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: "bold",
    flex: 1,
  },
  badge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  badgeText: {
    color: "var(--app-primary-text)",
    fontSize: 12,
    fontWeight: "600",
    textTransform: "capitalize",
  },
  tripDetails: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 8,
    gap: 8,
  },
  tripText: {
    fontSize: 14,
  },
  modal: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 16,
  },
  modalContent: {
    width: "100%",
    maxWidth: 400,
    padding: 24,
    borderRadius: 16,
    maxHeight: "80%",
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: "bold",
    marginBottom: 16,
  },
  input: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
    marginBottom: 12,
  },
  modalActions: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 12,
    marginTop: 16,
  },
  modalButton: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
  },
  modalButtonText: {
    color: "var(--app-primary-text)",
    fontSize: 16,
    fontWeight: "600",
  },
  dayHeader: {
    marginBottom: 16,
  },
  dayTitle: {
    fontSize: 16,
    fontWeight: "bold",
  },
  dayDate: {
    fontSize: 14,
    marginTop: 4,
  },
  activityCard: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginBottom: 12,
    gap: 12,
  },
  timeSlotBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  timeSlotText: {
    color: "var(--app-primary-text)",
    fontSize: 10,
    fontWeight: "600",
    textTransform: "uppercase",
  },
  activityTitle: {
    fontSize: 14,
    fontWeight: "600",
    marginBottom: 4,
  },
  activityLocation: {
    fontSize: 12,
    marginBottom: 2,
  },
  activityCost: {
    fontSize: 12,
    fontWeight: "600",
  },
  miniButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 8,
    borderRadius: 8,
    gap: 6,
    marginTop: 8,
  },
  miniButtonText: {
    color: "var(--app-primary-text)",
    fontSize: 12,
    fontWeight: "600",
  },
  budgetCard: {
    padding: 20,
    borderRadius: 12,
    borderWidth: 1,
    alignItems: "center",
  },
  budgetAmount: {
    fontSize: 24,
    fontWeight: "bold",
    marginBottom: 8,
  },
  budgetRemaining: {
    fontSize: 16,
    fontWeight: "600",
    marginBottom: 16,
  },
  progressBar: {
    width: "100%",
    height: 8,
    borderRadius: 4,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
  },
  actionButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 14,
    borderRadius: 8,
    gap: 8,
  },
  actionButtonText: {
    color: "var(--app-primary-text)",
    fontSize: 16,
    fontWeight: "600",
  },
  expenseCard: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 8,
  },
  expenseDesc: {
    fontSize: 14,
    fontWeight: "600",
    marginBottom: 4,
  },
  expenseCat: {
    fontSize: 12,
    textTransform: "capitalize",
  },
  expenseAmount: {
    fontSize: 16,
    fontWeight: "bold",
  },
  aiModeSelector: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 16,
  },
  modeButton: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 12,
    borderRadius: 8,
    borderWidth: 1,
    gap: 6,
  },
  modeLabel: {
    fontSize: 12,
    fontWeight: "600",
  },
  aiButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 14,
    borderRadius: 8,
    gap: 8,
    marginTop: 8,
  },
  aiButtonText: {
    color: "var(--app-primary-text)",
    fontSize: 16,
    fontWeight: "600",
  },
  aiResultCard: {
    marginTop: 16,
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    maxHeight: 400,
  },
  aiResultText: {
    fontSize: 14,
    lineHeight: 20,
  },
  checklistItem: {
    flexDirection: "row",
    alignItems: "center",
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 8,
  },
  checklistTitle: {
    fontSize: 14,
    fontWeight: "600",
    marginBottom: 4,
  },
  checklistCat: {
    fontSize: 12,
    textTransform: "capitalize",
  },
});
