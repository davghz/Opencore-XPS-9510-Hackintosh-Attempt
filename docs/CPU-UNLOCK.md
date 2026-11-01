# Dell XPS 9510 CPU CFG Lock

This is an adaptation of the [HP CFG utility](https://github.com/davghz/hackintosh/tree/2ac346e4c2ba7745e58c1ad049838b4b2227631b/tools/cpu-unlock).
It controls Intel CPU CFG Lock (MSR 0xE2 bit 15). It is not a bootloader unlock,
Secure Boot switch, overclocking unlock, or macOS installer fix.

**The checked XPS is already unlocked. Do not install an unlock driver on it.**
On 2026-11-01 all 16 online CPUs reported `0x0000000074000008`, with bit 15 clear;
the saved CFG byte was 0. The [verification record](../verification/CFG-9510-1.47.0.md)
separates those hardware measurements from synthetic tests of the writer.

## Exact supported profile

| Field | Required value |
| --- | --- |
| System | Dell Inc. / XPS 15 9510 |
| Board | Dell Inc. / 01V4T3 |
| BIOS / firmware date | 1.47.0 / 05/31/2026 |
| Variable / GUID | CpuSetup / B08F97FF-E6E8-4193-A997-5E9E9B0ADB32 |
| Payload / attributes | 654 bytes (0x28E) / 7 |
| CFG byte | Payload offset 0x43; 0 = disabled, 1 = enabled |
| Installer ESP | /dev/nvme0n1p1 mounted as vfat at /boot/efi |

Dell's matching firmware independently establishes the variable GUID, size,
offset, options and MSR meaning. The offset is relative to the payload; Linux
efivarfs prepends four attribute bytes. The HP's 961-byte baseline and binary
are not compatible with this Dell. A different BIOS requires fresh firmware
analysis and a separately verified profile.

## Check first

From the repository root, in Linux on the physical XPS:

```sh
sudo modprobe msr
sudo python3 tools/cpu-unlock/check.py
```

The checker reads every CPU listed in Linux's online CPU set, checks for CPU
hotplug during measurement, and reads the saved setting. Exit 0 means complete
verification of disabled CFG Lock; 1 means locked or inconsistent state; 2
means incomplete verification. Permission failures or missing CPU devices never
count as success. Use `--json` for an export without serial numbers or the full
firmware-variable payload. The checker does not write firmware or MSRs.

If all CPUs and the saved byte are 0, stop. If the saved byte is 0 but hardware
is locked, investigate the disagreement; do not fabricate a locked baseline.
The repository's `AppleXcpmCfgLock=False` already matches the verified current
state. Recheck after firmware updates or restoring BIOS defaults.

## Only if this exact profile later becomes locked

The early driver is an experimental fallback based on the HP mechanism. Dell
may protect its variables at a different point; synthetic tests do not prove
that DriverOrder execution will precede Dell's lock. A normal EFI-shell setting
write may suffice on Dell. Do not treat an accepted setting as hardware proof.

Dependencies: Python 3.9+, GNU-EFI, GCC, make/binutils, QEMU x86_64, OVMF,
dosfstools, mtools, findmnt, efibootmgr, and Linux's msr module. The tested local
build used GNU-EFI 3.0.15, GCC and QEMU 8.2.2. `EFI_PREFIX` optionally changes
the GNU-EFI prefix (default `/usr`); `OVMF_DIR` optionally selects firmware
containing `OVMF_CODE_4M.fd` and `OVMF_VARS_4M.fd`. Secure Boot must already be
disabled; the installer does not change it. Keep a working recovery boot path.

For an actually locked machine matching every profile field:

```sh
cd tools/cpu-unlock/early-cfg
python3 prepare_baseline.py
make EarlyCfg.efi Fixture.efi
python3 run_vm_test.py
sudo python3 manage.py install
```

If reading CpuSetup requires root on your distribution, run the preparation
step with sudo and return ownership of its two generated files to your user.
Preparation writes only a private local baseline and header; it refuses CFG=0,
wrong identity, attributes or size, and existing baseline files. Installation
requires the exact binary's passing VM result and an unchanged live baseline.

The driver consumes an exact one-shot token, checks SMBIOS identity and the
entire baseline, changes only byte 0x43 from 1 to 0, and verifies the entire
readback. It uses standard UEFI SetVariable. It never flashes firmware code,
writes MSRs, or reboots. `Fixture.efi` is for OVMF only; never put it on a real ESP.

Installation adds a temporary Driver entry, preserves existing entries and
Boot variables, and arms the next boot. It does not reboot. Save your work and
reboot manually into Linux, then:

```sh
sudo python3 manage.py status
sudo python3 manage.py remove
```

`READBACK EXACT` means the setting was stored, not that CPU initialization has
used it yet. Write protection, `ABORT`, missing execution evidence, unchanged
state or a readback mismatch require inspection; do not repeatedly rearm.
Cleanup removes only the recorded driver entry and token, and verifies existing
driver entries and Boot variables remain intact. It does not relock the CPU.
Keep the result log, baseline and installation record.

After successful readback and cleanup, reboot a second time. Run `check.py`
again and require all online CPU lock bits and the saved byte to be 0. The
procedure needs setup and manual reboots; it is not a one-click bootloader tool.

## Developer validation

```sh
python3 tools/cpu-unlock/test_guards.py
python3 tools/cpu-unlock/test_synthetic_vm.py
```

The latter builds inside an isolated `.local/synthetic-cfg-*` directory with a
made-up locked baseline. Its EFI binaries are VM-only and must never be deployed.
It exercises the same driver source, but does not qualify a different binary
generated from a real locked machine. That binary must pass `run_vm_test.py`.
No production baseline or deployment binary was generated on this unlocked XPS.

Original utility code is MIT-licensed; attribution and terms are in
[tools/cpu-unlock/LICENSE](../tools/cpu-unlock/LICENSE). Other files already in
the repository retain their existing terms.
