#!/usr/bin/env python3
"""Build pinned Voodoo input sources for the Dell's Tahoe installer on Linux.

Uses the Tahoe SDK declaration overlay described in docs/INSTALLER.md.
Only metadata and that SDK overlay differ from the pinned implementation sources.
"""
import argparse
from pathlib import Path
import concurrent.futures
import plistlib
import shutil
import struct
import subprocess

HERE = Path(__file__).resolve().parent
# Paths supplied by the builder; generated binaries stay outside tracked sources.

def source(name):
    children = [p for p in (DEPS / ('native-' + name)).iterdir() if p.is_dir()]
    assert len(children) == 1, name
    return children[0]

def main():
    OUT.mkdir(exist_ok=True)
    sdk, src, inp, hid, gpio, base = [source(n) for n in ['sdk', 'i2c', 'input', 'hid', 'gpio', 'i2c-hid-base']]
    for parent in [src, base]:
        shutil.copytree(gpio, parent / 'Dependencies/VoodooGPIO', dirs_exist_ok=True)
    hid_dest = base / 'VoodooI2C Satellites/VoodooI2CHID'
    shutil.copytree(hid, hid_dest, dirs_exist_ok=True)
    overlay = OUT / 'include/IOKit/hid'
    overlay.mkdir(parents=True, exist_ok=True)
    header = (sdk / 'Headers/IOKit/hid/IOHIDDevice.h').read_text()
    anchor = '    virtual void stop( IOService * provider ) APPLE_KEXT_OVERRIDE;'
    assert header.count(anchor) == 1
    header = header.replace(anchor, anchor + '''
    // Existing Tahoe overrides, without new virtual slots or instance data.
    virtual bool willTerminate(IOService *provider, IOOptionBits options) APPLE_KEXT_OVERRIDE;
    virtual bool didTerminate(IOService *provider, IOOptionBits options, bool *defer) APPLE_KEXT_OVERRIDE;
    virtual IOReturn configureReport(IOReportChannelList *channels, IOReportConfigureAction action, void *result, void *destination) APPLE_KEXT_OVERRIDE;
    virtual IOReturn updateReport(IOReportChannelList *channels, IOReportUpdateAction action, void *result, void *destination) APPLE_KEXT_OVERRIDE;
''')
    (overlay / 'IOHIDDevice.h').write_text(header)
    kexts = OUT / 'Kexts'
    if not (kexts / 'VoodooI2C.kext').exists():
        shutil.copytree(DEPS / 'i2c-release/VoodooI2C.kext', kexts / 'VoodooI2C.kext')
    for plugin in ['VoodooInput.kext']:
        shutil.rmtree(kexts / 'VoodooI2C.kext/Contents/PlugIns' / plugin, ignore_errors=True)
    units = list((src / 'VoodooI2C/VoodooI2C').rglob('*.cpp'))
    units += list((src / 'Multitouch Support').rglob('*.cpp'))
    units += [src / 'Dependencies/helpers.cpp', src / 'Dependencies/VoodooI2CACPIResourcesParser/VoodooI2CACPIResourcesParser.cpp']
    targets = [
        ('VoodooI2C', units, inp, False),
        ('VoodooInput', sorted((inp / 'VoodooInput').rglob('*.cpp')), inp / 'VoodooInput', True),
        ('VoodooI2CHID', sorted((hid_dest / 'VoodooI2CHID').rglob('*.cpp')), hid_dest / 'VoodooI2CHID', True),
    ]
    linker = LINKER
    assert linker.exists(), linker
    for name, units, includes, use_overlay in targets:
        print('Building', name, flush=True)
        work = OUT / name
        work.mkdir(exist_ok=True)
        bundle = kexts / (name + '.kext')
        (bundle / 'Contents/MacOS').mkdir(parents=True, exist_ok=True)
        info = plistlib.loads((HERE / 'templates' / (name + '.plist')).read_bytes())
        info.pop('HP8BDFBuild', None)
        info['XPS9510Build'] = 'Pinned upstream sources; Tahoe IOHIDDevice declarations; Dell 43e9/0a61 metadata; hardware test pending'
        if name == 'VoodooI2C':
            personalities = info['IOKitPersonalities']
            for key in list(personalities):
                if key.startswith('HP8BDF'):
                    del personalities[key]
            personalities['XPS9510TigerLakeTouchpadController'] = {
                'CFBundleIdentifier': 'com.alexandred.VoodooI2C',
                'IOClass': 'VoodooI2CPCIController', 'IOProviderClass': 'IOPCIDevice',
                'IOPCIPrimaryMatch': '0x43e98086', 'IOPCISecondaryMatch': '0x0a611028',
                'IOProbeScore': 9999, 'I2CClkRate': 133000000,
                'I2CSdaHoldTimeNs': 42, 'I2CSdaFallingTimeNs': 171, 'I2CSclFallingTimeNs': 208}
        (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        kmod = work / 'kmod.c'
        kmod.write_text('''#include <mach/mach_types.h>
extern kern_return_t _start(kmod_info_t *, void *);
extern kern_return_t _stop(kmod_info_t *, void *);
KMOD_EXPLICIT_DECL(%s, "%s", _start, _stop)
__private_extern__ kmod_start_func_t *_realmain = 0;
__private_extern__ kmod_stop_func_t *_antimain = 0;
__private_extern__ int _kext_apple_cc = __APPLE_CC__;
''' % (info['CFBundleIdentifier'], info['CFBundleVersion']))
        flags = ['-target', 'x86_64-apple-macos13', '-mkernel', '-nostdinc', '-fno-builtin',
                 '-fno-common', '-fno-stack-protector', '-mno-red-zone', '-mno-mmx', '-mno-sse',
                 '-mno-sse2', '-mno-avx', '-fno-vectorize', '-fno-slp-vectorize', '-DKERNEL',
                 '-DKERNEL_PRIVATE', '-DDRIVER_PRIVATE', '-DAPPLE', '-DNeXT', '-O2', '-g']
        if use_overlay:
            flags += ['-I', str(OUT / 'include')]
        flags += ['-isystem', str(sdk / 'Headers')]
        for directory in [includes, *sorted(p for p in includes.rglob('*') if p.is_dir())]:
            flags += ['-I', str(directory)]
        cxx = ['-std=gnu++14', '-nostdinc++', '-fno-exceptions', '-fno-rtti', '-fapple-kext',
               '-fno-register-global-dtors-with-atexit',
               '-mllvm', '-disable-atexit-based-global-dtor-lowering',
               '-Werror', '-Wno-deprecated-declarations', '-Wno-inconsistent-missing-override',
               '-Wno-unused-parameter', '-Wno-macro-redefined', '-Wno-non-c-typedef-for-linkage']
        def compile_one(item):
            index, unit = item
            obj = work / ('%03d.o' % index)
            args = ['clang-18' if unit.suffix == '.c' else 'clang++-18', *flags,
                    *([] if unit.suffix == '.c' else cxx), '-c', str(unit), '-o', str(obj)]
            result = subprocess.run(args, capture_output=True, text=True)
            (work / ('%03d.log' % index)).write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(str(unit) + '\n' + result.stderr[-4000:])
            return obj
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            objects = list(pool.map(compile_one, enumerate([kmod, *units])))
        binary = bundle / 'Contents/MacOS' / name
        args = [str(linker), '-arch', 'x86_64', '-kext', '-static', '-export_dynamic',
                '-macosx_version_min', '13.0', '-o', str(binary), *map(str, objects),
                str(sdk / 'Library/x86_64/libkmod.a')]
        result = subprocess.run(args, capture_output=True, text=True)
        (work / 'link.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr[-5000:]
        assert struct.unpack_from('<IIII', binary.read_bytes()) == (0xfeedfacf, 0x1000007, 3, 11), name
        print(name, 'linked as x86_64 MH_KEXT_BUNDLE', flush=True)
    # Bundles are injected by OpenCore. Remove signatures invalidated by rebuilding.
    for p in kexts.rglob('_CodeSignature'):
        shutil.rmtree(p)
    print('Built Dell input candidate. Runtime test still required.', flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deps', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--linker', type=Path, required=True)
    args = parser.parse_args()
    DEPS, OUT, LINKER = args.deps.resolve(), args.output.resolve(), args.linker.resolve()
    main()
