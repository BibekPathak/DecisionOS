import Link from "next/link";
import { ArrowLeft, Check, Circle, Clock3, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ProbabilityBars } from "@/components/probability-bars";
import { ActionBadge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { getDecision, getExplanation } from "@/lib/api";
import { formatDate, formatLatency, formatPercent } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function DecisionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const [decision, explanation] = await Promise.all([getDecision(id), getExplanation(id)]);
    return <>
      <Link href="/decisions" className="mb-5 inline-flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3.5 w-3.5" />Back to decisions</Link>
      <PageHeader eyebrow="Decision detail" title={decision.decision_id} description={`${decision.schema_name}@${decision.schema_version} · ${decision.decision_type} · created ${formatDate(decision.created_at)}`} action={<ActionBadge action={decision.action} />} />
      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-4">
          <Card><CardHeader><CardTitle>Decision signal</CardTitle></CardHeader><CardContent><div className="mb-5 grid grid-cols-2 gap-4 sm:grid-cols-4"><Metric label="Final action"><ActionBadge action={decision.action} /></Metric><Metric label="Model action"><ActionBadge action={explanation.model_action} /></Metric><Metric label="Confidence" value={formatPercent(decision.confidence)} /><Metric label="Risk" value={formatPercent(decision.risk)} /></div><ProbabilityBars probabilities={explanation.model_probabilities} /></CardContent></Card>
          <Card><CardHeader><CardTitle>Evidence</CardTitle></CardHeader><CardContent><div className="grid gap-4 sm:grid-cols-2"><Metric label="Provider" value={decision.provider} /><Metric label="Provider request" value={decision.provider_request_id || "—"} mono /><Metric label="Latency" value={formatLatency(decision.latency_ms)} /><Metric label="Schema version" value={`${decision.schema_name}@${decision.schema_version}`} mono /></div><div className="mt-5"><p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Reason codes</p>{decision.reason_codes.length ? <div className="flex flex-wrap gap-2">{decision.reason_codes.map((code) => <span key={code} className="rounded border border-border bg-secondary/50 px-2 py-1 font-mono text-[11px] text-muted-foreground">{code}</span>)}</div> : <p className="text-xs text-muted-foreground">No reason codes recorded.</p>}</div></CardContent></Card>
          <Card><CardHeader><CardTitle>Policy evaluation</CardTitle></CardHeader><CardContent>{explanation.policy_rules_triggered.length ? <div className="space-y-2">{explanation.policy_rules_triggered.map((rule) => <div key={rule} className="flex items-center gap-2 text-xs"><ShieldCheck className="h-3.5 w-3.5 text-primary" /><span>{rule}</span><Check className="ml-auto h-3.5 w-3.5 text-emerald-400" /></div>)}<p className="pt-2 text-[11px] text-muted-foreground">Precedence applied: {explanation.policy_precedence || "model_decision"}</p></div> : <p className="text-xs text-muted-foreground">No policy rules triggered.</p>}</CardContent></Card>
        </div>
        <Card className="h-fit"><CardHeader><CardTitle>Lifecycle timeline</CardTitle></CardHeader><CardContent><div className="space-y-0">{explanation.lifecycle.map((event, i) => <div key={`${event.type}-${i}`} className="relative flex gap-3 pb-5 last:pb-0"><div className="relative flex w-4 justify-center"><span className={`z-[1] mt-0.5 h-2.5 w-2.5 rounded-full border ${i === explanation.lifecycle.length - 1 ? "border-primary bg-primary" : "border-border bg-card"}`} />{i < explanation.lifecycle.length - 1 && <span className="absolute top-3 h-full w-px bg-border" />}</div><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><p className="text-xs font-medium">{event.type.replaceAll("_", " ")}</p><span className="shrink-0 text-[10px] text-muted-foreground">{formatDate(event.occurred_at)}</span></div>{event.from_state && event.to_state && <p className="mt-1 font-mono text-[10px] text-muted-foreground">{event.from_state} → {event.to_state}</p>}</div></div>)}</div>{explanation.lifecycle.length === 0 && <p className="text-xs text-muted-foreground">No lifecycle events recorded.</p>}</CardContent></Card>
      </div>
    </>;
  } catch (error) {
    return <><Link href="/decisions" className="mb-5 inline-flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3.5 w-3.5" />Back to decisions</Link><ErrorState message={error instanceof Error ? error.message : "Decision not found"} /></>;
  }
}

function Metric({ label, value, mono = false, children }: { label: string; value?: string; mono?: boolean; children?: React.ReactNode }) {
  return <div><p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>{children || <p className={`text-sm font-medium ${mono ? "break-all font-mono text-xs" : ""}`}>{value}</p>}</div>;
}
