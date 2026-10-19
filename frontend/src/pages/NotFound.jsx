import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <main className="login-page">
      <section className="login-card" style={{ textAlign: "center" }}>
        <h1>404</h1>
        <p>That page could not be found.</p>
        <Link to="/login">Back to sign in</Link>
      </section>
    </main>
  );
}
