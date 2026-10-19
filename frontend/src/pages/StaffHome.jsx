import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { DashboardIdentity } from "../components/ProfileIdentity";
import IssueFeed from "../components/IssueFeed";
import { DateFilter, Kpi, paramsOf } from "./AdminDashboard";
import { errMsg } from "../utils";

export default function StaffHome() {
  const { user } = useAuth();
  const [v, setV] = useState({ range: "this_month" });
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (v.range === "custom" && (!v.start || !v.end)) return;
    api.get("/api/analytics/staff", { params: paramsOf(v) }).then((r) => setD(r.data)).catch((e) => setErr(errMsg(e)));
  }, [v]);
  return (
    <div>
      <div className="page-header-row">
        <div><h2>Hello, {user.full_name.split(" ")[0]}</h2><p className="muted">Facility staff dashboard</p></div>
        <DashboardIdentity />
      </div>
      <DateFilter v={v} set={setV} />
      {err && <div className="alert" role="alert">{err}</div>}
      {d && (
        <div className="kpis">
          <Kpi label="Awaiting my acceptance" value={d.awaiting_acceptance} />
          <Kpi label="In progress" value={d.in_progress} />
          <Kpi label="Overdue" value={d.overdue} />
          <Kpi label="Completed today" value={d.completed_today} />
          <Kpi label="Completed this week" value={d.completed_week} />
          <Kpi label="Completed this month" value={d.completed_month} />
          <Kpi label="Completed this year" value={d.completed_year} />
          <Kpi label="Avg completion (hours)" value={d.avg_resolution_hours} />
          <Kpi label="Reopened" value={d.reopened} />
          <Kpi label="Satisfaction (issues I handled)" value={d.avg_rating ?? "Not enough data"} />
        </div>
      )}
      <h3>My assigned tasks</h3>
      <IssueFeed emptyText="No tasks assigned to you yet." />
    </div>
  );
}
