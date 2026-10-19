import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Bell,
  BriefcaseBusiness,
  ChartColumnIncreasing,
  FileText,
  Home,
  LogOut,
  Menu,
  Settings,
  ShieldCheck,
  UserCircle2,
  Users,
  Wrench,
} from "lucide-react";
import Logo from "./Logo";
import ThemeToggle from "./ThemeToggle";
import { ProfileAvatar } from "./ProfileIdentity";
import { useAuth } from "../auth";
import { api } from "../api";

const NAV = {
  student: [
    ["/student", "Dashboard", Home],
    ["/student/my", "My Complaints", FileText],
    ["/student/new", "Raise Complaint", BriefcaseBusiness],
    ["/student/profile", "My Profile", UserCircle2],
  ],
  admin: [
    ["/admin", "Admin Dashboard", ChartColumnIncreasing],
    ["/admin/issues", "Complaint Management", FileText],
    ["/admin/users", "User Management", Users],
    ["/admin/settings", "Retention & Cleanup", Settings],
    ["/admin/profile", "My Profile", UserCircle2],
  ],
  staff: [["/staff", "My Tasks", Wrench], ["/staff/profile", "My Profile", UserCircle2]],
};

function roleLabel(role) {
  return role === "admin" ? "Administrator" : role === "staff" ? "Facilities Staff" : "Student";
}

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api.get("/api/notifications/unread-count").then((r) => alive && setUnread(r.data.unread)).catch(() => {});
    load();
    const t = setInterval(load, 30000);
    window.addEventListener("cf-notif-changed", load);
    return () => { alive = false; clearInterval(t); window.removeEventListener("cf-notif-changed", load); };
  }, []);

  if (!user) return null;

  return (
    <div className="app-shell">
      <aside className={open ? "sidebar open" : "sidebar"} aria-label="Sidebar navigation">
        <div className="sidebar-header">
          <div className="profile-mini">
            <ProfileAvatar profile={user} size="sidebar" />
            <div className="profile-copy">
              <div className={`role-badge role-${user.role}`}>{roleLabel(user.role)}</div>
              <strong>{user.full_name || "Campus Fix user"}</strong>
              <span>{user.email || "campusfix@college.edu"}</span>
              <span className="sidebar-completion">{user.completion ?? 0}% profile complete</span>
            </div>
          </div>
        </div>

        <nav className="sidebar-nav" onClick={() => setOpen(false)}>
          {NAV[user.role].map(([to, label, Icon]) => (
            <NavLink key={to} to={to} end className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
          <NavLink to="/about" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            <ShieldCheck size={18} />
            <span>About</span>
          </NavLink>
          <NavLink to="/notifications" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            <Bell size={18} />
            <span>Notifications</span>
            {unread > 0 && <span className="nav-pill">{unread > 9 ? "9+" : unread}</span>}
          </NavLink>
          <NavLink to={user.role === "admin" ? "/admin/settings" : "/change-password"} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            <Settings size={18} />
            <span>{user.role === "admin" ? "Retention & Cleanup" : "Settings"}</span>
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <button className="logout-btn" type="button" onClick={() => { logout(); navigate("/login"); }}>
            <LogOut size={16} />
            Sign out
          </button>
        </div>
      </aside>

      <div className="main-panel">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-btn menu-btn" aria-label="Toggle navigation" onClick={() => setOpen(!open)}>
              <Menu size={18} />
            </button>
            <Link to={`/${user.role}`} className="topbar-brand">
              <Logo size={32} animate={false} />
              <strong>Campus Fix</strong>
            </Link>
          </div>

          <div className="topbar-actions">
            <Link to="/notifications" className="icon-btn bell" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}>
              <Bell size={18} />
              {unread > 0 && <span className="red-dot">{unread > 9 ? "9+" : unread}</span>}
            </Link>
            <ThemeToggle />
          </div>
        </header>

        <main className="content page-enter">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
