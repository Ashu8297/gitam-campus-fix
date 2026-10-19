import { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { MapPin, Star } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { PriorityBadge, StatusBadge } from "../components/Badges";
import Timeline from "../components/Timeline";
import { errMsg, fileUrl, fmtDate } from "../utils";

export default function IssueDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [issue, setIssue] = useState(null);
  const [staff, setStaff] = useState([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [staffId, setStaffId] = useState("");
  const [files, setFiles] = useState([]);
  const [rating, setRating] = useState(0);

  const load = useCallback(() =>
    api.get(`/api/issues/${id}`).then((r) => setIssue(r.data)).catch((e) => setErr(errMsg(e))), [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (user.role === "admin") api.get("/api/users/staff-options").then((r) => setStaff(r.data)).catch(() => {});
  }, [user.role]);

  async function act(path, body = {}, form = null) {
    setErr(""); setBusy(true);
    try {
      const r = await api.post(`/api/issues/${id}/${path}`, form || body);
      if (path === "decline") return nav("/staff");
      if (r.data?.id) setIssue(r.data); else await load();
      setText(""); setFiles([]);
      window.dispatchEvent(new Event("cf-notif-changed"));
    } catch (e) { setErr(errMsg(e)); }
    finally { setBusy(false); }
  }

  async function vote() {
    try {
      const r = await api.post(`/api/issues/${id}/vote`);
      setIssue({ ...issue, voted: r.data.voted, votes: r.data.votes });
    } catch (e) { setErr(errMsg(e)); }
  }

  function resolve() {
    const fd = new FormData();
    fd.append("description", text);
    files.forEach((f) => fd.append("images", f));
    act("resolve", null, fd);
  }

  if (!issue) return err ? <div className="alert" role="alert">{err}</div> : <div className="skeleton" />;
  const s = issue.status;
  const isAdmin = user.role === "admin", isStaff = user.role === "staff";
  const staffPicker = (
    <select aria-label="Staff member" value={staffId} onChange={(e) => setStaffId(e.target.value)}>
      <option value="">Choose staff…</option>
      {staff.map((x) => <option key={x.id} value={x.id}>{x.name}{x.category ? ` — ${x.category}` : ""}</option>)}
    </select>
  );

  return (
    <div className="detail-layout">
      <div className="detail-blank">
        <div className="card">
          <div className="row wrap" style={{ gap: "0.6rem" }}>
            <span className="muted">{issue.issue_number}</span>
            <PriorityBadge priority={issue.priority} /><StatusBadge status={s} />
            {issue.overdue && <span className="badge st-rejected">Overdue</span>}
          </div>

          <div className="row between" style={{ alignItems: "flex-start", marginTop: "0.8rem" }}>
            <div>
              <h2 style={{ marginTop: 0 }}>{issue.title}</h2>
              <p className="muted small row wrap" style={{ marginTop: "0.3rem" }}>
                <span><MapPin size={13} /> {issue.location}</span>
                <span>{issue.category}</span>
                <span>Reported by {issue.reporter.name}</span>
                <span>{fmtDate(issue.created_at)}</span>
                {issue.assigned_staff && <span>Assigned to {issue.assigned_staff}</span>}
              </p>
            </div>
            {issue.google_maps_url && (
              <a className="btn-small ghost" href={issue.google_maps_url} target="_blank" rel="noreferrer">View on Google Maps</a>
            )}
          </div>

          <div className="issue-media-wrap" style={{ marginTop: "1rem" }}>
            <div className="issue-media-grid">
              {issue.images.length > 0 ? issue.images.map((u) => (
                <a key={u} href={fileUrl(u)} target="_blank" rel="noreferrer">
                  <img className="issue-image" src={fileUrl(u)} alt="Reported issue" />
                </a>
              )) : <div className="card" style={{ marginTop: 0, padding: "0.9rem" }}><span className="muted">No evidence uploaded yet.</span></div>}
            </div>
          </div>

          <div className="card" style={{ marginTop: "1rem" }}>
            <h3>Complaint details</h3>
            <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{issue.description}</p>
          </div>

          {s === "rejected" && issue.rejection_reason && <div className="alert"><strong>Rejected:</strong> {issue.rejection_reason}</div>}
          {err && <div className="alert" role="alert">{err}</div>}
        </div>
      </div>

      <div className="side-panel">
      {isAdmin && (
        <div className="card actions">
          <h3>Administrator actions</h3>
          {(s === "reported") && <button className="btn-small ghost" disabled={busy} onClick={() => act("review")}>Start review</button>}
          {(s === "reported" || s === "under_review") && (<>
            <div className="row wrap">{staffPicker}
              <button className="btn-small" disabled={busy} onClick={() => act("approve", { staff_id: staffId ? Number(staffId) : null })}>
                {staffId ? "Approve & assign" : "Approve"}
              </button></div>
            <div className="row wrap">
              <input aria-label="Rejection reason" placeholder="Reason for rejection (required)" value={text} onChange={(e) => setText(e.target.value)} />
              <button className="btn-small danger" disabled={busy} onClick={() => act("reject", { reason: text })}>Reject</button></div>
          </>)}
          {["approved", "assigned", "reopened"].includes(s) && (
            <div className="row wrap">{staffPicker}
              <button className="btn-small" disabled={busy || !staffId} onClick={() => act("assign", { staff_id: Number(staffId) })}>
                {s === "assigned" ? "Reassign" : "Assign"}</button></div>
          )}
          {s === "resolved" && (<>
            <button className="btn-small" disabled={busy} onClick={() => act("close")}>Verify &amp; close</button>
            <div className="row wrap">
              <input aria-label="Reopen reason" placeholder="Reason to reopen (required)" value={text} onChange={(e) => setText(e.target.value)} />
              <button className="btn-small danger" disabled={busy} onClick={() => act("reopen", { reason: text })}>Reopen</button></div>
          </>)}
          <div className="row wrap">
            <label className="inline">Priority
              <select value={issue.priority} onChange={(e) => act("priority", { priority: e.target.value })}>
                <option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
              </select></label>
            <button className="btn-small ghost" disabled={busy} onClick={() => act("hide", { reason: text })}>
              {issue.is_hidden ? "Restore report" : "Hide report"}</button>
          </div>
        </div>
      )}

      {isStaff && (
        <div className="card actions">
          <h3>My task</h3>
          {s === "assigned" && (<>
            <button className="btn-small" disabled={busy} onClick={() => act("accept")}>Accept task</button>
            <div className="row wrap">
              <input aria-label="Decline reason" placeholder="Reason for declining (required)" value={text} onChange={(e) => setText(e.target.value)} />
              <button className="btn-small danger" disabled={busy} onClick={() => act("decline", { reason: text })}>Decline</button></div>
          </>)}
          {s === "accepted" && <button className="btn-small" disabled={busy} onClick={() => act("start")}>Start work</button>}
          {s === "in_progress" && (<>
            <textarea aria-label="Update or completion note" rows={3} placeholder="Progress update, or completion description" value={text} onChange={(e) => setText(e.target.value)} />
            <div className="row wrap">
              <button className="btn-small ghost" disabled={busy} onClick={() => act("progress", { note: text })}>Add progress update</button>
            </div>
            <label>Completion photos (1–5, required to resolve)
              <input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(e) => setFiles([...e.target.files].slice(0, 5))} /></label>
            <button className="btn-small" disabled={busy || files.length === 0} onClick={resolve}>Mark as resolved</button>
          </>)}
          {!["assigned", "accepted", "in_progress"].includes(s) && <p className="muted">No action needed right now.</p>}
        </div>
      )}

      {user.role === "student" && issue.is_mine && ["resolved", "closed"].includes(s) && (
        <div className="card">
          <h3>Your feedback</h3>
          {issue.my_feedback ? <p>You rated this {issue.my_feedback.rating}/5. Thank you!</p> : (<>
            <div className="stars" role="radiogroup" aria-label="Rating">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} type="button" role="radio" aria-checked={rating === n} aria-label={`${n} star${n > 1 ? "s" : ""}`}
                  className={n <= rating ? "star on" : "star"} onClick={() => setRating(n)}><Star size={24} /></button>
              ))}
            </div>
            <textarea rows={2} aria-label="Comment" placeholder="Optional comment" value={text} onChange={(e) => setText(e.target.value)} />
            <button className="btn-small" disabled={busy || !rating} onClick={() => act("feedback", { rating, comment: text })}>Submit feedback</button>
          </>)}
        </div>
      )}

        <div className="card">
          <h3>Activity timeline</h3>
          <Timeline items={issue.timeline} />
        </div>
      </div>
    </div>
  );
}
