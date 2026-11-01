#!/usr/bin/env python3
"""Read Dell firmware settings and every online CPU's CFG Lock. Never writes hardware.

Exit 0: verified unlocked; 1: locked or setting/hardware disagree; 2: incomplete.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'early-cfg'))
from target_profile import CFG_OFFSET, CPU_NAME, read_identity, validate

ONLINE = Path('/sys/devices/system/cpu/online')

def parse_online(text):
    cpus = set()
    for item in text.strip().split(','):
        ends = item.split('-')
        if len(ends) == 1:
            start = end = int(ends[0])
        elif len(ends) == 2:
            start, end = map(int, ends)
        else:
            raise ValueError('Invalid online CPU list')
        if start < 0 or end < start or end > 1048576:
            raise ValueError('Invalid online CPU range')
        cpus.update(range(start, end + 1))
    return sorted(cpus)

def read_msr(cpu):
    fd = os.open(f'/dev/cpu/{cpu}/msr', os.O_RDONLY)
    try:
        raw = os.pread(fd, 8, 0xE2)
    finally:
        os.close(fd)
    if len(raw) != 8:
        raise OSError('Short MSR read')
    return int.from_bytes(raw, 'little')

def collect():
    result = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'identity': {}, 'cfg_byte': None, 'cpus': [], 'errors': []}
    try:
        result['identity'] = read_identity()
        raw = (Path('/sys/firmware/efi/efivars') / CPU_NAME).read_bytes()
        payload = validate(raw, result['identity'])
        result['cfg_byte'] = payload[CFG_OFFSET]
        result['payload_size'] = len(payload)
        result['attributes'] = int.from_bytes(raw[:4], 'little')
    except (OSError, ValueError) as exc:
        result['errors'].append(f'Firmware: {exc}')
    try:
        cpus = parse_online(ONLINE.read_text())
        result['online_cpus'] = cpus
        for cpu in cpus:
            try:
                value = read_msr(cpu)
                result['cpus'].append({'cpu': cpu, 'msr_e2': f'0x{value:016X}',
                                       'cfg_lock_bit15': (value >> 15) & 1})
            except OSError as exc:
                result['errors'].append(f'CPU {cpu}: {exc}')
        if parse_online(ONLINE.read_text()) != cpus:
            result['errors'].append('Online CPUs changed during measurement; retry')
    except (OSError, ValueError) as exc:
        result['errors'].append(f'CPU enumeration: {exc}')
    code = classify(result)
    result['status'] = {0: 'unlocked', 1: 'locked-or-inconsistent', 2: 'unverified'}[code]
    return result, code

def classify(result):
    if result['errors'] or not result['cpus']:
        return 2
    if [cpu['cpu'] for cpu in result['cpus']] != result.get('online_cpus'):
        return 2
    if result['cfg_byte'] != 0 or any(cpu['cfg_lock_bit15'] for cpu in result['cpus']):
        return 1
    return 0

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Print a machine-readable report')
    args = parser.parse_args()
    result, code = collect()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print('Target:', result['identity'])
        print('Saved CpuSetup[0x43]:', result['cfg_byte'])
        for cpu in result['cpus']:
            print(f"CPU {cpu['cpu']}: MSR 0xE2={cpu['msr_e2']}; bit15={cpu['cfg_lock_bit15']}")
        for error in result['errors']:
            print(error, file=sys.stderr)
        print({'unlocked': 'CFG Lock is DISABLED on every online CPU.',
               'locked-or-inconsistent': 'CFG Lock is enabled or firmware and hardware disagree.',
               'unverified': 'INCOMPLETE: do not infer unlock from the saved byte alone.'}[result['status']])
    return code

if __name__ == '__main__':
    raise SystemExit(main())
