# XPS 9510 Tahoe recovery profile

This profile targets the original **Dell XPS 15 9510, BIOS 1.47.0**, with an
i7-11800H, Intel AX201 (`8086:43f0`), ELAN DLL0945 touchpad, and Realtek RTS5260
SD reader. The recovery image used for qualification was macOS **26.6.2,
build 25G83**, with Darwin **25.6.0**. The installer screen has been reached;
the subsequent Wi-Fi/input update still needs a hardware test. See the
[dated verification record](../verification/INSTALLER-9510-2026-11-01.md).

The root `BOOT/` and `OC/` directories belong to the 2022 attempt. The current
source of truth is [`tools/installer/`](../tools/installer/). Its config template
has empty identity fields and is not ready to boot until assembled.

## Build on this laptop in Linux

The builder requires x86_64 Linux, Python 3.12+, Clang 18, LLVM tools, ACPICA
`iasl`, and the cctools build prerequisites. On Ubuntu:

```sh
sudo apt install python3 clang-18 llvm build-essential autoconf automake libtool \
  pkg-config libxml2-dev libssl-dev uuid-dev zlib1g-dev libblocksruntime-dev acpica-tools
```

Run the following from the repository root. Only copying the firmware table
requires root; the build itself runs as your normal user. The private directory
is ignored by Git.

```sh
umask 077
mkdir -p .local/hardware
sudo cat /sys/firmware/acpi/tables/DSDT > .local/hardware/DSDT
python3 tools/installer/prepare.py --dsdt .local/hardware/DSDT
```

The builder checks the laptop model, BIOS, I2C controller IDs, and exact DSDT
hash before starting. It then verifies every downloaded archive against
[`downloads.json`](../tools/installer/downloads.json), builds the Apple linker
and three input kexts, compiles five SSDTs, generates a private MacBookPro16,2
identity, and runs OpenCore's matching `ocvalidate`. It checks binary types,
kext dependency order, and the absence of userspace destructor imports in the
rebuilt drivers.

Output is `.local/installer-build/EFI`. Logs and a SHA-256 manifest are next to
it. `INCOMPLETE.txt` remains if assembly fails; do not deploy an incomplete
output. Existing workspaces are never overwritten; use `--workspace` with a
new path for another build. Keep generated outputs outside version control.

Optional arguments:

| Argument | Purpose |
| --- | --- |
| `--cache PATH` | Reuse checked archives named by their `downloads.json` keys |
| `--iasl PATH` | Use a specific ACPICA compiler; original validation used 20230628 |
| `--linker PATH` | Reuse an ld64 built from the pinned cctools revision; skips rebuilding it |

The source revisions and settings are repeatable; generated identities, debug
paths, compiler versions, and linker UUIDs can change output hashes. Preserve
the existing identity when maintaining an already installed system. The builder
generates a new one for a new candidate and never reads a saved Wi-Fi password.

## Recovery media

The builder produces the EFI only. Obtain the recovery image directly from
Apple using the included upstream macrecovery utility:

```sh
python3 .local/installer-build/dependencies/opencore/Utilities/macrecovery/macrecovery.py \
  -b Mac-827FAC58A8FDFA22 -m 00000000000000000 \
  -o .local/installer-build/com.apple.recovery.boot download
```

Apple's recovery catalog can change. Confirm the downloaded image is Tahoe
(Darwin 25.x) before using this profile; it is not configured for arbitrary
macOS releases. The above command does not pin Apple's image to build 25G83.

The existing SD card has a 2 GiB FAT32 `XPSRECOVERY` partition and a separate
`MACOS-SD` target partition. Place the generated `EFI` and downloaded
`com.apple.recovery.boot` directories at the root of the FAT32 partition.
Preserve a copy of the working EFI first. The current card already has the
native-input candidate and an `EFI-before-native-input-20261101` backup.
To restore that backup, copy its contents back to the active `EFI` directory
from Linux; selecting a renamed backup directory is not a reliable alternate
boot path.

Both `EFI/BOOT/.contentVisibility` and `EFI/OC/.contentVisibility` must contain
`Disabled`. The builder copies these files from OpenCore. They hide the EFI
loader from its own picker, fixing the plain recovery entry that recursively
started OpenCore and stopped with **Already started**. Select the recovery
entry ending in **`(dmg)`**.

The preparation script never formats or mounts a disk, changes boot order,
writes firmware, or installs macOS. The intended installation target is the
SD card's separate `MACOS-SD` partition. Identify that partition by its device
and capacity in Disk Utility before preparing it for macOS; the internal
Ubuntu NVMe SSD is separate. Installing macOS remains a manual recovery step.

## Wi-Fi and input choices

Wi-Fi uses the Tahoe RELEASE build of
[laobamac/itlwm, alpha revision 7204c69](https://github.com/laobamac/itlwm/releases/tag/v2.4.0-alpha).
It is intended to expose the normal macOS Wi-Fi menu, without HeliPort or a
preconfigured network. It remains an added driver, not built-in Apple support
for the AX201. Join your network in the installer after confirming scanning
works. This build is experimental and the XPS adapter still needs validation.

The [pinned upstream README](https://github.com/laobamac/itlwm/blob/7204c69/README.md)
documents WPA2-Personal and WPA2/WPA3 transition mode with optional PMF.
WPA3-only, mandatory PMF, AWDL/AirDrop, and MLO are unsupported. Wi-Fi 6/HE
remains disabled by default. This profile leaves that default unchanged.
The new Wi-Fi and input entries are restricted to Darwin `25.0.0–25.99.99`.

The internal keyboard retains VoodooPS2Controller 2.3.7 and its keyboard plugin
with `ps2kbdonly=1`. The PS/2 mouse and trackpad plugins are removed. The Dell
touchpad instead uses VoodooI2C, VoodooI2CHID, and standalone VoodooInput.
The static XPS9510USB map is retained for the USB controllers. An external
USB keyboard/mouse is useful while qualifying the internal devices.

The touchpad controller personality matches `8086:43e9`, subsystem
`1028:0a61`, at `PciRoot(0x0)/Pci(0x15,0x1)`. Polling is selected explicitly.
Its 133 MHz clock and 42/171/208 ns SDA hold/SDA fall/SCL fall values follow
the `bxt_i2c_info` entry used for this PCI ID in
[Linux v6.17 intel-lpss-pci.c](https://github.com/torvalds/linux/blob/v6.17/drivers/mfd/intel-lpss-pci.c).

The DSDT patch renames only `_SB.PC00.I2C1.TPD0._CRS` to `XCRS`. It matches a
unique method prefix including `TPDM`, uses `Count=1` and `TableLength=399123`,
and changes one method-name byte at offset 396225. The required original DSDT
SHA-256 is:

```text
37ef7d9047ca7d36fcfcc311250dd75f4323e9cf62b8c12d1917baab2f46515a
```

`SSDT-I2C1-XPS` returns the firmware's I2C address/speed resources on Darwin,
without its interrupt resource, and calls the original `XCRS` on other systems.
The HID descriptor method is retained. A BIOS change requires re-inspecting
the tables; do not bypass the builder's DSDT check.

## Source provenance

[`build_input.py`](../tools/installer/build_input.py) adapts the input build
recipe and Tahoe SDK overlay from
[davghz/hackintosh at 2ac346e4](https://github.com/davghz/hackintosh/tree/2ac346e4c2ba7745e58c1ad049838b4b2227631b/tools/installer).
The Dell controller personality, ACPI patch, and polling resources are specific
to this laptop; HP controller IDs and HP firmware patches are not used.

The Voodoo implementation sources come from the full revisions pinned in
`downloads.json`. VoodooI2CServices and VoodooGPIO binaries come from the
official VoodooI2C 2.9.1 release. VoodooI2C, VoodooInput, and VoodooI2CHID are
rebuilt with Linux Clang 18 and cctools-port ld64 609. The latter two use a
private MacKernelSDK header overlay declaring the existing Tahoe
`willTerminate`, `didTerminate`, `configureReport`, and `updateReport`
overrides. No instance fields or new virtual slots are added.

Both `-fno-register-global-dtors-with-atexit` and LLVM's
`-disable-atexit-based-global-dtor-lowering` are required in this Linux build:
the kexts must use kernel initializer/terminator sections rather than import
userspace `__cxa_atexit` or `__dso_handle`. OpenCore still performs its normal
kernel vtable adjustments during injection; a simple undefined-symbol list
does not by itself establish a link failure.

OpenCore, Lilu, VirtualSMC, WhateverGreen, NVMeFix, VoodooPS2, and the SD reader
driver come from the upstream release archives listed in `downloads.json`.
Copied Voodoo metadata retains its upstream licensing; the GPLv3 and VoodooInput
license texts are alongside the templates. Downloaded dependencies retain
their own licenses. Apple recovery images, firmware dumps, generated EFI
identities, Wi-Fi credentials, and raw boot logs are not included in this source
update.

## Remaining hardware checks

Boot the SD's recovery entry, join Wi-Fi and confirm actual network traffic,
type with the internal keyboard, and test touchpad movement/clicking/scrolling.
Then test reboot and shutdown. Offline linking verifies compatibility with
the recorded kernel collection; it does not establish device operation,
sleep/wake reliability, or successful macOS installation. Graphics currently
uses basic display output with `-igfxvesa -wegnoegpu`; this profile does not
configure accelerated graphics.
