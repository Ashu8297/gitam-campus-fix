import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Restore the session by asking the server who we are.
  useEffect(() => {
    const token = sessionStorage.getItem("cf-token");
    if (!token) return setLoading(false);
    api
      .get("/api/auth/me")
      .then((r) => setUser(r.data))
      .catch(() => sessionStorage.removeItem("cf-token"))
      .finally(() => setLoading(false));
  }, []);

  async function login(role, identifier, password) {
    const r = await api.post("/api/auth/login", { role, identifier, password });
    sessionStorage.setItem("cf-token", r.data.access_token);
    setUser(r.data.user);
    return r.data.user;
  }

  function logout() {
    sessionStorage.removeItem("cf-token");
    setUser(null);
  }

  function updateUser(profile) {
    setUser((current) => current ? {
      ...current,
      full_name: profile.full_name ?? current.full_name,
      profile_photo_url: profile.profile_photo_url ?? null,
      completion: profile.completion ?? current.completion ?? 0,
    } : current);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}
