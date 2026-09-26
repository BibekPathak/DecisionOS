import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import type { Decision } from "@/lib/api";
import { ActionBadge } from "@/components/ui/badge";
import { formatDate, formatPercent, formatLatency, shortId } from "@/lib/utils";
import { EmptyState } from "@/components/ui/empty-state";

export function DecisionTable({ decisions }: { decisions: Decision[] }) {
  if (!decisions.length) return <EmptyState title="No decisions recorded" description="Submit a decision through the API or run `make demo` to populate this view." />;
  return <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-xs">
    <thead><tr className="border-b border-border text-[10px] uppercase tracking-wider text-muted-foreground">{["Decision", "Action", "Confidence", "Risk", "Provider", "Latency", "Created"].map((h) => <th key={h} className="px-3 py-3 font-medium">{h}</th>)}</tr></thead>
    <tbody>{decisions.map((d) => <tr key={d.decision_id} className="border-b border-border/60 transition-colors hover:bg-white/[0.025]">
      <td className="px-3 py-3"><Link href={`/decisions/${d.decision_id}`} className="group inline-flex items-center gap-1.5 font-mono text-foreground hover:text-primary">{shortId(d.decision_id)}<ArrowUpRight className="h-3 w-3 opacity-0 group-hover:opacity-100" /></Link><div className="mt-1 text-[10px] text-muted-foreground">{d.schema_name}@{d.schema_version}</div></td>
      <td className="px-3 py-3"><ActionBadge action={d.action} /></td>
      <td className="px-3 py-3 font-mono-nums">{formatPercent(d.confidence)}</td>
      <td className="px-3 py-3 font-mono-nums">{formatPercent(d.risk)}</td>
      <td className="px-3 py-3 text-muted-foreground">{d.provider}</td>
      <td className="px-3 py-3 font-mono-nums text-muted-foreground">{formatLatency(d.latency_ms)}</td>
      <td className="px-3 py-3 text-muted-foreground">{formatDate(d.created_at)}</td>
    </tr>)}</tbody>
  </table></div>;
}
