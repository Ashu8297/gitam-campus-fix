import axios from "axios";

export const API_BASE_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

export const api = axios.create({
  baseURL: API_BASE_URL,
});

// Token is kept in sessionStorage (cleared when the tab closes).
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("cf-token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
