import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Navbar from "./components/Navbar";
import { AuthProvider } from "./lib/AuthContext";
import { LanguageProvider } from "./lib/LanguageContext";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Agrosphere - AI-Powered Precision Agriculture",
  description:
    "AI-driven disease scanning, smart irrigation, yield prediction, and urban farming advisory.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-slate-50 text-slate-900">
        <LanguageProvider>
          <AuthProvider>
            <Navbar />
            <div className="flex flex-1 flex-col min-w-0 md:pl-64">
              <main className="flex-1 min-w-0 px-4 py-8 sm:px-6 lg:px-8">
                <div className="mx-auto w-full max-w-7xl">
                  {children}
                </div>
              </main>
            </div>
          </AuthProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
