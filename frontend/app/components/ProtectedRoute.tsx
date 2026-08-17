"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../lib/useAuth";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { token, user, isLoading } = useAuth();
  const didRedirectRef = useRef(false);

  useEffect(() => {
    if (isLoading) return;

    const hasSession = Boolean(token) || Boolean(user);
    if (hasSession) return;
    if (didRedirectRef.current) return;

    didRedirectRef.current = true;
    window.alert("Please log in to access this feature.");
    router.push("/login");
  }, [isLoading, token, user, router]);

  if (isLoading) return null;

  const hasSession = Boolean(token) || Boolean(user);
  if (!hasSession) return null;

  return <>{children}</>;
}

