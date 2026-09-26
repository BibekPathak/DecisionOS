import { actionColor, formatPercent } from "@/lib/utils";

export function ProbabilityBars({ probabilities }: { probabilities: Record<string, number> }) {
  return <div className="space-y-3">{Object.entries(probabilities).sort((a, b) => b[1] - a[1]).map(([action, value]) => <div key={action}>
    <div className="mb-1.5 flex justify-between text-xs"><span className="text-muted-foreground">{action.replaceAll("_", " ")}</span><span className="font-mono-nums text-foreground">{formatPercent(value, 1)}</span></div>
    <div className="h-1.5 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full transition-all" style={{ width: `${Math.max(0, Math.min(100, value * 100))}%`, background: actionColor(action) }} /></div>
  </div>)}</div>;
}
