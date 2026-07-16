import type { ComponentProps } from "react";
import type { Ionicons } from "@expo/vector-icons";

type IconName = ComponentProps<typeof Ionicons>["name"];

export type NotificationCategory = "meetings" | "hiring" | "system" | "general";
export type Filter = "all" | "unread" | NotificationCategory;

const AVATAR_URLS = [
  "https://images.unsplash.com/photo-1639149888905-fb39731f2e6c?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1MDZ8MHwxfHNlYXJjaHwzfHxwZXJzb24lMjBhdmF0YXJ8ZW58MHx8fHwxNzc1MDA4MDMyfDA&ixlib=rb-4.1.0&q=85",
  "https://images.unsplash.com/photo-1630910561339-4e22c7150093?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1MDZ8MHwxfHNlYXJjaHw0fHxwZXJzb24lMjBhdmF0YXJ8ZW58MHx8fHwxNzc1MDA4MDMyfDA&ixlib=rb-4.1.0&q=85",
  "https://images.unsplash.com/photo-1623582854588-d60de57fa33f?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1MDZ8MHwxfHNlYXJjaHwxfHxwZXJzb24lMjBhdmF0YXJ8ZW58MHx8fHwxNzc1MDA4MDMyfDA&ixlib=rb-4.1.0&q=85",
];

export const EMPTY_IMAGE = "https://images.unsplash.com/photo-1760336472685-4c3f0dd8d204?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMjh8MHwxfHNlYXJjaHwzfHxhYnN0cmFjdCUyMDNkJTIwZ2VvbWV0cmljJTIwc2hhcGVzJTIwc29mdCUyMGxpZ2h0aW5nJTIwbWluaW1hbGlzdHxlbnwwfHx8fDE3NzQzMjc1Mjl8MA&ixlib=rb-4.1.0&q=85";

export type VisualConfig = {
  name: IconName;
  color: string;
  category: NotificationCategory;
  accent: string;
  avatarUrl?: string;
};

export const TYPE_VISUAL: Record<string, VisualConfig> = {
  new_content: { name: "sparkles", color: "#4F46E5", category: "general", accent: "#EEF2FF" },
  expiring_soon: { name: "time", color: "#CA8A04", category: "system", accent: "#FEF9C3" },
  trending: { name: "trending-up", color: "#16A34A", category: "general", accent: "#DCFCE7" },
  new_booking: { name: "calendar", color: "#0F766E", category: "meetings", accent: "#DBEAFE" },
  booking_created: { name: "calendar", color: "#0F766E", category: "meetings", accent: "#DBEAFE" },
  booking_cancelled: { name: "close-circle", color: "#DC2626", category: "meetings", accent: "#FEE2E2" },
  booking_cancelled_by_host: { name: "close-circle", color: "#DC2626", category: "meetings", accent: "#FEE2E2" },
  booking_rescheduled: { name: "swap-horizontal", color: "#CA8A04", category: "meetings", accent: "#FEF3C7" },
  agenda_reminder: { name: "alarm", color: "#0F766E", category: "meetings", accent: "#DBEAFE" },
  meeting_reminder: { name: "alarm", color: "#0F766E", category: "meetings", accent: "#DBEAFE" },
  team_invite: { name: "people", color: "#4F46E5", category: "system", accent: "#EEF2FF", avatarUrl: AVATAR_URLS[0] },
  team_event: { name: "people-circle", color: "#4F46E5", category: "system", accent: "#EEF2FF", avatarUrl: AVATAR_URLS[1] },
  employer_approved: { name: "checkmark-circle", color: "#16A34A", category: "hiring", accent: "#DCFCE7" },
  employer_denied: { name: "close-circle", color: "#DC2626", category: "hiring", accent: "#FEE2E2" },
  employer_pending: { name: "hourglass", color: "#CA8A04", category: "hiring", accent: "#FEF3C7" },
  employer_need_info: { name: "information-circle", color: "#4F46E5", category: "hiring", accent: "#EEF2FF" },
  interview_scheduled: { name: "videocam", color: "#0F766E", category: "hiring", accent: "#DBEAFE" },
  ai_recommendation: { name: "sparkles", color: "#4F46E5", category: "hiring", accent: "#EEF2FF" },
  daily_briefing: { name: "sunny", color: "#CA8A04", category: "system", accent: "#FEF3C7" },
  weekly_ai_report: { name: "analytics", color: "#4F46E5", category: "system", accent: "#EEF2FF" },
  payment_confirmation: { name: "card", color: "#16A34A", category: "system", accent: "#DCFCE7" },
  admin_payment_alert: { name: "shield-checkmark", color: "#16A34A", category: "system", accent: "#DCFCE7" },
  kyc_verified: { name: "shield-checkmark", color: "#16A34A", category: "system", accent: "#DCFCE7" },
  kyc_pending_review: { name: "shield-half", color: "#CA8A04", category: "system", accent: "#FEF3C7" },
  nightly_categorization: { name: "moon", color: "#4F46E5", category: "system", accent: "#EEF2FF" },
  referral_signup: { name: "person-add", color: "#0F766E", category: "general", accent: "#DBEAFE", avatarUrl: AVATAR_URLS[2] },
  referral_subscription: { name: "cash", color: "#16A34A", category: "general", accent: "#DCFCE7", avatarUrl: AVATAR_URLS[1] },
  referral_credit_applied: { name: "wallet", color: "#4F46E5", category: "general", accent: "#EEF2FF", avatarUrl: AVATAR_URLS[0] },
  platform_integrity_alert: { name: "shield", color: "#DC2626", category: "system", accent: "#FEE2E2" },
  critical_journey_monitor_incident: { name: "warning", color: "#DC2626", category: "system", accent: "#FEE2E2" },
  self_repair: { name: "build", color: "#0F766E", category: "system", accent: "#DBEAFE" },
  general: { name: "notifications", color: "#0F766E", category: "general", accent: "#EFF6FF" },
};

export function getNotificationVisual(notification: any): VisualConfig {
  return TYPE_VISUAL[notification?.type || "general"] || TYPE_VISUAL.general;
}

export function timeAgo(dateStr?: string) {
  if (!dateStr) return "just now";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export function getGroupLabel(dateStr?: string) {
  if (!dateStr) return "Today";
  const date = new Date(dateStr);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const diffDays = Math.floor((today - target) / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return "Last 7 Days";
  return "Earlier";
}
