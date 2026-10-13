# -*- coding: utf-8 -*-
"""One-time Areej updater migration.

The V18.2 launcher moved the runtime outside the EXE, while the runtime kept a
hard-coded APP_VERSION. During this update the original full module is already
backed up by Areej's updater. This migration restores that full source, replaces
the hard-coded version with the runtime manifest version, writes the repaired
module back in place, then executes it.
"""
from pathlib import Path
import os

_here = Path(__file__).resolve()
_app_home = Path(os.environ.get("AREEJ_APP_HOME") or _here.parent.parent)
_backup_root = _app_home / "update_backups"

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

_source = None
for _candidate in _candidates:
    try:
        _text = _candidate.read_text(encoding="utf-8")
        if len(_text) > 50000 and "class ProductionApi" in _text and 'APP_VERSION = "18.2"' in _text:
            _source = _text
            break
    except Exception:
        pass

if not _source:
    raise RuntimeError("Areej updater migration could not find the backed-up runtime.")

_dynamic_version = r'''def _current_runtime_version():
    try:
        _runtime_dir = Path(os.environ.get("AREEJ_RUNTIME_DIR") or Path(__file__).resolve().parent)
        _marker_path = _runtime_dir / "runtime_manifest.json"
        _marker = json.loads(_marker_path.read_text(encoding="utf-8"))
        return str(_marker.get("version") or "18.2")
    except Exception:
        return "18.2"

APP_VERSION = _current_runtime_version()'''

_source = _source.replace('APP_VERSION = "18.2"', _dynamic_version, 1)

_tmp = _here.with_name(_here.name + ".migrating")
_tmp.write_text(_source, encoding="utf-8")
os.replace(_tmp, _here)

exec(compile(_source, str(_here), "exec"), globals(), globals())
