import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { DemoBanner } from "@/demo/banner";

import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const demoSite = process.env.DEMO_SITE_URL ?? "https://kunj157.github.io/opspilot";

export const metadata: Metadata = {
  title: "OpsPilot",
  description: "AI-assisted incident detection, investigation, and safe remediation.",
  // Link previews for the demo build, which is shared as a link (LinkedIn, Slack).
  ...(process.env.NEXT_PUBLIC_DEMO === "1" && {
    openGraph: {
      title: "OpsPilot live demo",
      description:
        "The real OpsPilot console replaying a recorded incident: detection, agent investigation with cited evidence, a rollback you approve, verified recovery and the postmortem.",
      type: "website",
      url: `${demoSite}/demo/`,
      images: [{ url: `${demoSite}/media/og-demo.png`, width: 1200, height: 630 }],
    },
  }),
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full`}>
      <body className="flex min-h-full flex-col">
        <DemoBanner />
        <div aria-hidden className="depth-backdrop" />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
