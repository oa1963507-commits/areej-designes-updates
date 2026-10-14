# -*- coding: utf-8 -*-
"""Areej V18.7 one-time runtime migration.

Makes external TIFF/PDF size edits detectable even when a network share or
editor preserves byte size / timestamps. The updater backs up the currently
working full runtime before installing this file. We patch that full source,
write it back in place, then execute it.
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
    raise RuntimeError("Areej V18.7 could not recover the working runtime.")

def _replace_method(source, method_header, next_header, replacement):
    start = source.find(method_header)
    if start < 0:
        raise RuntimeError("Missing runtime method: " + method_header.strip())
    end = source.find(next_header, start)
    if end < 0:
        raise RuntimeError("Missing runtime boundary: " + next_header.strip())
    return source[:start] + replacement.rstrip() + "\n" + source[end:]

_file_signature = r'''    def _file_signature(self, path: Path):
        """Robust on-disk fingerprint for external production-file edits.

        Network shares and some editors can preserve file byte size and can
        briefly expose the same timestamp while changing TIFF/PDF dimensions.
        Include ctime plus a small content fingerprint from the beginning/end
        of the file so real size edits are noticed reliably.
        """
        try:
            st = path.stat()
            mtime_ns = int(getattr(st, 'st_mtime_ns', int(st.st_mtime * 1_000_000_000)))
            ctime_ns = int(getattr(st, 'st_ctime_ns', int(st.st_ctime * 1_000_000_000)))
            size = int(st.st_size)
            digest = ''
            try:
                hashlib = __import__('hashlib')
                h = hashlib.blake2s(digest_size=8)
                with path.open('rb') as fh:
                    h.update(fh.read(131072))
                    if size > 131072:
                        fh.seek(max(0, size - 131072))
                        h.update(fh.read(131072))
                digest = h.hexdigest()
            except Exception:
                digest = ''
            return f'{mtime_ns}:{ctime_ns}:{size}:{digest}'
        except Exception:
            return '0:0:-1:'
'''

_design_signature = r'''    def _design_files_signature(self, design_id):
        """Return a robust signature for the selected production files.

        This follows physical file content as well as filesystem metadata, so
        external Photoshop/Illustrator/Acrobat saves are detected on network
        shares even when the byte count stays unchanged.
        """
        if not design_id or not self.db:
            return ''
        parts = []
        try:
            rows = self.db.files_for(int(design_id))
        except Exception:
            return ''
        for row in rows:
            path = self._abs(row['rel_path'])
            parts.append('|'.join([
                str(row.get('id', '')),
                str(row.get('material', '')),
                str(row.get('rel_path', '')),
                self._file_signature(path),
            ]))
        return '||'.join(parts)
'''

try:
    _source = _replace_method(
        _source,
        "    def _file_signature(self, path: Path):",
        "\n    def _versions_root",
        _file_signature,
    )
    _source = _replace_method(
        _source,
        "    def _design_files_signature(self, design_id):",
        "\n    def refresh_library_state",
        _design_signature,
    )

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
            # A content fingerprint can change even when mtime/size did not.
            # Never reuse cached dimensions after a detected physical edit.
            self.calc._production_dimension_cache = {}
            try:
                detail = self._file_detail(path)
"""
    if _needle in _source:
        _source = _source.replace(_needle, _replacement, 1)
    elif "Never reuse cached dimensions after a detected physical edit." not in _source:
        raise RuntimeError("Areej V18.7 could not patch file-size synchronization.")

    compile(_source, str(_here), "exec")
    _tmp = _here.with_suffix(".py.v187.tmp")
    _tmp.write_text(_source, encoding="utf-8")
    os.replace(str(_tmp), str(_here))
except Exception:
    raise

exec(compile(_source, str(_here), "exec"), globals(), globals())
