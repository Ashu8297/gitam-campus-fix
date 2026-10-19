# Campus Fix — Campus Facilities & Issue Reporting Portal

**Minor Project · Final Year B.Tech Computer Science · 7th Semester** · GITAM Bhubaneswar
Student-developed project. Not an official GITAM service.
Team: Ashutosh Pradhan, Nitan Moharana, Jayanta Kumar Pradhan, Krishna Chandra Rout.
Target submission: 4 November 2026.

## What is in this version
- Login for Student / Admin / Facilities Staff (Argon2, JWT, rate limit, roles enforced on the server)
- One-time admin setup, admin-managed student / administrator / facility staff accounts, temporary passwords with forced first-login change, invitation/reset links, CSV bulk import
- Issue reporting (camera or uploaded photos, required manual address, optional GPS, priority, category, building / floor / room details), community feed, one vote per student
- Admin approve / reject (with reason) / assign / reassign / priority change / close / reopen / hide, with bulk actions
- Staff workflow: accept, decline, start, progress updates, completion photos, resolve
- Shared timestamped timeline, database notifications (red dot), feedback ratings
- Admin and staff dashboards with date filters and charts built from real records
- Complaint retention & cleanup policy with admin-configurable deletion windows, dry-run previews, scheduled cleanup, and backup guidance
- Individual student, administrator, and facility-staff profiles with editable role-appropriate details, profile completion, and persisted profile photos
- About page (project, 7th-semester final-year minor project, team cards) editable by admins
- Light/dark mode, responsive layout, reduced-motion support

```
campus-fix/
  backend/   FastAPI app (app/), create_admin.py, tests/
  frontend/  React + Vite app (src/)
```

## 1. Create the MySQL database
Install MySQL, then (any terminal):
```
mysql -u root -p -e "CREATE DATABASE campus_fix CHARACTER SET utf8mb4;"
```

## 2. Backend  (run inside `campus-fix/backend`)
```
python -m venv .venv
.venv\Scripts\activate          # Windows   (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Mac/Linux: cp .env.example .env
```
Edit `.env`: set your MySQL password in `DATABASE_URL`, a long random `JWT_SECRET`,
and the three `INITIAL_ADMIN_*` values (your own email, name, strong password).

Create the first admin (one time only), then delete `INITIAL_ADMIN_PASSWORD` from `.env`:
```
python create_admin.py
```
Start the API:
```
uvicorn app.main:app --reload --port 8000
```
Check http://localhost:8000/api/health (should show `"database": "ok"`) and
http://localhost:8000/docs for the API docs.

Run tests (uses a temporary SQLite file, not your MySQL data):
```
pytest -q
```
> The test suite can be run locally with `pytest -q` from the backend directory.

## 3. Frontend  (run inside `campus-fix/frontend`, needs Node.js 18+)
```
npm install
copy .env.example .env          # Mac/Linux: cp .env.example .env
npm run dev
```
Open http://localhost:5173 and sign in as Admin with the account you created.

## How the demo flow works (use this for your presentation)
1. Sign in as Admin (account from `create_admin.py`). Open **Users** and create a Facility Staff account and a Student account. You can provide a temporary password or use the invitation link.
2. A user signing in with a temporary password must change it before using other Campus Fix features. If SMTP is not configured, use the displayed invitation link to choose a password.
3. Student: **Report issue**; the form requests GPS automatically, but a readable Location / Address is always required and GPS is optional. Capture or upload up to five photos, add building / floor / optional room details, and submit. Admin: **Issues** -> approve and assign to the staff member.
4. Staff: accept -> start work -> add a progress update -> resolve with a completion photo.
5. Admin: verify and close. Student: leave a rating. Open the issue to see the full timeline.
6. Admin **Dashboard** shows the charts; **About** shows the project page (editable by admin).

## Complaint retention policy and cleanup procedure

Campus Fix supports a configurable complaint retention window for permanent cleanup. The policy is calculated from each complaint's `created_at` timestamp, never from the last modification time.

- Default retention: 7 days
- Supported admin settings: 1 day, 7 days, 30 days
- Cleanup target: only complaints older than the configured retention threshold
- Automatic cleanup: runs in the backend as a protected background job after app startup and while the service stays running
- Manual cleanup: available in the admin **Retention & Cleanup** page, with explicit confirmation and a dry-run preview

Before permanent deletion:
1. Back up the database and the local upload directory (`backend/uploads/`) before running a cleanup.
2. Use the admin **Dry run** action to preview the complaints and attachments that would be deleted.
3. Confirm the number of complaints and attachment files before choosing **Delete now**.
4. Review the cleanup log after the run and keep a backup of the database snapshot for audit purposes.

How an administrator changes the retention period:
- Sign in as an admin.
- Open **Retention & Cleanup** from the sidebar.
- Select the retention period in days: 24 hours, 7 days, or 30 days.
- Save the policy. The next scheduled cleanup run will use the new threshold.
- Use **Dry run** to test the impact without deleting records.

The cleanup process only deletes complaint-specific records and their uploaded files. It does not touch user accounts, staff/admin accounts, profile photos, authentication records, or other complaints still within the retention period.

## User profiles and profile photos

All signed-in roles can open **My Profile** from the sidebar or dashboard identity chip. Students can edit their display name, username, department, branch, year, semester, and contact number. Facility staff can edit display name, contact number, and work category; staff ID is read-only. Administrators can edit display name and contact number. Email, role, account status, permissions, student registration number, and staff ID are protected from self-service changes.

Profile photos accept JPG, PNG, or WEBP up to the configured `MAX_UPLOAD_MB` size (5 MB by default) and are stored in the same uploads directory as other images, but are associated only with the user's account. Replaced/deleted profile files are removed only when no database record references the file. Existing databases receive nullable user profile-photo and contact columns automatically during startup through the compatibility column upgrade in `app.main`; no manual data migration is required.

### Delete every complaint

Admins can also choose **Delete All Complaints** on the same page. This separate action is manual-only and is never run during startup or deployment. The page displays the current complaint and attachment counts; the API checks those counts again before deletion. The administrator must type `DELETE ALL COMPLAINTS` exactly.

Before removing database records, the backend creates and verifies a ZIP archive in `backend/backups/` (or the configured `BACKUP_DIR`). The archive contains complaint-specific database rows and copies of available local complaint attachments. Preserve it securely because it may contain sensitive complaint details. A separate database and uploads-directory backup is still recommended. Only after archive verification does one database transaction remove complaint rows and their complaint-only children. Uploaded files are removed after the transaction commits, and files still referenced by another database record are retained. A database deletion failure leaves original records and files in place; filesystem deletion failures are logged while the complaint database deletion remains committed.

## Manual test checklist
- [ ] `/api/health` shows database ok; `/docs` lists the endpoints
- [ ] Admin login works; wrong password, unknown email and wrong role show the same message
- [ ] Admin creates a student; invitation link works once, then is rejected
- [ ] Suspended user cannot sign in
- [ ] Student cannot open `/admin` (redirected) and the API returns 403 for admin endpoints
- [ ] Report an issue with 1-5 photos using the camera or file chooser; a PDF renamed to .png is refused
- [ ] With GPS allowed, create a report with a photo and readable Location / Address; verify coordinates, numeric accuracy in meters, capture timestamp and Google Maps link
- [ ] Deny GPS permission and create a report with a photo and readable Location / Address; verify it submits successfully and the issue has no GPS coordinates, accuracy or timestamp
- [ ] Test GPS on `localhost` or HTTPS; location permission and device location services must be enabled. If GPS is unavailable, manual location entry remains available
- [ ] Double-clicking Submit creates only one report
- [ ] A second student can support a report once; supporting again removes support
- [ ] Reject without a reason is refused
- [ ] Bulk approve with one already-rejected issue shows 1 success and 1 failure
- [ ] Another staff member cannot open a task assigned to someone else
- [ ] Resolve without photos is refused; staff cannot close an issue
- [ ] Notifications show a red dot and "Mark all as read" clears it
- [ ] Dashboard numbers change after you create issues; custom date range works
- [ ] CSV import shows row-by-row errors
- [ ] About page shows "Minor Project - Final Year - 7th Semester" and four team cards
- [ ] Dark mode persists after refresh; layout works at phone width

## Known limitations (be upfront about these in your viva)
- GPS capture has not been exercised with a physical device in this environment. Test manually in a browser on `localhost` or HTTPS: allow location access, create an issue, verify its coordinates and accuracy, retry from another location, and submit a second issue to confirm it has different saved coordinates. Browser GPS accuracy varies by device and surroundings.
- Images are stored in `backend/uploads/` on disk. Free hosts wipe disk on restart, so for deployment swap `save_image()` in `app/storage.py` for a cloud service such as Cloudinary.
- Tables are created automatically at startup (`create_all`); startup also adds compatible issue and notification columns to existing databases and migrates the legacy `submitted` issue status to `reported` without deleting rows. Alembic migrations are **not** set up yet.
- Without SMTP settings, invitation and reset links are shown to the admin / printed in the API console instead of emailed.
- Login rate limiter is in-memory (fine for a single server).
- Not built yet: messaging and groups, profile photo upload, comment reporting/moderation UI, monthly report CSV export, WebSockets, deployment configs, demo-user seeding (categories and About content are seeded automatically).
