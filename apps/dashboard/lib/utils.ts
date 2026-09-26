import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "n/a";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  return value.toLocaleString("en-US");
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "n/a";
  return `${ms.toFixed(0)}ms`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "n/a";
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function shortId(id: string): string {
  return id.length > 16 ? `${id.slice(0, 14)}…` : id;
}

/** A stable colour per action, used across charts and badges. */
export function actionColor(action: string): string {
  switch (action) {
    case "allow":
    case "continue":
      return "#22c55e";
    case "human_review":
    case "pause":
      return "#eab308";
    case "deny":
    case "rollback":
      return "#ef4444";
    default:
      return "#60a5fa";
  }
}
