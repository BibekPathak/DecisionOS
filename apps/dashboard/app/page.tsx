import { Activity, Clock3, ShieldAlert, Sparkles } from "lucide-react";
import { DecisionTable } from "@/components/decision-table";
import { OverviewCharts } from "@/components/overview-charts";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { StatCard } from "@/components/ui/stat-card";
import { getCalibration, listDecisions } from "@/lib/api";
import { formatLatency, formatPercent } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  try {
    const [decisions, calibration] = await Promise.all([
      listDecisions({ limit: 50 }),
      getCalibration(),
    ]);
    const actions = decisions.reduce<Record<string, number>>((acc, d) => {
      acc[d.action] = (acc[d.action] || 0) + 1;
      return acc;
    }, {});
    const averageLatency = decisions.length
      ? decisions.reduce((sum, d) => sum + d.latency_ms, 0) / decisions.length
      : null;
    const overrides = decisions.filter((d) => d.policy?.overridden).length;

    return <>
      <PageHeader eyebrow="Runtime overview" title="Decision overview" description="Probabilistic signals, deterministic controls, and observed outcomes — in one place." action={<span className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />Connected to DecisionOS API</span>} />
      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Decisions in sample" value={decisions.length.toLocaleString()} hint="Most recent 50 from API" />
        <StatCard label="Human review" value={(actions.human_review || 0).toLocaleString()} hint={`${formatPercent(decisions.length ? (actions.human_review || 0) / decisions.length : 0)} of loaded decisions`} />
        <StatCard label="Avg provider latency" value={formatLatency(averageLatency)} hint="Loaded decision sample" />
        <StatCard label="Calibration ECE" value={calibration.expected_calibration_error === null ? "n/a" : calibration.expected_calibration_error.toFixed(3)} hint={`${calibration.sample_count.toLocaleString()} decisions with outcomes`} />
      </div>
      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <Card className="flex items-center gap-3 px-4 py-3"><Activity className="h-4 w-4 text-emerald-400" /><div><p className="text-[10px] uppercase tracking-wider text-muted-foreground">Allow</p><p className="font-mono-nums text-lg font-semibold">{(actions.allow || 0).toLocaleString()}</p></div></Card>
        <Card className="flex items-center gap-3 px-4 py-3"><ShieldAlert className="h-4 w-4 text-red-400" /><div><p className="text-[10px] uppercase tracking-wider text-muted-foreground">Denied</p><p className="font-mono-nums text-lg font-semibold">{(actions.deny || 0).toLocaleString()}</p></div></Card>
        <Card className="flex items-center gap-3 px-4 py-3"><Sparkles className="h-4 w-4 text-primary" /><div><p className="text-[10px] uppercase tracking-wider text-muted-foreground">Policy overrides</p><p className="font-mono-nums text-lg font-semibold">{overrides.toLocaleString()}</p></div></Card>
      </div>
      <OverviewCharts decisions={decisions} />
      <section className="mt-5 rounded-lg border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-5 py-4"><div><h2 className="text-sm font-semibold">Recent decisions</h2><p className="mt-1 text-xs text-muted-foreground">Latest records returned by the API</p></div><Clock3 className="h-4 w-4 text-muted-foreground" /></div>
        <div className="p-2"><DecisionTable decisions={decisions.slice(0, 8)} /></div>
      </section>
    </>;
  } catch (error) {
    return <><PageHeader eyebrow="Runtime overview" title="Decision overview" description="Probabilistic signals, deterministic controls, and observed outcomes — in one place." /><ErrorState message={error instanceof Error ? error.message : "API unavailable"} /></>;
  }
}
