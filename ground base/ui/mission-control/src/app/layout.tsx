import type { ReactNode } from "react";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { OperatorProvider } from "@/components/provider";
import { Shell } from "@/components/shell";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const grotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-grotesk", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata = {
  title: "Ground Mission Control",
  description: "Local operator console for the Ground station.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-theme="light" className={`${inter.variable} ${grotesk.variable} ${mono.variable}`}>
      <body className="font-sans">
        <OperatorProvider>
          <Shell>{children}</Shell>
        </OperatorProvider>
      </body>
    </html>
  );
}
