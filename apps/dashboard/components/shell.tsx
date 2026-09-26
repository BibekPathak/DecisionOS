"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Boxes, Braces, ChartNoAxesCombined, CircleHelp, Gauge, Layers3, Settings2, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/", label: "Overview", icon: Gauge },
  { href: "/decisions", label: "Decisions", icon: Activity },
  { href: "/schemas", label: "Schemas", icon: Braces },
  { href: "/policies", label: "Policies", icon: ShieldCheck },
  { href: "/calibration", label: "Calibration", icon: ChartNoAxesCombined },
  { href: "/settings", label: "Settings", icon: Settings2 },
];

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 border-r border-border bg-[#080d17] lg:flex lg:flex-col">
        <Link href="/" className="flex h-16 items-center gap-3 border-b border-border px-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/15 text-primary"><Layers3 className="h-4 w-4" /></div>
          <div><div className="text-sm font-semibold tracking-tight">DecisionOS</div><div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Runtime</div></div>
        </Link>
        <div className="px-3 pt-6"><p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Workspace</p>
          <nav className="space-y-1">{nav.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            const Icon = item.icon;
            return <Link key={item.href} href={item.href} className={cn("flex items-center gap-3 rounded-md px-3 py-2 text-[13px] transition-colors", active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground")}><Icon className="h-4 w-4" />{item.label}</Link>;
          })}</nav>
        </div>
        <div className="mt-auto border-t border-border p-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground"><span className="h-2 w-2 rounded-full bg-emerald-400" />API connection configured</div>
          <a href="https://github.com" className="mt-3 flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground"><CircleHelp className="h-3.5 w-3.5" /> Documentation</a>
        </div>
      </aside>
      <div className="lg:pl-60">
        <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-border bg-background/90 px-5 backdrop-blur md:px-8">
          <div className="flex items-center gap-3"><div className="lg:hidden flex h-7 w-7 items-center justify-center rounded bg-primary/15 text-primary"><Layers3 className="h-4 w-4" /></div><span className="text-xs text-muted-foreground">Probabilistic intelligence <span className="mx-1 text-border">/</span> deterministic control</span></div>
          <div className="flex items-center gap-2 rounded-full border border-border px-2.5 py-1 text-[11px] text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />System operational</div>
        </header>
        <main className="mx-auto max-w-[1440px] p-5 md:p-8">{children}</main>
      </div>
    </div>
  );
}
