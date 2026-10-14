# -*- coding: utf-8 -*-
"""Areej V18.20 permanent updater reliability migration.

Fixes missed updates by:
- bypassing HTTP/CDN caches for every request,
- reading GitHub Raw manifests through GitHub's Contents API when possible,
- supporting a unique bootstrap manifest URL while automatically returning to
  the canonical manifest.json for all future checks,
- keeping web-only updates hot (no desktop restart).
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
    raise RuntimeError("Areej V18.20 could not recover the working runtime.")

def _replace_method(src, header, next_header, replacement):
    start = src.find(header)
    end = src.find(next_header, start)
    if start < 0 or end < 0:
        raise RuntimeError("Areej V18.20 method boundary not found: " + header.strip())
    return src[:start] + replacement.rstrip() + "\n\n" + src[end:]

_read_bytes = r'''    def _read_update_bytes(self, source, timeout=12):
        value = str(source or '').strip()
        if value.lower().startswith(('http://','https://')):
            # A unique token makes every update request a fresh HTTP request,
            # avoiding stale GitHub Raw / proxy / WebView caches.
            sep = '&' if '?' in value else '?'
            fresh_url = value + sep + '_areej=' + str(time.time_ns())
            req = Request(
                fresh_url,
                headers={
                    'User-Agent': f'AreejDesignes/{APP_VERSION}',
                    'Cache-Control': 'no-cache, no-store, max-age=0',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                    'Accept': 'application/octet-stream, application/json;q=0.9, */*;q=0.8',
                },
            )
            with urlopen(req, timeout=timeout) as response:
                return response.read()

        path = Path(value)
        if path.is_dir():
            path = path / UPDATE_MANIFEST_NAME
        return path.read_bytes()
'''

_read_manifest = r'''    def _read_remote_manifest(self):
        source = self._get_update_source()
        if not source:
            raise ValueError('مصدر تحديث البرنامج غير مُعد. حدده مرة واحدة من إعدادات الـOwner.')

        raw = None
        parsed = urlparse(str(source).strip())

        # GitHub Raw can occasionally be stale behind a CDN. For GitHub-hosted
        # channels, fetch manifest.json through the GitHub Contents API instead.
        # A bootstrap manifest filename is also accepted; after V18.20 we always
        # resolve the canonical manifest.json in the same repository.
        if parsed.scheme in ('http','https') and parsed.netloc.lower() == 'raw.githubusercontent.com':
            try:
                parts = [p for p in parsed.path.split('/') if p]
                if len(parts) >= 4:
                    owner, repo, branch = parts[0], parts[1], parts[2]
                    rel_parts = parts[3:]
                    if rel_parts and rel_parts[-1].lower().startswith('manifest'):
                        rel_parts[-1] = UPDATE_MANIFEST_NAME
                    rel = '/'.join(rel_parts)
                    api_url = (
                        f'https://api.github.com/repos/{owner}/{repo}/contents/{rel}'
                        f'?ref={branch}&_areej={time.time_ns()}'
                    )
                    req = Request(
                        api_url,
                        headers={
                            'User-Agent': f'AreejDesignes/{APP_VERSION}',
                            'Accept': 'application/vnd.github+json',
                            'Cache-Control': 'no-cache, no-store, max-age=0',
                            'Pragma': 'no-cache',
                        },
                    )
                    with urlopen(req, timeout=12) as response:
                        envelope = json.loads(response.read().decode('utf-8-sig'))
                    encoded = str(envelope.get('content') or '').replace('\n','')
                    if encoded:
                        raw = base64.b64decode(encoded)
            except Exception:
                raw = None

        if raw is None:
            raw = self._read_update_bytes(source)

        data = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError('ملف التحديث غير صالح.')

        remote_version = str(data.get('version') or '').strip()
        if not remote_version:
            raise ValueError('نسخة التحديث غير محددة داخل manifest.')

        files = data.get('files') or []
        if not isinstance(files, list) or not files:
            raise ValueError('قائمة ملفات التحديث فارغة.')

        data['_source'] = source
        return data
'''

_apply = r'''    def apply_program_update(self):
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

try:
    _source = _replace_method(
        _source,
        "    def _read_update_bytes(self, source, timeout=12):",
        "    def _read_remote_manifest(self):",
        _read_bytes,
    )
    _source = _replace_method(
        _source,
        "    def _read_remote_manifest(self):",
        "    def check_program_update(self):",
        _read_manifest,
    )
    _source = _replace_method(
        _source,
        "    def apply_program_update(self):",
        "    # ---------- main state ----------",
        _apply,
    )

    compile(_source, str(_here), "exec")
    _tmp = _here.with_suffix(".py.v1820.tmp")
    _tmp.write_text(_source, encoding="utf-8")
    os.replace(str(_tmp), str(_here))
except Exception:
    raise

exec(compile(_source, str(_here), "exec"), globals(), globals())
