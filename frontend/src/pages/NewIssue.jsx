import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Loader2, LocateFixed, Camera } from "lucide-react";
import { api } from "../api";
import { errMsg, fmtDate } from "../utils";

const MAX_PHOTOS = 5;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const newClientToken = () => crypto.randomUUID().replace(/-/g, "");
const emptyForm = () => ({
  title: "", category_id: "", custom_category: "", description: "", location: "",
  building: "", floor: "", room_number: "", location_description: "", priority: "medium",
});

export default function NewIssue() {
  const nav = useNavigate();
  const videoRef = useRef(null);
  const filesRef = useRef([]);
  const [token, setToken] = useState(newClientToken);
  const [cats, setCats] = useState([]);
  const [categoryError, setCategoryError] = useState("");
  const [f, setF] = useState(emptyForm);
  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [cameraStream, setCameraStream] = useState(null);
  const [cameraError, setCameraError] = useState("");
  const [gps, setGps] = useState(null);
  const [gpsStatus, setGpsStatus] = useState("Getting location");
  const [locationError, setLocationError] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);

  useEffect(() => {
    api.get("/api/categories")
      .then((r) => setCats(r.data))
      .catch((error) => setCategoryError(errMsg(error)));
    locate();
  }, []);

  useEffect(() => () => cameraStream?.getTracks().forEach((track) => track.stop()), [cameraStream]);

  useEffect(() => {
    const urls = files.map((file) => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [files]);

  useEffect(() => {
    if (videoRef.current && cameraStream) videoRef.current.srcObject = cameraStream;
  }, [cameraStream]);

  const isOther = cats.find((c) => String(c.id) === f.category_id)?.name.startsWith("Other");
  const set = (k) => (e) => setF((current) => ({ ...current, [k]: e.target.value }));

  function updateFiles(nextFiles) {
    filesRef.current = nextFiles;
    setFiles(nextFiles);
  }

  function locate() {
    setLocationError("");
    setGps(null);
    if (!navigator.geolocation) {
      setGpsStatus("GPS unavailable");
      setLocationError("This browser does not support GPS location. Enter your location manually to continue.");
      return;
    }
    setGpsStatus("Getting location");
    try {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          setGps({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: position.coords.accuracy,
            capturedAt: new Date(position.timestamp).toISOString(),
          });
          setGpsStatus("Location captured");
        },
        (error) => {
          const messages = {
            1: "Location permission was denied. You can still report the issue by entering its location manually.",
            2: "Your device could not determine a GPS location. Enter the location manually to continue.",
            3: "The GPS request timed out. Enter the location manually or try GPS again.",
          };
          setLocationError(messages[error.code] || "GPS is unavailable. Enter the location manually to continue.");
          setGpsStatus("GPS unavailable");
        },
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
      );
    } catch {
      setLocationError("GPS is unavailable. Enter the location manually to continue.");
      setGpsStatus("GPS unavailable");
    }
  }

  function validateImages(selected) {
    if (selected.length > MAX_PHOTOS) return `You can attach up to ${MAX_PHOTOS} photos.`;
    const invalidType = selected.find((file) => !ALLOWED_IMAGE_TYPES.includes(file.type));
    if (invalidType) return `${invalidType.name} is not a JPG, PNG, or WEBP image.`;
    const tooLarge = selected.find((file) => file.size > MAX_IMAGE_BYTES);
    if (tooLarge) return `${tooLarge.name} is larger than 5 MB.`;
    return "";
  }

  function chooseFiles(event) {
    const selected = [...filesRef.current, ...event.target.files];
    const imageError = validateImages(selected);
    if (imageError) setErr(imageError);
    else {
      updateFiles(selected);
      setErr("");
    }
    event.target.value = "";
  }

  async function startCamera() {
    setCameraError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Camera access is not available in this browser. Use the photo upload option instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      setCameraStream(stream);
    } catch (error) {
      const denied = error.name === "NotAllowedError" || error.name === "PermissionDeniedError";
      setCameraError(denied
        ? "Camera permission was denied. Allow camera access or use the photo upload option."
        : "Could not open a camera. Check that one is connected, or use the photo upload option.");
    }
  }

  function stopCamera() {
    cameraStream?.getTracks().forEach((track) => track.stop());
    setCameraStream(null);
  }

  function capturePhoto() {
    const video = videoRef.current;
    if (!video?.videoWidth || !video.videoHeight) {
      setCameraError("The camera is not ready yet. Please wait a moment and try again.");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      setCameraError("Could not prepare the camera image. Please use the photo upload option.");
      return;
    }
    context.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) {
        setCameraError("Could not capture a photo. Please try again or upload an image.");
        return;
      }
      const photo = new File([blob], `campus-fix-${Date.now()}.jpg`, { type: "image/jpeg" });
      const nextFiles = [...filesRef.current, photo];
      const imageError = validateImages(nextFiles);
      if (imageError) setErr(imageError);
      else { updateFiles(nextFiles); setErr(""); }
      stopCamera();
    }, "image/jpeg", 0.9);
  }

  function removePhoto(index) {
    updateFiles(filesRef.current.filter((_, currentIndex) => currentIndex !== index));
  }

  async function submit(e) {
    e.preventDefault();
    setErr("");
    if (busy) return;
    if (f.title.trim().length < 5) return setErr("Title must be at least 5 characters.");
    if (!f.category_id) return setErr("Please choose a category.");
    if (isOther && !f.custom_category.trim()) return setErr("Please enter your custom category.");
    if (f.description.trim().length < 10) return setErr("Please describe the issue in at least 10 characters.");
    if (f.location.trim().length < 2) return setErr("Please enter a location or address.");
    const imageError = validateImages(files);
    if (imageError) return setErr(imageError);

    const fd = new FormData();
    Object.entries({ ...f, client_token: token }).forEach(([key, value]) => fd.append(key, value));
    if (gps) {
      fd.append("latitude", String(gps.latitude));
      fd.append("longitude", String(gps.longitude));
      fd.append("gps_accuracy_meters", String(gps.accuracy));
      fd.append("gps_captured_at", gps.capturedAt);
    }
    files.forEach((file) => fd.append("images", file));
    setBusy(true);
    try {
      const response = await api.post("/api/issues", fd);
      setDone(response.data);
    } catch (error) {
      setErr(errMsg(error));
    } finally {
      setBusy(false);
    }
  }

  if (done) return (
    <div className="card center-card">
      <CheckCircle2 size={48} color="var(--green)" />
      <h2>Report submitted</h2>
      <p>Your issue <strong>{done.issue_number}</strong> has been submitted.</p>
      <p><strong>{done.title}</strong> · {done.category} · {done.location}</p>
      <button className="btn-small" onClick={() => nav(`/issues/${done.id}`)}>View my report</button>
      <button className="btn-small ghost" onClick={() => {
        setDone(null); setF(emptyForm()); updateFiles([]); setGps(null);
        setLocationError(""); setGpsStatus("Getting location"); setErr(""); setToken(newClientToken());
        locate();
      }}>Report another issue</button>
    </div>
  );

  return (
    <form className="card form" onSubmit={submit} noValidate>
      <h2>Report a new issue</h2>
      {categoryError && <div className="alert" role="alert">{categoryError} Refresh the page to try loading categories again.</div>}
      <label htmlFor="t">Issue title</label>
      <input id="t" value={f.title} onChange={set("title")} maxLength={200} required />
      <label htmlFor="c">Category</label>
      <select id="c" value={f.category_id} onChange={set("category_id")} required>
        <option value="">Select a category</option>
        {cats.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
      </select>
      {isOther && (<><label htmlFor="cc">Custom category</label><input id="cc" value={f.custom_category} onChange={set("custom_category")} maxLength={100} required /></>)}
      <label htmlFor="d">Detailed description</label>
      <textarea id="d" rows={4} value={f.description} onChange={set("description")} maxLength={5000} required />
      <label htmlFor="l">Location / Address</label>
      <input id="l" name="location" value={f.location} onChange={set("location")} maxLength={200} placeholder="Building, classroom, floor, room, or nearby landmark" required />
      <div className="row wrap">
        <button type="button" className="btn-small ghost" onClick={locate} disabled={gpsStatus === "Getting location"}>
          <LocateFixed size={14} /> {gpsStatus === "Getting location" ? "Getting location" : gpsStatus === "Location captured" ? "Get location again" : "Try GPS again"}
        </button>
        <strong className="small" aria-live="polite">{gpsStatus}</strong>
      </div>
      {locationError && <div className="alert" role="status">{locationError}</div>}
      {gps && (
        <div className="card gps-summary" aria-live="polite">
          <strong>Location captured</strong>
          <p className="small">Latitude: {gps.latitude.toFixed(6)} · Longitude: {gps.longitude.toFixed(6)}</p>
          <p className="small">GPS accuracy: {Math.round(gps.accuracy)} meters · Captured: {fmtDate(gps.capturedAt)}</p>
          <p className="muted small">GPS coordinates do not identify the exact room. Enter the readable location above to help staff find the issue.</p>
        </div>
      )}
      <div className="grid2">
        <label>Building / Block<input value={f.building} onChange={set("building")} maxLength={150} /></label>
        <label>Floor<input value={f.floor} onChange={set("floor")} maxLength={40} placeholder="e.g. Ground, 2" /></label>
        <label>Room Number (if applicable)<input value={f.room_number} onChange={set("room_number")} maxLength={60} /></label>
        <label>Additional Location Description<textarea rows={2} value={f.location_description} onChange={set("location_description")} maxLength={1000} placeholder="Nearby landmark, entrance, or directions" /></label>
      </div>
      <fieldset>
        <legend>Priority</legend>
        <div className="row wrap">
          {[["high", "High (red)"], ["medium", "Medium (orange)"], ["low", "Low (yellow)"]].map(([value, label]) => (
            <label key={value} className={`prio-opt prio-${value}${f.priority === value ? " on" : ""}`}>
              <input type="radio" name="p" value={value} checked={f.priority === value} onChange={set("priority")} /> {label}
            </label>
          ))}
        </div>
        <p className="muted small">Priority shows how urgent it feels to you. It does not guarantee the order of repair.</p>
      </fieldset>
      <label htmlFor="img">Photos (up to 5, JPG/PNG/WEBP, 5 MB each)</label>
      <div className="row wrap">
        <button type="button" className="btn-small ghost" onClick={startCamera} disabled={!!cameraStream || files.length >= MAX_PHOTOS}>
          <Camera size={14} /> Open camera
        </button>
        <label className="btn-small ghost file-picker" htmlFor="img">Choose photo / use device camera</label>
        <input id="img" className="photo-input" type="file" accept="image/jpeg,image/png,image/webp" capture="environment"
          multiple onChange={chooseFiles} disabled={files.length >= MAX_PHOTOS} />
      </div>
      {cameraError && <div className="alert" role="status">{cameraError}</div>}
      {cameraStream && (
        <div className="camera-preview">
          <video ref={videoRef} autoPlay playsInline muted aria-label="Camera preview" />
          <div className="row wrap">
            <button type="button" className="btn-small" onClick={capturePhoto}><Camera size={14} /> Capture photo</button>
            <button type="button" className="btn-small ghost" onClick={stopCamera}>Close camera</button>
          </div>
        </div>
      )}
      {previews.length > 0 && (
        <div className="photo-previews" aria-label="Photo previews">
          {previews.map((url, index) => (
            <div className="photo-preview" key={`${url}-${index}`}>
              <img src={url} alt={`Selected issue photo ${index + 1}`} />
              <span className="small">{files[index].name}</span>
              <div className="row wrap">
                <label className="btn-small ghost file-picker" htmlFor={`retake-${index}`}>Retake / replace</label>
                <input id={`retake-${index}`} className="photo-input" type="file" accept="image/jpeg,image/png,image/webp" capture="environment"
                  onChange={(event) => {
                    if (!event.target.files.length) return;
                    const replacement = event.target.files[0];
                    const next = [...filesRef.current];
                    next[index] = replacement;
                    const imageError = validateImages(next);
                    if (imageError) setErr(imageError);
                    else { updateFiles(next); setErr(""); }
                    event.target.value = "";
                  }} />
                <button type="button" className="btn-small danger" onClick={() => removePhoto(index)}>Remove</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {err && <div className="alert" role="alert">{err}</div>}
      <button className="btn-primary" disabled={busy || !!categoryError}>
        {busy && <Loader2 className="spin" size={18} />} {busy ? "Submitting…" : "Submit report"}
      </button>
    </form>
  );
}
