# Opencore-XPS-9510-Hackintosh

Dell XPS 15 9510 experiments, with a current Linux build recipe for the
**BIOS 1.47.0 / macOS Tahoe recovery installer**.

## Installer status — 2026-11-01

The SD-card recovery installer reached the macOS installation screen on this
XPS. A subsequent native-menu Wi-Fi and I2C touchpad update has been built,
validated offline, and copied to the SD card. **Wi-Fi, keyboard typing, and
touchpad operation with that update still need confirmation on hardware.**
A completed macOS installation has not yet been verified.

| Component | Current profile |
| --- | --- |
| OpenCore | 1.0.8 DEBUG; recovery picker recursion fixed |
| Intel AX201 Wi-Fi | Tahoe AirportItlwm alpha; native macOS Wi-Fi menu; hardware test pending |
| Internal keyboard | VoodooPS2Controller + keyboard plugin, `ps2kbdonly=1` |
| ELAN DLL0945 touchpad | Rebuilt VoodooI2C/Input/HID; Dell I2C1 match and polling ACPI patch; hardware test pending |
| SD reader | RealtekCardReader 0.9.7; conservative 3.3 V/SDR operation |
| Graphics | Basic display with `-igfxvesa`; NVIDIA disabled for macOS; acceleration not configured |

Start with the [installer build guide](docs/INSTALLER.md) and
[verification record](verification/INSTALLER-9510-2026-11-01.md).
The public source is under [`tools/installer/`](tools/installer/); downloaded
drivers, generated identities, recovery images, and local backups stay in the
ignored `.local/` directory. The builder prepares files without partitioning a
disk or changing firmware.

**The root `BOOT/` and `OC/` directories are the historical 2022 attempt.**
They are retained for reference; use the current build recipe for this profile.

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
The CFG tool is separate from the installer profile above.

## Original attempt — 2022-12-16

The original EFI reached the installation screen but repeatedly crashed with
roughly 11–12 minutes remaining. That attempt was abandoned; it was not a
confirmed installation.
