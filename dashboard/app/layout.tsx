import type { Metadata, Viewport } from "next";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { FailureBanner } from "@/components/chrome/FailureBanner";
import { SetupNudge } from "@/components/chrome/SetupNudge";
import { setupCompleted } from "@/lib/data/paths";
import { MobileHeader } from "@/components/chrome/MobileHeader";
import { AutoRefresh } from "@/components/chrome/AutoRefresh";
import { Sidebar } from "@/components/chrome/Sidebar";
import { TabBar } from "@/components/chrome/TabBar";
import { PAGE_COLORS, THEME_SCRIPT } from "@/lib/theme";

// Every page reads the data dir at request time; this also keeps the built-in error routes from being
// prerendered with the layout's client hooks (which throws on this Next version).
export const dynamic = "force-dynamic";

const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap", weight: ["400", "500", "600", "700"] });

export const metadata: Metadata = {
  title: "focos",
  applicationName: "focos",
  description: "Family Office Chief Of Staff",
  appleWebApp: { capable: true, title: "focos", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: PAGE_COLORS.light },
    { media: "(prefers-color-scheme: dark)", color: PAGE_COLORS.dark },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${mono.variable} h-full`} suppressHydrationWarning>
      <head>
        <meta name="color-scheme" content="dark light" />
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <AutoRefresh />
        <div className="flex min-h-dvh">
          <Sidebar />
          <div className="min-w-0 flex-1">
            <MobileHeader />
            <SetupNudge completed={setupCompleted()} />
            <FailureBanner />
            <main className="w-full max-w-[1900px] px-4 py-4 pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom)+1rem)] md:px-6 lg:px-8 lg:py-7 lg:pb-7">{children}</main>
          </div>
        </div>
        <TabBar />
      </body>
    </html>
  );
}
