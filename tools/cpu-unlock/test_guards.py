"""Regression checks for refusal conditions and complete CPU coverage."""
from pathlib import Path
import struct
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / 'early-cfg'))
from target_profile import IDENTITY, validate
from check import classify, parse_online
import manage

class Guards(unittest.TestCase):
    def raw(self, cfg=1, size=654, attrs=7):
        payload = bytearray(size)
        payload[0x43] = cfg
        return struct.pack('<I', attrs) + payload

    def test_locked_baseline_accepted(self):
        self.assertEqual(len(validate(self.raw(), IDENTITY, True)), 654)

    def test_unlocked_is_readable_but_cannot_arm(self):
        self.assertEqual(validate(self.raw(0), IDENTITY)[0x43], 0)
        with self.assertRaisesRegex(ValueError, 'already disabled'):
            validate(self.raw(0), IDENTITY, True)

    def test_every_identity_field_matters(self):
        for key in IDENTITY:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(self.raw(), {**IDENTITY, key: 'different'}, True)

    def test_wrong_layout_rejected(self):
        for raw in (b'', self.raw(size=961), self.raw(size=653),
                    self.raw(attrs=3), self.raw(cfg=2)):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                validate(raw, IDENTITY, True)

    def test_sparse_online_list(self):
        self.assertEqual(parse_online('0-3,8,10-11\n'), [0,1,2,3,8,10,11])

    def test_invalid_cpu_lists(self):
        for text in ('', '-1', '3-1', 'a', '1-2-3'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_online(text)

    def result(self):
        return {'errors': [], 'cfg_byte': 0, 'online_cpus': [0, 1],
                'cpus': [{'cpu': 0, 'cfg_lock_bit15': 0}, {'cpu': 1, 'cfg_lock_bit15': 0}]}

    def test_complete_unlocked(self):
        self.assertEqual(classify(self.result()), 0)

    def test_missing_cpu_cannot_report_success(self):
        r = self.result(); r['cpus'].pop()
        self.assertEqual(classify(r), 2)

    def test_permission_error_cannot_report_success(self):
        r = self.result(); r['errors'] = ['permission denied']
        self.assertEqual(classify(r), 2)

    def test_one_locked_cpu_is_failure(self):
        r = self.result(); r['cpus'][1]['cfg_lock_bit15'] = 1
        self.assertEqual(classify(r), 1)

    def test_saved_setting_disagrees_is_failure(self):
        r = self.result(); r['cfg_byte'] = 1
        self.assertEqual(classify(r), 1)

class ManagerGuards(unittest.TestCase):
    def test_install_refuses_already_disabled_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cpu = Path(tmp)/'cpu'
            cpu.write_bytes(struct.pack('<I', 7)+bytes(654))
            with patch.object(manage, 'CPU', cpu), patch.object(manage, 'read_identity', return_value=IDENTITY), \
                 patch.object(manage, 'check_esp') as mount, patch.object(manage.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'already disabled'):
                    manage.install()
                mount.assert_not_called()
                run.assert_not_called()
                self.assertEqual(list(Path(tmp).iterdir()), [cpu])

    def cleanup_case(self, tamper=False):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp); ev = work/'ev'; ev.mkdir(); esp = work/'esp'; esp.mkdir()
            state = work/'installation.json'; guid = manage.GLOBAL
            old = ev/f'Driver0000-{guid}'; old.write_bytes(b'existing-driver')
            boot = ev/f'BootOrder-{guid}'; boot.write_bytes(struct.pack('<IHH', 7, 0, 2))
            order = ev/f'DriverOrder-{guid}'; order.write_bytes(struct.pack('<IHH', 7, 0xc043, 0))
            entry = ev/f'DriverC043-{guid}'; entry.write_bytes(b'our-driver')
            state.write_text(json.dumps({'driver_number': 'C043', 'driver_entry_sha256': manage.sha(entry.read_bytes())}))
            (esp/'early-cfg.arm').write_bytes(manage.ARM)
            if tamper: entry.write_bytes(b'changed-driver')
            def remove_entry(command, check):
                self.assertEqual(command, ['efibootmgr', '-r', '-b', 'C043', '-B'])
                entry.unlink(); order.write_bytes(struct.pack('<IH', 7, 0))
            with patch.object(manage, 'EV', ev), patch.object(manage, 'ESP', esp), \
                 patch.object(manage, 'STATE', state), patch.object(manage, 'check_esp'), \
                 patch.object(manage.os, 'sync'), patch.object(manage.subprocess, 'run', side_effect=remove_entry) as run:
                if tamper:
                    with self.assertRaisesRegex(SystemExit, 'refusing to delete'):
                        manage.remove()
                    run.assert_not_called(); self.assertTrue(entry.exists())
                else:
                    manage.remove()
                    self.assertFalse(entry.exists())
                    self.assertEqual(order.read_bytes(), struct.pack('<IH', 7, 0))
                    self.assertEqual(json.loads(state.read_text())['status'], 'removed')
            self.assertEqual(old.read_bytes(), b'existing-driver')
            self.assertEqual(boot.read_bytes(), struct.pack('<IHH', 7, 0, 2))
            self.assertFalse((esp/'early-cfg.arm').exists())

    def test_cleanup_preserves_existing_driver_and_boot_order(self):
        self.cleanup_case()

    def test_cleanup_refuses_changed_driver_entry(self):
        self.cleanup_case(tamper=True)

if __name__ == '__main__':
    unittest.main()
