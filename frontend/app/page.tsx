"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./lib/useAuth";

const FEATURES = [
  {
    href: "/scan",
    icon: "🔬",
    title: "Crop Scanner",
    blurb: "Visual disease diagnosis.",
  },
  {
    href: "/irrigation",
    icon: "💧",
    title: "Smart Irrigation",
    blurb: "Custom watering schedules.",
  },
  {
    href: "/yield-estimator",
    icon: "📊",
    title: "Yield Estimator",
    blurb: "Forecast harvest from acreage and inputs.",
  },
  {
    href: "/market",
    icon: "📈",
    title: "Market Insights",
    blurb: "Track crop prices and trends.",
  },
] as const;

export default function HomePage() {
  const router = useRouter();
  const { token, user, isLoading } = useAuth();

  useEffect(() => {
    if (isLoading) return;
    if (token || user) {
      router.replace("/scan");
    }
  }, [isLoading, token, user, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-sm font-medium text-slate-500">Loading…</p>
      </div>
    );
  }

  if (token || user) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-sm font-medium text-slate-500">Taking you to the scanner…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center mx-auto max-w-6xl w-full py-16 px-4">
      <section className="flex flex-col items-center text-center mt-12">
        <h1 className="text-4xl md:text-5xl font-bold text-white tracking-tight">
          Smart Agriculture, Simplified.
        </h1>
        <p className="text-slate-400 text-lg max-w-xl mt-3">
          AI-powered crop diagnosis, precision irrigation, and yield forecasting in one clean dashboard.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3 mt-8">
          <Link
            href="/login"
            className="bg-emerald-600 hover:bg-emerald-500 text-white px-5 py-2.5 rounded-lg font-medium transition-colors"
          >
            Sign In
          </Link>
          <Link
            href="/signup"
            className="bg-slate-800 hover:bg-slate-700 text-slate-200 px-5 py-2.5 rounded-lg font-medium border border-slate-700 transition-colors"
          >
            Create Account
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-12 w-full">
        {FEATURES.map(({ href, icon, title, blurb }) => (
          <Link
            key={href}
            href="/login"
            className="group flex flex-col items-start gap-2 rounded-xl border border-slate-800 bg-slate-900/50 p-5 transition-all hover:bg-slate-800/80 hover:border-slate-700"
          >
            <span className="text-2xl mb-1" aria-hidden="true">
              {icon}
            </span>
            <h2 className="text-base font-semibold text-slate-200 group-hover:text-white transition-colors">
              {title}
            </h2>
            <p className="text-sm text-slate-400">{blurb}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}
