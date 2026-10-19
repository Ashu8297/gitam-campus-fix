import { useEffect, useState } from "react";
import { Github, Linkedin, Instagram, Youtube, Pencil, GraduationCap } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import Logo from "../components/Logo";
import { errMsg, fileUrl } from "../utils";

const SOCIAL = [["github", Github], ["linkedin", Linkedin], ["instagram", Instagram], ["youtube", Youtube]];
const FIELDS = [["project_type", "Project type (e.g. semester / year)"], ["purpose", "Purpose"], ["problem", "Problem being solved"],
  ["features", "Key features (one per line)"], ["tech_stack", "Technology (one per line)"], ["submission_date", "Submission date"], ["disclaimer", "Disclaimer"]];
const lines = (s = "") => s.split("\n").filter(Boolean);

export default function About() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [d, setD] = useState(null);
  const [edit, setEdit] = useState(false);
  const [draft, setDraft] = useState({});
  const [msg, setMsg] = useState("");
  const load = () => api.get("/api/about").then((r) => { setD(r.data); setDraft(r.data.content); });
  useEffect(() => { load(); }, []);
  if (!d) return <div className="skeleton" />;
  const c = d.content;

  async function saveContent() {
    try { await api.put("/api/about/content", { content: draft }); setMsg("Saved."); setEdit(false); load(); } catch (e) { setMsg(errMsg(e)); }
  }

  return (
    <div className="about">
      <section className="card hero">
        <Logo size={72} />
        <div>
          <h2>{c.project_name}</h2>
          <p className="badge project-type"><GraduationCap size={14} /> {c.project_type}</p>
          <p className="muted">{c.institution} · Target submission: <strong>{c.submission_date}</strong></p>
        </div>
        {isAdmin && <button className="btn-small ghost" onClick={() => setEdit(!edit)}><Pencil size={14} /> {edit ? "Cancel" : "Edit page"}</button>}
      </section>
      {msg && <div className="ok" role="status">{msg}</div>}

      {edit ? (
        <div className="card form">
          {FIELDS.map(([k, l]) => (<div key={k}><label htmlFor={k}>{l}</label>
            <textarea id={k} rows={k === "submission_date" || k === "project_type" ? 1 : 4} value={draft[k] || ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} /></div>))}
          <button className="btn-primary" onClick={saveContent}>Save changes</button>
        </div>
      ) : (<>
        <section className="card"><h3>Purpose</h3><p>{c.purpose}</p><h3>The problem</h3><p>{c.problem}</p></section>
        <section className="card grid2">
          <div><h3>Key features</h3><ul>{lines(c.features).map((x) => <li key={x}>{x}</li>)}</ul></div>
          <div><h3>Technology stack</h3><ul>{lines(c.tech_stack).map((x) => <li key={x}>{x}</li>)}</ul></div>
        </section>
      </>)}

      <h3>Project development team</h3>
      <p className="muted small">Final-year B.Tech Computer Science students, 7th semester minor project.</p>
      <div className="team">{d.team.map((m) => <Member key={m.id} m={m} isAdmin={isAdmin} reload={load} />)}</div>
      <p className="muted small disclaimer-line">{c.disclaimer}</p>
    </div>
  );
}

function Member({ m, isAdmin, reload }) {
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState(m);
  const [err, setErr] = useState("");
  const initials = m.name.split(" ").map((x) => x[0]).slice(0, 2).join("");
  async function save() {
    try { const { id, ...body } = f; await api.put(`/api/about/team/${m.id}`, body); setEdit(false); reload(); } catch (e) { setErr(errMsg(e)); }
  }
  async function photo(e) {
    const fd = new FormData(); fd.append("file", e.target.files[0]);
    try { const r = await api.post("/api/about/upload", fd); setF({ ...f, photo_url: r.data.url }); } catch (e2) { setErr(errMsg(e2)); }
  }
  return (
    <article className="card member">
      {m.photo_url ? <img className="avatar" src={fileUrl(m.photo_url)} alt={m.name} /> : <div className="avatar ph" aria-hidden>{initials}</div>}
      <h4>{m.name}</h4>
      <p className="muted small">{m.role}</p>
      {m.skills && <p className="small">{m.skills}</p>}
      <div className="row center">
        {SOCIAL.map(([k, Icon]) => m[k] && <a key={k} href={m[k]} target="_blank" rel="noreferrer noopener" aria-label={`${m.name} on ${k}`} className="icon-btn"><Icon size={16} /></a>)}
      </div>
      {isAdmin && <button className="btn-small ghost" onClick={() => setEdit(!edit)}>{edit ? "Cancel" : "Edit"}</button>}
      {edit && (
        <div className="form">
          {["name", "role", "skills", "github", "linkedin", "instagram", "youtube"].map((k) => (
            <label key={k}>{k}<input value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>))}
          <label>Photo<input type="file" accept="image/*" onChange={photo} /></label>
          {err && <div className="alert">{err}</div>}
          <button className="btn-small" onClick={save}>Save</button>
        </div>
      )}
    </article>
  );
}
