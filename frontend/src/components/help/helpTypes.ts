export interface ChatMessage {
  id: string;
  message_id?: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  attachment?: { url: string; filename: string; content_type: string };
  transcription?: string;
  gps_context?: {
    gps_source?: string;
    gps_live?: boolean;
    gps_version?: number;
    gps_updated_at?: string;
    gps_freshness_sec?: number | null;
    gps_counts?: { features?: number; plans?: number; faq?: number; knowledge_docs?: number };
    gps_failed_checks?: string[];
  };
  feedback_submitted?: boolean;
}

export interface FAQItem {
  q: string;
  a: string;
  category: string;
}

export type TabKey = 'support' | 'faq' | 'features' | 'contact';
export type ContactMode = 'chat' | 'email';

export type SupportCategory = 'general' | 'billing' | 'technical' | 'account' | 'feature_request' | 'bug' | 'other';
export type SupportPriority = 'low' | 'medium' | 'high' | 'critical';

export interface SupportAttachmentDraft {
  id: string;
  name: string;
  type: string;
  size: number;
  file?: any;
}

export interface SupportDuplicateHint {
  ticket_id: string;
  subject: string;
  status: string;
  created_at?: string;
  similarity: number;
}

export interface SupportFAQHint {
  question: string;
  answer: string;
  category?: string;
}

export interface SupportInsights {
  total_tickets: number;
  open_tickets: number;
  avg_response_hours: number | null;
  last_ticket: { ticket_id: string; status: string; created_at?: string } | null;
}

export interface SupportAISuggestion {
  subject: string;
  message: string;
  category: SupportCategory;
  priority: SupportPriority;
  confidence: number;
  source: string;
  intent?: string;
}

export interface ThemeColors {
  primary: string;
  bg: string;
  bgSoft: string;
  card: string;
  text: string;
  textSec: string;
  textMuted: string;
  border: string;
  success: string;
  warning: string;
  error: string;
  violet: string;
}
