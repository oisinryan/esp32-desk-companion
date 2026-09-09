#!/usr/bin/env python3
"""Package the committed source tree reproducibly; never read private working files."""
import argparse
import hashlib
import io
import re
import subprocess
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_NAMES = {'.env','pet_config.h','codey_assets.h','codey-sheet.webp','codey-device-frame.png'}
FORBIDDEN_PARTS = {'.git','.venv','.pio','.pio-core','artifacts','runtime','dist','node_modules','__pycache__'}


def validate_names(names):
    for name in names:
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or path.name in FORBIDDEN_NAMES or
            any(part in FORBIDDEN_PARTS for part in path.parts) or path.suffix in ('.bin','.elf','.pyc')):
            raise ValueError(f'Private/generated file in committed source: {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True, help='Release version matching committed package.json')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?', args.version):
        parser.error('Use a semantic version such as 1.0.0')
    import json
    package = json.loads(subprocess.check_output(['git','show','HEAD:package.json'], cwd=ROOT))
    if package['version'] != args.version:
        parser.error('Version does not match committed package.json')
    prefix = f'esp32-desk-companion-{args.version}/'
    raw = subprocess.check_output(['git','archive','--format=zip',f'--prefix={prefix}','HEAD'], cwd=ROOT)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        validate_names([name.removeprefix(prefix) for name in archive.namelist()])
        if archive.testzip() is not None:
            raise ValueError('Source archive integrity failure')
        count = len(archive.namelist())
    target = ROOT/f'dist/esp32-desk-companion-v{args.version}-source.zip'
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(raw)
    (target.parent/'SHA256SUMS.txt').write_text(hashlib.sha256(raw).hexdigest()+'  '+target.name+'\n')
    print(f'Packaged {count} committed entries: {target.name}')


if __name__ == '__main__':
    main()
