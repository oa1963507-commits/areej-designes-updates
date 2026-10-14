# -*- coding: utf-8 -*-
"""Areej V18.18 updater cache-busting migration.

Fixes stale GitHub Raw/CDN responses by adding a unique query token to every
HTTP update request. The working full runtime is restored from the updater
backup, patched in-place, persisted, then executed.
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
        and "def _read_update_bytes(" in text
        and "def _read_remote_manifest(" in text
        and "def apply_program_update(" in text
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
    raise RuntimeError("Areej V18.18 could not recover the working runtime.")

_new_method = r'''    def _read_update_bytes(self, source, timeout=12):
        value = str(source or '').strip()
        if value.lower().startswith(('http://','https://')):
            # Always bypass intermediary/browser/CDN caches so a newly
            # published manifest or web asset is visible immediately.
            sep = '&' if '?' in value else '?'
            fresh_url = value + sep + '_areej=' + str(time.time_ns())
            req = Request(
                fresh_url,
                headers={
                    'User-Agent': f'AreejDesignes/{APP_VERSION}',
                    'Cache-Control': 'no-cache, no-store, max-age=0',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                },
            )
            with urlopen(req, timeout=timeout) as response:
                return response.read()
        path = Path(value)
        if path.is_dir():
            path = path / UPDATE_MANIFEST_NAME
        return path.read_bytes()

'''

start = _source.find("    def _read_update_bytes(self, source, timeout=12):")
end = _source.find("    def _read_remote_manifest(self):", start)
if start < 0 or end < 0:
    raise RuntimeError("Areej V18.18 updater read method boundary not found.")

_source = _source[:start] + _new_method + _source[end:]

compile(_source, str(_here), "exec")
_tmp = _here.with_suffix(".py.v1818.tmp")
_tmp.write_text(_source, encoding="utf-8")
os.replace(str(_tmp), str(_here))

exec(compile(_source, str(_here), "exec"), globals(), globals())
