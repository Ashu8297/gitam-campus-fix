import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import Logo from "../components/Logo";
import { api } from "../api";
import { errMsg } from "../utils";
import { useAuth } from "../auth";

export function SetPassword() {
  const [sp] = useSearchParams();
  const [pw, setPw] = useState(""); const [pw2, setPw2] = useState("");
  const [err, setErr] = useState(""); const [done, setDone] = useState(false); const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault(); setErr("");
    if (pw !== pw2) return setErr("Passwords do not match.");
    setBusy(true);
    try { await api.post("/api/auth/set-password", { token: sp.get("token") || "", password: pw }); setDone(true); }
    catch (e2) { setErr(errMsg(e2)); } finally { setBusy(false); }
  }
  return (
    <main className="login-page"><section className="login-card">
      <div className="brand"><Logo size={64} /><h1>Set your password</h1></div>
      {done ? <><div className="ok">Password saved. You can now sign in.</div><p><Link to="/login">Go to sign in</Link></p></> : (
        <form onSubmit={submit} noValidate>
          <label htmlFor="p1">New password</label><input id="p1" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
          <p className="muted small">At least 10 characters, with upper and lower case letters and a number.</p>
          <label htmlFor="p2">Confirm password</label><input id="p2" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
          {err && <div className="alert" role="alert">{err}</div>}
          <button className="btn-primary" disabled={busy}>{busy ? "Saving…" : "Save password"}</button>
        </form>)}
    </section></main>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState(""); const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  async function submit(e) {
    e.preventDefault(); setErr("");
    try { const r = await api.post("/api/auth/forgot-password", { email }); setMsg(r.data.message); } catch (e2) { setErr(errMsg(e2)); }
  }
  return (
    <main className="login-page"><section className="login-card">
      <div className="brand"><Logo size={64} /><h1>Forgot password</h1></div>
      {msg ? <div className="ok">{msg}</div> : (
        <form onSubmit={submit}>
          <label htmlFor="e">Your account email</label><input id="e" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          {err && <div className="alert" role="alert">{err}</div>}
          <button className="btn-primary">Send reset link</button>
        </form>)}
      <p className="forgot"><Link to="/login">Back to sign in</Link></p>
    </section></main>
  );
}

export function ChangePassword() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [pw, setPw] = useState(""); const [pw2, setPw2] = useState("");
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  if (!user) return <Navigate to="/login" replace />;

  async function submit(e) {
    e.preventDefault(); setErr("");
    if (pw !== pw2) return setErr("Passwords do not match.");
    setBusy(true);
    try {
      await api.post("/api/auth/change-password", { password: pw });
      logout();
      navigate("/login", { replace: true, state: { message: "Password updated. Sign in with your new password." } });
    } catch (e2) { setErr(errMsg(e2)); }
    finally { setBusy(false); }
  }

  return (
    <main className="login-page"><section className="login-card">
      <div className="brand"><Logo size={64} /><h1>Change temporary password</h1></div>
      <p className="muted">Choose a new password to continue using Campus Fix.</p>
      <form onSubmit={submit} noValidate>
        <label htmlFor="new-pw">New password</label><input id="new-pw" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
        <p className="muted small">At least 10 characters, with upper and lower case letters and a number.</p>
        <label htmlFor="confirm-pw">Confirm password</label><input id="confirm-pw" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
        {err && <div className="alert" role="alert">{err}</div>}
        <button className="btn-primary" disabled={busy}>{busy ? "Saving…" : "Save new password"}</button>
      </form>
    </section></main>
  );
}
