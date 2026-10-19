import { Link } from "react-router-dom";
import { UserCircle2 } from "lucide-react";
import { useAuth } from "../auth";
import { fileUrl } from "../utils";

const ROLE_LABEL = { student: "Student", admin: "Administrator", staff: "Facilities Staff" };

export function ProfileAvatar({ profile, size = "normal" }) {
  return (
    <span className={`profile-avatar ${size}`} aria-label={`${profile?.full_name || "User"} profile photo`}>
      {profile?.profile_photo_url ? (
        <img src={fileUrl(profile.profile_photo_url)} alt="" />
      ) : (
        <UserCircle2 aria-hidden="true" />
      )}
    </span>
  );
}

export function DashboardIdentity() {
  const { user } = useAuth();
  if (!user) return null;
  const profilePath = user.role === "student" ? "/student/profile" : user.role === "admin" ? "/admin/profile" : "/staff/profile";
  return (
    <Link to={profilePath} className="dashboard-identity" aria-label="Open My Profile">
      <ProfileAvatar profile={user} size="small" />
      <span><strong>{user.full_name}</strong><small>{ROLE_LABEL[user.role]} · {user.completion ?? 0}% complete</small></span>
    </Link>
  );
}
