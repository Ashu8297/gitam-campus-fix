import { useEffect, useState } from "react";
import { api } from "../api";

export default function AdminSettings() {
  const [retentionDays, setRetentionDays] = useState(7);
  const [preview, setPreview] = useState({ complaint_count: 0, attachment_count: 0, issues: [] });
  const [logs, setLogs] = useState([]);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [allPreview, setAllPreview] = useState({ complaint_count: 0, attachment_count: 0 });
  const [showDeleteAllConfirm, setShowDeleteAllConfirm] = useState(false);
  const [deleteAllPhrase, setDeleteAllPhrase] = useState("");
  const [status, setStatus] = useState("");

  const load = async () => {
    try {
      const r = await api.get("/api/admin/settings");
      setRetentionDays(r.data.retention_days || 7);
      setPreview(r.data.preview || { complaint_count: 0, attachment_count: 0, issues: [] });
      setLogs(r.data.logs || []);
      const all = await api.get("/api/admin/settings/cleanup/delete-all/preview");
      setAllPreview(all.data);
    } catch (err) {
      setStatus(err.response?.data?.detail || "Unable to load retention settings.");
    }
  };

  useEffect(() => { load(); }, []);

  const saveRetention = async () => {
    setSaving(true);
    setStatus("");
    try {
      await api.put("/api/admin/settings/retention", { days: Number(retentionDays) });
      setStatus("Retention policy updated.");
      await load();
    } catch (err) {
      setStatus(err.response?.data?.detail || "Unable to update retention.");
    } finally {
      setSaving(false);
    }
  };

  const runPreview = async () => {
    setRunning(true);
    setStatus("");
    try {
      const r = await api.post("/api/admin/settings/cleanup/preview");
      setPreview(r.data || { complaint_count: 0, attachment_count: 0, issues: [] });
      setStatus(`Preview ready: ${r.data.complaint_count} complaints eligible.`);
    } catch (err) {
      setStatus(err.response?.data?.detail || "Unable to preview cleanup.");
    } finally {
      setRunning(false);
    }
  };

  const runCleanup = async () => {
    setRunning(true);
    setStatus("");
    try {
      const confirmed = window.confirm(
        `Permanently delete ${preview.complaint_count} old complaints and ${preview.attachment_count} attachments?\n\nThis action cannot be undone and will only affect records older than the selected retention period.`
      );
      if (!confirmed) {
        setStatus("Cleanup cancelled.");
        return;
      }
      const r = await api.post("/api/admin/settings/cleanup", { confirm: true, dry_run: false });
      setStatus(`Cleanup finished: ${r.data.complaint_count} complaints removed.`);
      await load();
    } catch (err) {
      setStatus(err.response?.data?.detail || "Cleanup failed.");
    } finally {
      setRunning(false);
    }
  };

  const reviewDeleteAll = async () => {
    setRunning(true);
    setStatus("");
    setDeleteAllPhrase("");
    try {
      const r = await api.get("/api/admin/settings/cleanup/delete-all/preview");
      setAllPreview(r.data);
      setShowDeleteAllConfirm(true);
    } catch (err) {
      setStatus(err.response?.data?.detail || "Unable to preview all complaints.");
    } finally {
      setRunning(false);
    }
  };

  const confirmDeleteAll = async () => {
    if (deleteAllPhrase !== "DELETE ALL COMPLAINTS") {
      setStatus("Type DELETE ALL COMPLAINTS exactly to continue.");
      return;
    }
    setRunning(true);
    setStatus("");
    try {
      const r = await api.post("/api/admin/settings/cleanup/delete-all", {
        confirmation: deleteAllPhrase,
        expected_complaints: allPreview.complaint_count,
        expected_attachments: allPreview.attachment_count,
      });
      setStatus(
        `Deleted ${r.data.complaint_count} complaints and ${r.data.attachment_count} attachments. Verified backup: ${r.data.backup || "not needed"}.` +
        (r.data.file_errors ? ` ${r.data.file_errors} attachment files could not be removed.` : "")
      );
      setShowDeleteAllConfirm(false);
      setDeleteAllPhrase("");
      await load();
    } catch (err) {
      setStatus(err.response?.data?.detail || "Delete-all operation failed.");
      if (err.response?.status === 409) {
        await api.get("/api/admin/settings/cleanup/delete-all/preview")
          .then((r) => setAllPreview(r.data))
          .catch(() => {});
      }
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="page-header-row">
      <div style={{ width: "100%" }}>
        <h2>Retention &amp; cleanup</h2>
        <p className="muted">The configured retention period is calculated from each complaint’s created date and applies before any automatic cleanup runs.</p>

        <div className="card">
          <div className="row wrap" style={{ alignItems: "center" }}>
            <label htmlFor="retention-days" style={{ margin: 0, minWidth: 180 }}>Retention period</label>
            <select id="retention-days" value={retentionDays} onChange={(e) => setRetentionDays(Number(e.target.value))}>
              <option value={1}>24 hours</option>
              <option value={7}>7 days</option>
              <option value={30}>30 days</option>
            </select>
            <button className="btn-small" onClick={saveRetention} disabled={saving}>{saving ? "Saving…" : "Save policy"}</button>
          </div>
          <p className="muted small" style={{ marginTop: 12 }}>
            Backup first, then dry-run cleanup before permanent deletion. All cleanup actions are limited to complaint records older than the selected retention period.
          </p>
        </div>

        <div className="card">
          <div className="row wrap" style={{ justifyContent: "space-between" }}>
            <div>
              <strong>Cleanup preview</strong>
              <div className="muted small">{preview.complaint_count} complaints eligible</div>
            </div>
            <div className="row wrap">
              <button className="btn-small ghost" onClick={runPreview} disabled={running}>{running ? "Working…" : "Dry run"}</button>
              <button className="btn-small danger" onClick={runCleanup} disabled={running || preview.complaint_count === 0}>Delete now</button>
            </div>
          </div>

          {preview.issues.length > 0 ? (
            <ul className="meta-list" style={{ marginTop: 16 }}>
              {preview.issues.slice(0, 10).map((issue) => (
                <li key={issue.id}>
                  <span>{issue.issue_number}</span>
                  <span>{issue.attachment_count} attached files</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small" style={{ marginTop: 16 }}>No complaint records are currently eligible for permanent cleanup.</p>
          )}
        </div>

        <div className="card">
          <h3>Delete All Complaints</h3>
          <p className="muted">
            Permanently removes every complaint, regardless of age, with its complaint-only records.
            User accounts, profiles, authentication records, application settings, and unrelated/shared files are preserved.
          </p>
          <p><strong>{allPreview.complaint_count}</strong> complaints and <strong>{allPreview.attachment_count}</strong> attachments are currently in scope.</p>
          <p className="muted small">
            A verified backup archive of complaint records and available local attachments is created before database deletion.
            Back up the database and uploads directory separately as an additional safeguard.
          </p>
          {!showDeleteAllConfirm ? (
            <button className="btn-small danger" onClick={reviewDeleteAll} disabled={running || allPreview.complaint_count === 0}>
              {running ? "Loading preview…" : "Review Delete All"}
            </button>
          ) : (
            <div className="card" role="group" aria-label="Confirm deleting all complaints">
              <p className="field-error">
                Confirm permanent deletion of {allPreview.complaint_count} complaints and {allPreview.attachment_count} attachments.
                A verified backup will be created before deletion.
              </p>
              <label htmlFor="delete-all-phrase">Type DELETE ALL COMPLAINTS to confirm</label>
              <input
                id="delete-all-phrase"
                value={deleteAllPhrase}
                onChange={(e) => setDeleteAllPhrase(e.target.value)}
                autoComplete="off"
              />
              <div className="row wrap" style={{ marginTop: 12 }}>
                <button className="btn-small danger" onClick={confirmDeleteAll} disabled={running || deleteAllPhrase !== "DELETE ALL COMPLAINTS"}>
                  {running ? "Creating backup and deleting…" : "Delete All Complaints"}
                </button>
                <button className="btn-small ghost" onClick={() => { setShowDeleteAllConfirm(false); setDeleteAllPhrase(""); }} disabled={running}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

        {status && <div className="alert" role="status">{status}</div>}

        <div className="card">
          <h3 style={{ marginBottom: 12 }}>Recent cleanup logs</h3>
          {logs.length === 0 ? (
            <p className="muted small">No cleanup activity yet.</p>
          ) : (
            <ul className="meta-list">
              {logs.map((log) => (
                <li key={log.id}>
                  <span>{new Date(log.started_at).toLocaleString()}</span>
                  <span>{log.status} · {log.complaint_count} complaints</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
