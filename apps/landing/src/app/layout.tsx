import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import "./globals.css";

const sans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "OpsPilot — AI-assisted incident response with human approval",
  description:
    "OpsPilot detects incidents in Kubernetes services, investigates them with evidence-citing AI agents, proposes a safe rollback, runs it after a human approves, verifies recovery, and writes the postmortem.",
  openGraph: {
    title: "OpsPilot",
    description: "Incidents, investigated by agents. Fixed only when you say so.",
    type: "website",
  },
};

export const viewport: Viewport = { colorScheme: "dark" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="backdrop min-h-dvh">{children}</body>
    </html>
  );
}
