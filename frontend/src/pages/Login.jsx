import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff, GraduationCap, ShieldCheck, Wrench, Loader2 } from "lucide-react";
import Logo from "../components/Logo";
import ThemeToggle from "../components/ThemeToggle";
import { useAuth } from "../auth";

const ROLES = [
  { id: "student", label: "Student", icon: GraduationCap, hint: "Email" },
  { id: "staff", label: "Facilities Staff", icon: Wrench, hint: "Email or Staff ID" },
  { id: "admin", label: "Admin", icon: ShieldCheck, hint: "Email" },
];

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [role, setRole] = useState("student");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={user.must_change_password ? "/change-password" : `/${user.role}`} replace />;

  async function submit(e) {
    e.preventDefault();
    const fe = {};
    if (!identifier.trim()) fe.identifier = "Please enter your email or ID.";
    if (!password) fe.password = "Please enter your password.";
    setFieldErrors(fe);
    setError("");
    if (Object.keys(fe).length) return;

    setBusy(true);
    try {
      const u = await login(role, identifier.trim(), password);
      navigate(u.must_change_password ? "/change-password" : `/${u.role}`, { replace: true });
    } catch (err) {
      if (!err.response) setError("Cannot reach the server. Check your connection and try again.");
      else setError(err.response.data?.detail || "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const current = ROLES.find((r) => r.id === role);

  return (
    <main className="login-page">
      <div className="login-theme">
        <ThemeToggle />
      </div>
      <section className="login-card">
        <div className="brand">
          <Logo size={84} />
          <h1>Campus Fix</h1>
          <p className="brand-sub">GITAM Bhubaneswar</p>
          <p className="brand-tag">Campus Facilities &amp; Issue Reporting Portal</p>
        </div>

        <form onSubmit={submit} noValidate>
          {location.state?.message && <div className="ok" role="status">{location.state.message}</div>}
          <div className="role-tabs" role="radiogroup" aria-label="Sign in as">
            {ROLES.map(({ id, label, icon: Icon }) => (
              <button
                type="button"
                key={id}
                role="radio"
                aria-checked={role === id}
                className={role === id ? "role-tab active" : "role-tab"}
                onClick={() => setRole(id)}
              >
                <Icon size={18} />
                <span>{label}</span>
              </button>
            ))}
          </div>

          <label htmlFor="identifier">{current.hint}</label>
          <input
            id="identifier"
            autoComplete="username"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            aria-invalid={!!fieldErrors.identifier}
          />
          {fieldErrors.identifier && <p className="field-error">{fieldErrors.identifier}</p>}

          <label htmlFor="password">Password</label>
          <div className="pw-wrap">
            <input
              id="password"
              type={show ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={!!fieldErrors.password}
            />
            <button
              type="button"
              className="pw-toggle"
              onClick={() => setShow(!show)}
              aria-label={show ? "Hide password" : "Show password"}
            >
              {show ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          {fieldErrors.password && <p className="field-error">{fieldErrors.password}</p>}

          {error && (
            <div className="alert" role="alert">
              {error}
            </div>
          )}

          <button className="btn-primary" type="submit" disabled={busy}>
            {busy ? <Loader2 className="spin" size={18} /> : null}
            {busy ? "Signing in…" : "Sign in"}
          </button>

          <p className="forgot">
            <Link to="/forgot-password">Forgot password?</Link>
          </p>
        </form>

        <p className="disclaimer">
          Student-developed minor project. Not an official GITAM service.
        </p>
      </section>
    </main>
  );
}
