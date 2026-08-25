"""
Safely diagnoses DATABASE_URL structure WITHOUT ever printing the value
itself, any substring of it, or anything derived from its characters.
Only reports boolean/structural facts (scheme ok? parses? suspicious
literal brackets present? count of '@'?) — see docs/PHASE_STATUS.md Phase 2
"known limitations" for why this exists (a prior parsing mistake leaked
credentials into a terminal transcript; this script is deliberately
paranoid about never repeating that).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ENV = REPO_ROOT / "backend" / ".env"


def main() -> None:
    load_dotenv(dotenv_path=BACKEND_ENV)
    dsn = os.environ.get("DATABASE_URL")

    if not dsn:
        print("DATABASE_URL is not set.")
        return

    print(f"length: {len(dsn)} characters")
    print(f"starts_with_postgres_scheme: {dsn.startswith(('postgres://', 'postgresql://'))}")
    print(f"at_symbol_count: {dsn.count('@')}  (expect exactly 1, outside the password)")
    print(f"contains_literal_square_bracket: {'[' in dsn or ']' in dsn}")
    print(
        "  -> if True: Supabase's dashboard shows a TEMPLATE like "
        "postgresql://postgres:[YOUR-PASSWORD]@... — the [ and ] must be "
        "deleted along with the placeholder text, not left in around your "
        "real password."
    )
    print(f"contains_whitespace: {any(c.isspace() for c in dsn)}")

    try:
        parts = urlsplit(dsn)
        print(f"urlsplit_scheme: {parts.scheme!r}")
        print(f"urlsplit_hostname_present: {parts.hostname is not None}")
        print(f"urlsplit_port_present: {parts.port is not None}")
        try:
            _ = parts.port  # accessing .port raises ValueError if non-numeric
            print("port_parses_as_int: True")
        except ValueError:
            print("port_parses_as_int: False  <-- likely cause: '@' inside the password is")
            print("  not percent-encoded, so urlsplit is misreading part of the password")
            print("  or host as the port.")
        print(f"urlsplit_path_present: {bool(parts.path and parts.path != '/')}")
        # Check the userinfo (user:pass) segment specifically for raw reserved
        # characters that MUST be percent-encoded in a URI, without ever
        # printing the segment itself.
        if parts.netloc and "@" in parts.netloc:
            userinfo = parts.netloc.rsplit("@", 1)[0]
            if ":" in userinfo:
                _user, password = userinfo.split(":", 1)
                unencoded_reserved = re.findall(r"[^A-Za-z0-9\-._~%]", password)
                print(f"password_segment_length: {len(password)}")
                print(
                    f"password_has_unencoded_reserved_chars: {bool(unencoded_reserved)} "
                    f"(count: {len(unencoded_reserved)})"
                )
                # Verify every '%' is followed by two hex digits (valid percent-encoding).
                bad_percent = re.findall(r"%(?![0-9A-Fa-f]{2})", password)
                print(f"password_has_malformed_percent_encoding: {bool(bad_percent)}")
    except Exception as exc:  # noqa: BLE001
        print(f"urlsplit_raised: {type(exc).__name__}")


if __name__ == "__main__":
    main()
