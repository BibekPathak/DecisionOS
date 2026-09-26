import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { DecisionTable } from "@/components/decision-table";
import { ErrorState } from "@/components/ui/error-state";
import { listDecisions } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DecisionsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  try {
    const params = await searchParams;
    const provider = typeof params.provider === "string" ? params.provider : undefined;
    const action = typeof params.action === "string" ? params.action : undefined;
    const decisionType = typeof params.decision_type === "string" ? params.decision_type : undefined;
    const decisions = await listDecisions({ limit: 100, provider, action, decision_type: decisionType });
    return <>
      <PageHeader eyebrow="Audit trail" title="Decisions" description="Inspect individual decisions, probability distributions, policy results, and observed outcomes." />
      <form className="mb-4 flex flex-wrap gap-2" action="/decisions">
        <input name="provider" defaultValue={provider} placeholder="Provider" className="h-9 rounded-md border border-input bg-card px-3 text-xs outline-none focus:ring-1 focus:ring-ring" />
        <input name="action" defaultValue={action} placeholder="Action" className="h-9 rounded-md border border-input bg-card px-3 text-xs outline-none focus:ring-1 focus:ring-ring" />
        <input name="decision_type" defaultValue={decisionType} placeholder="Decision type" className="h-9 rounded-md border border-input bg-card px-3 text-xs outline-none focus:ring-1 focus:ring-ring" />
        <button className="h-9 rounded-md bg-secondary px-3 text-xs hover:bg-accent">Filter</button>
        {(provider || action || decisionType) && <Link href="/decisions" className="flex h-9 items-center px-2 text-xs text-muted-foreground hover:text-foreground">Clear</Link>}
      </form>
      <div className="rounded-lg border border-border bg-card p-2"><DecisionTable decisions={decisions} /></div>
      <p className="mt-3 text-[11px] text-muted-foreground">Showing up to 100 matching decisions. Use the API for pagination and time-range queries.</p>
    </>;
  } catch (error) {
    return <><PageHeader eyebrow="Audit trail" title="Decisions" description="Inspect individual decision records." /><ErrorState message={error instanceof Error ? error.message : "API unavailable"} /></>;
  }
}
