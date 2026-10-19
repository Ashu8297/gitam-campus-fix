import { useEffect, useState, useCallback } from "react";
import { Download, Upload } from "lucide-react";
import { api } from "../api";
import { errMsg } from "../utils";

const blank = { role: "student", full_name: "", email: "", temporary_password: "", registration_number: "", staff_id: "", department: "", branch: "", year_of_study: "", semester: "", contact_number: "", work_category: "" };

export default function Users() {
  const [list, setList] = useState([]);
  const [q, setQ] = useState(""); const [role, setRole] = useState(""); const [status, setStatus] = useState("");
  const [f, setF] = useState(blank);
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  const [links, setLinks] = useState([]);
  const [imp, setImp] = useState({ role: "student", file: null });
  const [result, setResult] = useState(null);
  const [editing, setEditing] = useState(null);
  const [editForm, setEditForm] = useState(null);

  const load = useCallback(() => api.get("/api/users", { params: { q, role, status } }).then((r) => setList(r.data)).catch((e) => setErr(errMsg(e))), [q, role, status]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  async function create(e) {
    e.preventDefault(); setErr(""); setMsg("");
    const body = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ""));
    ["year_of_study", "semester"].forEach((k) => body[k] && (body[k] = Number(body[k])));
    try {
      const r = await api.post("/api/users", body);
      setMsg(body.temporary_password
        ? "Account created. The user must change the temporary password after their first sign-in."
        : r.data.email_sent ? "Account created and invitation emailed." : "Account created. Email is not configured, so share the link below manually.");
      if (r.data.invite_link) setLinks([{ email: body.email, link: r.data.invite_link }]);
      setF(blank); load();
    } catch (e2) { setErr(errMsg(e2)); }
  }

  async function setSt(u, s) { try { await api.patch(`/api/users/${u.id}/status`, { status: s }); load(); } catch (e) { setErr(errMsg(e)); } }
  async function resend(u) {
    try { const r = await api.post(`/api/users/${u.id}/resend-invite`);
      setMsg(r.data.email_sent ? "Invitation emailed." : "Email not configured; copy the link below.");
      if (r.data.invite_link) setLinks([{ email: u.email, link: r.data.invite_link }]); } catch (e) { setErr(errMsg(e)); }
  }
  async function template() {
    const r = await api.get("/api/users/template", { params: { role: imp.role }, responseType: "blob" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(r.data); a.download = `${imp.role}_template.csv`; a.click();
  }
  async function runImport() {
    setErr(""); setResult(null);
    const fd = new FormData(); fd.append("file", imp.file);
    try { const r = await api.post(`/api/users/bulk-import?role=${imp.role}`, fd); setResult(r.data); setLinks(r.data.invite_links); load(); }
    catch (e) { setErr(errMsg(e)); }
  }
  function edit(u) {
    setEditing(u.id);
    setEditForm({
      role: u.role, full_name: u.full_name, email: u.email,
      registration_number: u.registration_number || "", department: u.department || "",
      branch: u.branch || "", year_of_study: u.year_of_study || "",
      semester: u.semester || "", student_contact_number: u.student_contact_number || "",
      staff_id: u.staff_id || "", work_category: u.work_category || "",
      staff_contact_number: u.staff_contact_number || "",
    });
  }
  async function saveEdit(e) {
    e.preventDefault(); setErr(""); setMsg("");
    const body = { ...editForm };
    ["year_of_study", "semester"].forEach((k) => {
      body[k] = body[k] ? Number(body[k]) : null;
    });
    try {
      await api.patch(`/api/users/${editing}`, body);
      setEditing(null); setEditForm(null); setMsg("Account updated."); load();
    } catch (e2) { setErr(errMsg(e2)); }
  }
  const setEdit = (key) => (e) => setEditForm({ ...editForm, [key]: e.target.value });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  return (
    <div>
      <h2>User management</h2>
      {err && <div className="alert" role="alert">{err}</div>}
      {msg && <div className="ok" role="status">{msg}</div>}
      {links.length > 0 && (
        <div className="card"><strong>Invitation links (valid 48 hours, one use)</strong>
          <p className="muted small">Shown only because email is not configured. Send each link only to its owner.</p>
          {links.map((l) => <div key={l.email} className="small linkrow"><b>{l.email}</b> <input readOnly value={l.link} onFocus={(e) => e.target.select()} /></div>)}
        </div>
      )}
      <form className="card form grid2" onSubmit={create}>
        <h3 style={{ gridColumn: "1/-1" }}>Create one account</h3>
        <label>Role<select value={f.role} onChange={set("role")}><option value="student">Student</option><option value="admin">Administrator</option><option value="staff">Facility staff</option></select></label>
        <label>Full name<input value={f.full_name} onChange={set("full_name")} required /></label>
        <label>Email<input type="email" value={f.email} onChange={set("email")} required /></label>
        <label>Initial temporary password (optional)<input type="password" autoComplete="new-password" value={f.temporary_password} onChange={set("temporary_password")} placeholder="Leave blank to send an invitation" /></label>
        <p className="muted small" style={{ gridColumn: "1/-1" }}>Temporary passwords must be at least 10 characters and include upper/lowercase letters and a number. The password is stored only as a secure hash, and the user must change it after signing in.</p>
        {f.role === "student" ? (<>
          <label>Registration number<input value={f.registration_number} onChange={set("registration_number")} required /></label>
          <label>Department<input value={f.department} onChange={set("department")} /></label>
          <label>Branch<input value={f.branch} onChange={set("branch")} /></label>
          <label>Year<input type="number" min="1" max="6" value={f.year_of_study} onChange={set("year_of_study")} /></label>
          <label>Semester<input type="number" min="1" max="12" value={f.semester} onChange={set("semester")} /></label>
        </>) : f.role === "staff" ? (<>
          <label>Staff ID<input value={f.staff_id} onChange={set("staff_id")} required /></label>
          <label>Work category<input value={f.work_category} onChange={set("work_category")} placeholder="e.g. Electrical" /></label>
          <label>Contact number<input value={f.contact_number} onChange={set("contact_number")} /></label>
        </>) : <p className="muted small">Administrator accounts have access to account and issue management features.</p>}
        {f.role === "student" && <label>Contact number<input value={f.contact_number} onChange={set("contact_number")} /></label>}
        <button className="btn-small" style={{ gridColumn: "1/-1", justifySelf: "start" }}>Create account</button>
      </form>
      <p className="muted small">Only administrators can create or promote administrator accounts.</p>

      <div className="card form">
        <h3>Bulk import (CSV, up to 200 rows)</h3>
        <div className="row wrap">
          <select aria-label="Import role" value={imp.role} onChange={(e) => setImp({ ...imp, role: e.target.value })}><option value="student">Students</option><option value="staff">Staff</option></select>
          <button className="btn-small ghost" onClick={template}><Download size={14} /> Sample CSV</button>
          <input type="file" accept=".csv,text/csv" aria-label="CSV file" onChange={(e) => setImp({ ...imp, file: e.target.files[0] })} />
          <button className="btn-small" disabled={!imp.file} onClick={runImport}><Upload size={14} /> Import</button>
        </div>
        {result && (<div role="status"><strong>{result.created} created, {result.failed.length} failed.</strong>
          {result.failed.map((x) => <div key={x.row} className="small field-error">Row {x.row} {x.email}: {x.error}</div>)}</div>)}
      </div>

      <div className="filters">
        <input aria-label="Search users" placeholder="Search name, email, ID…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Role filter" value={role} onChange={(e) => setRole(e.target.value)}><option value="">All roles</option><option value="student">Students</option><option value="admin">Administrators</option><option value="staff">Facility staff</option></select>
        <select aria-label="Status filter" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option><option value="invited">Invited</option><option value="active">Active</option><option value="suspended">Suspended</option><option value="deactivated">Deactivated</option></select>
      </div>
      <div className="table-wrap"><table>
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Details</th><th>Status</th><th>Registered</th><th>Actions</th></tr></thead>
        <tbody>
          {list.length === 0 && <tr><td colSpan="7" className="muted">No users found.</td></tr>}
          {list.map((u) => (
            <tr key={u.id}><td>{u.full_name}</td><td>{u.email}</td><td>{u.role}</td>
              <td className="small">{u.role === "student"
                ? [u.registration_number, u.department, u.branch, u.year_of_study && `Year ${u.year_of_study}`, u.semester && `Semester ${u.semester}`].filter(Boolean).join(" · ") || "—"
                : u.role === "staff" ? [u.staff_id, u.work_category].filter(Boolean).join(" · ") || "—" : "—"}</td>
              <td><span className={`badge us-${u.status}`}>{u.status}</span></td>
              <td className="small">{u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}</td>
              <td className="row wrap">
                <button className="btn-small ghost" onClick={() => editing === u.id ? (setEditing(null), setEditForm(null)) : edit(u)}>Edit</button>
                {u.status === "invited" && <button className="btn-small ghost" onClick={() => resend(u)}>Resend invite</button>}
                {u.status === "active" && <button className="btn-small ghost" onClick={() => setSt(u, "suspended")}>Suspend</button>}
                {(u.status === "suspended" || u.status === "deactivated") && <button className="btn-small ghost" onClick={() => setSt(u, "active")}>Reactivate</button>}
                {u.status === "active" && <button className="btn-small danger" onClick={() => window.confirm("Deactivate this account?") && setSt(u, "deactivated")}>Deactivate</button>}
                {u.status === "active" && <button className="btn-small ghost" onClick={() => resend(u)}>Reset link</button>}
              </td></tr>
          ))}
          {editing && editForm && <tr><td colSpan="7">
            <form className="form grid2" onSubmit={saveEdit}>
              <h3 style={{ gridColumn: "1/-1" }}>Edit account</h3>
              <label>Role<select value={editForm.role} onChange={setEdit("role")}><option value="student">Student</option><option value="admin">Administrator</option><option value="staff">Facility staff</option></select></label>
              <label>Full name<input required value={editForm.full_name} onChange={setEdit("full_name")} /></label>
              <label>Email<input type="email" required value={editForm.email} onChange={setEdit("email")} /></label>
              {editForm.role === "student" && <>
                <label>Registration number<input required value={editForm.registration_number} onChange={setEdit("registration_number")} /></label>
                <label>Department<input value={editForm.department} onChange={setEdit("department")} /></label>
                <label>Branch<input value={editForm.branch} onChange={setEdit("branch")} /></label>
                <label>Year<input type="number" min="1" max="6" value={editForm.year_of_study} onChange={setEdit("year_of_study")} /></label>
                <label>Semester<input type="number" min="1" max="12" value={editForm.semester} onChange={setEdit("semester")} /></label>
                <label>Contact number<input value={editForm.student_contact_number} onChange={setEdit("student_contact_number")} /></label>
              </>}
              {editForm.role === "staff" && <>
                <label>Staff ID<input required value={editForm.staff_id} onChange={setEdit("staff_id")} /></label>
                <label>Work category<input value={editForm.work_category} onChange={setEdit("work_category")} /></label>
                <label>Contact number<input value={editForm.staff_contact_number} onChange={setEdit("staff_contact_number")} /></label>
              </>}
              <div className="row" style={{ gridColumn: "1/-1" }}>
                <button className="btn-small">Save changes</button>
                <button type="button" className="btn-small ghost" onClick={() => { setEditing(null); setEditForm(null); }}>Cancel</button>
              </div>
            </form>
          </td></tr>}
        </tbody></table></div>
    </div>
  );
}
