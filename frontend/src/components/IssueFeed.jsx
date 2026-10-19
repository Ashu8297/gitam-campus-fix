import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { ThumbsUp, MapPin, Clock } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { PriorityBadge, StatusBadge } from "./Badges";
import { STATUS_OPTIONS, STATUS_LABEL, errMsg, fileUrl, timeAgo, fmtDate } from "../utils";

export default function IssueFeed({ mine = false, selectable = false, emptyText = "No issues found." }) {
  const { user } = useAuth();
  const [f, setF] = useState({ q: "", category_id: "", status: "", priority: "", sort: "newest" });
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ items: [], total: 0, page_size: 10 });
  const [cats, setCats] = useState([]);
  const [state, setState] = useState("loading");
  const [msg, setMsg] = useState("");
  const [sel, setSel] = useState([]);
  const [staff, setStaff] = useState([]);
  const [bulk, setBulk] = useState({ action: "approve", staff_id: "", reason: "" });
  const [bulkResult, setBulkResult] = useState(null);

  const load = useCallback(() => {
    setState("loading");
    const params = { ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)), page, mine };
    api.get("/api/issues", { params })
      .then((r) => { setData(r.data); setState("ok"); })
      .catch((e) => { setMsg(errMsg(e)); setState("error"); });
  }, [f, page, mine]);

  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  useEffect(() => {
    api.get("/api/categories").then((r) => setCats(r.data)).catch(() => {});
    if (selectable) api.get("/api/users/staff-options").then((r) => setStaff(r.data)).catch(() => {});
  }, [selectable]);

  const set = (k) => (e) => { setF({ ...f, [k]: e.target.value }); setPage(1); };
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));

  async function vote(issue) {
    try {
      const r = await api.post(`/api/issues/${issue.id}/vote`);
      setData((d) => ({ ...d, items: d.items.map((i) => (i.id === issue.id ? { ...i, voted: r.data.voted, votes: r.data.votes } : i)) }));
    } catch (e) { setMsg(errMsg(e)); }
  }

  async function runBulk() {
    setBulkResult(null);
    try {
      const body = { ids: sel, action: bulk.action, reason: bulk.reason, staff_id: bulk.staff_id ? Number(bulk.staff_id) : null };
      const r = await api.post("/api/issues/bulk/action", body);
      setBulkResult(r.data);
      setSel([]);
      load();
    } catch (e) { setMsg(errMsg(e)); }
  }

  return (
    <section>
      <div className="filters">
        <input aria-label="Search issues" placeholder="Search title, location, ID…" value={f.q} onChange={set("q")} />
        <select aria-label="Category" value={f.category_id} onChange={set("category_id")}>
          <option value="">All categories</option>
          {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select aria-label="Status" value={f.status} onChange={set("status")}>
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </select>
        <select aria-label="Priority" value={f.priority} onChange={set("priority")}>
          <option value="">All priorities</option>
          <option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
        </select>
        <select aria-label="Sort" value={f.sort} onChange={set("sort")}>
          <option value="newest">Newest</option><option value="oldest">Oldest</option><option value="votes">Most supported</option>
        </select>
      </div>

      {selectable && sel.length > 0 && (
        <div className="card bulkbar">
          <strong>{sel.length} selected</strong>
          <select aria-label="Bulk action" value={bulk.action} onChange={(e) => setBulk({ ...bulk, action: e.target.value })}>
            <option value="approve">Approve</option><option value="reject">Reject</option><option value="assign">Assign</option>
          </select>
          {bulk.action !== "reject" && (
            <select aria-label="Staff" value={bulk.staff_id} onChange={(e) => setBulk({ ...bulk, staff_id: e.target.value })}>
              <option value="">{bulk.action === "assign" ? "Choose staff" : "Staff (optional)"}</option>
              {staff.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
          {bulk.action === "reject" && (
            <input aria-label="Reason" placeholder="Reason (required)" value={bulk.reason} onChange={(e) => setBulk({ ...bulk, reason: e.target.value })} />
          )}
          <button className="btn-small" onClick={runBulk}>Apply</button>
        </div>
      )}
      {bulkResult && (
        <div className="card" role="status">
          <strong>{bulkResult.succeeded} succeeded, {bulkResult.failed} failed.</strong>
          {bulkResult.results.filter((r) => !r.ok).map((r) => (
            <div key={r.id} className="small field-error">Issue #{r.id}: {r.error}</div>
          ))}
        </div>
      )}
      {msg && <div className="alert" role="alert">{msg}</div>}

      {state === "loading" && <div className="skeletons">{[1, 2, 3].map((i) => <div key={i} className="skeleton" />)}</div>}
      {state === "error" && <p className="muted">Could not load issues.</p>}
      {state === "ok" && data.items.length === 0 && <div className="card empty">{emptyText}</div>}
      {state === "ok" && data.items.map((i) => {
        const selected = sel.includes(i.id);
        return (
          <article key={i.id} className={`card issue-card ${selected ? "selected" : ""}`}>
            <div className="issue-card-inner">
              <div className="issue-header-row">
                {selectable && (
                  <label className="issue-select" htmlFor={`select-issue-${i.id}`}>
                    <input
                      id={`select-issue-${i.id}`}
                      type="checkbox"
                      className="issue-select-input"
                      aria-label={`Select complaint ${i.issue_number}`}
                      checked={selected}
                      onChange={(e) => setSel(e.target.checked ? [...sel, i.id] : sel.filter((x) => x !== i.id))}
                    />
                  </label>
                )}
                <span className="issue-id">{i.issue_number}</span>
                <PriorityBadge priority={i.priority} />
                <StatusBadge status={i.status} />
                {i.overdue && <span className="badge st-rejected">Overdue</span>}
                {i.is_hidden && <span className="badge">Hidden</span>}
              </div>

              <div className="issue-visual">
                {i.images.length > 0 && (
                  <a className="issue-thumb-link" href={fileUrl(i.images[0])} target="_blank" rel="noopener noreferrer" aria-label={`Open larger image for ${i.issue_number}`}>
                    <img className="issue-thumb" src={fileUrl(i.images[0])} alt={`Issue evidence for ${i.issue_number}`} loading="lazy" />
                  </a>
                )}

                <div className="issue-copy">
                  <h3><Link to={`/issues/${i.id}`}>{i.title}</Link></h3>
                  <p className="muted small row wrap issue-meta-row">
                    <span><MapPin size={13} /> {i.location}</span>
                    {[i.building, i.floor, i.room_number].filter(Boolean).length > 0 &&
                      <span>{[i.building, i.floor && `Floor ${i.floor}`, i.room_number && `Room ${i.room_number}`].filter(Boolean).join(" · ")}</span>}
                    <span>{i.category}</span>
                    <span title={fmtDate(i.created_at)}><Clock size={13} /> {timeAgo(i.created_at)}</span>
                    <span>by {i.reporter.name}</span>
                  </p>
                  <p className="issue-description">{i.description}{i.description.length >= 160 ? "…" : ""}</p>
                  {i.location_description && <p className="muted small">{i.location_description}</p>}
                  <div className="issue-actions row wrap">
                    {user.role === "student" ? (
                      <button className={i.voted ? "btn-small voted" : "btn-small ghost"} onClick={() => vote(i)} aria-pressed={i.voted}>
                        <ThumbsUp size={14} /> {i.voted ? "Supported" : "Support"} · {i.votes}
                      </button>
                    ) : <span className="muted small"><ThumbsUp size={13} /> {i.votes} supports</span>}
                    <Link className="btn-small ghost" to={`/issues/${i.id}`}>View details</Link>
                    {i.google_maps_url && <a className="btn-small ghost" href={i.google_maps_url} target="_blank" rel="noreferrer">View on Google Maps</a>}
                  </div>
                </div>
              </div>
            </div>
          </article>
        );
      })}

      {pages > 1 && (
        <div className="pager">
          <button className="btn-small ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page} of {pages}</span>
          <button className="btn-small ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </section>
  );
}
