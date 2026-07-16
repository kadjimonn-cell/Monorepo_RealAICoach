import { Ionicons } from '@expo/vector-icons';

export interface Feature {
  id: string;
  title: string;
  description: string;
  icon: keyof typeof Ionicons.glyphMap;
  route: string;
  category: string;
  color: string;
  isNew?: boolean;
  premium?: boolean;
}

// GPS-only architecture: hardcoded feature definitions are intentionally disabled.
export const FEATURES: Feature[] = [];
export const CATEGORIES: { id: string; label: string }[] = [];
