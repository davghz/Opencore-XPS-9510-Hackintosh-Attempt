/* VM-only test fixture. NEVER deploy this file or Fixture.efi on the laptop ESP. */
#include <efi.h>
#include <efilib.h>
#include "expected.h"
static EFI_SYSTEM_TABLE *st;
static EFI_HANDLE dev,parent;
static EFI_FILE_HANDLE root;
static EFI_GUID cpu={0xb08f97ff,0xe6e8,0x4193,{0xa9,0x97,0x5e,0x9e,0x9b,0x0a,0xdb,0x32}};
static EFI_SET_VARIABLE real_set;
static UINTN writes;
static BOOLEAN deny;
static UINT8 sm[64], table[256];
static UINTN table_len;
static EFI_GUID sm3=SMBIOS3_TABLE_GUID;
static VOID quit(UINT32 code) {__asm__ volatile("outl %0,%1"::"a"(code),"Nd"((UINT16)0xf4));for(;;)__asm__ volatile("hlt");}
static VOID check(BOOLEAN good,CHAR16 *label) {
    Print(L"%s: %s\r\n",good?L"PASS":L"FAIL",label);
    if(!good)quit(2);
}
static EFI_STATUS EFIAPI tracked_set(CHAR16 *name,EFI_GUID *guid,UINT32 attrs,UINTN size,VOID *data) {
    /* CompareGuid return semantics differ across GNU-EFI versions. */
    if(!CompareMem(guid,&cpu,sizeof(cpu))&&!StrCmp(name,L"CpuSetup")) {
        ++writes;if(deny)return EFI_WRITE_PROTECTED;
    }
    return real_set(name,guid,attrs,size,data);
}
static VOID remove_file(CHAR16 *path) {
    EFI_FILE_HANDLE f=NULL;
    if(root->Open(root,&f,path,EFI_FILE_MODE_READ|EFI_FILE_MODE_WRITE,0)==EFI_SUCCESS)f->Delete(f);
}
static VOID arm(VOID) {
    EFI_FILE_HANDLE f=NULL;CHAR8 txt[]="DELL-XPS9510-1470-CFG43-ZERO-v1\n";UINTN n=sizeof(txt)-1;
    remove_file(L"\\EFI\\CFGUnlock\\early-cfg.arm");
    remove_file(L"\\EFI\\CFGUnlock\\early-cfg-result.txt");
    check(root->Open(root,&f,L"\\EFI\\CFGUnlock\\early-cfg.arm",EFI_FILE_MODE_READ|EFI_FILE_MODE_WRITE|EFI_FILE_MODE_CREATE,0)==EFI_SUCCESS,L"create arm file");
    check(f->Write(f,&n,txt)==EFI_SUCCESS&&n==sizeof(txt)-1,L"write arm token");
    check(f->Flush(f)==EFI_SUCCESS,L"flush arm token");f->Close(f);
}
static VOID run_driver(VOID) {
    EFI_HANDLE image=NULL;EFI_STATUS s;EFI_DEVICE_PATH *path=FileDevicePath(dev,L"\\EFI\\CFGUnlock\\EarlyCfg.efi");
    s=st->BootServices->LoadImage(FALSE,parent,path,NULL,0,&image);FreePool(path);
    check(s==EFI_SUCCESS,L"LoadImage real production driver");
    s=st->BootServices->StartImage(image,NULL,NULL);
    check(s==EFI_SUCCESS,L"driver returns normally");
}
static VOID seed(UINT32 attrs,BOOLEAN mutate) {
    UINT8 b[sizeof(expected_cpu)];
    real_set(L"CpuSetup",&cpu,0,0,NULL);
    CopyMem(b,(VOID*)expected_cpu,sizeof(b));if(mutate)b[0x44]^=1;
    check(real_set(L"CpuSetup",&cpu,attrs,sizeof(b),b)==EFI_SUCCESS,L"seed VM CpuSetup");
    writes=0;deny=FALSE;
}
static VOID verify(UINT8 cfg,UINTN count,BOOLEAN mutate) {
    UINT8 b[sizeof(expected_cpu)],want[sizeof(expected_cpu)];UINTN n=sizeof(b);UINT32 a=0;
    CopyMem(want,(VOID*)expected_cpu,sizeof(want));want[0x43]=cfg;if(mutate)want[0x44]^=1;
    check(st->RuntimeServices->GetVariable(L"CpuSetup",&cpu,&a,&n,b)==EFI_SUCCESS&&n==sizeof(b),L"readback variable");
    check(!CompareMem(b,want,sizeof(b)),L"all 654 bytes exactly as expected");
    check(writes==count,L"exact expected number of writes");
}
static VOID make_smbios(VOID) {
    UINTN i;UINT8 sum=0;UINT8 bios[9]={0,9,0,0,1,2,0,0,3};UINT8 board[6]={2,6,1,0,1,2};
    char bs[]="Dell Inc.\0" "1.47.0\0" "05/31/2026\0";char bd[]="Dell Inc.\0" "01V4T3\0";
    UINT8 system[6]={1,6,2,0,1,2};char sy[]="Dell Inc.\0" "XPS 15 9510\0";
    CopyMem(table,bios,sizeof(bios));table_len=sizeof(bios);
    CopyMem(table+table_len,bs,sizeof(bs));table_len+=sizeof(bs);
    CopyMem(table+table_len,board,sizeof(board));table_len+=sizeof(board);
    CopyMem(table+table_len,bd,sizeof(bd));table_len+=sizeof(bd);
    CopyMem(table+table_len,system,sizeof(system));table_len+=sizeof(system);
    CopyMem(table+table_len,sy,sizeof(sy));table_len+=sizeof(sy);
    SetMem(sm,sizeof(sm),0);CopyMem(sm,"_SM3_",5);sm[6]=24;sm[7]=3;
    CopyMem(sm+12,&table_len,4);UINT64 addr=(UINTN)table;CopyMem(sm+16,&addr,8);
    for(i=0;i<24;i++){sum+=sm[i];}
    sm[5]=(UINT8)(0-sum);
}
static VOID corrupt_identity(const char *text) {
    UINTN i,n=0;
    while(text[n])++n;
    for(i=0;i+n<=table_len;i++) {
        if(!CompareMem(table+i,(VOID*)text,n)) {table[i]^=1;return;}
    }
    check(FALSE,L"find identity field to corrupt");
}
EFI_STATUS efi_main(EFI_HANDLE image,EFI_SYSTEM_TABLE *system) {
    EFI_LOADED_IMAGE_PROTOCOL *loaded;EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *fs;
    EFI_GUID lg=EFI_LOADED_IMAGE_PROTOCOL_GUID,fg=EFI_SIMPLE_FILE_SYSTEM_PROTOCOL_GUID;
    EFI_CONFIGURATION_TABLE tables[2];EFI_CONFIGURATION_TABLE *saved;UINTN savedn;
    st=system;parent=image;InitializeLib(image,st);
    /* Hard guard against this synthetic-variable fixture running on physical hardware. */
    Print(L"Fixture firmware vendor: %s\r\n",st->FirmwareVendor);
    if(StrCmp(st->FirmwareVendor,L"EDK II") && StrCmp(st->FirmwareVendor,L"EDK II / OVMF") && StrCmp(st->FirmwareVendor,L"Ubuntu distribution of EDK II"))return EFI_UNSUPPORTED;
    check(st->BootServices->HandleProtocol(image,&lg,(VOID**)&loaded)==EFI_SUCCESS,L"loaded protocol");dev=loaded->DeviceHandle;
    check(st->BootServices->HandleProtocol(dev,&fg,(VOID**)&fs)==EFI_SUCCESS,L"filesystem protocol");
    check(fs->OpenVolume(fs,&root)==EFI_SUCCESS,L"open VM filesystem");
    make_smbios();tables[0].VendorGuid=sm3;tables[0].VendorTable=sm;
    saved=st->ConfigurationTable;savedn=st->NumberOfTableEntries;
    st->ConfigurationTable=tables;st->NumberOfTableEntries=1;
    real_set=st->RuntimeServices->SetVariable;st->RuntimeServices->SetVariable=tracked_set;
    seed(7,FALSE);arm();run_driver();verify(0,1,FALSE);
    Print(L"CASE success complete\r\n");
    writes=0;run_driver();verify(0,0,FALSE);Print(L"CASE one-shot complete\r\n");
    seed(7,FALSE);arm();deny=TRUE;run_driver();verify(1,1,FALSE);Print(L"CASE write-protected complete\r\n");
    seed(7,TRUE);arm();run_driver();verify(1,0,TRUE);Print(L"CASE baseline mismatch complete\r\n");
    seed(3,FALSE);arm();run_driver();verify(1,0,FALSE);Print(L"CASE attribute mismatch complete\r\n");
    /* A rearmed driver must not rewrite an already-disabled variable. */
    seed(7,FALSE);arm();run_driver();verify(0,1,FALSE);
    writes=0;arm();run_driver();verify(0,0,FALSE);Print(L"CASE already disabled complete\r\n");
    make_smbios();corrupt_identity("XPS 15 9510");seed(7,FALSE);arm();run_driver();verify(1,0,FALSE);Print(L"CASE wrong system complete\r\n");
    make_smbios();corrupt_identity("01V4T3");seed(7,FALSE);arm();run_driver();verify(1,0,FALSE);Print(L"CASE wrong board complete\r\n");
    make_smbios();corrupt_identity("1.47.0");seed(7,FALSE);arm();run_driver();verify(1,0,FALSE);Print(L"CASE wrong BIOS complete\r\n");
    make_smbios();corrupt_identity("05/31/2026");seed(7,FALSE);arm();run_driver();verify(1,0,FALSE);Print(L"CASE wrong BIOS date complete\r\n");
    make_smbios();
    seed(7,FALSE);arm();st->NumberOfTableEntries=0;run_driver();verify(1,0,FALSE);st->NumberOfTableEntries=1;Print(L"CASE identity mismatch complete\r\n");
    seed(7,FALSE);remove_file(L"\\EFI\\CFGUnlock\\early-cfg.arm");run_driver();verify(1,0,FALSE);Print(L"CASE unarmed complete\r\n");
    st->RuntimeServices->SetVariable=real_set;st->ConfigurationTable=saved;st->NumberOfTableEntries=savedn;
    Print(L"ALL VM CHECKS PASSED\r\n");quit(0);return EFI_SUCCESS;
}
