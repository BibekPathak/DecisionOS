import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium", className)} {...props} />;
}

export function ActionBadge({ action }: { action: string }) {
  const styles: Record<string, string> = {
    allow: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
    continue: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
    human_review: "border-amber-500/30 bg-amber-500/10 text-amber-400",
    pause: "border-amber-500/30 bg-amber-500/10 text-amber-400",
    deny: "border-red-500/30 bg-red-500/10 text-red-400",
    rollback: "border-red-500/30 bg-red-500/10 text-red-400",
  };
  return <Badge className={cn("border", styles[action] || "border-blue-500/30 bg-blue-500/10 text-blue-400")}>{action.replaceAll("_", " ")}</Badge>;
}
