# -*- coding: utf-8 -*-
"""Areej V18.13 one-time updater migration.

Installs hot web updates: HTML/CSS/JS changes are applied in-place and the
WebView reloads itself without restarting the desktop process. Python/runtime
changes still restart because loaded Python code cannot be safely replaced in
the running process.
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
        and "def apply_program_update(self):" in text
        and "def _safe_runtime_target(" in text
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
    raise RuntimeError("Areej V18.13 could not recover the working runtime.")

_new_method = r'''    def apply_program_update(self):
        global APP_VERSION
        try:
            self._require_auth()
            manifest = self._read_remote_manifest()
            remote = str(manifest.get('version') or '')
            if _version_tuple(remote) <= _version_tuple(APP_VERSION):
                return self._ok(updated=False, version=APP_VERSION, message='البرنامج على آخر إصدار.')

            runtime = Path(os.environ.get('AREEJ_RUNTIME_DIR') or Path(__file__).resolve().parent).resolve()
            app_home = Path(os.environ.get('AREEJ_APP_HOME') or runtime.parent)
            stage = app_home / 'update_staging' / core.sanitize_component(remote)
            backup = app_home / 'update_backups' / f"{core.sanitize_component(APP_VERSION)}_{int(time.time())}"
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
            stage.mkdir(parents=True, exist_ok=True)
            backup.mkdir(parents=True, exist_ok=True)

            prepared = []
            for item in manifest.get('files') or []:
                if not isinstance(item, dict):
                    continue
                rel, target = self._safe_runtime_target(item.get('path'))
                source = self._resolve_update_file_source(manifest, item)
                blob = self._read_update_bytes(source, timeout=30)
                expected = str(item.get('sha256') or '').strip().lower()
                actual = hashlib.sha256(blob).hexdigest().lower()
                if expected and actual != expected:
                    raise ValueError(f'فشل التحقق من ملف التحديث: {rel}')
                staged = stage / Path(rel)
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(blob)
                if rel.lower().endswith('.py'):
                    try:
                        compile(blob.decode('utf-8-sig'), rel, 'exec')
                    except Exception as syntax_exc:
                        raise ValueError(f'ملف تحديث Python غير صالح: {rel} | {syntax_exc}')
                prepared.append((rel, target, staged))

            if not prepared:
                raise ValueError('لم يتم تجهيز أي ملفات للتحديث.')

            # Web-only updates can be swapped safely while the app is running.
            # Runtime/Python files still require a process restart.
            requires_restart = any(not rel.replace('\\','/').startswith('web/') for rel, _, _ in prepared)

            for rel, target, staged in prepared:
                if target.exists():
                    b = backup / Path(rel)
                    b.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, b)
                target.parent.mkdir(parents=True, exist_ok=True)
                temp_target = target.with_name(target.name + '.updating')
                shutil.copy2(staged, temp_target)
                os.replace(temp_target, target)

            marker = runtime / 'runtime_manifest.json'
            marker.write_text(json.dumps({
                'version': remote,
                'channel': str(manifest.get('channel') or 'stable'),
                'notes': str(manifest.get('notes') or ''),
                'updated_at': core.now_text(),
            }, ensure_ascii=False, indent=2), encoding='utf-8')

            # Keep version checks correct without forcing a process restart.
            APP_VERSION = remote

            if not requires_restart:
                return self._ok(
                    updated=True,
                    version=remote,
                    restarting=False,
                    hot_reload=True,
                    changed_files=[rel for rel, _, _ in prepared],
                )

            def restart_later():
                time.sleep(1.0)
                try:
                    command = json.loads(os.environ.get('AREEJ_RESTART_COMMAND') or '[]')
                    if isinstance(command, list) and command:
                        subprocess.Popen(command, cwd=str(Path(command[-1]).resolve().parent if len(command)>1 else Path(command[0]).resolve().parent))
                finally:
                    os._exit(0)

            threading.Thread(target=restart_later, name='AreejUpdaterRestart', daemon=True).start()
            return self._ok(
                updated=True,
                version=remote,
                restarting=True,
                hot_reload=False,
                changed_files=[rel for rel, _, _ in prepared],
            )
        except Exception as exc:
            return self._err(exc)

'''

start=_source.find("    def apply_program_update(self):")
end=_source.find("    # ---------- main state ----------", start)
if start<0 or end<0:
    raise RuntimeError("Areej V18.13 updater method boundary not found.")
_source=_source[:start]+_new_method+_source[end:]

try:
    compile(_source, str(_here), "exec")
    _tmp = _here.with_suffix(".py.v1813.tmp")
    _tmp.write_text(_source, encoding="utf-8")
    os.replace(str(_tmp), str(_here))
except Exception:
    raise

exec(compile(_source, str(_here), "exec"), globals(), globals())
