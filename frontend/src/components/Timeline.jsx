import { fmtDate } from "../utils";

export default function Timeline({ items }) {
  return (
    <ol className="timeline">
      {items.map((t) => (
        <li key={t.id}>
          <span className="dot" />
          <div>
            <strong>{t.event}</strong>
            <div className="muted small">
              {fmtDate(t.created_at)} · {t.actor}
              {t.actor_role ? ` (${t.actor_role})` : ""}
            </div>
            {t.note && <p className="note">{t.note}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
