"""Install, inspect, or remove the one-shot early CFG experiment (root required)."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from target_profile import read_identity, validate

WORK = Path(__file__).resolve().parent
ESP = Path('/boot/efi/EFI/CFGUnlock')
EV = Path('/sys/firmware/efi/efivars')
GLOBAL = '8be4df61-93ca-11d2-aa0d-00e098032b8c'
CPU = EV / 'CpuSetup-b08f97ff-e6e8-4193-a997-5e9e9b0adb32'
STATE = WORK / 'installation.json'
ARM = b'DELL-XPS9510-1470-CFG43-ZERO-v1\n'

def sha(b):
    return hashlib.sha256(b).hexdigest()

def need(condition, message):
    if not condition:
        raise SystemExit(message)

def optional(path):
    return path.read_bytes() if path.exists() else None

def check_esp():
    mount = json.loads(subprocess.check_output(['findmnt', '-J', '-T', '/boot/efi']))['filesystems'][0]
    need(mount['target'] == '/boot/efi' and mount['fstype'] == 'vfat'
         and mount['source'] == '/dev/nvme0n1p1', 'ABORT: unexpected ESP mount.')

def snapshot(prefix):
    return {p.name: p.read_bytes().hex() for p in EV.glob(prefix+'*-'+GLOBAL)}

def install():
    validate(CPU.read_bytes(), read_identity(), require_locked=True)
    need(not STATE.exists(), 'Installation state already exists; inspect it first.')
    baseline = (WORK.parent/'CpuSetup-original.efivar').read_bytes()
    validate(baseline, read_identity(), require_locked=True)
    need(CPU.read_bytes() == baseline, 'ABORT: CpuSetup changed since baseline capture.')
    binary = (WORK/'EarlyCfg.efi').read_bytes()
    test = json.loads((WORK/'vm-test-result.json').read_text())
    need(test['passed'] and test['driver_sha256'] == sha(binary),
         'ABORT: exact production binary has not passed the VM tests.')
    pe = struct.unpack_from('<I', binary, 0x3c)[0]
    need(binary[pe:pe+4] == b'PE\0\0' and struct.unpack_from('<H',binary,pe+4)[0] == 0x8664
         and struct.unpack_from('<H',binary,pe+24+68)[0] == 11,
         'ABORT: expected x64 EFI boot-services driver.')
    check_esp()
    need((EV/('SecureBoot-'+GLOBAL)).read_bytes()[4:] == b'\0', 'Secure Boot must already be disabled.')
    ESP.mkdir(exist_ok=True)
    need(not (ESP/'early-cfg.arm').exists() and not (ESP/'early-cfg-result.txt').exists(),
         'An existing arm token or result needs review first.')
    boot_before = {p.name: p.read_bytes().hex() for p in EV.glob('Boot*-'+GLOBAL)}
    driver_before = {p.name: p.read_bytes().hex() for p in EV.glob('Driver*-'+GLOBAL)}
    number = next(i for i in range(0xc043, 0xc053) if not (EV/f'Driver{i:04X}-{GLOBAL}').exists())
    dst = ESP/'EarlyCfg.efi'
    need(not dst.exists(), 'EarlyCfg.efi already exists; inspect the previous install.')
    shutil.copyfile(WORK/'EarlyCfg.efi', dst)
    os.sync()
    need(dst.read_bytes() == binary, 'ESP copy verification failed.')
    record = {'driver_number': f'{number:04X}', 'driver_sha256': sha(binary),
              'boot_before': boot_before, 'driver_before': driver_before,
              'boot_id_at_install': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'status': 'creating-driver-entry'}
    STATE.write_text(json.dumps(record, indent=2)+'\n'); STATE.chmod(0o600)
    # Full device path is important for Driver#### support on some firmware.
    command = ['efibootmgr', '-r', '-c', '-b', f'{number:04X}', '--full-dev-path',
               '-d', '/dev/nvme0n1', '-p', '1', '-l', r'\EFI\CFGUnlock\EarlyCfg.efi',
               '-L', 'Dell XPS 9510 CFG one-shot']
    try:
        subprocess.run(command, check=True)
        entry = (EV/f'Driver{number:04X}-{GLOBAL}').read_bytes()
        need('Dell XPS 9510 CFG one-shot'.encode('utf-16le') in entry and
             r'\EFI\CFGUnlock\EarlyCfg.efi'.encode('utf-16le') in entry, 'Driver entry mismatch.')
        boot_after = {p.name: p.read_bytes().hex() for p in EV.glob('Boot*-'+GLOBAL)}
        need(boot_after == boot_before, 'Unexpected change to Boot variables; inspect before reboot.')
        order = (EV/('DriverOrder-'+GLOBAL)).read_bytes()[4:]
        old_order = bytes.fromhex(driver_before.get('DriverOrder-'+GLOBAL, ''))[4:]
        need(order == struct.pack('<H', number)+old_order, 'Unexpected DriverOrder; inspect before reboot.')
        for name, value in driver_before.items():
            if name != 'DriverOrder-'+GLOBAL:
                need((EV/name).read_bytes().hex() == value,
                     'Existing firmware driver changed; inspect before reboot.')
        record['driver_entry_sha256'] = sha(entry)
        record['status'] = 'registered-not-armed'
        STATE.write_text(json.dumps(record, indent=2)+'\n')
        (ESP/'early-cfg.arm').write_bytes(ARM);os.sync()
        need((ESP/'early-cfg.arm').read_bytes() == ARM, 'Arm file verification failed.')
        record['status'] = 'armed'
        STATE.write_text(json.dumps(record, indent=2)+'\n');os.sync()
    except BaseException:
        (ESP/'early-cfg.arm').unlink(missing_ok=True)
        os.sync()
        print('Installation interrupted; token removed. Inspect installation.json before reboot.')
        raise
    print('Armed for the next normal boot. No reboot performed. CFG is not yet unlocked.')

def status():
    print('Armed token present:', (ESP/'early-cfg.arm').exists())
    result = ESP/'early-cfg-result.txt'
    print(result.read_text() if result.exists() else 'No early-driver result yet.')
    raw = CPU.read_bytes()
    validate(raw, read_identity())
    print(f'Current nonvolatile CpuSetup[0x43] = {raw[4+0x43]}')
    subprocess.run(['modprobe', 'msr'], check=True)
    subprocess.run([sys.executable, str(WORK.parent/'check.py')], check=True)

def remove():
    check_esp()
    record = json.loads(STATE.read_text())
    number = record['driver_number']
    need(isinstance(number, str) and len(number) == 4 and
         all(c in '0123456789ABCDEF' for c in number) and
         0xc043 <= int(number, 16) < 0xc053, 'Invalid recorded driver number.')
    (ESP/'early-cfg.arm').unlink(missing_ok=True);os.sync()
    boot_before = snapshot('Boot')
    drivers_before = snapshot('Driver')
    order_name = 'DriverOrder-'+GLOBAL
    order = bytes.fromhex(drivers_before.get(order_name, ''))[4:]
    need(len(order) % 2 == 0, 'Malformed DriverOrder; inspect before cleanup.')
    remaining = b''.join(order[i:i+2] for i in range(0, len(order), 2)
                         if order[i:i+2] != struct.pack('<H', int(number, 16)))
    entry = EV/f'Driver{number}-{GLOBAL}'
    if entry.exists():
        need('driver_entry_sha256' in record and sha(entry.read_bytes()) == record['driver_entry_sha256'],
             'Driver entry changed or installation incomplete; refusing to delete an unverified entry.')
        subprocess.run(['efibootmgr', '-r', '-b', number, '-B'], check=True)
    need(not entry.exists(), 'Temporary driver entry was not removed.')
    need(snapshot('Boot') == boot_before, 'Boot variables changed during cleanup.')
    for name, value in drivers_before.items():
        if name not in (entry.name, order_name):
            need((EV/name).read_bytes().hex() == value, 'Existing firmware driver changed during cleanup.')
    after = optional(EV/order_name)
    need((after[4:] if after else b'') == remaining,
         'Unexpected DriverOrder after cleanup; inspect before reboot.')
    record['status'] = 'removed'
    STATE.write_text(json.dumps(record, indent=2)+'\n')
    print('One-shot token and Driver entry removed. CpuSetup was not changed by cleanup.')

if __name__ == '__main__':
    need(os.geteuid() == 0, 'Run with sudo.')
    need(len(sys.argv) == 2 and sys.argv[1] in ('install','status','remove'),
         'Usage: sudo python3 manage.py install|status|remove')
    globals()[sys.argv[1]]()
