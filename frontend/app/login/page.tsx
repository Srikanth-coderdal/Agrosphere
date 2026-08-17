"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { loginUser, fetchCurrentUser } from "../lib/api";
import { useAuth } from "../lib/useAuth";

/* ── Shared input style ─────────────────────────────────────────────── */
const inputCls =
  "w-full rounded-xl border border-emerald-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition-colors focus:border-emerald-500 focus:ring-2 disabled:cursor-not-allowed disabled:opacity-50";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email.trim() || !password) {
      setError("Please enter your email and password.");
      return;
    }

    setIsLoading(true);
    try {
      const { access_token } = await loginUser(email.trim(), password);
      const user = await fetchCurrentUser(access_token);
      login(access_token, user);
      router.push("/scan");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-4">
      <div
        className="w-full max-w-md rounded-3xl border p-8 shadow-xl"
        style={{
          borderColor: "color-mix(in srgb,var(--primary) 20%,transparent)",
          background: "color-mix(in srgb,var(--primary) 3%,white)",
        }}
      >
        {/* Header */}
        <div className="mb-8 flex flex-col items-center gap-2 text-center">
          <span className="text-5xl" aria-hidden="true">🌾</span>
          <h1 className="text-2xl font-extrabold" style={{ color: "var(--primary)" }}>
            Welcome back
          </h1>
          <p className="text-sm" style={{ color: "var(--foreground)", opacity: 0.55 }}>
            Sign in to your Agrosphere account
          </p>
        </div>

        {/* Form */}
        <form id="login-form" onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
          {/* Email */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="login-email"
              className="text-xs font-semibold uppercase tracking-wide"
              style={{ color: "var(--primary)" }}
            >
              Email Address
            </label>
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              placeholder="farmer@agrosphere.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isLoading}
              className={inputCls}
              style={{ color: "var(--foreground)" }}
              required
            />
          </div>

          {/* Password */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="login-password"
              className="text-xs font-semibold uppercase tracking-wide"
              style={{ color: "var(--primary)" }}
            >
              Password
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              className={inputCls}
              style={{ color: "var(--foreground)" }}
              required
            />
          </div>

          {/* Error */}
          {error && (
            <p
              role="alert"
              className="flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium"
              style={{
                background: "color-mix(in srgb,#ef4444 10%,transparent)",
                color: "#b91c1c",
              }}
            >
              ⚠️ {error}
            </p>
          )}

          {/* Submit */}
          <button
            id="login-submit-btn"
            type="submit"
            disabled={isLoading}
            aria-busy={isLoading}
            className="mt-2 flex w-full items-center justify-center gap-2.5 rounded-2xl px-6 py-3.5 text-sm font-bold text-white shadow-lg transition-all duration-200 hover:brightness-110 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: "linear-gradient(135deg,var(--primary),var(--primary-dk))" }}
          >
            {isLoading ? (
              <>
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
                Signing in…
              </>
            ) : (
              "Sign In"
            )}
          </button>
        </form>

        {/* Footer */}
        <p className="mt-6 text-center text-sm" style={{ color: "var(--foreground)", opacity: 0.55 }}>
          Don&apos;t have an account?{" "}
          <Link
            href="/signup"
            className="font-semibold underline-offset-2 hover:underline"
            style={{ color: "var(--primary)" }}
          >
            Create one free
          </Link>
        </p>
      </div>
    </div>
  );
}
