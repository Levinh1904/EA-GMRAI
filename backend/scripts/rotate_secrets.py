"""Rotate GMRAI secrets: JWT signing key, ingest API key, admin password.

Writes the new values to `backend/.env` (never printed to the console) and
applies them to the live database so existing installs pick them up without a
manual reseed:

  * admin user password hash
  * `env-bootstrap` API key hash
  * `collector/.env` GMRAI_API_KEY if that file exists

Usage (from repo root or backend/):
    python -m scripts.rotate_secrets            # apply
    python -m scripts.rotate_secrets --dry-run  # show what would change

MT5 broker credentials are NOT rotatable from here: change the FTMO password in
the broker portal, then re-enter it in collector/.env on the Windows host.
"""
from __future__ import annotations

import argparse
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db import get_engine, session  # noqa: E402
from app.models import ApiKey, User  # noqa: E402
from app.security.auth import hash_api_key, hash_password  # noqa: E402

ENV_PATH = BACKEND_DIR / ".env"
COLLECTOR_ENV_PATH = REPO_ROOT / "collector" / ".env"


def _new_secret_key() -> str:
    return secrets.token_hex(32)


def _new_api_key() -> str:
    return "gmrai_" + secrets.token_urlsafe(32)


def _new_admin_password() -> str:
    return secrets.token_urlsafe(18)


def _upsert_env(path: Path, values: dict[str, str]) -> None:
    """Rewrite KEY=VALUE lines in place, appending any keys that are missing."""
    lines = path.read_text().splitlines() if path.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if m and m.group(1) in values:
            key = m.group(1)
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    missing = [k for k in values if k not in seen]
    if missing:
        if out and out[-1].strip():
            out.append("")
        out.extend(f"{k}={values[k]}" for k in missing)
    path.write_text("\n".join(out) + "\n")


def rotate(dry_run: bool = False) -> dict:
    secret_key = _new_secret_key()
    api_key = _new_api_key()
    admin_password = _new_admin_password()

    db = session()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        bootstrap = db.query(ApiKey).filter(ApiKey.name == "env-bootstrap").first()
        admin_found, key_found = admin is not None, bootstrap is not None
        if not dry_run:
            if admin is not None:
                admin.hashed_password = hash_password(admin_password)
            if bootstrap is not None:
                bootstrap.key_hash = hash_api_key(api_key)
            db.commit()
    finally:
        db.close()

    if not dry_run:
        _upsert_env(
            ENV_PATH,
            {
                "GMRAI_SECRET_KEY": secret_key,
                "GMRAI_API_KEY": api_key,
                "GMRAI_ADMIN_PASSWORD": admin_password,
            },
        )
        if COLLECTOR_ENV_PATH.exists():
            _upsert_env(COLLECTOR_ENV_PATH, {"GMRAI_API_KEY": api_key})

    return {
        "dry_run": dry_run,
        "rotated_at": datetime.now(timezone.utc).isoformat(),
        "admin_user_found": admin_found,
        "bootstrap_key_found": key_found,
        "env_path": str(ENV_PATH),
        "collector_env_updated": COLLECTOR_ENV_PATH.exists() and not dry_run,
        "admin_password": None if dry_run else admin_password,
        "api_key": None if dry_run else api_key,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    result = rotate(dry_run=args.dry_run)
    print(f"secret rotation {'(dry-run) ' if args.dry_run else ''}complete")
    print(f"  backend env : {result['env_path']}")
    print(f"  admin user  : {'updated' if result['admin_user_found'] else 'not found'}")
    print(f"  api key row : {'updated' if result['bootstrap_key_found'] else 'not found'}")
    print(f"  collector   : {'api key rewritten' if result['collector_env_updated'] else 'skipped'}")
    if not args.dry_run:
        print("\nNew admin password (store it now, it is not shown again):")
        print(f"  {result['admin_password']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
