"""Build a native LOW SKY installer using an isolated build interpreter.

Run with a venv containing requirements-agent.txt and requirements-desktop.txt.
Only public runtime assets are copied; project .env and .local never enter payload.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / 'desktop'
PAYLOAD = DESKTOP / 'src-tauri' / 'payload'
BUILD = DESKTOP / 'build'
# Optional copy target for finished installers (e.g. a synced Google Drive folder). The path stays out of Git:
# pass --publish-dir, set LOWSKY_INSTALLER_DIR, or write the path into this ignored file.
PUBLISH_DIR_FILE = ROOT / '.local' / 'installer-publish-dir.txt'


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def assert_public_payload(root):
    forbidden = []
    for path in root.rglob('*'):
        if (path.name.startswith('.env') or path.suffix.lower() in ('.docx', '.jsonl')
                               or '.local' in path.relative_to(root).parts):
            forbidden.append(str(path.relative_to(root)))
    if forbidden:
        raise RuntimeError('Private files in payload: ' + ', '.join(forbidden))


def publish_dir(argument):
    if argument:
        return Path(argument).expanduser()
    if os.environ.get('LOWSKY_INSTALLER_DIR'):
        return Path(os.environ['LOWSKY_INSTALLER_DIR']).expanduser()
    if PUBLISH_DIR_FILE.is_file() and PUBLISH_DIR_FILE.read_text(encoding='utf-8').strip():
        return Path(PUBLISH_DIR_FILE.read_text(encoding='utf-8').strip()).expanduser()
    return None


def sha256(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def publish(installer, folder):
    """Copy an installer into folder, replacing a previous copy with the same name only once it is complete."""
    if not folder.is_dir():
        raise RuntimeError(f'Installer publish folder not found: {folder}')
    target = folder / installer.name
    partial = folder / f'.{installer.name}.partial'
    shutil.copyfile(installer, partial)
    if sha256(partial) != sha256(installer):
        partial.unlink()
        raise RuntimeError(f'Copy to {folder} did not match the built installer')
    os.replace(partial, target)
    print(f'Published: {target}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', type=Path, help='Godot 4.5 editor executable; templates must be installed')
    parser.add_argument('--skip-backend', action='store_true', help='Reuse an already frozen local backend')
    parser.add_argument('--skip-godot', action='store_true', help='Reuse an already exported local Godot build')
    parser.add_argument('--prepare-only', action='store_true', help='Prepare runtime resources without Tauri bundling')
    parser.add_argument('--publish-dir', help='Also copy finished installers here (overrides LOWSKY_INSTALLER_DIR '
                                              'and .local/installer-publish-dir.txt)')
    args = parser.parse_args()
    if sys.platform not in ('darwin', 'win32'):
        parser.error('Run on macOS or Windows; build each installer on its target OS.')
    PAYLOAD.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    if not args.skip_backend:
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir',
                   '--name', 'lowsky-server', '--distpath', str(BUILD / 'frozen'),
                   '--workpath', str(BUILD / 'pyinstaller'), '--specpath', str(BUILD),
                   '--paths', str(ROOT), '--add-data', f'{ROOT / "data"}{os.pathsep}data',
                   '--add-data', f'{ROOT / "monitor"}{os.pathsep}monitor', '--recursive-copy-metadata', 'deepagents',
                   '--recursive-copy-metadata', 'langchain-openai', '--recursive-copy-metadata', 'langchain-anthropic']
        for package in ('langchain_openai', 'langchain_anthropic', 'tiktoken_ext.openai_public'):
            command += ['--hidden-import', package]
        command += [str(ROOT / 'tools' / 'desktop_runtime.py')]
        run(*command, cwd=ROOT)
        if (PAYLOAD / 'backend').exists():
            shutil.rmtree(PAYLOAD / 'backend')
        shutil.copytree(BUILD / 'frozen' / 'lowsky-server', PAYLOAD / 'backend')
    if not args.skip_godot:
        godot = args.godot
        if godot is None:
            result = subprocess.run([sys.executable, str(DESKTOP / 'fetch_godot.py')], check=True, capture_output=True, text=True)
            godot = Path(result.stdout.strip().splitlines()[-1])
        version = subprocess.check_output([str(godot), '--version'], text=True).strip()
        if not version.startswith('4.5.stable.'):
            raise RuntimeError('Godot 4.5 stable is required for reproducible exports')
        target = PAYLOAD / 'godot'
        if target.exists():
            shutil.rmtree(target)
        target.mkdir()
        preset = 'macOS' if sys.platform == 'darwin' else 'Windows Desktop'
        output = target / ('LOW SKY 3D.app' if sys.platform == 'darwin' else 'LOW SKY 3D.exe')
        run(godot, '--headless', '--path', ROOT / 'godot', '--editor', '--import', cwd=ROOT)
        run(godot, '--headless', '--path', ROOT / 'godot', '--export-release', preset, output, cwd=ROOT)
    if sys.platform == 'darwin':
        app_bundle = PAYLOAD / 'godot/LOW SKY 3D.app'
        executable_name = 'LOW SKY — 3D Simulation'
        if (app_bundle / 'Contents/Info.plist').is_file():
            with (app_bundle / 'Contents/Info.plist').open('rb') as handle:
                executable_name = plistlib.load(handle)['CFBundleExecutable']
        executable = app_bundle / 'Contents/MacOS' / executable_name
    else:
        executable = PAYLOAD / 'godot/LOW SKY 3D.exe'
    if not args.skip_godot or executable.is_file():
        (PAYLOAD / 'godot-executable.txt').write_text(executable.relative_to(PAYLOAD).as_posix(), encoding='utf-8')
    licenses = PAYLOAD / 'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'requirements-agent.txt', licenses / 'python-runtime-requirements.txt')
    for path in (ROOT / 'godot').rglob('*'):
        if path.is_file() and any(word in path.name.lower() for word in ('license', 'copyright', 'attribution')) and '.godot' not in path.parts:
            dest = licenses / 'godot-assets' / path.relative_to(ROOT / 'godot')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    assert_public_payload(PAYLOAD)
    (PAYLOAD / 'build-info.json').write_text(json.dumps({'version': json.loads((DESKTOP / 'src-tauri/tauri.conf.json').read_text(encoding='utf-8'))['version'], 'platform': sys.platform,
        'architecture': platform.machine(), 'godot': '4.5.stable', 'python': platform.python_version()}, indent=2))
    if not args.prepare_only:
        npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
        if not npm:
            raise RuntimeError('Node.js / npm is required to build Tauri')
        run(npm, 'ci', cwd=DESKTOP)
        bundles = 'app,dmg' if sys.platform == 'darwin' else 'nsis'
        # Keep packaging non-interactive, including DMG creation without Finder automation.
        run(npm, 'run', 'build', '--', '--bundles', bundles, cwd=DESKTOP, env={**os.environ, 'CI': 'true'})
        output = ROOT / 'dist'
        output.mkdir(exist_ok=True)
        suffix = '.dmg' if sys.platform == 'darwin' else '.exe'
        bundle = DESKTOP / 'src-tauri/target/release/bundle'
        for artifact in bundle.rglob('*' + suffix):
            if artifact.parent.name not in ('dmg', 'nsis'):
                continue
            target = output / artifact.name
            shutil.copy2(artifact, target)
            checksum = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
            target.with_suffix(target.suffix + '.sha256').write_text(f'{checksum}  {target.name}\n')
            print(f'Installer: {target}')
            folder = publish_dir(args.publish_dir)
            if folder:
                publish(target, folder)


if __name__ == '__main__':
    main()
