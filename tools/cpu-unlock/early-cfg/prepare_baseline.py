#!/usr/bin/env python3
"""Read the exact supported Dell's CpuSetup and generate local-only build inputs.

Does not write firmware, EFI variables, the ESP, or MSRs. Linux only.
"""
from pathlib import Path
import os
import platform
from target_profile import CPU_NAME, read_identity, validate

WORK = Path(__file__).resolve().parent
def header(payload):
    rows = [', '.join(f'0x{x:02x}' for x in payload[i:i+16]) for i in range(0, len(payload), 16)]
    return '/* PRIVATE: generated from this machine; never publish. */\nstatic const unsigned char expected_cpu[] = {\n' + ',\n'.join(rows) + '\n};\n'

def main():
    if platform.system() != 'Linux':
        raise SystemExit('This helper requires Linux booted directly on the target Dell')
    identity = read_identity()
    raw = (Path('/sys/firmware/efi/efivars')/CPU_NAME).read_bytes()
    try:
        payload = validate(raw, identity, require_locked=True)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    baseline = WORK.parent/'CpuSetup-original.efivar'
    expected = WORK/'expected.h'
    if baseline.exists() or expected.exists():
        raise SystemExit('Existing baseline/header preserved; inspect before preparing another build')
    os.umask(0o077)
    with baseline.open('xb') as f:
        f.write(raw)
    with expected.open('x') as f:
        f.write(header(payload))
    print('Saved private baseline and generated expected.h; firmware untouched.')
    print('Build and run the exact-binary OVMF tests before using manage.py install.')

if __name__ == '__main__':
    main()
