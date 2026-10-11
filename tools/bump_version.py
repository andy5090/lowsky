"""Set the LOW SKY version everywhere and release the Unreleased changelog section (stdlib only).

Usage: python tools/bump_version.py 0.3.0 [--date YYYY-MM-DD] [--check]

The version source of truth is desktop/src-tauri/tauri.conf.json; the build reads it from there. This script
rewrites every other version field to match and moves CHANGELOG.md's Unreleased entries under the new
version. --check only reports whether all fields already agree.
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / 'CHANGELOG.md'
REPOSITORY = 'https://github.com/andy5090/lowsky'
SEMVER = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')


def _sub(pattern, replacement, text, count):
    result, found = re.subn(pattern, replacement, text, count=count, flags=re.MULTILINE)
    if found != count:
        raise ValueError(f'Expected {count} match(es) for {pattern!r}, found {found}')
    return result


# (path, reader, writer). Readers return the version string(s) found in the file.
def _json_version(path):
    return [json.loads((ROOT / path).read_text(encoding='utf-8'))['version']]


FIELDS = {
    'desktop/src-tauri/tauri.conf.json': (
        _json_version,
        lambda text, v: _sub(r'^(  "version": )"[^"]+"', rf'\g<1>"{v}"', text, 1)),
    'desktop/package.json': (
        _json_version,
        lambda text, v: _sub(r'^(  "version": )"[^"]+"', rf'\g<1>"{v}"', text, 1)),
    'desktop/package-lock.json': (
        lambda path: [(data := json.loads((ROOT / path).read_text(encoding='utf-8')))['version'],
                      data['packages']['']['version']],
        lambda text, v: _sub(r'^(  "version": |      "version": )"[^"]+"(,\n(?:      "devDependencies"|  "lockfileVersion"))',
                             rf'\g<1>"{v}"\g<2>', text, 2)),
    'desktop/src-tauri/Cargo.toml': (
        lambda path: re.findall(r'^\[package\]\nname = "[^"]+"\nversion = "([^"]+)"',
                                (ROOT / path).read_text(encoding='utf-8'), re.MULTILINE),
        lambda text, v: _sub(r'^(\[package\]\nname = "[^"]+"\nversion = )"[^"]+"', rf'\g<1>"{v}"', text, 1)),
    'desktop/src-tauri/Cargo.lock': (
        lambda path: re.findall(r'^name = "lowsky-desktop"\nversion = "([^"]+)"',
                                (ROOT / path).read_text(encoding='utf-8'), re.MULTILINE),
        lambda text, v: _sub(r'^(name = "lowsky-desktop"\nversion = )"[^"]+"', rf'\g<1>"{v}"', text, 1)),
    'README.md': (
        lambda path: re.findall(r'^\[한국어\]\(README\.ko\.md\) · Version (\S+) ·', (ROOT / path).read_text(encoding='utf-8'), re.MULTILINE),
        lambda text, v: _sub(r'^(\[한국어\]\(README\.ko\.md\) · Version )\S+( ·)', rf'\g<1>{v}\g<2>', text, 1)),
    'README.ko.md': (
        lambda path: re.findall(r'^\[English\]\(README\.md\) · 버전 (\S+) ·', (ROOT / path).read_text(encoding='utf-8'), re.MULTILINE),
        lambda text, v: _sub(r'^(\[English\]\(README\.md\) · 버전 )\S+( ·)', rf'\g<1>{v}\g<2>', text, 1)),
    'tools/version.py': (
        lambda path: re.findall(r"^VERSION = '([^']+)'$", (ROOT / path).read_text(encoding='utf-8'), re.MULTILINE),
        lambda text, v: _sub(r"^VERSION = '[^']+'$", f"VERSION = '{v}'", text, 1)),
    'godot/export_presets.cfg': (
        lambda path: [m.removesuffix('.0') if m.count('.') == 3 else m for m in re.findall(
            r'^application/(?:short_version|version|file_version|product_version)="([^"]+)"',
            (ROOT / path).read_text(encoding='utf-8'), re.MULTILINE)],
        lambda text, v: _sub(r'^(application/(?:file_version|product_version)=)"[^"]+"', rf'\g<1>"{v}.0"',
                             _sub(r'^(application/(?:short_version|version)=)"[^"]+"', rf'\g<1>"{v}"', text, 2), 2)),
}


def current_versions():
    return {path: reader(path) for path, (reader, _) in FIELDS.items()}


def released_versions(text=None):
    text = CHANGELOG.read_text(encoding='utf-8') if text is None else text
    return re.findall(r'^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$', text, re.MULTILINE)


def release_changelog(text, version, date):
    if version in released_versions(text):
        raise ValueError(f'{version} is already in CHANGELOG.md')
    marker = '## [Unreleased]\n'
    if marker not in text:
        raise ValueError('CHANGELOG.md has no Unreleased section')
    start = text.index(marker) + len(marker)
    following = re.search(r'^## \[', text[start:], re.MULTILINE)
    body = text[start:start + following.start()] if following else text[start:]
    if not body.strip():
        raise ValueError('The Unreleased section is empty; record the changes before releasing')
    previous = released_versions(text)
    text = text[:start] + f'\n## [{version}] - {date}\n' + body.rstrip('\n') + '\n\n' + text[start + len(body):]
    links = f'[Unreleased]: {REPOSITORY}/compare/v{version}...HEAD\n'
    links += (f'[{version}]: {REPOSITORY}/compare/v{previous[0]}...v{version}\n' if previous
              else f'[{version}]: {REPOSITORY}/releases/tag/v{version}\n')
    return re.sub(r'^\[Unreleased\]: .*\n', links, text, count=1, flags=re.MULTILINE)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('version', nargs='?')
    parser.add_argument('--date', default=datetime.date.today().isoformat())
    parser.add_argument('--check', action='store_true', help='Only verify that every version field agrees')
    args = parser.parse_args()
    if args.check:
        found = current_versions()
        values = {value for versions in found.values() for value in versions}
        latest = released_versions()[:1]
        ok = len(values) == 1 and latest == list(values)
        print(json.dumps(dict(ok=ok, versions=found, changelog_latest=latest[0] if latest else None), indent=1))
        return 0 if ok else 1
    if not args.version or not SEMVER.match(args.version):
        parser.error('Give a version like 0.3.0')
    text = release_changelog(CHANGELOG.read_text(encoding='utf-8'), args.version, args.date)
    for path, (_, writer) in FIELDS.items():
        file = ROOT / path
        file.write_text(writer(file.read_text(encoding='utf-8'), args.version), encoding='utf-8')
    CHANGELOG.write_text(text, encoding='utf-8')
    print(f'Version {args.version}. Review CHANGELOG.md, then commit and tag v{args.version}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
