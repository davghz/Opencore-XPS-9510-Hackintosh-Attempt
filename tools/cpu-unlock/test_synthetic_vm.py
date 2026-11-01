#!/usr/bin/env python3
"""Test the Dell source with a synthetic locked baseline, without touching hardware.

Artifacts stay in an isolated .local directory. Never deploy those binaries.
For a real locked machine, prepare_baseline.py and run_vm_test.py must be used
separately to qualify its exact production binary.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

source = Path(__file__).resolve().parent / 'early-cfg'
sys.path.insert(0, str(source))
from prepare_baseline import header

local = source.parents[2] / '.local'
local.mkdir(exist_ok=True)
work = Path(tempfile.mkdtemp(prefix='synthetic-cfg-', dir=local))
for name in ('early_cfg.c', 'fixture.c', 'Makefile', 'run_vm_test.py'):
    shutil.copy2(source/name, work/name)
payload = bytearray((i * 37 + 11) % 256 for i in range(654))
payload[0x43] = 1
(work/'expected.h').write_text(header(payload))
(work/'VM-ONLY.txt').write_text('SYNTHETIC BASELINE. Never install these binaries on physical hardware.\n')
print('VM-only build directory:', work, flush=True)
subprocess.run(['make', 'EarlyCfg.efi', 'Fixture.efi'], cwd=work, check=True)
subprocess.run([sys.executable, 'run_vm_test.py'], cwd=work, check=True)
