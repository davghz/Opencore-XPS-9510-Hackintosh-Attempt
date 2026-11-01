#!/usr/bin/env python3
"""Build the XPS 9510 BIOS 1.47.0 Tahoe EFI from pinned sources on Linux.

Run without sudo. Output contains a newly generated private Mac identity.
This prepares files only; it does not write disks, NVRAM, or firmware.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import secrets
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import urllib.request
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DSDT_SHA256 = '37ef7d9047ca7d36fcfcc311250dd75f4323e9cf62b8c12d1917baab2f46515a'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_hardware(dsdt, config):
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64',
            'Build on this XPS using x86_64 Linux.')
    for field, expected in [('product_name', 'XPS 15 9510'), ('bios_version', '1.47.0')]:
        actual = (Path('/sys/class/dmi/id') / field).read_text().strip()
        require(actual == expected, f'Unexpected {field}; expected {expected}.')
    require(digest(dsdt) == DSDT_SHA256, 'Unrecognized DSDT. Do not reuse this ACPI patch.')
    controller = Path('/sys/bus/pci/devices/0000:00:15.1')
    for field, expected in [('vendor', '0x8086'), ('device', '0x43e9'),
                            ('subsystem_vendor', '0x1028'), ('subsystem_device', '0x0a61')]:
        require((controller / field).read_text().strip() == expected,
                'I2C controller does not match this Dell profile.')
    original = dsdt.read_bytes()
    patches = [p for p in config['ACPI']['Patch'] if p['Enabled']]
    require(len(patches) == 1, 'Expected one scoped ACPI rename.')
    patch = patches[0]
    require(patch['TableSignature'] == b'DSDT' and patch['TableLength'] == len(original)
            and patch['Count'] == 1, 'ACPI patch scope changed.')
    require(original.count(patch['Find']) == 1 and original.index(patch['Find']) == 396222,
            'Touchpad method signature changed.')
    patched = original.replace(patch['Find'], patch['Replace'])
    require(len(patched) == len(original)
            and [i for i, (a, b) in enumerate(zip(original, patched)) if a != b] == [396225],
            'Expected only the TPD0 _CRS to XCRS rename.')


def fetch(name, pin, cache):
    archive = cache / name
    if not archive.exists():
        print('Downloading', name, flush=True)
        temporary = cache / (name + '.partial')
        request = urllib.request.Request(pin['url'], headers={'User-Agent': 'XPS9510-EFI-builder'})
        try:
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as out:
                shutil.copyfileobj(response, out)
            require(digest(temporary) == pin['sha256'], 'Download checksum mismatch: ' + name)
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    require(digest(archive) == pin['sha256'], 'Cache checksum mismatch: ' + name)
    return archive


def extract(archive, target):
    target.mkdir(parents=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                path = (target / member.filename).resolve()
                require(path.is_relative_to(target.resolve()), 'Archive path escapes destination.')
                mode = member.external_attr >> 16
                require(not stat.S_ISLNK(mode), 'Unexpected ZIP symlink.')
                if member.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(member) as inp, path.open('wb') as out:
                        shutil.copyfileobj(inp, out)
                    path.chmod(0o700 if mode & 0o111 else 0o600)
    else:
        with tarfile.open(archive) as source:
            source.extractall(target, filter='data')


def run(args, log, **kwargs):
    with log.open('w') as stream:
        result = subprocess.run(list(map(str, args)), stdout=stream, stderr=subprocess.STDOUT, **kwargs)
    require(result.returncode == 0, f'Command failed; inspect {log}')


def build_linker(deps, workspace):
    roots = list((deps / 'native-toolchain').glob('*/cctools'))
    require(len(roots) == 1, 'Unexpected cctools source layout.')
    root = roots[0]
    env = dict(os.environ, CC='clang-18', CXX='clang++-18')
    print('Building the pinned Apple linker; this takes a few minutes.', flush=True)
    if not (root / 'configure').exists():
        run(['./autogen.sh'], workspace / 'linker-autogen.log', cwd=root, env=env)
    run(['./configure', '--prefix=' + str(workspace / 'toolchain'),
         '--target=x86_64-apple-darwin', '--disable-lto-support', '--disable-clang-as',
         '--without-libtapi'], workspace / 'linker-configure.log', cwd=root, env=env)
    run(['make', '-j' + str(min(os.cpu_count() or 2, 8))], workspace / 'linker-build.log',
        cwd=root, env=env)
    linker = root / 'ld64/src/ld/ld'
    require(linker.is_file(), 'Linker build did not produce ld64.')
    return linker


def copy_kext(deps, key, name, destination):
    matches = [p for p in (deps / key).rglob(name + '.kext') if 'dSYM' not in str(p)]
    require(len(matches) == 1, 'Ambiguous kext: ' + name)
    shutil.copytree(matches[0], destination / (name + '.kext'))


def x86_kext_header(binary):
    data = binary.read_bytes()
    # Lilu and VirtualSMC ship universal bundles; inspect their x86_64 slice.
    if data[:4] == bytes.fromhex('cafebabe'):
        count = struct.unpack_from('>I', data, 4)[0]
        require(8 + count * 20 <= len(data), 'Truncated universal Mach-O header.')
        slices = [struct.unpack_from('>IIIII', data, 8 + i * 20) for i in range(count)]
        matches = [s for s in slices if s[0] == 0x1000007 and s[1] == 3]
        require(len(matches) == 1, 'Expected one generic x86_64 Mach-O slice.')
        _, _, offset, size, _ = matches[0]
        require(size >= 32 and offset + size <= len(data), 'Invalid Mach-O slice bounds.')
        data = data[offset:offset + size]
    require(len(data) >= 32, 'Truncated Mach-O binary.')
    return struct.unpack_from('<IIII', data)


def validate(efi, config):
    for section, directory in [('ACPI', 'ACPI'), ('UEFI', 'Drivers')]:
        entries = config[section]['Add' if section == 'ACPI' else 'Drivers']
        for entry in entries:
            if entry['Enabled']:
                require((efi / 'OC' / directory / entry['Path']).is_file(), 'Missing ' + entry['Path'])
    infos = []
    for entry in config['Kernel']['Add']:
        if not entry['Enabled']:
            continue
        bundle = efi / 'OC/Kexts' / entry['BundlePath']
        infos.append(plistlib.loads((bundle / entry['PlistPath']).read_bytes()))
        if entry['ExecutablePath']:
            binary = bundle / entry['ExecutablePath']
            require(x86_kext_header(binary) == (0xfeedfacf, 0x1000007, 3, 11),
                    'Expected x86_64 MH_KEXT_BUNDLE: ' + entry['BundlePath'])
            if entry['BundlePath'] in ['VoodooInput.kext', 'VoodooI2C.kext', 'VoodooI2CHID.kext']:
                symbols = subprocess.check_output(['llvm-nm', '--undefined-only', str(binary)], text=True)
                require('___cxa_atexit' not in symbols and '___dso_handle' not in symbols,
                        'Userspace destructor registration in ' + entry['BundlePath'])
    enabled = {info['CFBundleIdentifier'] for info in infos}
    seen = set()
    for info in infos:
        identifier = info['CFBundleIdentifier']
        require(identifier not in seen, 'Duplicate kext ID: ' + identifier)
        for dependency in info.get('OSBundleLibraries', {}):
            require(dependency not in enabled or dependency in seen, 'Kext dependency order: ' + identifier)
        seen.add(identifier)
    for directory in ['BOOT', 'OC']:
        require((efi / directory / '.contentVisibility').read_bytes() == b'Disabled',
                'Missing picker recursion fix.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsdt', type=Path, required=True, help='Private copy of this machine\'s DSDT')
    parser.add_argument('--workspace', type=Path, default=REPO / '.local/installer-build',
                        help='New output directory; existing directories are never overwritten')
    parser.add_argument('--cache', type=Path, help='Optional cache of pinned archives named by downloads.json key')
    parser.add_argument('--iasl', default='iasl', help='ACPICA compiler executable')
    parser.add_argument('--linker', type=Path, help='Optional existing ld64 built from the pinned cctools source')
    args = parser.parse_args()
    require(sys.version_info >= (3, 12), 'Python 3.12 or newer is required.')
    require(os.geteuid() != 0, 'Run without sudo; only reading the original DSDT needs root.')
    config = plistlib.loads((HERE / 'templates/config.plist').read_bytes())
    check_hardware(args.dsdt, config)
    iasl = shutil.which(args.iasl)
    require(iasl, 'Install acpica-tools or pass --iasl /path/to/iasl.')
    for command in ['clang-18', 'clang++-18', 'llvm-nm', 'make']:
        require(shutil.which(command), 'Missing build command: ' + command)
    workspace = args.workspace.resolve()
    require(not workspace.exists(), 'Workspace already exists. Choose a new --workspace.')
    os.umask(0o077)
    workspace.mkdir(parents=True, mode=0o700)
    incomplete = workspace / 'INCOMPLETE.txt'
    incomplete.write_text('Build has not passed validation. Do not deploy this EFI.\n')
    cache = args.cache.resolve() if args.cache else workspace / 'downloads'
    cache.mkdir(parents=True, exist_ok=True)
    deps = workspace / 'dependencies'
    pins = json.loads((HERE / 'downloads.json').read_text())
    for name, pin in pins.items():
        if name == 'native-toolchain' and args.linker:
            continue
        extract(fetch(name, pin, cache), deps / name)
    linker = args.linker.resolve() if args.linker else build_linker(deps, workspace)
    run([sys.executable, HERE / 'build_input.py', '--deps', deps, '--output', workspace / 'input',
         '--linker', linker], workspace / 'input-build.log')

    efi = workspace / 'EFI'
    for directory in ['BOOT', 'OC/ACPI', 'OC/Drivers', 'OC/Kexts']:
        (efi / directory).mkdir(parents=True)
    oc = deps / 'opencore'
    for relative in ['BOOT/BOOTx64.efi', 'BOOT/.contentVisibility', 'OC/OpenCore.efi',
                     'OC/.contentVisibility', 'OC/Drivers/OpenRuntime.efi', 'OC/Drivers/OpenHfsPlus.efi']:
        shutil.copy2(oc / 'X64/EFI' / relative, efi / relative)
    for source in sorted((HERE / 'acpi').glob('*.dsl')):
        run([iasl, '-p', efi / 'OC/ACPI' / source.stem, source], workspace / (source.stem + '.log'))
    kexts = efi / 'OC/Kexts'
    for key, name in [('lilu', 'Lilu'), ('virtualsmc', 'VirtualSMC'), ('whatevergreen', 'WhateverGreen'),
                      ('nvmefix', 'NVMeFix'), ('ps2', 'VoodooPS2Controller'),
                      ('realtekcardreader', 'RealtekCardReader'), ('native-airport-tahoe', 'AirportItlwm')]:
        copy_kext(deps, key, name, kexts)
    for name in ['VoodooPS2Mouse', 'VoodooPS2Trackpad', 'VoodooInput']:
        shutil.rmtree(kexts / 'VoodooPS2Controller.kext/Contents/PlugIns' / (name + '.kext'), ignore_errors=True)
    for name in ['VoodooInput', 'VoodooI2C', 'VoodooI2CHID']:
        shutil.copytree(workspace / 'input/Kexts' / (name + '.kext'), kexts / (name + '.kext'))
    usb = kexts / 'XPS9510USB.kext/Contents'
    usb.mkdir(parents=True)
    shutil.copy2(HERE / 'templates/XPS9510USB.plist', usb / 'Info.plist')

    serialtool = oc / 'Utilities/macserial/macserial.linux'
    serialtool.chmod(0o700)
    generated = subprocess.check_output([str(serialtool), '-m', 'MacBookPro16,2', '-n', '1'], text=True)
    match = re.search(r'\b([A-Z0-9]{12})\s*\|\s*([A-Z0-9]{17})\b', generated)
    require(match, 'Serial generation failed.')
    config['PlatformInfo']['Generic'].update(SystemSerialNumber=match[1], MLB=match[2],
        SystemUUID=str(uuid.uuid4()).upper(), ROM=b'\x02' + secrets.token_bytes(5))
    config_path = efi / 'OC/config.plist'
    config_path.write_bytes(plistlib.dumps(config))
    validate(efi, config)
    validator = oc / 'Utilities/ocvalidate/ocvalidate.linux'
    validator.chmod(0o700)
    run([validator, config_path], workspace / 'ocvalidate.log')
    manifest = {'profile': 'XPS9510-1.47.0-Tahoe-native-input', 'hardware_tested': False,
                'dsdt_sha256': DSDT_SHA256, 'downloads': pins,
                'linker_override': bool(args.linker), 'linker_sha256': digest(linker),
                'sha256': {str(p.relative_to(efi)): digest(p) for p in sorted(efi.rglob('*')) if p.is_file()}}
    (workspace / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    incomplete.unlink()
    print('EFI built and validated:', efi)
    print('Native Wi-Fi and touchpad still require a hardware test. Keep the generated identity private.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
