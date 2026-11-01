"""Boot the production EFI driver under OVMF using a VM-only fixture."""
from pathlib import Path
import json
import os
import shutil
import subprocess

work = Path(__file__).resolve().parent
# A failed or interrupted rerun must not leave an earlier passing certificate.
(work/'vm-test-result.json').unlink(missing_ok=True)
ovmf = Path(os.environ.get('OVMF_DIR', '/usr/share/OVMF'))
vm = work / 'vm-test'
esp = vm / 'esp'
(esp / 'EFI/BOOT').mkdir(parents=True, exist_ok=True)
(esp / 'EFI/CFGUnlock').mkdir(exist_ok=True)
for name in ('early-cfg.arm', 'early-cfg-result.txt'):
    (esp / 'EFI/CFGUnlock' / name).unlink(missing_ok=True)
shutil.copy2(work / 'Fixture.efi', esp / 'EFI/BOOT/BOOTX64.EFI')
shutil.copy2(work / 'EarlyCfg.efi', esp / 'EFI/CFGUnlock/EarlyCfg.efi')
shutil.copy2(ovmf/'OVMF_VARS_4M.fd', vm / 'vars.fd')
disk = vm / 'esp.img'
with disk.open('wb') as f:
    f.truncate(64 * 1024 * 1024)
subprocess.run(['mkfs.vfat', '-F', '32', str(disk)], check=True, capture_output=True)
subprocess.run(['mcopy', '-s', '-i', str(disk), str(esp/'EFI'), '::/'], check=True)
args = ['qemu-system-x86_64', '-machine', 'q35', '-m', '256',
        '-drive', f'if=pflash,format=raw,readonly=on,file={ovmf}/OVMF_CODE_4M.fd',
        '-drive', f'if=pflash,format=raw,file={vm}/vars.fd',
        '-drive', f'format=raw,file={disk}', '-net', 'none',
        '-display', 'none', '-serial', f'file:{vm}/serial.log', '-monitor', 'none',
        '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04', '-no-reboot']
if os.environ.get('QEMU_DATA_DIR'):
    args.extend(['-L', os.environ['QEMU_DATA_DIR']])
p = subprocess.run(args, timeout=45, capture_output=True, text=True)
if p.stderr:
    print(p.stderr)
output = (vm / 'serial.log').read_text(errors='replace')
print(output)
passed = p.returncode == 1 and 'ALL VM CHECKS PASSED' in output and 'FAIL:' not in output
log = subprocess.run(['mtype', '-i', str(disk), '::/EFI/CFGUnlock/early-cfg-result.txt'],
                     capture_output=True, text=True)
(vm/'persisted-result.txt').write_text(log.stdout)
passed = passed and log.returncode == 0 and 'ABORT: SMBIOS board/BIOS/date mismatch.' in log.stdout
print('Persisted FAT log verified:', passed)
(work / 'vm-test-result.json').write_text(json.dumps({
    'passed': passed, 'qemu_exit_code': p.returncode,
    'driver_sha256': __import__('hashlib').sha256((work/'EarlyCfg.efi').read_bytes()).hexdigest(),
    'test_log': str(vm/'serial.log'),
    'scope': 'Production binary in OVMF, synthetic CpuSetup and SMBIOS; Dell lock timing untested'
}, indent=2)+'\n')
raise SystemExit(0 if passed else 1)
