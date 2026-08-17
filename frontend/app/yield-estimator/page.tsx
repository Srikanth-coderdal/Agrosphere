"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import ProtectedRoute from "../components/ProtectedRoute";

function RedirectTo({ target }: { target: string }) {
  const router = useRouter();

  useEffect(() => {
    router.replace(target);
  }, [router, target]);

  return null;
}

export default function YieldEstimatorAliasPage() {
  return (
    <ProtectedRoute>
      <RedirectTo target="/yield" />
    </ProtectedRoute>
  );
}

