"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Scan, Droplets, TrendingUp, Sprout, Globe, LogOut, LogIn, UserPlus } from "lucide-react";
import { useAuth } from "@/app/lib/useAuth";
import useProfileStore from "@/store/useProfileStore";
import ProfileSwitcher from "./ProfileSwitcher";
import { getMessages } from "@/app/lib/i18n";

interface SidebarProps {
  onItemClick?: () => void;
  isMobile?: boolean;
}

export const NAV_ITEMS = [
  { key: "cropScanner", label: "Crop Scanner", href: "/scan", icon: Scan },
  { key: "irrigation", label: "Smart Irrigation", href: "/irrigation", icon: Droplets },
  { key: "yield", label: "Yield Optimizer", href: "/yield-estimator", icon: TrendingUp },
  { key: "urban", label: "Urban Gardening", href: "/urban", icon: Sprout },
];

export default function Sidebar({ onItemClick, isMobile = false }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading, logout } = useAuth();
  const { language, toggleLanguage } = useProfileStore();
  const msg = getMessages(language);
  const nav = msg?.nav ?? msg?.navbar;

  const handleLogout = async () => {
    await logout();
    if (onItemClick) onItemClick();
    router.push("/login");
  };

  return (
    <div className="flex flex-col h-full justify-between gap-6 overflow-y-auto">
      {/* Top Section */}
      <div className="flex flex-col gap-6">
        {/* Brand Header */}
        <Link
          href="/"
          onClick={onItemClick}
          className="flex items-center gap-2.5 text-2xl font-bold tracking-tight text-emerald-800 dark:text-emerald-400"
        >
          <span className="text-2xl" aria-hidden="true">🌾</span>
          <span>Agrosphere</span>
        </Link>

        {/* Mode Toggle Switcher Card */}
        <ProfileSwitcher />

        {/* Navigation Menu */}
        <nav className="flex flex-col gap-1.5" aria-label="Main Navigation">
          {NAV_ITEMS.map(({ key, label, href, icon: Icon }) => {
            const isActive = pathname === href;
            const translatedLabel =
              (msg?.nav && (msg.nav as any)[key]) ||
              (nav && (nav as any)[key]) ||
              label;

            return (
              <Link
                key={href}
                href={href}
                onClick={onItemClick}
                className={`p-3 rounded-xl flex items-center gap-3 transition-colors text-sm font-medium ${
                  isActive
                    ? "bg-emerald-50 text-emerald-700 font-semibold dark:bg-emerald-950/40 dark:text-emerald-400"
                    : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                <Icon className="w-5 h-5 shrink-0" />
                <span className="truncate">{translatedLabel}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Bottom Section */}
      <div className="flex flex-col gap-4 pt-4 border-t border-slate-200 dark:border-slate-800 mt-auto">
        {/* Auth status / action */}
        {!isLoading && !user && (
          <div className="flex flex-col gap-2">
            <Link
              href="/login"
              onClick={onItemClick}
              className="flex items-center justify-center gap-2 w-full p-2.5 rounded-xl border border-emerald-200 dark:border-emerald-800 text-sm font-semibold text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 transition-colors"
            >
              <LogIn className="w-4 h-4" />
              <span>{msg?.nav?.signIn || nav?.signIn || "Sign In"}</span>
            </Link>
            <Link
              href="/signup"
              onClick={onItemClick}
              className="flex items-center justify-center gap-2 w-full p-2.5 rounded-xl text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 transition-colors shadow-sm"
            >
              <UserPlus className="w-4 h-4" />
              <span>{msg?.nav?.getStarted || nav?.getStarted || "Get Started"}</span>
            </Link>
          </div>
        )}

        {!isLoading && user && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-3 px-3 py-2 rounded-xl bg-slate-100 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700">
              <div className="h-8 w-8 rounded-full bg-emerald-100 dark:bg-emerald-900/60 flex items-center justify-center text-emerald-700 dark:text-emerald-300 font-bold text-xs shrink-0">
                {user.full_name?.charAt(0)?.toUpperCase() || "U"}
              </div>
              <div className="flex flex-col min-w-0 overflow-hidden">
                <span className="text-xs font-bold truncate text-slate-800 dark:text-slate-100">
                  {user.full_name}
                </span>
                <span className="text-[11px] text-slate-500 dark:text-slate-400 truncate">
                  {user.email}
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={handleLogout}
              className="flex items-center gap-3 w-full p-3 rounded-xl text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors text-sm font-medium mt-auto cursor-pointer"
            >
              <LogOut className="w-5 h-5 shrink-0" />
              <span>{msg?.nav?.logout || nav?.logout || "Log Out"}</span>
            </button>
          </div>
        )}

        {/* Language Controls */}
        <div className="flex items-center justify-between pt-4 border-t border-slate-200 dark:border-slate-800 mt-auto">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-600 dark:text-slate-400">
            <Globe className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span>Language</span>
          </div>
          <div className="flex rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-1">
            <button
              type="button"
              onClick={toggleLanguage}
              className={`rounded-lg px-2.5 py-1 text-xs font-bold transition-colors cursor-pointer ${
                language === "en"
                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 shadow-xs"
                  : "bg-transparent text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
              }`}
              aria-pressed={language === "en"}
            >
              EN
            </button>
            <button
              type="button"
              onClick={toggleLanguage}
              className={`rounded-lg px-2.5 py-1 text-xs font-bold transition-colors cursor-pointer ${
                language === "ta"
                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 shadow-xs"
                  : "bg-transparent text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
              }`}
              aria-pressed={language === "ta"}
            >
              தமிழ்
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
