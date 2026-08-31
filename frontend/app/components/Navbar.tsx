"use client";

import Link from "next/link";
import { useState } from "react";
import { Menu, X } from "lucide-react";
import Sidebar from "@/components/Sidebar";

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <>
      {/* Desktop Persistent Left Sidebar */}
      <aside className="hidden md:flex md:w-64 md:flex-col md:fixed md:inset-y-0 md:border-r md:bg-white dark:md:bg-slate-900 border-slate-200 dark:border-slate-800 p-6 z-40">
        <Sidebar />
      </aside>

      {/* Mobile Top Navbar */}
      <header className="sticky top-0 z-50 w-full nav-glass md:hidden bg-white/90 dark:bg-slate-900/90 backdrop-blur-md border-b border-slate-200 dark:border-slate-800">
        <nav
          className="flex items-center justify-between px-4 py-3 sm:px-6"
          aria-label="Main navigation"
        >
          {/* Brand */}
          <Link
            href="/"
            className="flex items-center gap-2 text-xl font-bold tracking-tight text-emerald-800 dark:text-emerald-400"
          >
            <span aria-hidden="true">🌾</span>
            <span>Agrosphere</span>
          </Link>

          {/* Hamburger menu toggle */}
          <button
            type="button"
            className="inline-flex items-center justify-center rounded-lg p-2 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
            onClick={() => setMenuOpen((prev) => !prev)}
          >
            {menuOpen ? (
              <X className="h-6 w-6" />
            ) : (
              <Menu className="h-6 w-6" />
            )}
          </button>
        </nav>

        {/* Mobile dropdown drawer */}
        {menuOpen && (
          <div
            id="mobile-menu"
            className="border-t border-slate-200 dark:border-slate-800 p-5 bg-white dark:bg-slate-900 max-h-[calc(100vh-4rem)] overflow-y-auto"
            aria-hidden={!menuOpen}
          >
            <Sidebar onItemClick={() => setMenuOpen(false)} isMobile={true} />
          </div>
        )}
      </header>
    </>
  );
}
