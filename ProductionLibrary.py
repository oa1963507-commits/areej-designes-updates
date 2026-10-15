# -*- coding: utf-8 -*-
"""Areej V18.24 database self-healing migration.

FastNetworkLibraryDB intentionally skips LibraryDB._create() for speed, which
meant older libraries could miss newer tables such as activity_log. This patch
adds a tiny startup schema check that creates the activity table and indexes
only when needed, without touching design/file data.
"""
from pathlib import Path
import os
import sys

_here = Path(__file__).resolve()
_app_home = Path(os.environ.get("AREEJ_APP_HOME") or _here.parent.parent)
_backup_root = _app_home / "update_backups"

def _is_full_runtime(text):
    return (
        len(text) > 100000
        and "class WebApi:" in text
        and "class FastNetworkLibraryDB:" in text
        and "def _set_root(" in text
    )

_source = None
_candidates = []
if _backup_root.exists():
    try:
        _candidates = sorted(
            _backup_root.glob("*/ProductionLibrary.py"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        _candidates = []

for _candidate in _candidates:
    try:
        _text = _candidate.read_text(encoding="utf-8")
        if _is_full_runtime(_text):
            _source = _text
            break
    except Exception:
        pass

if not _source:
    for _root in [
        Path(getattr(sys, "_MEIPASS", "")),
        Path(sys.executable).resolve().parent,
        Path(sys.executable).resolve().parent / "_internal",
    ]:
        try:
            _bundled = _root / "runtime" / "ProductionLibrary.py"
            _text = _bundled.read_text(encoding="utf-8")
            if _is_full_runtime(_text):
                _source = _text
                break
        except Exception:
            pass

if not _source:
    raise RuntimeError("Areej V18.24 could not recover the working runtime.")

_marker = "    @staticmethod\n    def _plain(value):"
if _marker not in _source:
    raise RuntimeError("Areej V18.24 database patch point not found.")

_patch = r'''    def _ensure_activity_schema(self):
        """Create the shared activity table for older libraries if missing."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0
        )
        try:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL DEFAULT 'info',
                    event_type TEXT NOT NULL DEFAULT 'event',
                    user_name TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL DEFAULT '',
                    entity_type TEXT NOT NULL DEFAULT '',
                    entity_id TEXT NOT NULL DEFAULT '',
                    serial TEXT NOT NULL DEFAULT '',
                    details TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_activity_created "
                "ON activity_log(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_activity_user "
                "ON activity_log(user_name)"
            )
            conn.commit()
        finally:
            conn.close()

'''

if "def _ensure_activity_schema(self):" not in _source:
    _source = _source.replace(_marker, _patch + _marker, 1)

_init_tail = '''        finally:
            conn.close()

    @staticmethod
    def _plain(value):'''

_init_new = '''        finally:
            conn.close()

        # Self-heal libraries created before activity_log existed.
        self._ensure_activity_schema()

    @staticmethod
    def _plain(value):'''

if "_ensure_activity_schema()" not in _source:
    if _init_tail not in _source:
        raise RuntimeError("Areej V18.24 constructor patch point not found.")
    _source = _source.replace(_init_tail, _init_new, 1)

compile(_source, str(_here), "exec")
_tmp = _here.with_suffix(".py.v1824.tmp")
_tmp.write_text(_source, encoding="utf-8")
os.replace(str(_tmp), str(_here))

exec(compile(_source, str(_here), "exec"), globals(), globals())
