import { ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { listPolicies } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function PoliciesPage() {
  try {
    const policies = await listPolicies();
    return <><PageHeader eyebrow="Deterministic control" title="Policies" description="Versioned rules that always outrank model output. Policies decide what is permitted." />
      {!policies.length ? <EmptyState title="No policies registered" description="Register a policy version through POST /v1/policies." /> : <div className="space-y-3">{policies.map((policy) => <Card key={`${policy.name}@${policy.version}`} className="p-5"><div className="mb-4 flex items-start gap-3"><div className="rounded-md bg-emerald-500/10 p-2 text-emerald-400"><ShieldCheck className="h-4 w-4" /></div><div><h2 className="font-mono text-sm font-semibold">{policy.name}<span className="text-muted-foreground">@{policy.version}</span></h2>{policy.description && <p className="mt-1 text-xs text-muted-foreground">{policy.description}</p>}</div></div><div className="overflow-x-auto"><table className="w-full min-w-[540px] text-left text-xs"><thead><tr className="border-b border-border text-[10px] uppercase tracking-wider text-muted-foreground"><th className="py-2 pr-4 font-medium">Rule</th><th className="py-2 pr-4 font-medium">Conditions</th><th className="py-2 font-medium">Require</th></tr></thead><tbody>{policy.rules.map((rule) => <tr key={rule.name} className="border-b border-border/50 last:border-0"><td className="py-3 pr-4 font-mono">{rule.name}</td><td className="py-3 pr-4"><div className="flex flex-wrap gap-1.5">{Object.entries(rule.when).map(([key, value]) => <span key={key} className="rounded border border-border bg-secondary/50 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{key}: {typeof value === "object" ? JSON.stringify(value) : String(value)}</span>)}</div></td><td className="py-3 font-mono text-primary">{rule.require}</td></tr>)}</tbody></table></div></Card>)}</div>}
    </>;
  } catch (error) { return <><PageHeader eyebrow="Deterministic control" title="Policies" /><ErrorState message={error instanceof Error ? error.message : "API unavailable"} /></>; }
}
