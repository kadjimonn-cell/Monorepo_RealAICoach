/**
 * Feature 10: Smart Shopping Advisor - Enterprise Workspace
 * 
 * AI-powered shopping intelligence platform with:
 * - Wishlist management with price tracking
 * - Price alert engine
 * - AI product comparison and recommendations
 * - Shopping budget tracker with analytics
 * - Deal and coupon finder
 * - Carbon footprint calculator
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

interface WishlistItem {
  item_id: string;
  product_name: string;
  product_url?: string;
  target_price?: number;
  current_price?: number;
  price_alert_enabled: boolean;
  image_url?: string;
  notes?: string;
  priority: "high" | "medium" | "low";
  added_at: string;
  updated_at: string;
}

interface Wishlist {
  id: string;
  user_id: string;
  name: string;
  description?: string;
  items: WishlistItem[];
  created_at: string;
  updated_at: string;
}

interface PriceAlert {
  id: string;
  user_id: string;
  wishlist_id: string;
  item_id: string;
  product_name: string;
  target_price: number;
  current_price: number;
  alert_threshold_pct: number;
  status: "active" | "triggered" | "expired";
  last_checked_at: string;
  triggered_at?: string;
  created_at: string;
}

interface ShoppingBudget {
  id: string;
  user_id: string;
  name: string;
  category: string;
  monthly_limit: number;
  currency: string;
  alert_threshold_pct: number;
  spent_this_month: number;
  remaining?: number;
  spent_pct?: number;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
}

interface Purchase {
  id: string;
  user_id: string;
  budget_id?: string;
  product_name: string;
  amount: number;
  currency: string;
  merchant?: string;
  category: string;
  purchase_date: string;
  notes?: string;
  carbon_footprint_kg: number;
  created_at: string;
}

interface BootstrapData {
  user_id: string;
  tier: string;
  limits: {
    wishlists_max: number;
    wishlist_items_max: number;
    price_alerts_max: number;
    budgets_max: number;
    ai_queries_per_month: number;
  };
  usage: {
    wishlists_count: number;
    price_alerts_count: number;
    budgets_count: number;
    ai_queries_this_month: number;
  };
  features_available: string[];
}

export default function SmartShoppingAdvisor() {
  const { colors } = useTheme();
  const { t } = useTranslation();

  // Core state
  const [loading, setLoading] = useState(true);
  const [bootstrap, setBootstrap] = useState<BootstrapData | null>(null);
  const [activeTab, setActiveTab] = useState<
    "wishlists" | "budgets" | "deals" | "ai" | "carbon"
  >("wishlists");

  // Wishlist state
  const [wishlists, setWishlists] = useState<Wishlist[]>([]);
  const [selectedWishlist, setSelectedWishlist] = useState<Wishlist | null>(null);
  const [showWishlistForm, setShowWishlistForm] = useState(false);
  const [wishlistForm, setWishlistForm] = useState({
    name: "",
    description: "",
  });

  // Item form state
  const [showItemForm, setShowItemForm] = useState(false);
  const [itemForm, setItemForm] = useState({
    product_name: "",
    target_price: "",
    current_price: "",
    priority: "medium" as "high" | "medium" | "low",
    notes: "",
  });

  // Budget state
  const [budgets, setBudgets] = useState<ShoppingBudget[]>([]);
  const [showBudgetForm, setShowBudgetForm] = useState(false);
  const [budgetForm, setBudgetForm] = useState({
    name: "",
    category: "general",
    monthly_limit: "",
  });
  const [budgetAnalytics, setBudgetAnalytics] = useState<any>(null);

  // Purchase state
  const [showPurchaseForm, setShowPurchaseForm] = useState(false);
  const [purchaseForm, setPurchaseForm] = useState({
    product_name: "",
    amount: "",
    category: "general",
    merchant: "",
    budget_id: "",
  });
  const [purchases, setPurchases] = useState<Purchase[]>([]);

  // AI Advisor state
  const [aiMode, setAiMode] = useState<"compare" | "recommend" | "deals">("compare");
  const [aiInput, setAiInput] = useState("");
  const [aiResult, setAiResult] = useState<string>("");
  const [aiLoading, setAiLoading] = useState(false);

  // Price alerts state
  const [priceAlerts, setPriceAlerts] = useState<PriceAlert[]>([]);

  // Carbon tracking state
  const [carbonReport, setCarbonReport] = useState<any>(null);

  // Deals state
  const [deals, setDeals] = useState<any[]>([]);

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
      
      const [bootstrapRes, wishlistsRes, budgetsRes, alertsRes, dealsRes, carbonRes] = await Promise.all([
        apiRequest(`${API_BASE}/api/smart-shopping-advisor/bootstrap?fallback_user_id=${fallbackUserId}`),
        apiRequest(`${API_BASE}/api/smart-shopping-advisor/wishlists?fallback_user_id=${fallbackUserId}`),
        apiRequest(`${API_BASE}/api/smart-shopping-advisor/budgets?fallback_user_id=${fallbackUserId}`),
        apiRequest(`${API_BASE}/api/smart-shopping-advisor/price-alerts?fallback_user_id=${fallbackUserId}`),
        apiRequest(`${API_BASE}/api/smart-shopping-advisor/deals?fallback_user_id=${fallbackUserId}&limit=10`),
        apiRequest(`${API_BASE}/api/smart-shopping-advisor/carbon-report?fallback_user_id=${fallbackUserId}`),
      ]);

      if (bootstrapRes.ok) {
        const data = await bootstrapRes.json();
        setBootstrap(data);
      }

      if (wishlistsRes.ok) {
        const data = await wishlistsRes.json();
        setWishlists(data.wishlists || []);
      }

      if (budgetsRes.ok) {
        const data = await budgetsRes.json();
        setBudgets(data.budgets || []);
      }

      if (alertsRes.ok) {
        const data = await alertsRes.json();
        setPriceAlerts(data.alerts || []);
      }

      if (dealsRes.ok) {
        const data = await dealsRes.json();
        setDeals(data.deals || []);
      }

      if (carbonRes.ok) {
        const data = await carbonRes.json();
        setCarbonReport(data);
      }

    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/smartbuy.tsx#initializeWorkspace',
        error,
        message: 'Failed to initialize Smart Shopping Advisor',
        notifyMode: 'silent',
      });
    } finally {
      setLoading(false);
    }
  };

  // Wishlist operations
  const createWishlist = async () => {
    if (!wishlistForm.name.trim()) {
      Alert.alert("Error", "Please enter a wishlist name");
      return;
    }

    try {
      const response = await apiRequest(`${API_BASE}/api/smart-shopping-advisor/wishlists?fallback_user_id=${fallbackUserId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: wishlistForm.name,
          description: wishlistForm.description,
          items: [],
        }),
      });

      if (response.ok) {
        Alert.alert("Success", "Wishlist created!");
        setWishlistForm({ name: "", description: "" });
        setShowWishlistForm(false);
        
        // Refresh wishlists
        const wishlistsRes = await apiRequest(`${API_BASE}/api/smart-shopping-advisor/wishlists?fallback_user_id=${fallbackUserId}`);
        if (wishlistsRes.ok) {
          const data = await wishlistsRes.json();
          setWishlists(data.wishlists || []);
        }
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "Failed to create wishlist");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/smartbuy.tsx#createWishlist',
        error,
        message: 'Failed to create wishlist',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void createWishlist(); },
      });
    }
  };

  const addItemToWishlist = async () => {
    if (!selectedWishlist || !itemForm.product_name.trim()) {
      Alert.alert("Error", "Please enter product name");
      return;
    }

    try {
      const response = await apiRequest(
        `${API_BASE}/api/smart-shopping-advisor/wishlists/${selectedWishlist.id}/items?fallback_user_id=${fallbackUserId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            product_name: itemForm.product_name,
            target_price: itemForm.target_price ? parseFloat(itemForm.target_price) : null,
            current_price: itemForm.current_price ? parseFloat(itemForm.current_price) : null,
            priority: itemForm.priority,
            notes: itemForm.notes,
          }),
        }
      );

      if (response.ok) {
        Alert.alert("Success", "Item added to wishlist!");
        setItemForm({ product_name: "", target_price: "", current_price: "", priority: "medium", notes: "" });
        setShowItemForm(false);
        
        // Refresh wishlist
        const wishlistRes = await apiRequest(
          `${API_BASE}/api/smart-shopping-advisor/wishlists/${selectedWishlist.id}?fallback_user_id=${fallbackUserId}`
        );
        if (wishlistRes.ok) {
          const data = await wishlistRes.json();
          setSelectedWishlist(data);
          
          // Update wishlists array
          setWishlists((prev) =>
            prev.map((w) => (w.id === data.id ? data : w))
          );
        }
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "Failed to add item");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/smartbuy.tsx#addItemToWishlist',
        error,
        message: 'Failed to add item',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void addItemToWishlist(); },
      });
    }
  };

  // Budget operations
  const createBudget = async () => {
    if (!budgetForm.name.trim() || !budgetForm.monthly_limit) {
      Alert.alert("Error", "Please fill in all budget fields");
      return;
    }

    try {
      const response = await apiRequest(`${API_BASE}/api/smart-shopping-advisor/budgets?fallback_user_id=${fallbackUserId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: budgetForm.name,
          category: budgetForm.category,
          monthly_limit: parseFloat(budgetForm.monthly_limit),
          currency: "USD",
          alert_threshold_pct: 80.0,
        }),
      });

      if (response.ok) {
        Alert.alert("Success", "Budget created!");
        setBudgetForm({ name: "", category: "general", monthly_limit: "" });
        setShowBudgetForm(false);
        
        // Refresh budgets
        const budgetsRes = await apiRequest(`${API_BASE}/api/smart-shopping-advisor/budgets?fallback_user_id=${fallbackUserId}`);
        if (budgetsRes.ok) {
          const data = await budgetsRes.json();
          setBudgets(data.budgets || []);
        }
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "Failed to create budget");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/smartbuy.tsx#createBudget',
        error,
        message: 'Failed to create budget',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void createBudget(); },
      });
    }
  };

  const logPurchase = async () => {
    if (!purchaseForm.product_name.trim() || !purchaseForm.amount) {
      Alert.alert("Error", "Please fill in product name and amount");
      return;
    }

    try {
      const response = await apiRequest(`${API_BASE}/api/smart-shopping-advisor/purchases?fallback_user_id=${fallbackUserId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_name: purchaseForm.product_name,
          amount: parseFloat(purchaseForm.amount),
          category: purchaseForm.category,
          merchant: purchaseForm.merchant,
          budget_id: purchaseForm.budget_id || null,
          currency: "USD",
        }),
      });

      if (response.ok) {
        const data = await response.json();
        Alert.alert(
          "Purchase Logged!",
          `Carbon footprint: ${data.carbon_footprint_kg} kg CO₂`
        );
        setPurchaseForm({ product_name: "", amount: "", category: "general", merchant: "", budget_id: "" });
        setShowPurchaseForm(false);
        
        // Refresh budgets and analytics
        const budgetsRes = await apiRequest(`${API_BASE}/api/smart-shopping-advisor/budgets?fallback_user_id=${fallbackUserId}`);
        if (budgetsRes.ok) {
          const budgetsData = await budgetsRes.json();
          setBudgets(budgetsData.budgets || []);
        }

        // Refresh carbon report
        const carbonRes = await apiRequest(`${API_BASE}/api/smart-shopping-advisor/carbon-report?fallback_user_id=${fallbackUserId}`);
        if (carbonRes.ok) {
          const carbonData = await carbonRes.json();
          setCarbonReport(carbonData);
        }
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "Failed to log purchase");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/smartbuy.tsx#logPurchase',
        error,
        message: 'Failed to log purchase',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void logPurchase(); },
      });
    }
  };

  // AI Advisor operations
  const runAIAdvisor = async () => {
    if (!aiInput.trim()) {
      Alert.alert("Error", "Please enter your query");
      return;
    }

    setAiLoading(true);
    setAiResult("");

    try {
      let endpoint = "";
      let body: any = {};

      if (aiMode === "compare") {
        endpoint = "/api/smart-shopping-advisor/product-compare";
        body = {
          products: [
            { name: aiInput, description: "Product to compare" },
          ],
          comparison_criteria: ["price", "features", "quality"],
        };
      } else if (aiMode === "recommend") {
        endpoint = "/api/smart-shopping-advisor/ai-recommendation";
        body = {
          query: aiInput,
          budget: null,
          preferences: {},
        };
      } else if (aiMode === "deals") {
        endpoint = "/api/smart-shopping-advisor/deals/search";
        body = {
          query: aiInput,
          category: null,
          max_price: null,
        };
      }

      const response = await apiRequest(`${API_BASE}${endpoint}?fallback_user_id=${fallbackUserId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (response.ok) {
        const data = await response.json();
        const result = data.comparison || data.recommendation || data.deals || "No result";
        setAiResult(result);
      } else {
        const error = await response.json();
        Alert.alert("Error", error.detail || "AI query failed");
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/smartbuy.tsx#runAIAdvisor',
        error,
        message: 'AI query failed',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void runAIAdvisor(); },
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
          <Ionicons name="heart-outline" size={24} color={colors.primary} />
          <Text style={[styles.kpiValue, { color: colors.text }]}>
            {bootstrap?.usage.wishlists_count || 0}
          </Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>Wishlists</Text>
        </View>

        <View style={styles.kpiCard}>
          <Ionicons name="notifications-outline" size={24} color={colors.accent} />
          <Text style={[styles.kpiValue, { color: colors.text }]}>
            {priceAlerts.filter((a) => a.status === "active").length}
          </Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>Active Alerts</Text>
        </View>

        <View style={styles.kpiCard}>
          <Ionicons name="wallet-outline" size={24} color={colors.success} />
          <Text style={[styles.kpiValue, { color: colors.text }]}>
            {budgets.length}
          </Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>Budgets</Text>
        </View>

        <View style={styles.kpiCard}>
          <Ionicons name="leaf-outline" size={24} color={colors.success} />
          <Text style={[styles.kpiValue, { color: colors.text }]}>
            {carbonReport?.total_carbon_kg?.toFixed(1) || 0}
          </Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>kg CO₂</Text>
        </View>
      </View>
    </View>
  );

  const renderTabBar = () => (
    <View style={[styles.tabBar, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        {[
          { key: "wishlists", icon: "heart", label: "Wishlists" },
          { key: "budgets", icon: "wallet", label: "Budgets" },
          { key: "deals", icon: "pricetag", label: "Deals" },
          { key: "ai", icon: "sparkles", label: "AI Advisor" },
          { key: "carbon", icon: "leaf", label: "Carbon" },
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

  const renderWishlistsTab = () => (
    <View style={styles.tabContent}>
      <View style={styles.sectionHeader}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>My Wishlists</Text>
        <TouchableOpacity
          style={[styles.addButton, { backgroundColor: colors.primary }]}
          onPress={() => setShowWishlistForm(true)}
        >
          <Ionicons name="add" size={20} color={colors.primaryText} />
          <Text style={styles.addButtonText}>New Wishlist</Text>
        </TouchableOpacity>
      </View>

      {wishlists.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="heart-outline" size={64} color={colors.textSecondary} />
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            No wishlists yet. Create one to start tracking products!
          </Text>
        </View>
      ) : (
        <ScrollView>
          {wishlists.map((wishlist) => (
            <TouchableOpacity
              key={wishlist.id}
              style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}
              onPress={() => setSelectedWishlist(wishlist)}
            >
              <View style={styles.cardHeader}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>{wishlist.name}</Text>
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{wishlist.items.length} items</Text>
                </View>
              </View>
              {wishlist.description && (
                <Text style={[styles.cardDescription, { color: colors.textSecondary }]}>
                  {wishlist.description}
                </Text>
              )}
              
              {wishlist.items.slice(0, 3).map((item) => (
                <View key={item.item_id} style={styles.itemPreview}>
                  <Ionicons name="pricetag-outline" size={16} color={colors.textSecondary} />
                  <Text style={[styles.itemPreviewText, { color: colors.text }]}>
                    {item.product_name}
                  </Text>
                  {item.target_price && item.current_price && item.current_price < item.target_price && (
                    <Ionicons name="arrow-down" size={16} color={colors.success} />
                  )}
                </View>
              ))}
            </TouchableOpacity>
          ))}
        </ScrollView>
      )}

      {/* Wishlist Form Modal */}
      {showWishlistForm && (
        <View style={[styles.modal, { backgroundColor: colors.background }]}>
          <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
            <Text style={[styles.modalTitle, { color: colors.text }]}>Create Wishlist</Text>
            
            <TextInput
              style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
              placeholder="Wishlist name"
              placeholderTextColor={colors.textSecondary}
              value={wishlistForm.name}
              onChangeText={(text) => setWishlistForm((prev) => ({ ...prev, name: text }))}
            />

            <TextInput
              style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
              placeholder="Description (optional)"
              placeholderTextColor={colors.textSecondary}
              value={wishlistForm.description}
              onChangeText={(text) => setWishlistForm((prev) => ({ ...prev, description: text }))}
              multiline
            />

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={[styles.modalButton, { backgroundColor: colors.border }]}
                onPress={() => setShowWishlistForm(false)}
              >
                <Text style={[styles.modalButtonText, { color: colors.text }]}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalButton, { backgroundColor: colors.primary }]}
                onPress={createWishlist}
              >
                <Text style={styles.modalButtonText}>Create</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}

      {/* Selected Wishlist Detail */}
      {selectedWishlist && (
        <View style={[styles.modal, { backgroundColor: colors.background }]}>
          <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>{selectedWishlist.name}</Text>
              <TouchableOpacity onPress={() => setSelectedWishlist(null)}>
                <Ionicons name="close" size={24} color={colors.text} />
              </TouchableOpacity>
            </View>

            <TouchableOpacity
              style={[styles.addButton, { backgroundColor: colors.primary, marginBottom: 16 }]}
              onPress={() => setShowItemForm(true)}
            >
              <Ionicons name="add" size={20} color={colors.primaryText} />
              <Text style={styles.addButtonText}>Add Item</Text>
            </TouchableOpacity>

            <ScrollView style={{ maxHeight: 400 }}>
              {selectedWishlist.items.map((item) => (
                <View
                  key={item.item_id}
                  style={[styles.itemCard, { backgroundColor: colors.background, borderColor: colors.border }]}
                >
                  <View style={styles.itemHeader}>
                    <Text style={[styles.itemName, { color: colors.text }]}>{item.product_name}</Text>
                    <View style={[styles.priorityBadge, { backgroundColor: getPriorityColor(item.priority) }]}>
                      <Text style={styles.priorityText}>{item.priority}</Text>
                    </View>
                  </View>
                  
                  {item.current_price && (
                    <Text style={[styles.itemPrice, { color: colors.text }]}>
                      Current: ${item.current_price.toFixed(2)}
                    </Text>
                  )}
                  
                  {item.target_price && (
                    <Text style={[styles.itemTarget, { color: colors.textSecondary }]}>
                      Target: ${item.target_price.toFixed(2)}
                    </Text>
                  )}

                  {item.notes && (
                    <Text style={[styles.itemNotes, { color: colors.textSecondary }]}>{item.notes}</Text>
                  )}
                </View>
              ))}
            </ScrollView>

            {showItemForm && (
              <View style={[styles.formOverlay, { backgroundColor: colors.card }]}>
                <Text style={[styles.formTitle, { color: colors.text }]}>Add Item</Text>
                
                <TextInput
                  style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                  placeholder="Product name"
                  placeholderTextColor={colors.textSecondary}
                  value={itemForm.product_name}
                  onChangeText={(text) => setItemForm((prev) => ({ ...prev, product_name: text }))}
                />

                <TextInput
                  style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                  placeholder="Target price"
                  placeholderTextColor={colors.textSecondary}
                  keyboardType="decimal-pad"
                  value={itemForm.target_price}
                  onChangeText={(text) => setItemForm((prev) => ({ ...prev, target_price: text }))}
                />

                <TextInput
                  style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
                  placeholder="Current price"
                  placeholderTextColor={colors.textSecondary}
                  keyboardType="decimal-pad"
                  value={itemForm.current_price}
                  onChangeText={(text) => setItemForm((prev) => ({ ...prev, current_price: text }))}
                />

                <View style={styles.modalActions}>
                  <TouchableOpacity
                    style={[styles.modalButton, { backgroundColor: colors.border }]}
                    onPress={() => setShowItemForm(false)}
                  >
                    <Text style={[styles.modalButtonText, { color: colors.text }]}>Cancel</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.modalButton, { backgroundColor: colors.primary }]}
                    onPress={addItemToWishlist}
                  >
                    <Text style={styles.modalButtonText}>Add</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}
          </View>
        </View>
      )}
    </View>
  );

  const renderBudgetsTab = () => (
    <View style={styles.tabContent}>
      <View style={styles.sectionHeader}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Shopping Budgets</Text>
        <TouchableOpacity
          style={[styles.addButton, { backgroundColor: colors.primary }]}
          onPress={() => setShowBudgetForm(true)}
        >
          <Ionicons name="add" size={20} color={colors.primaryText} />
          <Text style={styles.addButtonText}>New Budget</Text>
        </TouchableOpacity>
      </View>

      {budgets.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="wallet-outline" size={64} color={colors.textSecondary} />
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            No budgets yet. Create one to track your spending!
          </Text>
        </View>
      ) : (
        <ScrollView>
          {budgets.map((budget) => (
            <View
              key={budget.id}
              style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}
            >
              <View style={styles.cardHeader}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>{budget.name}</Text>
                <View style={[styles.badge, { backgroundColor: getCategoryColor(budget.category) }]}>
                  <Text style={styles.badgeText}>{budget.category}</Text>
                </View>
              </View>

              <View style={styles.budgetProgress}>
                <View style={styles.budgetStats}>
                  <Text style={[styles.budgetAmount, { color: colors.text }]}>
                    ${budget.spent_this_month.toFixed(2)} / ${budget.monthly_limit.toFixed(2)}
                  </Text>
                  <Text style={[styles.budgetPercent, { color: colors.textSecondary }]}>
                    {budget.spent_pct?.toFixed(1)}% used
                  </Text>
                </View>
                
                <View style={[styles.progressBar, { backgroundColor: colors.background }]}>
                  <View
                    style={[
                      styles.progressFill,
                      {
                        width: `${Math.min(budget.spent_pct || 0, 100)}%`,
                        backgroundColor: getProgressColor(budget.spent_pct || 0),
                      },
                    ]}
                  />
                </View>

                <Text style={[styles.remaining, { color: colors.success }]}>
                  ${budget.remaining?.toFixed(2) || 0} remaining
                </Text>
              </View>
            </View>
          ))}

          <TouchableOpacity
            style={[styles.actionButton, { backgroundColor: colors.primary }]}
            onPress={() => setShowPurchaseForm(true)}
          >
            <Ionicons name="cart" size={20} color={colors.primaryText} />
            <Text style={styles.actionButtonText}>Log Purchase</Text>
          </TouchableOpacity>
        </ScrollView>
      )}

      {/* Budget Form Modal */}
      {showBudgetForm && (
        <View style={[styles.modal, { backgroundColor: colors.background }]}>
          <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
            <Text style={[styles.modalTitle, { color: colors.text }]}>Create Budget</Text>
            
            <TextInput
              style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
              placeholder="Budget name"
              placeholderTextColor={colors.textSecondary}
              value={budgetForm.name}
              onChangeText={(text) => setBudgetForm((prev) => ({ ...prev, name: text }))}
            />

            <TextInput
              style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
              placeholder="Monthly limit"
              placeholderTextColor={colors.textSecondary}
              keyboardType="decimal-pad"
              value={budgetForm.monthly_limit}
              onChangeText={(text) => setBudgetForm((prev) => ({ ...prev, monthly_limit: text }))}
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

      {/* Purchase Form Modal */}
      {showPurchaseForm && (
        <View style={[styles.modal, { backgroundColor: colors.background }]}>
          <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
            <Text style={[styles.modalTitle, { color: colors.text }]}>Log Purchase</Text>
            
            <TextInput
              style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
              placeholder="Product name"
              placeholderTextColor={colors.textSecondary}
              value={purchaseForm.product_name}
              onChangeText={(text) => setPurchaseForm((prev) => ({ ...prev, product_name: text }))}
            />

            <TextInput
              style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
              placeholder="Amount"
              placeholderTextColor={colors.textSecondary}
              keyboardType="decimal-pad"
              value={purchaseForm.amount}
              onChangeText={(text) => setPurchaseForm((prev) => ({ ...prev, amount: text }))}
            />

            <TextInput
              style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
              placeholder="Merchant (optional)"
              placeholderTextColor={colors.textSecondary}
              value={purchaseForm.merchant}
              onChangeText={(text) => setPurchaseForm((prev) => ({ ...prev, merchant: text }))}
            />

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={[styles.modalButton, { backgroundColor: colors.border }]}
                onPress={() => setShowPurchaseForm(false)}
              >
                <Text style={[styles.modalButtonText, { color: colors.text }]}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalButton, { backgroundColor: colors.primary }]}
                onPress={logPurchase}
              >
                <Text style={styles.modalButtonText}>Log</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}
    </View>
  );

  const renderAITab = () => (
    <View style={styles.tabContent}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>AI Shopping Advisor</Text>

      <View style={styles.aiModeSelector}>
        {[
          { key: "recommend", label: "Recommend", icon: "bulb" },
          { key: "compare", label: "Compare", icon: "git-compare" },
          { key: "deals", label: "Find Deals", icon: "pricetag" },
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
        style={[styles.aiInput, { backgroundColor: colors.card, color: colors.text, borderColor: colors.border }]}
        placeholder={
          aiMode === "recommend"
            ? "What are you looking for?"
            : aiMode === "compare"
            ? "Enter product names to compare"
            : "Search for deals..."
        }
        placeholderTextColor={colors.textSecondary}
        value={aiInput}
        onChangeText={setAiInput}
        multiline
      />

      <TouchableOpacity
        style={[styles.aiButton, { backgroundColor: colors.primary }]}
        onPress={runAIAdvisor}
        disabled={aiLoading}
      >
        {aiLoading ? (
          <ActivityIndicator color={colors.primaryText} />
        ) : (
          <>
            <Ionicons name="sparkles" size={20} color={colors.primaryText} />
            <Text style={styles.aiButtonText}>Get AI Advice</Text>
          </>
        )}
      </TouchableOpacity>

      {aiResult && (
        <View style={[styles.aiResultCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.aiResultText, { color: colors.text }]}>{aiResult}</Text>
        </View>
      )}
    </View>
  );

  const renderCarbonTab = () => (
    <View style={styles.tabContent}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>Carbon Footprint</Text>

      <View style={[styles.carbonCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <View style={styles.carbonHeader}>
          <Ionicons name="leaf" size={32} color={colors.success} />
          <Text style={[styles.carbonValue, { color: colors.text }]}>
            {carbonReport?.total_carbon_kg?.toFixed(1) || 0} kg CO₂
          </Text>
        </View>
        <Text style={[styles.carbonLabel, { color: colors.textSecondary }]}>
          This month ({carbonReport?.month})
        </Text>
        <Text style={[styles.carbonPurchases, { color: colors.textSecondary }]}>
          From {carbonReport?.total_purchases || 0} purchases
        </Text>
      </View>

      {carbonReport?.category_breakdown && Object.keys(carbonReport.category_breakdown).length > 0 && (
        <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.cardTitle, { color: colors.text }]}>By Category</Text>
          {Object.entries(carbonReport.category_breakdown).map(([category, carbon]: [string, any]) => (
            <View key={category} style={styles.categoryRow}>
              <Text style={[styles.categoryName, { color: colors.text }]}>{category}</Text>
              <Text style={[styles.categoryCarbon, { color: colors.textSecondary }]}>
                {carbon.toFixed(1)} kg CO₂
              </Text>
            </View>
          ))}
        </View>
      )}

      <View style={[styles.infoCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <Ionicons name="information-circle" size={24} color={colors.primary} />
        <Text style={[styles.infoText, { color: colors.textSecondary }]}>
          Track your environmental impact from shopping. Every purchase matters!
        </Text>
      </View>
    </View>
  );

  const renderDealsTab = () => (
    <View style={styles.tabContent}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>Available Deals</Text>

      {deals.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="pricetag-outline" size={64} color={colors.textSecondary} />
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            No deals available yet. Check back soon!
          </Text>
        </View>
      ) : (
        <ScrollView>
          {deals.map((deal, index) => (
            <View
              key={index}
              style={[styles.dealCard, { backgroundColor: colors.card, borderColor: colors.border }]}
            >
              <View style={styles.dealHeader}>
                <Text style={[styles.dealTitle, { color: colors.text }]}>{deal.product_name}</Text>
                <View style={[styles.discountBadge, { backgroundColor: colors.success }]}>
                  <Text style={styles.discountText}>-{deal.discount_pct}%</Text>
                </View>
              </View>
              <View style={styles.dealPrices}>
                <Text style={[styles.dealOriginal, { color: colors.textSecondary }]}>
                  ${deal.original_price}
                </Text>
                <Text style={[styles.dealPrice, { color: colors.success }]}>
                  ${deal.deal_price}
                </Text>
              </View>
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );

  // Helper functions
  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case "high":
        return colors.error;
      case "medium":
        return colors.warning;
      case "low":
        return colors.success;
      default:
        return colors.textMuted;
    }
  };

  const getCategoryColor = (category: string) => {
    const colors_map: Record<string, string> = {
      electronics: colors.primary,
      clothing: colors.primary,
      food: colors.success,
      furniture: colors.warning,
      general: colors.textMuted,
    };
    return colors_map[category] || colors.textMuted;
  };

  const getProgressColor = (percent: number) => {
    if (percent >= 90) return colors.error;
    if (percent >= 80) return colors.warning;
    return colors.success;
  };

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[styles.loadingText, { color: colors.text }]}>
            Loading Smart Shopping Advisor...
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={[styles.header, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
        <View style={styles.headerContent}>
          <Ionicons name="cart" size={32} color={colors.primary} />
          <View style={styles.headerText}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>Smart Shopping</Text>
            <Text style={[styles.headerSubtitle, { color: colors.textSecondary }]}>
              AI-Powered Shopping Intelligence
            </Text>
          </View>
        </View>
      </View>

      {renderKPIDashboard()}
      {renderTabBar()}

      <ScrollView style={styles.content}>
        {activeTab === "wishlists" && renderWishlistsTab()}
        {activeTab === "budgets" && renderBudgetsTab()}
        {activeTab === "deals" && renderDealsTab()}
        {activeTab === "ai" && renderAITab()}
        {activeTab === "carbon" && renderCarbonTab()}
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
    marginBottom: 8,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: "bold",
  },
  cardDescription: {
    fontSize: 14,
    marginBottom: 12,
  },
  badge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    backgroundColor: "var(--app-primary)",
  },
  badgeText: {
    color: "var(--app-primary-text)",
    fontSize: 12,
    fontWeight: "600",
  },
  itemPreview: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    gap: 8,
  },
  itemPreviewText: {
    flex: 1,
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
  },
  modalHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 16,
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
  itemCard: {
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 8,
  },
  itemHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  itemName: {
    fontSize: 16,
    fontWeight: "600",
    flex: 1,
  },
  priorityBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  priorityText: {
    color: "var(--app-primary-text)",
    fontSize: 12,
    fontWeight: "600",
  },
  itemPrice: {
    fontSize: 14,
    fontWeight: "600",
    marginBottom: 4,
  },
  itemTarget: {
    fontSize: 14,
    marginBottom: 4,
  },
  itemNotes: {
    fontSize: 12,
    marginTop: 4,
  },
  formOverlay: {
    padding: 16,
    borderRadius: 8,
    marginTop: 16,
  },
  formTitle: {
    fontSize: 18,
    fontWeight: "bold",
    marginBottom: 12,
  },
  budgetProgress: {
    marginTop: 12,
  },
  budgetStats: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  budgetAmount: {
    fontSize: 18,
    fontWeight: "bold",
  },
  budgetPercent: {
    fontSize: 14,
  },
  progressBar: {
    height: 8,
    borderRadius: 4,
    overflow: "hidden",
    marginBottom: 8,
  },
  progressFill: {
    height: "100%",
  },
  remaining: {
    fontSize: 14,
    fontWeight: "600",
  },
  actionButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 14,
    borderRadius: 8,
    marginTop: 16,
    gap: 8,
  },
  actionButtonText: {
    color: "var(--app-primary-text)",
    fontSize: 16,
    fontWeight: "600",
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
    gap: 8,
  },
  modeLabel: {
    fontSize: 14,
    fontWeight: "600",
  },
  aiInput: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 16,
    minHeight: 100,
    textAlignVertical: "top",
    marginBottom: 16,
  },
  aiButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 14,
    borderRadius: 8,
    gap: 8,
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
  },
  aiResultText: {
    fontSize: 14,
    lineHeight: 20,
  },
  carbonCard: {
    padding: 24,
    borderRadius: 12,
    borderWidth: 1,
    alignItems: "center",
    marginBottom: 16,
  },
  carbonHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginBottom: 8,
  },
  carbonValue: {
    fontSize: 32,
    fontWeight: "bold",
  },
  carbonLabel: {
    fontSize: 14,
    marginBottom: 4,
  },
  carbonPurchases: {
    fontSize: 14,
  },
  categoryRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 8,
  },
  categoryName: {
    fontSize: 16,
    fontWeight: "500",
    textTransform: "capitalize",
  },
  categoryCarbon: {
    fontSize: 16,
  },
  infoCard: {
    flexDirection: "row",
    alignItems: "center",
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginTop: 16,
    gap: 12,
  },
  infoText: {
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
  dealCard: {
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
  },
  dealHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  dealTitle: {
    fontSize: 16,
    fontWeight: "600",
    flex: 1,
  },
  discountBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  discountText: {
    color: "var(--app-primary-text)",
    fontSize: 14,
    fontWeight: "bold",
  },
  dealPrices: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  dealOriginal: {
    fontSize: 16,
    textDecorationLine: "line-through",
  },
  dealPrice: {
    fontSize: 20,
    fontWeight: "bold",
  },
});
