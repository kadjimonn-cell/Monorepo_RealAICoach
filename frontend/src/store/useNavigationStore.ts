import { create } from 'zustand';
import { Platform } from 'react-native';

interface NavigationState {
  stack: string[];
  index: number;
  popstateTriggered: boolean;
  canGoBack: boolean;
  canGoForward: boolean;
  initialized: boolean;
  onPopState: () => void;
  onPathChange: (path: string) => void;
  goBack: () => void;
  goForward: () => void;
}

export const useNavigationStore = create<NavigationState>((set, get) => ({
  stack: [],
  index: -1,
  popstateTriggered: false,
  canGoBack: false,
  canGoForward: false,
  initialized: false,

  onPopState: () => {
    set({ popstateTriggered: true });
  },

  onPathChange: (path: string) => {
    const { stack, index, popstateTriggered, initialized } = get();

    if (!initialized) {
      set({
        stack: [path],
        index: 0,
        initialized: true,
        popstateTriggered: false,
        canGoBack: false,
        canGoForward: false,
      });
      return;
    }

    // Skip if same path as current
    if (stack[index] === path && !popstateTriggered) return;

    if (popstateTriggered) {
      // Back or forward via browser or our buttons
      // Check adjacent positions first
      if (index > 0 && stack[index - 1] === path) {
        const newIndex = index - 1;
        set({
          index: newIndex,
          popstateTriggered: false,
          canGoBack: newIndex > 0,
          canGoForward: newIndex < stack.length - 1,
        });
        return;
      }
      if (index < stack.length - 1 && stack[index + 1] === path) {
        const newIndex = index + 1;
        set({
          index: newIndex,
          popstateTriggered: false,
          canGoBack: newIndex > 0,
          canGoForward: newIndex < stack.length - 1,
        });
        return;
      }
      // Search broader (multi-step back/forward)
      for (let i = index - 2; i >= 0; i--) {
        if (stack[i] === path) {
          set({
            index: i,
            popstateTriggered: false,
            canGoBack: i > 0,
            canGoForward: i < stack.length - 1,
          });
          return;
        }
      }
      for (let i = index + 2; i < stack.length; i++) {
        if (stack[i] === path) {
          set({
            index: i,
            popstateTriggered: false,
            canGoBack: i > 0,
            canGoForward: i < stack.length - 1,
          });
          return;
        }
      }
      // Fallback: treat as new push
      set({ popstateTriggered: false });
    }

    // Regular push navigation — truncate forward stack and add new path
    const newStack = stack.slice(0, index + 1);
    newStack.push(path);
    const newIndex = newStack.length - 1;
    set({
      stack: newStack,
      index: newIndex,
      canGoBack: newIndex > 0,
      canGoForward: false,
    });
  },

  goBack: () => {
    if (get().canGoBack && Platform.OS === 'web' && typeof window !== 'undefined') {
      window.history.back();
    }
  },

  goForward: () => {
    if (get().canGoForward && Platform.OS === 'web' && typeof window !== 'undefined') {
      window.history.forward();
    }
  },
}));
