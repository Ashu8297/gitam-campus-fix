import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Camera } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { ProfileAvatar } from "../components/ProfileIdentity";
import { errMsg } from "../utils";

const ROLE_LABEL = { student: "Student", admin: "Administrator", staff: "Facilities Staff" };
const PHOTO_MAX_BYTES = 5 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

function fieldsFor(profile) {
  const common = [
    { key: "full_name", label: "Display name", type: "text", required: true },
    { key: "email", label: "Email address", readOnly: true },
  ];
  if (profile.role === "student") {
    return [
      ...common,
      { key: "registration_number", label: "Registration number", readOnly: true },
      { key: "username", label: "Display username", type: "text" },
      { key: "department", label: "Department", type: "text" },
      { key: "branch", label: "Branch", type: "text" },
      { key: "year_of_study", label: "Year of study", type: "number", min: 1, max: 6 },
      { key: "semester", label: "Semester", type: "number", min: 1, max: 12 },
      { key: "contact_number", label: "Contact number", type: "tel" },
    ];
  }
  if (profile.role === "staff") {
    return [
      ...common,
      { key: "staff_id", label: "Staff ID", readOnly: true },
      { key: "work_category", label: "Assigned unit / work category", type: "text" },
      { key: "contact_number", label: "Contact number", type: "tel" },
    ];
  }
  return [...common, { key: "contact_number", label: "Contact number", type: "tel" }];
}

export default function Profile() {
  const { user, updateUser } = useAuth();
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState({});
  const [editing, setEditing] = useState(false);
  const [photo, setPhoto] = useState(null);
  const [photoPreview, setPhotoPreview] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const fields = useMemo(() => profile ? fieldsFor(profile) : [], [profile]);

  async function loadProfile() {
    setLoading(true);
    setError("");
    try {
      const response = await api.get("/api/users/me/profile");
      setProfile(response.data);
      setForm(response.data);
      updateUser(response.data);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadProfile(); }, []);

  useEffect(() => () => {
    if (photoPreview) URL.revokeObjectURL(photoPreview);
  }, [photoPreview]);

  function selectPhoto(event) {
    const file = event.target.files?.[0];
    setError("");
    setMessage("");
    if (!file) return;
    if (!PHOTO_TYPES.includes(file.type)) {
      setPhoto(null);
      setPhotoPreview("");
      setError("Choose a JPG, PNG, or WEBP image.");
      event.target.value = "";
      return;
    }
    if (file.size > PHOTO_MAX_BYTES) {
      setPhoto(null);
      setPhotoPreview("");
      setError("Profile photos must be 5 MB or smaller.");
      event.target.value = "";
      return;
    }
    setPhoto(file);
    setPhotoPreview(URL.createObjectURL(file));
  }

  async function saveProfile(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    const payload = {};
    fields.filter((field) => !field.readOnly).forEach(({ key, type }) => {
      const value = form[key];
      payload[key] = value === "" || value == null
        ? null
        : type === "number" ? Number(value) : value.trim();
    });
    try {
      const response = await api.patch("/api/users/me/profile", payload);
      setProfile(response.data);
      setForm(response.data);
      updateUser(response.data);
      setEditing(false);
      setMessage("Profile changes saved.");
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setSaving(false);
    }
  }

  async function savePhoto() {
    if (!photo) return;
    setSaving(true);
    setError("");
    setMessage("");
    const body = new FormData();
    body.append("file", photo);
    try {
      const response = await api.post("/api/users/me/profile/photo", body);
      setProfile(response.data);
      setForm(response.data);
      updateUser(response.data);
      setPhoto(null);
      setPhotoPreview("");
      setMessage("Profile photo updated.");
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setSaving(false);
    }
  }

  async function deletePhoto() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await api.delete("/api/users/me/profile/photo");
      setProfile(response.data);
      setForm(response.data);
      updateUser(response.data);
      setPhoto(null);
      setPhotoPreview("");
      setMessage("Profile photo removed. Your default avatar is restored.");
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setSaving(false);
    }
  }

  function cancelEditing() {
    setForm(profile);
    setEditing(false);
    setError("");
  }

  if (loading) return <div className="skeleton" aria-label="Loading profile" />;
  if (!profile) return <div className="alert" role="alert">{error || "Profile could not be loaded."}</div>;

  const photoSrc = photoPreview || profile.profile_photo_url;
  return (
    <section className="profile-page">
      <div className="profile-page-heading">
        <div><h2>My Profile</h2><p className="muted">Manage your personal account details.</p></div>
        <Link className="btn-small ghost" to={`/${user.role}`}>Back to dashboard</Link>
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
      {message && <div className="ok" role="status">{message}</div>}

      <div className="card profile-summary">
        <div className="profile-avatar-wrap">
          <ProfileAvatar profile={{ ...profile, profile_photo_url: photoSrc }} size="profile-large" />
          <div className="profile-photo-actions">
            <label className="btn-small ghost profile-file-label" htmlFor="profile-photo"><Camera size={15} /> Choose photo</label>
            <input id="profile-photo" className="profile-photo-input" type="file" accept="image/jpeg,image/png,image/webp" onChange={selectPhoto} />
            {photo && <button type="button" className="btn-small" onClick={savePhoto} disabled={saving}>Save photo</button>}
            {profile.profile_photo_url && !photo && <button type="button" className="btn-small ghost" onClick={deletePhoto} disabled={saving}>Remove photo</button>}
            <small className="muted">JPG, PNG or WEBP · up to 5 MB</small>
          </div>
        </div>
        <div className="profile-summary-info">
          <span className={`role-badge role-${profile.role}`}>{ROLE_LABEL[profile.role]}</span>
          <h3>{profile.full_name}</h3>
          <p className="muted">{profile.email}</p>
          <div className="profile-completion-line">
            <span>Profile completion</span><strong>{profile.completion}%</strong>
          </div>
          <div className="progress" aria-label={`Profile ${profile.completion}% complete`}><span style={{ width: `${profile.completion}%` }} /></div>
          {profile.missing.length > 0 && <p className="muted small">Still needed: {profile.missing.map((item) => item.replaceAll("_", " ")).join(", ")}</p>}
        </div>
      </div>

      <form className="card form profile-edit-card" onSubmit={saveProfile}>
        <div className="row between wrap">
          <div><h3>Personal details</h3><p className="muted small">Protected account role and permissions cannot be edited here.</p></div>
          {!editing && <button type="button" className="btn-small" onClick={() => { setForm(profile); setEditing(true); }}>Edit profile</button>}
        </div>
        <div className="profile-fields">
          {fields.map(({ key, label, type = "text", readOnly, min, max, required }) => (
            <div key={key}>
              <label htmlFor={`profile-${key}`}>{label}{required ? " *" : ""}</label>
              <input
                id={`profile-${key}`}
                type={type}
                min={min}
                max={max}
                value={form[key] ?? ""}
                readOnly={readOnly || !editing}
                required={required}
                onChange={(event) => setForm({ ...form, [key]: event.target.value })}
              />
            </div>
          ))}
        </div>
        {editing && (
          <div className="row wrap profile-edit-actions">
            <button className="btn-small" type="submit" disabled={saving}>{saving ? "Saving…" : "Save changes"}</button>
            <button className="btn-small ghost" type="button" onClick={cancelEditing} disabled={saving}>Cancel</button>
          </div>
        )}
      </form>
    </section>
  );
}
