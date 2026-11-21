import type { Metadata, Viewport } from "next";
import { Shell } from "@/components/Shell";
import { AppProvider } from "@/lib/store";
import "./globals.css";

export const metadata: Metadata = { title: "OpsLens | Business investigation agent", description: "Don't just show me the numbers. Tell me what's going wrong." };
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#07070b" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en"><body className="font-sans"><AppProvider><Shell>{children}</Shell></AppProvider></body></html>
  );
}
