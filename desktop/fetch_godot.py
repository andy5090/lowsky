"""Fetch checksum-pinned Godot 4.5 build tools; print the editor path for packaging."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '4.5-stable'
BASE_URL = f'https://github.com/godotengine/godot-builds/releases/download/{VERSION}/'
ASSETS = {
    'templates': ('Godot_v4.5-stable_export_templates.tpz', '375d83b661794f91746d2dec9b569a99d4d24f85a70c4ec0068aafb18b551d53'),
    'macos': ('Godot_v4.5-stable_macos.universal.zip', 'abb7cabe99fead0bd63ce03bd8c611734b2941f9b90051e8e3b5c6691527954d'),
    'windows': ('Godot_v4.5-stable_win64.exe.zip', '303206071cb8be502cfa5b1e2b37b848c280347c03f78dcc2eb8a630857f7d10'),
}
TEMPLATES = {'macos': ('macos.zip',),
             'windows': ('windows_debug_x86_64.exe', 'windows_release_x86_64.exe')}


def checksum(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def fetch(kind, cache):
    name, expected = ASSETS[kind]
    target = cache / name
    cache.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if checksum(target) != expected:
            raise ValueError(f'Cached SHA-256 mismatch: {target}; remove it and retry')
        return target
    temporary = target.with_suffix(target.suffix + '.part')
    # An interrupted download is never installed or trusted as a completed artifact.
    print(f'Downloading {name}', file=sys.stderr, flush=True)
    request = urllib.request.Request(BASE_URL + name, headers={'User-Agent': 'LOW-SKY-desktop-build'})
    value = hashlib.sha256()
    last_report, size = time.monotonic(), 0
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as stream:
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)
            value.update(chunk)
            size += len(chunk)
            if time.monotonic() - last_report >= 10:
                print(f'{name}: {size // (1024 * 1024)} MiB received', file=sys.stderr, flush=True)
                last_report = time.monotonic()
    if value.hexdigest() != expected:
        temporary.unlink(missing_ok=True)
        raise ValueError(f'Download SHA-256 mismatch: {name}')
    temporary.replace(target)
    return target


def template_directory():
    if sys.platform == 'darwin':
        root = Path.home() / 'Library/Application Support/Godot'
    elif sys.platform == 'win32':
        root = Path(os.environ['APPDATA']) / 'Godot'
    else:
        root = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'godot'
    return root / 'export_templates' / '4.5.stable'


def install_templates(archive, platform):
    directory = template_directory()
    directory.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for name in TEMPLATES[platform]:
            member = f'templates/{name}'
            temporary = directory / (name + '.part')
            with package.open(member) as source, temporary.open('wb') as target:
                shutil.copyfileobj(source, target)
            temporary.replace(directory / name)
    print(f'Installed {platform} templates in {directory}', file=sys.stderr)


def validate_editor(path):
    try:
        result = subprocess.run([str(path), '--version'], capture_output=True, text=True, check=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.stdout.strip().startswith('4.5.stable.')


def find_editor(platform, cache, override=None):
    if override is not None:
        path = Path(override).expanduser().resolve()
        if not validate_editor(path):
            raise ValueError(f'Expected a runnable Godot 4.5 stable editor: {path}')
        return path
    candidates = []
    if platform == 'macos' and sys.platform == 'darwin':
        candidates.append(Path('/Applications/Godot.app/Contents/MacOS/Godot'))
    discovered = shutil.which('godot') or shutil.which('godot4')
    if discovered:
        candidates.append(Path(discovered))
    for candidate in candidates:
        if validate_editor(candidate):
            return candidate.resolve()
    archive = fetch(platform, cache)
    destination = cache / f'editor-{platform}-4.5'
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for info in package.infolist():
            target = (destination / info.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError('Unsafe archive entry')
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(info) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
            mode = info.external_attr >> 16
            if mode:
                target.chmod(mode & 0o777)
    if platform == 'macos':
        editor = destination / 'Godot.app/Contents/MacOS/Godot'
        editor.chmod(editor.stat().st_mode | 0o755)
    else:
        editor = destination / 'Godot_v4.5-stable_win64_console.exe'
        if not editor.exists():
            editor = destination / 'Godot_v4.5-stable_win64.exe'
    if not validate_editor(editor):
        raise ValueError(f'Downloaded editor is not runnable Godot 4.5 stable: {editor}')
    return editor.resolve()


def main():
    default_platform = 'macos' if sys.platform == 'darwin' else 'windows' if sys.platform == 'win32' else None
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=('macos', 'windows'), default=default_platform)
    parser.add_argument('--editor', help='Existing Godot 4.5 editor executable')
    parser.add_argument('--cache', type=Path, default=ROOT / '.local/desktop-downloads')
    args = parser.parse_args()
    if args.platform is None:
        parser.error('Select --platform and --editor for cross-platform exports')
    try:
        editor = find_editor(args.platform, args.cache, args.editor)
        install_templates(fetch('templates', args.cache), args.platform)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f'Godot build setup failed: {error}\n')
    print(editor)


if __name__ == '__main__':
    main()
