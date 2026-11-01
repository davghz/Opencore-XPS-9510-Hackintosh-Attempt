# Opencore-XPS-9510-Hackintosh

I haven't seen anyone try to put hackintosh on the 9510, so I thought I'd give it a try.

## CFG Lock: verified on BIOS 1.47.0

The original XPS was checked on 2026-11-01: **CFG Lock is already disabled**.
`CpuSetup[0x43]` is 0 and all 16 logical CPUs report MSR `0xE2 = 0x74000008`
(lock bit 15 = 0). No firmware write or reboot was needed for that check.

The HP project's constrained CFG utility has been adapted for the Dell XPS 15
9510, board 01V4T3, BIOS 1.47.0. This controls the CPU CFG setting; it does not
unlock a bootloader, disable Secure Boot, or fix other macOS installation issues.
Start with the [Dell CFG guide](docs/CPU-UNLOCK.md) and the
[verification record](verification/CFG-9510-1.47.0.md).

```sh
sudo modprobe msr
sudo python3 tools/cpu-unlock/check.py
```

The original GRUB command was `setup_var_cv CpuSetup 0x43 0x01 0x00`.
The offset has now been independently verified in Dell's 1.47.0 firmware, but
do not rerun a write on an already-unlocked system or assume the same layout
on another BIOS. A command accepting a setting does not by itself prove the
CPU is unlocked; verify every online CPU after reboot.

The adapted early EFI writer passed synthetic OVMF tests. Its write timing on
a locked physical Dell remains untested because this XPS is already unlocked.
The existing EFI and OpenCore configuration are unchanged by this adaptation.

EDIT: 12/16/22
I got it to work til the installation screen. It kept crashing with only like 11 or 12 minutes remaining.
I gave up after a while
