# -*- coding: utf-8 -*-
"""Areej V18.15 permanent hot-update migration.

This is a one-time migration. It restores the current full runtime, replaces
only the updater method, persists the repaired runtime, then runs it.

After this migration:
- web/* updates are installed without restarting the desktop process.
- runtime/Python updates still restart when genuinely required.
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
        and "def _read_remote_manifest(" in text
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

# One-dir/one-file launcher fallback.
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
    raise RuntimeError("Areej V18.15 could not recover the working runtime.")

_new_method = r'''    def apply_program_update(self):
        global APP_VERSION
        try:
            self._require_auth()
            manifest = self._read_remote_manifest()
            remote = str(manifest.get('version') or '')
            if _version_tuple(remote) <= _version_tuple(APP_VERSION):
                return self._ok(
                    updated=False,
                    version=APP_VERSION,
                    message='البرنامج على آخر إصدار.'
                )

            runtime = Path(
                os.environ.get('AREEJ_RUNTIME_DIR')
                or Path(__file__).resolve().parent
            ).resolve()
            app_home = Path(
                os.environ.get('AREEJ_APP_HOME')
                or runtime.parent
            )
            stage = app_home / 'update_staging' / core.sanitize_component(remote)
            backup = app_home / 'update_backups' / (
                f"{core.sanitize_component(APP_VERSION)}_{int(time.time())}"
            )

            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
            stage.mkdir(parents=True, exist_ok=True)
            backup.mkdir(parents=True, exist_ok=True)

            prepared = []
            for item in manifest.get('files') or []:
                if not isinstance(item, dict):
                    continue

                rel, target = self._safe_runtime_target(item.get('path'))
                rel_norm = rel.replace('\\', '/')
                source = self._resolve_update_file_source(manifest, item)
                blob = self._read_update_bytes(source, timeout=30)

                expected = str(item.get('sha256') or '').strip().lower()
                actual = hashlib.sha256(blob).hexdigest().lower()
                if expected and actual != expected:
                    raise ValueError(f'فشل التحقق من ملف التحديث: {rel}')

                staged = stage / Path(rel)
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(blob)

                if rel_norm.lower().endswith('.py'):
                    try:
                        compile(blob.decode('utf-8-sig'), rel, 'exec')
                    except Exception as syntax_exc:
                        raise ValueError(
                            f'ملف تحديث Python غير صالح: {rel} | {syntax_exc}'
                        )

                prepared.append((rel, rel_norm, target, staged))

            if not prepared:
                raise ValueError('لم يتم تجهيز أي ملفات للتحديث.')

            # ONLY runtime files require a process restart.
            # HTML/CSS/JS/assets under web/ are safe to swap live.
            requires_restart = any(
                not rel_norm.lower().startswith('web/')
                for _, rel_norm, _, _ in prepared
            )

            changed_files = []
            for rel, rel_norm, target, staged in prepared:
                if target.exists():
                    b = backup / Path(rel)
                    b.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, b)

                target.parent.mkdir(parents=True, exist_ok=True)
                temp_target = target.with_name(target.name + '.updating')
                shutil.copy2(staged, temp_target)
                os.replace(temp_target, target)
                changed_files.append(rel_norm)

            marker = runtime / 'runtime_manifest.json'
            marker.write_text(
                json.dumps({
                    'version': remote,
                    'channel': str(manifest.get('channel') or 'stable'),
                    'notes': str(manifest.get('notes') or ''),
                    'updated_at': core.now_text(),
                }, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )

            # Keep this running process aware of the new version.
            APP_VERSION = remote

            if not requires_restart:
                return self._ok(
                    updated=True,
                    version=remote,
                    restarting=False,
                    hot_reload=True,
                    changed_files=changed_files,
                )

            def restart_later():
                time.sleep(0.9)
                try:
                    command = json.loads(
                        os.environ.get('AREEJ_RESTART_COMMAND') or '[]'
                    )
                    if isinstance(command, list) and command:
                        cwd = Path(command[0]).resolve().parent
                        subprocess.Popen(command, cwd=str(cwd))
                finally:
                    os._exit(0)

            threading.Thread(
                target=restart_later,
                name='AreejUpdaterRestart',
                daemon=True
            ).start()

            return self._ok(
                updated=True,
                version=remote,
                restarting=True,
                hot_reload=False,
                changed_files=changed_files,
            )
        except Exception as exc:
            return self._err(exc)

'''

start = _source.find("    def apply_program_update(self):")
end = _source.find("    # ---------- main state ----------", start)
if start < 0 or end < 0:
    raise RuntimeError("Areej V18.15 updater method boundary not found.")

_source = _source[:start] + _new_method + _source[end:]

compile(_source, str(_here), "exec")
_tmp = _here.with_suffix(".py.v1815.tmp")
_tmp.write_text(_source, encoding="utf-8")
os.replace(str(_tmp), str(_here))

exec(compile(_source, str(_here), "exec"), globals(), globals())
