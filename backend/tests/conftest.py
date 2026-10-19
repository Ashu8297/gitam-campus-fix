import os
import tempfile
from pathlib import Path

# Must be set before the app is imported: tests use isolated SQLite and upload paths.
test_dir = Path(tempfile.mkdtemp(prefix="campus-fix-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(test_dir / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(test_dir / "uploads")
os.environ["SMTP_HOST"] = ""
