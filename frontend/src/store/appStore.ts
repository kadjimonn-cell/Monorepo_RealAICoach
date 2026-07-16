import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createJSONStorage, persist } from 'zustand/middleware.js';
import { v4 as uuidv4 } from 'uuid';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

export interface AppScenario {
  id?: string;
  title?: string;
  [key: string]: unknown;
}

interface PersistedAppState {
  userId?: string;
  currentConversationId?: string | null;
  currentScenario?: AppScenario | null;
}

const APP_STORE_VERSION = 3;

const generateUserId = () => `user_${uuidv4().replace(/-/g, '')}`;

interface AppState {
  userId: string;
  currentConversationId: string | null;
  currentScenario: AppScenario | null;
  hasHydrated: boolean;
  _hasHydrated: boolean;
  setUserId: (id: string) => Promise<void>;
  setCurrentConversation: (id: string | null) => void;
  setCurrentScenario: (scenario: AppScenario | null) => void;
  setHasHydrated: (value: boolean) => void;
  initializeUser: () => Promise<void>;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      userId: '',
      currentConversationId: null,
      currentScenario: null,
      hasHydrated: false,
      _hasHydrated: false,

      setUserId: async (id: string) => {
        set({ userId: id });
        try {
          await AsyncStorage.setItem('realtalk_user_id', id);
        } catch (error) {
          console.warn('appStore.setUserId persistence failed:', error);
        }
      },

      setCurrentConversation: (id: string | null) => set({ currentConversationId: id }),

      setCurrentScenario: (scenario: AppScenario | null) => set({ currentScenario: scenario }),

      setHasHydrated: (value: boolean) => set({ hasHydrated: value, _hasHydrated: value }),

      initializeUser: async () => {
        try {
          if (get().userId) return;

          // Legacy migration support from pre-persist key.
          let userId = await AsyncStorage.getItem('realtalk_user_id');
          if (!userId) {
            userId = generateUserId();
          }

          set({ userId });
          await AsyncStorage.setItem('realtalk_user_id', userId);
        } catch (error) {
          console.error('Error initializing user:', error);
          const userId = generateUserId();
          set({ userId });
          try {
            await AsyncStorage.setItem('realtalk_user_id', userId);
          } catch (error) { handleAppRecoverableError({ scope: 'src/store/appStore.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        }
      },
    }),
    {
      name: 'realtalk_app_store',
      storage: createJSONStorage(() => AsyncStorage),
      version: APP_STORE_VERSION,
      migrate: (persistedState: unknown, _version: number) => {
        const state = (persistedState && typeof persistedState === 'object'
          ? persistedState
          : {}) as PersistedAppState;

        const normalizedScenario =
          state.currentScenario && typeof state.currentScenario === 'object'
            ? state.currentScenario
            : null;

        return {
          userId: typeof state.userId === 'string' ? state.userId : '',
          currentConversationId:
            typeof state.currentConversationId === 'string' || state.currentConversationId === null
              ? state.currentConversationId
              : null,
          currentScenario: normalizedScenario,
          hasHydrated: false,
          _hasHydrated: false,
        };
      },
      partialize: (state) => ({
        userId: state.userId,
        currentConversationId: state.currentConversationId,
        currentScenario: state.currentScenario,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);
