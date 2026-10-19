import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, X } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { DashboardIdentity } from "../components/ProfileIdentity";
import IssueFeed from "../components/IssueFeed";

export function StudentHome() {
  const { user } = useAuth();
  const [p, setP] = useState(null);
  const [hide, setHide] = useState(() => sessionStorage.getItem("cf-hide-profile") === "1");
  useEffect(() => { api.get("/api/users/me/profile").then((r) => setP(r.data)).catch(() => {}); }, []);
  return (
    <>
      <div className="page-header-row">
        <div>
          <h2 className="welcome-heading">Welcome, {user.full_name.split(" ")[0]}</h2>
          <p className="muted">Recent campus issues</p>
        </div>
        <div className="dashboard-header-actions">
          <DashboardIdentity />
          <Link to="/student/new" className="btn-small primary-pill"><Plus size={14} /> Report new issue</Link>
        </div>
      </div>
      {p && p.completion < 100 && !hide && (
        <div className="card reminder">
          <div style={{ flex: 1 }}>
            <strong>Profile {p.completion}% complete.</strong> Still missing: {p.missing.map((m) => m.replace(/_/g, " ")).join(", ")}.{" "}
            <Link to="/student/profile">Complete profile</Link>
            <div className="progress"><span style={{ width: `${p.completion}%` }} /></div>
          </div>
          <button className="icon-btn" aria-label="Dismiss reminder" onClick={() => { sessionStorage.setItem("cf-hide-profile", "1"); setHide(true); }}><X size={16} /></button>
        </div>
      )}
      <IssueFeed emptyText="No public issues yet. Be the first to report one." />
    </>
  );
}

export function MyReports() {
  return (<><h2>My reports</h2><IssueFeed mine emptyText="You have not reported any issues yet." /></>);
}
