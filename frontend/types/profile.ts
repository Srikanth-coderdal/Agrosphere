/**
 * Profile mode type — isolates Field Ag and Urban Gardening workflows.
 * Stored in auth state and used to gate feature visibility/API behavior.
 */
export type ProfileMode = 'FIELD_AG' | 'URBAN_GARDEN';

/**
 * A user's profile metadata.
 */
export interface UserProfile {
  id: string;
  name: string;
  email: string;
  profileMode: ProfileMode;
  /** ISO timestamp of the last profile update. */
  updatedAt: string;
}

/**
 * Mutable profile state managed by the ProfileContext/Zustand store.
 */
export interface ProfileState {
  profileMode: ProfileMode;
  userProfile: UserProfile | null;
  /** Whether the profile is still being resolved from storage/auth. */
  isHydrated: boolean;
  language: 'en' | 'ta';
}

/**
 * Actions exposed by the profile store.
 */
export interface ProfileActions {
  setProfileMode: (mode: ProfileMode) => void;
  toggleProfileMode: () => void;
  setUserProfile: (profile: UserProfile) => void;
  clearUserProfile: () => void;
  hydrate: () => void;
  toggleLanguage: () => void;
}
