import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BellRing, Filter, Search } from "lucide-react";
import { api } from "../api";
import { fmtDate, timeAgo } from "../utils";

const FILTERS = ["all", "unread", "complaints", "facilities", "approvals", "users", "security", "system"];

function categoryFromMessage(message = "") {
  const text = message.toLowerCase();
  if (text.includes("assigned") || text.includes("work") || text.includes("task")) return "facilities";
  if (text.includes("approved") || text.includes("verified") || text.includes("closed")) return "approvals";
  if (text.includes("password") || text.includes("security") || text.includes("login")) return "security";
  if (text.includes("updated") || text.includes("profile") || text.includes("user")) return "users";
  if (text.includes("report") || text.includes("complaint") || text.includes("issue")) return "complaints";
  return "system";
}

export default function Notifications() {
  const nav = useNavigate();
  const [d, setD] = useState(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");

  const load = () => api.get("/api/notifications").then((r) => { setD(r.data); window.dispatchEvent(new Event("cf-notif-changed")); });
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    if (!d) return [];
    return d.items.filter((n) => {
      const cat = categoryFromMessage(n.message);
      const matchesFilter = filter === "all" || (filter === "unread" ? !n.is_read : cat === filter);
      const matchesQuery = !query || `${n.message} ${fmtDate(n.created_at)}`.toLowerCase().includes(query.toLowerCase());
      return matchesFilter && matchesQuery;
    });
  }, [d, filter, query]);

  if (!d) return <div className="skeleton" />;

  async function open(n) {
    if (!n.is_read) await api.post(`/api/notifications/${n.id}/read`);
    if (n.issue_id) nav(`/issues/${n.issue_id}`);
    else load();
  }

  return (
    <div className="page-header">
      <div className="header-row">
        <div>
          <p className="eyebrow">Inbox</p>
          <h2>Notifications</h2>
        </div>
        <div className="header-actions">
          <span className="status-chip status-neutral">{d.unread} unread</span>
          <button className="btn-small ghost" disabled={!d.unread} onClick={async () => { await api.post("/api/notifications/read-all"); load(); }}>
            Mark all as read
          </button>
        </div>
      </div>

      <div className="card notification-panel">
        <div className="notification-toolbar">
          <div className="search-box">
            <Search size={16} />
            <input aria-label="Search notifications" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search notifications" />
          </div>
          <div className="filter-row" aria-label="Notification filters">
            {FILTERS.map((item) => (
              <button key={item} type="button" className={filter === item ? "filter-pill active" : "filter-pill"} onClick={() => setFilter(item)}>
                {item === "all" ? "All" : item.charAt(0).toUpperCase() + item.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {filtered.length === 0 && (
          <div className="empty-state">
            <BellRing size={32} />
            <p>No notifications match your current search.</p>
          </div>
        )}

        {filtered.map((n) => {
          const kind = categoryFromMessage(n.message);
          return (
            <article key={n.id} className={n.is_read ? "notification-item" : "notification-item unread"}>
              <div className={`notification-badge ${kind}`} aria-hidden="true" />
              <div className="notification-main">
                <div className="notification-head">
                  <strong>{n.message}</strong>
                  {!n.is_read && <span className="red-dot small-dot" aria-label="Unread notification" />}
                </div>
                <div className="notification-meta">
                  <span className="status-chip status-neutral">{kind}</span>
                  <span>{timeAgo(n.created_at)}</span>
                  <span>{fmtDate(n.created_at)}</span>
                </div>
              </div>
              <div className="notification-actions">
                {n.issue_id && (<button className="btn-small ghost" type="button" onClick={() => nav(`/issues/${n.issue_id}`)}>View details</button>)}
                {!n.is_read && (<button className="btn-small ghost" type="button" onClick={async () => { await api.post(`/api/notifications/${n.id}/read`); load(); }}>Mark read</button>)}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
