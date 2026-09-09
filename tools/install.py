#!/usr/bin/env python3
"""Manifest-driven local installer. Run without arguments for guided setup."""
from __future__ import annotations
import argparse
import configparser
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
import venv

ROOT = Path(__file__).resolve().parents[1]


def run(args, root=ROOT):
    subprocess.run([str(a) for a in args], cwd=root, check=True)


def python_path(root=ROOT):
    return root / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')


def profiles(root=ROOT):
    data = json.loads((root/'installer/profiles.json').read_text())
    if data.get('schema') != 1 or not isinstance(data.get('profiles'), dict) or not data['profiles']:
        raise ValueError('Unsupported or empty firmware manifest')
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(root/'firmware/platformio.ini')
    for key, value in data['profiles'].items():
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', key) or not isinstance(value, dict):
            raise ValueError('Invalid profile identifier')
        env = value.get('environment', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', env) or f'env:{env}' not in ini:
            raise ValueError(f'Profile {key} has no matching PlatformIO environment')
        if value.get('companion') not in ('pip', 'codey') or value.get('assets') not in ('none', 'codey'):
            raise ValueError(f'Unsupported companion or asset type in {key}')
        if not isinstance(value.get('name'), str):
            raise ValueError(f'Profile {key} needs a name')
    return data['profiles']


def env_value(text, key):
    matches = re.findall(r'^\s*' + re.escape(key) + r'\s*=\s*(.*?)\s*$', text, re.M)
    if len(matches) > 1:
        raise ValueError(f'Duplicate {key} in .env; resolve it before configuring')
    if not matches:
        return None
    value = matches[0]
    if value.startswith('"'):
        return json.loads(value)
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value.split('#', 1)[0].strip()


def set_env(text, key, value):
    line = f'{key}={value}'
    pattern = r'^\s*' + re.escape(key) + r'\s*=.*$'
    return re.sub(pattern, lambda _: line, text, flags=re.M) if re.search(pattern, text, re.M) else text.rstrip()+'\n'+line+'\n'


def macro(text, key):
    match = re.search(r'^#define\s+'+re.escape(key)+r'\s+("[^\n]*")\s*$', text, re.M)
    return json.loads(match[1]) if match else None


def set_macro(text, key, value):
    pattern = r'^#define\s+'+re.escape(key)+r'\s+.*$'
    if not re.search(pattern, text, re.M):
        raise ValueError(f'Missing {key} in firmware configuration')
    return re.sub(pattern, lambda _: '#define '+key+' '+json.dumps(value), text, flags=re.M)


def private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name+'-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(value)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def configure(profile, bridge_url=None, root=ROOT):
    env_path, header_path = root/'.env', root/'firmware/include/pet_config.h'
    env = env_path.read_text() if env_path.exists() else (root/'.env.example').read_text()
    header = header_path.read_text() if header_path.exists() else (root/'firmware/include/pet_config.example.h').read_text()
    url = bridge_url or (macro(header, 'PET_BRIDGE_URL') if header_path.exists() else None)
    if not url:
        raise ValueError('Supply --bridge-url http://YOUR_COMPUTER_LAN_IP:8787 on first setup')
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or not parsed.hostname or parsed.username or parsed.password or
        parsed.path not in ('', '/') or parsed.query or parsed.fragment or
        any(c.isspace() for c in url) or parsed.hostname in ('localhost', '127.0.0.1', '::1', '0.0.0.0')):
        raise ValueError('Bridge URL must be an HTTP LAN host and port, without credentials or path')
    port = parsed.port or 80
    if not 1 <= port <= 65535:
        raise ValueError('Invalid bridge port')
    placeholder = 'replace-with-a-long-random-pairing-token'
    tokens = [x for x in (env_value(env, 'PET_TOKEN'), macro(header, 'PET_TOKEN')) if x and x != placeholder]
    if len(set(tokens)) > 1:
        raise ValueError('Existing companion and firmware tokens differ; reconcile them before setup')
    token = tokens[0] if tokens else secrets.token_hex(24)
    if not re.fullmatch(r'[A-Za-z0-9_-]{24,256}', token):
        raise ValueError('Pairing token must contain 24–256 letters, digits, hyphens or underscores')
    for key, value in {'HOST':'0.0.0.0', 'PORT':str(port), 'PET_TOKEN':token,
                       'CODEX_PET':'1' if profile['companion']=='codey' else '0'}.items():
        env_value(env, key)  # Reject duplicates before touching either file.
        env = set_env(env, key, value)
    header = set_macro(set_macro(header, 'PET_TOKEN', token), 'PET_BRIDGE_URL', url.rstrip('/'))
    old_env = env_path.read_text() if env_path.exists() else None
    private_write(env_path, env)
    try:
        private_write(header_path, header)
    except OSError:
        if old_env is None:
            env_path.unlink(missing_ok=True)
        else:
            private_write(env_path, old_env)
        raise
    print('Paired companion and firmware configuration saved. Existing Wi-Fi settings and API key preserved.')


def require_python(root=ROOT):
    path = python_path(root)
    if not path.exists():
        raise ValueError('Run bootstrap first to install the build tools')
    return path


def bootstrap(root=ROOT):
    if sys.version_info < (3, 11):
        raise ValueError('Python 3.11 or newer is required')
    if not python_path(root).exists():
        venv.EnvBuilder(with_pip=True).create(root/'.venv')
    run([python_path(root), '-m', 'pip', 'install', '-r', root/'installer/requirements.txt'], root)


def serial_ports(root=ROOT):
    result = subprocess.run([require_python(root), '-m', 'platformio', 'device', 'list', '--json-output'],
                            cwd=root, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def choose_port(devices, requested=None):
    ports = [d['port'] for d in devices if d.get('port')]
    if requested:
        if requested not in ports:
            raise ValueError('Requested serial port is not connected; run devices')
        return requested
    candidates = [d['port'] for d in devices if d.get('port') and 'VID:PID=' in d.get('hwid', '')]
    if len(candidates) != 1:
        raise ValueError('Specify --port from devices; automatic selection requires exactly one USB serial device')
    return candidates[0]


def build_command(profile, root=ROOT, port=None):
    args = [require_python(root), '-m', 'platformio', 'run', '--project-dir', root/'firmware', '-e', profile['environment']]
    if port:
        args += ['--target', 'upload', '--upload-port', port]
    return args


def check_assets(profile, root=ROOT):
    if profile['assets'] == 'codey' and not (root/'firmware/include/codey_assets.h').exists():
        raise ValueError('Run assets --profile codey-tft first; Codey artwork is not distributed')


def require_node():
    node = shutil.which('node')
    if not node:
        raise ValueError('Install Node.js 22.9 or newer to run the companion')
    version = subprocess.check_output([node, '--version'], text=True).strip().lstrip('v').split('.')
    if tuple(map(int, version[:2])) < (22, 9):
        raise ValueError('Node.js 22.9 or newer is required')
    return node


def assets(profile, sheet=None, app=None, root=ROOT):
    if profile['assets'] == 'none':
        print('This profile includes its artwork in source.')
        return
    args = [require_python(root), root/'tools/export_codey.py']
    if sheet:
        args += ['--sheet', sheet]
    if app:
        args += ['--app', app]
    run(args, root)


def wizard():
    choices = profiles()
    for key, value in choices.items():
        print(f'  {key}: {value["name"]}')
    key = input('Firmware profile [pip-tft]: ').strip() or 'pip-tft'
    if key not in choices:
        raise ValueError('Unknown firmware profile')
    profile = choices[key]
    if profile['companion']=='codey' and sys.platform!='darwin':
        raise ValueError('The Codey desktop integration currently requires macOS')
    require_node()
    url = input('Computer LAN URL (for example http://192.168.1.50:8787): ').strip()
    if not url:
        raise ValueError('A LAN URL is required')
    bootstrap()
    configure(profile, url)
    assets(profile)
    run(build_command(profile))
    print('Build complete. Flashing replaces the connected board firmware.')
    if input('Flash now? [y/N]: ').strip().lower() == 'y':
        devices = serial_ports()
        for device in devices:
            print(device['port'], device.get('description', ''))
        port = choose_port(devices, input('USB serial port (blank for one detected device): ').strip() or None)
        run(build_command(profile, port=port))
        print(f'Next: python3 tools/install.py wifi --port {port}')
    print('Start the companion with: python3 tools/install.py start')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', nargs='?', choices=['list','bootstrap','doctor','devices','configure','assets','build','flash','wifi','start','hooks'])
    p.add_argument('--profile', help='Firmware profile from list')
    p.add_argument('--bridge-url', help='Computer LAN address, e.g. http://192.168.1.50:8787')
    p.add_argument('--port', help='Explicit connected USB serial port')
    p.add_argument('--http-port', type=int, default=8788, help='Loopback Wi-Fi setup page port')
    p.add_argument('--sheet', type=Path, help='Compatible sprite sheet you have permission to use')
    p.add_argument('--app', type=Path, help='macOS app bundle containing Codey artwork')
    args = p.parse_args()
    if not args.command:
        if not sys.stdin.isatty():
            p.print_help(); return
        return wizard()
    choices = profiles()
    profile = choices.get(args.profile)
    if args.profile and not profile:
        raise ValueError('Unknown profile; run list')
    if args.command in ('configure','assets','build','flash') and not profile:
        raise ValueError('--profile is required; run list')
    if args.command == 'list':
        for key, value in choices.items():
            print(f'{key:12} {value["name"]} [{value["environment"]}]')
    elif args.command == 'bootstrap':
        bootstrap()
    elif args.command == 'doctor':
        print(f'Python: {sys.version.split()[0]}')
        print(f'Node: {require_node()}')
        print(f'Build Python: {require_python()}')
        run([require_python(), '-m', 'platformio', '--version'])
        print(f'Firmware profiles: {len(choices)}; configuration present: {(ROOT/".env").exists()}')
        print('Codey app navigation: '+('macOS supported' if sys.platform=='darwin' else 'unavailable on this OS'))
    elif args.command == 'devices':
        for device in serial_ports():
            print(device['port'], device.get('description', ''))
    elif args.command == 'configure':
        if profile['companion']=='codey' and sys.platform!='darwin':
            raise ValueError('The Codey desktop integration currently requires macOS; cross-compiling is supported')
        configure(profile, args.bridge_url)
    elif args.command == 'assets':
        assets(profile, args.sheet, args.app)
    elif args.command in ('build','flash'):
        check_assets(profile)
        port = None
        if args.command == 'flash':
            if not (ROOT/'firmware/include/pet_config.h').exists() or not (ROOT/'.env').exists():
                raise ValueError('Run configure before flashing')
            mode = env_value((ROOT/'.env').read_text(), 'CODEX_PET')
            if mode != ('1' if profile['companion']=='codey' else '0'):
                raise ValueError('Run configure for this profile before flashing; companion mode differs')
            # Revalidate pairing without modifying the configuration.
            token = env_value((ROOT/'.env').read_text(), 'PET_TOKEN')
            if not token or token != macro((ROOT/'firmware/include/pet_config.h').read_text(), 'PET_TOKEN'):
                raise ValueError('Companion and firmware pairing tokens differ; run configure')
            port = choose_port(serial_ports(), args.port)
        run(build_command(profile, port=port))
    elif args.command == 'wifi':
        port = choose_port(serial_ports(), args.port)
        run([require_python(), ROOT/'tools/setup_wifi.py', '--port', port, '--http-port', str(args.http_port)])
    elif args.command == 'start':
        if not (ROOT/'.env').exists():
            raise ValueError('Run configure first')
        run([require_node(), '--env-file=.env', ROOT/'bridge/server.mjs'])
    elif args.command == 'hooks':
        if sys.platform != 'darwin':
            raise ValueError('Codey desktop hooks currently support macOS only')
        run([require_python(), ROOT/'tools/install_codex_hook.py'])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        # Subprocess commands never contain passwords or pairing tokens.
        print(f'Installer: {error}', file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print('\nSetup cancelled.', file=sys.stderr)
        sys.exit(130)
