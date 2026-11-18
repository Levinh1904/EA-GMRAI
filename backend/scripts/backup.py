"""Backup the GMRAI database and model artifacts.

There was no backup path at all. This script does a consistent copy without
stopping the API:

  * SQLite  -> `VACUUM INTO` (safe while the server is running, unlike `cp`)
  * Postgres -> `pg_dump` (custom format, restorable with `pg_restore`)
  * artifacts/ -> tar.gz next to the database dump

Usage:
    cd backend
    ./venv/bin/python -m scripts.backup                     # ./backups/<timestamp>/
    ./venv/bin/python -m scripts.backup --out /tmp/gmrai-bk
    ./venv/bin/python -m scripts.backup --db-only
    ./venv/bin/python -m scripts.backup --keep 7           # delete backups older than N

Restore (SQLite):
    sqlite3 gmrai.db ".restore '<dump>'"
Restore (Postgres):
    pg_restore -d "$GMRAI_DATABASE_URL" --clean --if-exists <dump>
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402


def _sqlite_path(url: str) -> Path | None:
    if not url.startswith("sqlite"):
        return None
    # sqlite:///./gmrai.db  ->  backend/gmrai.db
    raw = url.split(":///", 1)[-1]
    if raw in ("", ":memory:"):
        return None
    p = Path(raw)
    return p if p.is_absolute() else (BACKEND_DIR / p).resolve()


def _backup_sqlite(db_path: Path, target: Path) -> str:
    if not db_path.exists():
        raise SystemExit(f"Không tìm thấy database: {db_path}")
    # VACUUM INTO produces a consistent snapshot while the app keeps writing.
    import sqlite3

    con = sqlite3.connect(str(db_path))
    try:
        con.execute("VACUUM INTO ?", (str(target),))
    finally:
        con.close()
    return f"sqlite VACUUM INTO ({target.stat().st_size / 1e6:.1f} MB)"


def _backup_postgres(url: str, target: Path) -> str:
    if shutil.which("pg_dump") is None:
        raise SystemExit("Không có pg_dump trong PATH — cài postgresql-client.")
    cmd = ["pg_dump", "--format=custom", "--no-owner", f"--file={target}", url]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(f"pg_dump thất bại: {res.stderr[:400]}")
    return f"pg_dump custom ({target.stat().st_size / 1e6:.1f} MB)"


def _backup_artifacts(artifacts_dir: Path, target: Path) -> str:
    if not artifacts_dir.exists():
        return "không có artifacts/ — bỏ qua"
    with tarfile.open(target, "w:gz") as tar:
        tar.add(artifacts_dir, arcname="artifacts")
    return f"tar.gz ({target.stat().st_size / 1e6:.1f} MB)"


def _prune_old(out_dir: Path, keep: int) -> list[str]:
    if keep <= 0:
        return []
    dirs = sorted([d for d in out_dir.iterdir() if d.is_dir()], reverse=True)
    removed = []
    for d in dirs[keep:]:
        shutil.rmtree(d, ignore_errors=True)
        removed.append(d.name)
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO_ROOT / "backups"))
    ap.add_argument("--db-only", action="store_true")
    ap.add_argument("--keep", type=int, default=0, help="chỉ giữ N bản mới nhất (0 = không xoá)")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    url = settings.database_url
    db_path = _sqlite_path(url)
    print(f"GMRAI backup → {out_dir}")
    print(f"  database : {url.split('://', 1)[0]}")

    if db_path is not None:
        target = out_dir / "gmrai.db"
        print("  db        :", _backup_sqlite(db_path, target))
    else:
        target = out_dir / "gmrai.dump"
        print("  db        :", _backup_postgres(url, target))

    if not args.db_only:
        print("  artifacts :", _backup_artifacts(Path(settings.artifact_dir), out_dir / "artifacts.tar.gz"))

    (out_dir / "README.txt").write_text(
        "GMRAI backup\n"
        f"created_at: {stamp}\n"
        f"database_url_scheme: {url.split('://', 1)[0]}\n"
        "restore sqlite: sqlite3 gmrai.db \".restore '<this dir>/gmrai.db'\"\n"
        "restore postgres: pg_restore -d \"$GMRAI_DATABASE_URL\" --clean --if-exists <this dir>/gmrai.dump\n",
        encoding="utf-8",
    )

    if args.keep:
        removed = _prune_old(Path(args.out), args.keep)
        if removed:
            print(f"  đã xoá {len(removed)} bản cũ: {', '.join(removed)}")

    print("Xong.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
