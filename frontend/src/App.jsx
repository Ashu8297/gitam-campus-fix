import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import { SetPassword, ForgotPassword, ChangePassword } from "./pages/SetPassword";
import { StudentHome, MyReports } from "./pages/StudentHome";
import NewIssue from "./pages/NewIssue";
import Profile from "./pages/Profile";
import IssueDetail from "./pages/IssueDetail";
import Notifications from "./pages/Notifications";
import AdminDashboard from "./pages/AdminDashboard";
import AdminIssues from "./pages/AdminIssues";
import AdminSettings from "./pages/AdminSettings";
import Users from "./pages/Users";
import StaffHome from "./pages/StaffHome";
import About from "./pages/About";

// Frontend guards are for convenience only; the API enforces roles for real.
function Protected({ roles, children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center-note">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to={`/${user.role}`} replace />;
  return children;
}
const P = (roles, el) => <Protected roles={roles}>{el}</Protected>;

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<Login />} />
      <Route path="/set-password" element={<SetPassword />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/change-password" element={<ChangePassword />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route path="/student" element={P(["student"], <StudentHome />)} />
        <Route path="/student/my" element={P(["student"], <MyReports />)} />
        <Route path="/student/new" element={P(["student"], <NewIssue />)} />
        <Route path="/student/profile" element={P(["student"], <Profile />)} />
        <Route path="/admin" element={P(["admin"], <AdminDashboard />)} />
        <Route path="/admin/issues" element={P(["admin"], <AdminIssues />)} />
        <Route path="/admin/users" element={P(["admin"], <Users />)} />
        <Route path="/admin/settings" element={P(["admin"], <AdminSettings />)} />
        <Route path="/admin/profile" element={P(["admin"], <Profile />)} />
        <Route path="/staff" element={P(["staff"], <StaffHome />)} />
        <Route path="/staff/profile" element={P(["staff"], <Profile />)} />
        <Route path="/issues/:id" element={<IssueDetail />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/about" element={<About />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
