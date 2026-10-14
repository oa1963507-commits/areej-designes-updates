# -*- coding: utf-8 -*-
"""Areej V18.8 one-time runtime migration.

Restores instant design navigation while preserving external size-change
detection. V18.7 used content hashing during every design selection; that could
read large production files over the network and slow the UI. V18.8 switches
normal change detection to nanosecond mtime + ctime + byte-size metadata and
keeps the important dimension-cache invalidation added in V18.7.
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
        and "def _sync_file_states(" in text
        and "def _design_files_signature(" in text
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
    try:
        _bundle_root = Path(getattr(sys, "_MEIPASS", ""))
        _bundled = _bundle_root / "runtime" / "ProductionLibrary.py"
        _text = _bundled.read_text(encoding="utf-8")
        if _is_full_runtime(_text):
            _source = _text
    except Exception:
        pass

if not _source:
    raise RuntimeError("Areej V18.8 could not recover the working runtime.")

def _replace_method(source, method_header, next_header, replacement):
    start = source.find(method_header)
    if start < 0:
        raise RuntimeError("Missing runtime method: " + method_header.strip())
    end = source.find(next_header, start)
    if end < 0:
        raise RuntimeError("Missing runtime boundary: " + next_header.strip())
    return source[:start] + replacement.rstrip() + "\n" + source[end:]

_fast_signature = r'''    def _file_signature(self, path: Path):
        """Fast network-friendly signature for external production-file edits.

        Uses high-resolution filesystem metadata only, so switching designs
        never reads TIFF/PDF contents across the network. Size edits saved by
        Photoshop/Illustrator/Acrobat update Windows write/change metadata and
        are therefore detected without the V18.7 navigation penalty.
        """
        try:
            st = path.stat()
            mtime_ns = int(getattr(st, 'st_mtime_ns', int(st.st_mtime * 1_000_000_000)))
            ctime_ns = int(getattr(st, 'st_ctime_ns', int(st.st_ctime * 1_000_000_000)))
            size = int(st.st_size)
            return f'{mtime_ns}:{ctime_ns}:{size}'
        except Exception:
            return '0:0:-1'
'''

try:
    _source = _replace_method(
        _source,
        "    def _file_signature(self, path: Path):",
        "\n    def _versions_root",
        _fast_signature,
    )

    # Preserve the V18.7 fix that invalidates cached dimensions whenever the
    # physical file signature changes. Add it for older recovered runtimes too.
    _needle = """            sig = self._file_signature(path)
            old_sig = str(state.get('last_signature') or '')
            if sig == old_sig:
                continue
            try:
                detail = self._file_detail(path)
"""
    _replacement = """            sig = self._file_signature(path)
            old_sig = str(state.get('last_signature') or '')
            if sig == old_sig:
                continue
            self.calc._production_dimension_cache = {}
            try:
                detail = self._file_detail(path)
"""
    if _needle in _source:
        _source = _source.replace(_needle, _replacement, 1)

    compile(_source, str(_here), "exec")
    _tmp = _here.with_suffix(".py.v188.tmp")
    _tmp.write_text(_source, encoding="utf-8")
    os.replace(str(_tmp), str(_here))
except Exception:
    raise

exec(compile(_source, str(_here), "exec"), globals(), globals())
