"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "../lib/useAuth";
import { useLanguage } from "../lib/useLanguage";
import { getMessages } from "../lib/i18n";

const NAV_LINKS = [
  { key: "cropScanner", href: "/scan", icon: "🔬" },
  { key: "irrigation", href: "/irrigation", icon: "💧" },
  { key: "yield", href: "/yield", icon: "📈" },
  { key: "urban", href: "/urban", icon: "🏙️" },
];

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const { user, isLoading, logout } = useAuth();
  const { language, setLanguage, isLoading: isLangLoading } = useLanguage();
  const msg = getMessages(language);
  const nav = msg?.nav ?? msg?.navbar;

  const handleLogout = () => {
    logout();
    setMenuOpen(false);
    router.push("/");
  };

  return (
    <>
      {/* Desktop Persistent Left Sidebar */}
      <aside className="hidden md:flex md:w-64 md:flex-col md:fixed md:inset-y-0 md:border-r md:bg-white border-emerald-100 dark:border-emerald-950 p-6 z-40">
        <div className="flex flex-col h-full justify-between">
          <div>
            {/* Logo/Brand */}
            <Link
              href="/"
              className="flex items-center gap-2 text-2xl font-bold tracking-tight mb-8"
              style={{ color: "var(--primary)" }}
            >
              <span aria-hidden="true">🌾</span>
              <span>Agrosphere</span>
            </Link>

            {/* Navigation links - vertical column */}
            <nav className="flex flex-col gap-2" aria-label="Sidebar navigation">
              {NAV_LINKS.map(({ key, href, icon }) => (
                <Link
                  key={href}
                  href={href}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition-all ${
                    pathname === href
                      ? "bg-emerald-50 text-emerald-700 shadow-sm border border-emerald-100"
                      : "text-slate-700 hover:bg-slate-50 hover:text-emerald-600"
                  }`}
                >
                  <span className="text-lg" aria-hidden="true">{icon}</span>
                  <span>{(msg?.nav && (msg.nav as any)[key]) || (nav && (nav as any)[key]) || key}</span>
                </Link>
              ))}
            </nav>
          </div>

          {/* Language selector */}
          <div className="border-t border-slate-100 pt-6">
            <div className="flex items-center justify-between gap-4">
              <span className="text-xs font-semibold" style={{ color: "var(--primary)" }}>
                🌐
              </span>
              <div className="flex rounded-xl border border-slate-200 bg-white p-1">
                <button
                  type="button"
                  onClick={() => setLanguage("en")}
                  disabled={isLangLoading}
                  className={`rounded-lg px-3 py-1 text-xs font-bold transition-colors ${
                    language === "en"
                      ? "bg-emerald-50 text-emerald-700"
                      : "bg-transparent text-slate-700 hover:bg-slate-50"
                  }`}
                  aria-pressed={language === "en"}
                >
                  EN
                </button>
                <button
                  type="button"
                  onClick={() => setLanguage("ta")}
                  disabled={isLangLoading}
                  className={`rounded-lg px-3 py-1 text-xs font-bold transition-colors ${
                    language === "ta"
                      ? "bg-emerald-50 text-emerald-700"
                      : "bg-transparent text-slate-700 hover:bg-slate-50"
                  }`}
                  aria-pressed={language === "ta"}
                >
                  தமிழ்
                </button>
              </div>
            </div>
          </div>

          {/* User Auth Zone - bottom of sidebar */}
          <div className="pt-6">
            {!isLoading && !user && (
              <div className="flex flex-col gap-3">
                <Link
                  href="/login"
                  className="flex items-center justify-center w-full py-2.5 rounded-xl border border-emerald-100 text-sm font-bold transition-all text-emerald-700 hover:bg-emerald-50"
                >
                  {msg?.nav?.signIn || nav?.signIn || "Sign In"}
                </Link>
                <Link
                  href="/signup"
                  className="flex items-center justify-center w-full py-2.5 rounded-xl text-sm font-bold text-white transition-all hover:brightness-110"
                  style={{ background: "var(--primary)" }}
                >
                  {msg?.nav?.getStarted || nav?.getStarted || "Get Started"}
                </Link>
              </div>
            )}
            {!isLoading && user && (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2 px-2 py-1">
                  <span className="text-xl" aria-hidden="true">👤</span>
                  <div className="flex flex-col overflow-hidden">
                    <span className="text-sm font-bold truncate text-slate-800">{user.full_name}</span>
                    <span className="text-xs text-slate-500 truncate">{user.email}</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="flex items-center justify-center w-full py-2.5 rounded-xl border border-red-100 text-sm font-bold transition-all text-red-600 hover:bg-red-50"
                >
                  🚪 {msg?.nav?.logout || nav?.logout || "Logout"}
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Mobile Top Navbar */}
      <header className="sticky top-0 z-50 w-full nav-glass md:hidden">
        <nav
          className="flex items-center justify-between px-4 py-3 sm:px-6"
          aria-label="Main navigation"
        >
          {/* Brand */}
          <Link
            href="/"
            className="flex items-center gap-2 text-xl font-bold tracking-tight"
            style={{ color: "var(--primary)" }}
          >
            <span aria-hidden="true">🌾</span>
            <span>Agrosphere</span>
          </Link>

          {/* Hamburger menu toggle */}
          <button
            type="button"
            className="inline-flex items-center justify-center rounded-md p-2"
            style={{ color: "var(--primary)" }}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
            onClick={() => setMenuOpen((prev) => !prev)}
          >
            {menuOpen ? (
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </nav>

        {/* Mobile dropdown */}
        <div
          id="mobile-menu"
          className={`mobile-menu${menuOpen ? " open" : ""}`}
          aria-hidden={!menuOpen}
        >
          {NAV_LINKS.map(({ key, href, icon }) => (
            <Link
              key={href}
              href={href}
              className={`mobile-nav-link${pathname === href ? " active" : ""}`}
              onClick={() => setMenuOpen(false)}
            >
              <span aria-hidden="true">{icon}</span>
              {(msg?.nav && (msg.nav as any)[key]) || (nav && (nav as any)[key]) || key}
            </Link>
          ))}

          {/* Mobile auth */}
          <div className="mt-2 border-t pt-3" style={{ borderColor: "var(--nav-border)" }}>
            <div className="mb-3 flex items-center justify-between gap-3">
              <span className="text-xs font-semibold" style={{ color: "var(--primary)" }}>
                🌐
              </span>
              <div className="flex rounded-xl border border-slate-200 bg-white p-1">
                <button
                  type="button"
                  onClick={() => setLanguage("en")}
                  disabled={isLangLoading}
                  className={`rounded-lg px-3 py-1 text-xs font-bold transition-colors ${
                    language === "en"
                      ? "bg-emerald-50 text-emerald-700"
                      : "bg-transparent text-slate-700 hover:bg-slate-50"
                  }`}
                  aria-pressed={language === "en"}
                >
                  EN
                </button>
                <button
                  type="button"
                  onClick={() => setLanguage("ta")}
                  disabled={isLangLoading}
                  className={`rounded-lg px-3 py-1 text-xs font-bold transition-colors ${
                    language === "ta"
                      ? "bg-emerald-50 text-emerald-700"
                      : "bg-transparent text-slate-700 hover:bg-slate-50"
                  }`}
                  aria-pressed={language === "ta"}
                >
                  தமிழ்
                </button>
              </div>
            </div>

            {!isLoading && !user && (
              <div className="flex flex-col gap-2">
                <Link
                  href="/login"
                  className="mobile-nav-link"
                  onClick={() => setMenuOpen(false)}
                >
                  🔑 {msg?.nav?.signIn || nav?.signIn || "Sign In"}
                </Link>
                <Link
                  href="/signup"
                  className="mobile-nav-link font-semibold"
                  style={{ color: "var(--primary)" }}
                  onClick={() => setMenuOpen(false)}
                >
                  🌱 {msg?.nav?.createAccount || nav?.createAccount || "Create Account"}
                </Link>
              </div>
            )}
            {!isLoading && user && (
              <div className="flex flex-col gap-2">
                <span className="px-3 py-1 text-sm font-medium text-slate-800">
                  👤 {user.full_name}
                </span>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="mobile-nav-link text-left text-red-600 hover:bg-red-50"
                >
                  🚪 {msg?.nav?.logout || nav?.logout || "Logout"}
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
    </>
  );
}
