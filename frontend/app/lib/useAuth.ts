"use client";

import { useContext } from "react";
import { AuthContext } from "./AuthContext";

/**
 * Returns the current auth context value.
 * Must be used inside <AuthProvider>.
 */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an <AuthProvider>.");
  }
  return ctx;
}
