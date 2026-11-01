EFI_PREFIX ?= /usr
CFLAGS = -I$(EFI_PREFIX)/include/efi -I$(EFI_PREFIX)/include/efi/x86_64 -DGNU_EFI_USE_MS_ABI -fpic -ffreestanding -fshort-wchar -fno-stack-protector -fno-stack-check -mno-red-zone -fno-strict-aliasing -fno-asynchronous-unwind-tables -Wall -Wextra -Werror -O2
LDFLAGS = -nostdlib -zdefs -znocombreloc -T $(EFI_PREFIX)/lib/elf_x86_64_efi.lds -shared -Bsymbolic $(EFI_PREFIX)/lib/crt0-efi-x86_64.o -L$(EFI_PREFIX)/lib
SECTIONS = -j .rodata -j .text -j .sdata -j .data -j .dynamic -j .dynsym -j .rel -j .rela -j .reloc

all: EarlyCfg.efi
early_cfg.o: early_cfg.c expected.h
fixture.o: fixture.c expected.h

EarlyCfg.so: early_cfg.o
	ld $(LDFLAGS) $< -lefi -lgnuefi -o $@
EarlyCfg.efi: EarlyCfg.so
	objcopy $(SECTIONS) -O efi-bsdrv-x86_64 $< $@

fixture.so: fixture.o
	ld $(LDFLAGS) $< -lefi -lgnuefi -o $@
Fixture.efi: fixture.so
	objcopy $(SECTIONS) -O efi-app-x86_64 $< $@

clean:
	rm -f *.o *.so EarlyCfg.efi Fixture.efi
