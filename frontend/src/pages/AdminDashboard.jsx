import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { api } from "../api";
import { STATUS_LABEL, errMsg } from "../utils";
import { DashboardIdentity } from "../components/ProfileIdentity";

const RANGES = [["today", "Today"], ["yesterday", "Yesterday"], ["this_week", "This week"], ["last_week", "Last week"],
  ["this_month", "This month"], ["last_month", "Last month"], ["this_year", "This year"], ["last_year", "Last year"],
  ["all", "All time"], ["custom", "Custom range"]];
const PRIO = { high: "#dc2626", medium: "#ea580c", low: "#ca8a04" };

export function Kpi({ label, value }) {
  return <div className="card kpi"><div className="kpi-v">{value ?? "—"}</div><div className="muted small">{label}</div></div>;
}

export function DateFilter({ v, set }) {
  return (
    <div className="filters">
      <select aria-label="Date range" value={v.range} onChange={(e) => set({ ...v, range: e.target.value })}>
        {RANGES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      {v.range === "custom" && (<>
        <input type="date" aria-label="Start date" value={v.start || ""} onChange={(e) => set({ ...v, start: e.target.value })} />
        <input type="date" aria-label="End date" value={v.end || ""} onChange={(e) => set({ ...v, end: e.target.value })} />
      </>)}
      {v.group !== undefined && (
        <select aria-label="Group by" value={v.group} onChange={(e) => set({ ...v, group: e.target.value })}>
          <option value="day">Per day</option><option value="week">Per week</option>
          <option value="month">Per month</option><option value="year">Per year</option>
        </select>
      )}
    </div>
  );
}

export function paramsOf(v) {
  const p = { range: v.range, group: v.group };
  if (v.range === "custom") { p.start = v.start; p.end = v.end; }
  return p;
}

export default function AdminDashboard() {
  const [v, setV] = useState({ range: "this_month", group: "day" });
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (v.range === "custom" && (!v.start || !v.end)) return;
    setErr("");
    api.get("/api/analytics/admin", { params: paramsOf(v) }).then((r) => setD(r.data)).catch((e) => setErr(errMsg(e)));
  }, [v]);

  const entries = (o) => Object.entries(o || {}).map(([name, value]) => ({ name, value }));
  return (
    <div>
      <div className="page-header-row">
        <h2>Admin dashboard</h2>
        <DashboardIdentity />
      </div>
      <DateFilter v={v} set={setV} />
      {err && <div className="alert" role="alert">{err}</div>}
      {!d ? <div className="skeleton" /> : (<>
        <div className="kpis">
          <Kpi label="Registered students" value={d.students} />
          <Kpi label="Active staff" value={d.staff} />
          <Kpi label="Issues reported" value={d.total} />
          <Kpi label="Pending review" value={d.pending_review} />
          <Kpi label="High priority (open)" value={d.high_priority_open} />
          <Kpi label="Awaiting staff acceptance" value={d.awaiting_acceptance} />
          <Kpi label="In progress" value={d.in_progress} />
          <Kpi label="Resolved / closed" value={d.resolved_or_closed} />
          <Kpi label="Rejected" value={d.rejected} />
          <Kpi label="Overdue" value={d.overdue} />
          <Kpi label="Avg resolution (hours)" value={d.avg_resolution_hours} />
          <Kpi label={`Avg rating (${d.rating_count} ratings)`} value={d.avg_rating ?? "Not enough data"} />
        </div>
        {d.total === 0 ? <div className="card empty">No issues in this period yet. Charts appear once issues are reported.</div> : (
          <div className="charts">
            <div className="card"><h4>Issues by priority</h4>
              <ResponsiveContainer width="100%" height={220}><PieChart>
                <Pie data={entries(d.by_priority)} dataKey="value" nameKey="name" label>{entries(d.by_priority).map((e) => <Cell key={e.name} fill={PRIO[e.name]} />)}</Pie>
                <Tooltip /><Legend /></PieChart></ResponsiveContainer></div>
            <div className="card"><h4>Issues by category</h4>
              <ResponsiveContainer width="100%" height={220}><BarChart data={entries(d.by_category)} layout="vertical" margin={{ left: 40 }}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis type="number" allowDecimals={false} /><YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 11 }} />
                <Tooltip /><Bar dataKey="value" fill="#14b8a6" /></BarChart></ResponsiveContainer></div>
            <div className="card"><h4>Issues by status</h4>
              <ResponsiveContainer width="100%" height={220}><BarChart data={entries(d.by_status).map((e) => ({ ...e, name: STATUS_LABEL[e.name] }))}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} /><Tooltip />
                <Bar dataKey="value" fill="#13315c" /></BarChart></ResponsiveContainer></div>
            <div className="card"><h4>Reported vs resolved over time</h4>
              <ResponsiveContainer width="100%" height={220}><LineChart data={d.series}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="period" tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} /><Tooltip /><Legend />
                <Line dataKey="reported" stroke="#ea580c" strokeWidth={2} /><Line dataKey="resolved" stroke="#16a34a" strokeWidth={2} /></LineChart></ResponsiveContainer></div>
            <div className="card wide"><h4>Staff workload</h4>
              {d.workload.length === 0 ? <p className="muted">No active staff yet.</p> :
                <ResponsiveContainer width="100%" height={220}><BarChart data={d.workload}>
                  <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Legend />
                  <Bar dataKey="open" name="Open tasks" fill="#ea580c" /><Bar dataKey="completed" name="Completed" fill="#16a34a" /></BarChart></ResponsiveContainer>}</div>
          </div>
        )}
      </>)}
    </div>
  );
}
