import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', SOURCE/'tools/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('.env.example','firmware/include/pet_config.example.h','firmware/platformio.ini','installer/profiles.json'):
            target = self.root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE/name, target)
        self.profiles = installer.profiles(self.root)

    def configure(self, key='pip-tft', url='http://192.168.1.50:8787'):
        installer.configure(self.profiles[key], url, self.root)

    def test_pairing_and_switch_preserve_secrets_and_pins(self):
        self.configure()
        env_path = self.root/'.env'
        header_path = self.root/'firmware/include/pet_config.h'
        token = installer.env_value(env_path.read_text(), 'PET_TOKEN')
        self.assertEqual(len(token), 48)
        env_path.write_text(env_path.read_text().replace('OPENAI_API_KEY=', 'OPENAI_API_KEY=fixture-key'))
        header_path.write_text(header_path.read_text().replace('PET_SDA 21', 'PET_SDA 19').replace('PET_WIFI_SSID ""', 'PET_WIFI_SSID "fixture-wifi"'))
        self.configure('codey-tft', 'http://192.168.1.51:8790')
        env, header = env_path.read_text(), header_path.read_text()
        self.assertEqual(installer.env_value(env, 'PET_TOKEN'), token)
        self.assertEqual(installer.macro(header, 'PET_TOKEN'), token)
        self.assertEqual(installer.env_value(env, 'PORT'), '8790')
        self.assertEqual(installer.env_value(env, 'CODEX_PET'), '1')
        self.assertIn('fixture-key', env)
        self.assertIn('fixture-wifi', header)
        self.assertIn('PET_SDA 19', header)
        self.configure('pip-oled', None)
        self.assertEqual(installer.macro(header_path.read_text(), 'PET_BRIDGE_URL'), 'http://192.168.1.51:8790')
        self.assertEqual(installer.env_value(env_path.read_text(), 'CODEX_PET'), '0')

    def test_rejects_invalid_url_without_writes(self):
        for url in (None, 'http://localhost:8787','http://127.0.0.1:8787','https://192.168.1.50','http://user:pass@host','http://host/path','http://host:99999','http://host/?query=1','http://host\n'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.configure(url=url)
            self.assertFalse((self.root/'.env').exists())
            self.assertFalse((self.root/'firmware/include/pet_config.h').exists())

    def test_conflicting_tokens_do_not_overwrite(self):
        self.configure()
        header_path = self.root/'firmware/include/pet_config.h'
        header_path.write_text(installer.set_macro(header_path.read_text(), 'PET_TOKEN', 'a'*48))
        original = (self.root/'.env').read_text()
        with self.assertRaisesRegex(ValueError, 'tokens differ'):
            self.configure()
        self.assertEqual((self.root/'.env').read_text(), original)

    def test_duplicate_env_rejected(self):
        self.configure()
        env = self.root/'.env'
        env.write_text(env.read_text()+'\nCODEX_PET=1\n')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.configure()

    def test_rollback_on_header_write_failure(self):
        self.configure()
        original = (self.root/'.env').read_text()
        actual_write = installer.private_write
        def fail_header(path, value):
            if path.name == 'pet_config.h':
                raise OSError('fixture disk error')
            actual_write(path, value)
        with patch.object(installer, 'private_write', side_effect=fail_header):
            with self.assertRaises(OSError):
                self.configure('codey-tft')
        self.assertEqual((self.root/'.env').read_text(), original)

    def test_invalid_manifest_rejected(self):
        path = self.root/'installer/profiles.json'
        data = json.loads(path.read_text())
        data['profiles']['pip-tft']['environment'] = '../outside'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'environment'):
            installer.profiles(self.root)

    def test_build_never_flashes_implicitly(self):
        python = installer.python_path(self.root)
        python.parent.mkdir(parents=True)
        python.touch()
        for profile in self.profiles.values():
            command = installer.build_command(profile, self.root)
            self.assertNotIn('upload', command)
            self.assertEqual(command[-1], profile['environment'])
            flash = installer.build_command(profile, self.root, '/dev/fixture')
            self.assertEqual(flash[-4:], ['--target','upload','--upload-port','/dev/fixture'])

    def test_ambiguous_ports_and_missing_port_rejected(self):
        devices = [{'port':'COM3','hwid':'USB VID:PID=1A86:7523'}, {'port':'COM4','hwid':'USB VID:PID=10C4:EA60'}]
        with self.assertRaises(ValueError):
            installer.choose_port(devices)
        with self.assertRaises(ValueError):
            installer.choose_port(devices, 'COM5')
        self.assertEqual(installer.choose_port(devices, 'COM3'), 'COM3')
        self.assertEqual(installer.choose_port(devices[:1]), 'COM3')
        with self.assertRaises(ValueError):
            installer.choose_port([])

    def test_assets_required_only_for_codey(self):
        installer.check_assets(self.profiles['pip-tft'], self.root)
        installer.check_assets(self.profiles['pip-oled'], self.root)
        with self.assertRaisesRegex(ValueError, 'artwork'):
            installer.check_assets(self.profiles['codey-tft'], self.root)


if __name__ == '__main__':
    unittest.main()
