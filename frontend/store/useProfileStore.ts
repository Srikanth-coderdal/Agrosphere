import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import { ProfileState, ProfileActions, ProfileMode, UserProfile } from '@/types/profile';

const STORAGE_KEY = 'agrosphere-profile-mode';

export type ProfileStore = ProfileState & ProfileActions;

const useProfileStore = create<ProfileStore>()(
  devtools(
    persist(
      (set, get) => ({
        // ─── State ───────────────────────────────────────────
        profileMode: 'FIELD_AG',
        userProfile: null,
        isHydrated: false,
        language: 'en',

        // ─── Actions ─────────────────────────────────────────
        setProfileMode: (mode: ProfileMode) => {
          set((state) => {
            const updatedUserProfile = state.userProfile
              ? { ...state.userProfile, profileMode: mode, updatedAt: new Date().toISOString() }
              : null;
            return {
              profileMode: mode,
              userProfile: updatedUserProfile,
            };
          });
        },

        toggleProfileMode: () => {
          const next: ProfileMode = get().profileMode === 'FIELD_AG' ? 'URBAN_GARDEN' : 'FIELD_AG';
          get().setProfileMode(next);
        },

        setUserProfile: (profile: UserProfile) => {
          set({ userProfile: profile, profileMode: profile.profileMode });
        },

        clearUserProfile: () => {
          set({ userProfile: null, profileMode: 'FIELD_AG' });
        },

        hydrate: () => {
          set({ isHydrated: true });
        },

        toggleLanguage: () => {
          set((state) => ({ language: state.language === 'en' ? 'ta' : 'en' }));
        },
      }),
      {
        name: STORAGE_KEY,
        // Only persist the mode and profile; isHydrated is runtime-only.
        partialize: (state) => ({
          profileMode: state.profileMode,
          userProfile: state.userProfile,
          language: state.language,
        }),
      }
    ),
    { name: 'ProfileStore' }
  )
);

export default useProfileStore;
