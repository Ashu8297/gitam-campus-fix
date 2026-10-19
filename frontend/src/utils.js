import { API_BASE_URL } from "./api";

export const STATUS_LABEL = {
  reported: "Reported", under_review: "Under review", approved: "Approved", rejected: "Rejected",
  assigned: "Assigned", accepted: "Accepted", in_progress: "In progress", resolved: "Resolved",
  closed: "Closed", reopened: "Reopened",
};
export const STATUS_OPTIONS = Object.keys(STATUS_LABEL);

export function timeAgo(iso) {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  const units = [["year", 31536000], ["month", 2592000], ["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [name, secs] of units) {
    const n = Math.floor(s / secs);
    if (n >= 1) return `${n} ${name}${n > 1 ? "s" : ""} ago`;
  }
  return "just now";
}

// Server sends UTC; toLocaleString shows the viewer's own time zone.
export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString() : "");

export function errMsg(error) {
  if (error.response) {
    const { status, data } = error.response;
    const detail = typeof data?.detail === "string"
      ? data.detail
      : Array.isArray(data?.detail)
      ? data.detail.map((item) => item.msg).join(" ")
      : data?.detail
      ? JSON.stringify(data.detail)
      : typeof data === "string" && data
      ? data
      : error.response.statusText || "No error details returned by the server.";
    return `Request failed (HTTP ${status}): ${detail}`;
  }
  if (error.code === "ECONNABORTED" || error.code === "ETIMEDOUT") {
    return "The request timed out before the server responded. Check the backend and try again.";
  }
  if (error.code === "ERR_CANCELED") return "The request was canceled.";
  if (error.code === "ERR_NETWORK" || error.request) {
    return `No HTTP response was received from ${API_BASE_URL}. Check that FastAPI is running and reachable. If the browser Console reports CORS, allow the frontend origin in the backend CORS configuration.`;
  }
  return error.message || "The request could not be sent.";
}

export const fileUrl = (u) => (u?.startsWith("/uploads") ? API_BASE_URL + u : u);
