import type { Metadata } from "next";
import "./globals.css";
import { DashboardShell } from "@/components/shell";

export const metadata: Metadata = {
  title: "DecisionOS — Decision Runtime",
  description: "Probabilistic decisions, deterministic policies, and outcome-based calibration.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><DashboardShell>{children}</DashboardShell></body></html>;
}
