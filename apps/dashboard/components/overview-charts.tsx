"use client";

import {
  CartesianGrid,
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Decision } from "@/lib/api";
import { actionColor } from "@/lib/utils";

const tooltipStyle = {
  background: "#0d1421",
  border: "1px solid #263247",
  borderRadius: 8,
  color: "#e2e8f0",
  fontSize: 11,
};

export function OverviewCharts({ decisions }: { decisions: Decision[] }) {
  const timeline = [...decisions].reverse().map((d, i) => ({
    index: i + 1,
    confidence: Math.round(d.confidence * 100),
    risk: d.risk === null ? null : Math.round(d.risk * 100),
    latency: d.latency_ms,
  }));
  const counts = new Map<string, number>();
  decisions.forEach((d) => counts.set(d.action, (counts.get(d.action) || 0) + 1));
  const distribution = Array.from(counts, ([name, value]) => ({ name, value }));
  const confidence = [
    { band: "0–20", count: 0 }, { band: "20–40", count: 0 },
    { band: "40–60", count: 0 }, { band: "60–80", count: 0 }, { band: "80–100", count: 0 },
  ];
  decisions.forEach((d) => {
    const bucket = Math.min(4, Math.floor(d.confidence * 5));
    confidence[bucket].count += 1;
  });
  const byHour = new Map<string, number>();
  decisions.forEach((decision) => {
    const date = new Date(decision.created_at);
    const key = `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, "0")}:00`;
    byHour.set(key, (byHour.get(key) || 0) + 1);
  });
  const volume = Array.from(byHour, ([time, count]) => ({ time, count }));
  const overrides = decisions.reduce<Record<string, number>>((acc, decision) => {
    if (decision.policy?.overridden) {
      const policy = decision.policy.name;
      acc[policy] = (acc[policy] || 0) + 1;
    }
    return acc;
  }, {});
  const overrideData = Object.entries(overrides).map(([policy, count]) => ({ policy, count }));

  return <div className="grid gap-4 xl:grid-cols-2">
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="mb-4"><h3 className="text-sm font-semibold">Decisions over time</h3><p className="mt-1 text-xs text-muted-foreground">Hourly volume across the loaded sample</p></div>
      {volume.length < 2 ? <div className="flex h-52 items-center justify-center text-xs text-muted-foreground">More timestamps are needed to show a trend.</div> : <ResponsiveContainer width="100%" height={208}><LineChart data={volume}><CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 9 }} axisLine={false} tickLine={false} /><YAxis allowDecimals={false} tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipStyle} /><Line type="monotone" dataKey="count" stroke="#60a5fa" strokeWidth={2} dot={false} name="Decisions" /></LineChart></ResponsiveContainer>}
    </div>
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="mb-4"><h3 className="text-sm font-semibold">Confidence & risk</h3><p className="mt-1 text-xs text-muted-foreground">Recent decisions, as observed</p></div>
      {timeline.length < 2 ? <div className="flex h-52 items-center justify-center text-xs text-muted-foreground">At least two decisions are needed for a trend.</div> : <ResponsiveContainer width="100%" height={208}><LineChart data={timeline}><CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="index" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} unit="%" /><Tooltip contentStyle={tooltipStyle} formatter={(v) => [`${v}%`]} /><Line type="monotone" dataKey="confidence" stroke="#60a5fa" strokeWidth={2} dot={false} connectNulls name="Confidence" /><Line type="monotone" dataKey="risk" stroke="#f59e0b" strokeWidth={2} dot={false} connectNulls name="Risk" /></LineChart></ResponsiveContainer>}
    </div>
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="mb-4"><h3 className="text-sm font-semibold">Action distribution</h3><p className="mt-1 text-xs text-muted-foreground">Final actions in the loaded sample</p></div>
      {!distribution.length ? <div className="flex h-52 items-center justify-center text-xs text-muted-foreground">No observed actions yet.</div> : <div className="flex h-52 items-center"><ResponsiveContainer width="60%" height="100%"><PieChart><Pie data={distribution} dataKey="value" nameKey="name" innerRadius={52} outerRadius={78} paddingAngle={3} stroke="none">{distribution.map((entry) => <Cell key={entry.name} fill={actionColor(entry.name)} />)}</Pie><Tooltip contentStyle={tooltipStyle} /></PieChart></ResponsiveContainer><div className="flex flex-1 flex-col gap-3">{distribution.map((item) => <div key={item.name} className="flex items-center justify-between gap-2 text-xs"><span className="flex items-center gap-2 text-muted-foreground"><span className="h-2 w-2 rounded-full" style={{ background: actionColor(item.name) }} />{item.name.replaceAll("_", " ")}</span><span className="font-mono-nums">{item.value}</span></div>)}</div></div>}
    </div>
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="mb-4"><h3 className="text-sm font-semibold">Confidence distribution</h3><p className="mt-1 text-xs text-muted-foreground">Decision confidence across five bands</p></div>
      <ResponsiveContainer width="100%" height={190}><BarChart data={confidence}><CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="band" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis allowDecimals={false} tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipStyle} /><Bar dataKey="count" fill="#60a5fa" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>
    </div>
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="mb-4"><h3 className="text-sm font-semibold">Provider latency</h3><p className="mt-1 text-xs text-muted-foreground">Per-decision provider latency, milliseconds</p></div>
      {!timeline.length ? <div className="flex h-48 items-center justify-center text-xs text-muted-foreground">No provider measurements yet.</div> : <ResponsiveContainer width="100%" height={190}><BarChart data={timeline}><CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="index" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipStyle} formatter={(v) => [`${Number(v).toFixed(0)}ms`, "Latency"]} /><Bar dataKey="latency" fill="#a78bfa" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>}
    </div>
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="mb-4"><h3 className="text-sm font-semibold">Policy overrides</h3><p className="mt-1 text-xs text-muted-foreground">Actions forced by deterministic policies</p></div>
      {!overrideData.length ? <div className="flex h-48 items-center justify-center text-xs text-muted-foreground">No policy overrides in the loaded sample.</div> : <ResponsiveContainer width="100%" height={190}><BarChart data={overrideData} layout="vertical"><CartesianGrid stroke="#1e293b" strokeDasharray="3 3" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis type="category" dataKey="policy" width={120} tick={{ fill: "#94a3b8", fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipStyle} /><Bar dataKey="count" fill="#f59e0b" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer>}
    </div>
  </div>;
}
