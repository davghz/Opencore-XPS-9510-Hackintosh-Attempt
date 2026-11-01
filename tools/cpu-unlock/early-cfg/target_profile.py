"""Exact Dell target established from the 1.47.0 Setup IFR; no firmware writes."""
from pathlib import Path
import struct

CPU_NAME = 'CpuSetup-b08f97ff-e6e8-4193-a997-5e9e9b0adb32'
CFG_OFFSET = 0x43
PAYLOAD_SIZE = 654
IDENTITY = {
    'sys_vendor': 'Dell Inc.', 'product_name': 'XPS 15 9510',
    'board_vendor': 'Dell Inc.', 'board_name': '01V4T3',
    'bios_version': '1.47.0', 'bios_date': '05/31/2026',
}

def read_identity():
    return {key: (Path('/sys/class/dmi/id')/key).read_text().strip() for key in IDENTITY}

def validate(raw, identity, require_locked=False):
    if identity != IDENTITY:
        raise ValueError('Dell system, board, BIOS or firmware date mismatch')
    if len(raw) != 4 + PAYLOAD_SIZE or struct.unpack_from('<I', raw)[0] != 7:
        raise ValueError('Expected attributes 7 and exactly 654 CpuSetup payload bytes')
    value = raw[4 + CFG_OFFSET]
    if value not in (0, 1):
        raise ValueError('Unexpected CFG byte: only 0 and 1 are valid')
    if require_locked and value != 1:
        raise ValueError('CFG is already disabled in CpuSetup; verify MSRs, do not arm a writer')
    return raw[4:]
