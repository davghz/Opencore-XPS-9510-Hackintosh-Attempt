/* Dell XPS 9510 1.47.0: one-shot, early-boot CFG setting attempt.
 * Changes only CpuSetup data byte 0x43, using standard SetVariable.
 * No firmware-code patches, MMIO, MSR writes, or flash-controller access.
 * Does not reboot. Returns to the firmware boot manager on every path.
 */
#include <efi.h>
#include <efilib.h>
#include "expected.h"

#define CFG_OFFSET 0x43
_Static_assert(sizeof(expected_cpu) == 654, "Wrong Dell CpuSetup baseline size");
#define ARM_PATH L"\\EFI\\CFGUnlock\\early-cfg.arm"
#define LOG_PATH L"\\EFI\\CFGUnlock\\early-cfg-result.txt"
static const char arm_text[] = "DELL-XPS9510-1470-CFG43-ZERO-v1\n";
static EFI_GUID cpu_guid = {0xb08f97ff,0xe6e8,0x4193,{0xa9,0x97,0x5e,0x9e,0x9b,0x0a,0xdb,0x32}};
static EFI_SYSTEM_TABLE *sys;
static EFI_FILE_HANDLE log_file;
static BOOLEAN log_ok;

static UINTN alen(const char *s) { UINTN n=0; while(s[n]) ++n; return n; }
static BOOLEAN equal(const VOID *a,const VOID *b,UINTN n) {
    const UINT8 *x=a,*y=b; UINTN i;
    for(i=0;i<n;i++) if(x[i]!=y[i]) return FALSE;
    return TRUE;
}
static VOID log_line(const char *s) {
    UINTN n=alen(s),want=n;
    if(log_file) {
        if(log_file->Write(log_file,&n,(VOID*)s)!=EFI_SUCCESS || n!=want)log_ok=FALSE;
        if(log_file->Flush(log_file)!=EFI_SUCCESS)log_ok=FALSE;
    } else log_ok=FALSE;
}
static VOID log_status(const char *label,EFI_STATUS status) {
    char buf[128]; const char *hex="0123456789ABCDEF"; UINTN i,n=alen(label);
    if(n>100) n=100;
    for(i=0;i<n;i++) buf[i]=label[i];
    buf[n++]='0';buf[n++]='x';
    for(i=0;i<16;i++) buf[n++]=hex[(status>>((15-i)*4))&15];
    buf[n++]='\n';buf[n]=0;log_line(buf);
}
static UINT32 u32(const UINT8 *p) {
    return (UINT32)p[0]|((UINT32)p[1]<<8)|((UINT32)p[2]<<16)|((UINT32)p[3]<<24);
}
static UINT64 u64(const UINT8 *p) { return u32(p)|((UINT64)u32(p+4)<<32); }
static BOOLEAN checksum(const UINT8 *p,UINTN n) {
    UINT8 sum=0;UINTN i;for(i=0;i<n;i++)sum+=p[i];return sum==0;
}
static BOOLEAN smbios_string(const UINT8 *strings,const UINT8 *end,UINT8 idx,const char *want) {
    UINT8 i=1;const UINT8 *p=strings,*q;UINTN n=alen(want);
    if(!idx)return FALSE;
    while(p<end && *p) {
        q=p;while(q<end && *q)++q;
        if(q>=end)return FALSE;
        if(i==idx)return (UINTN)(q-p)==n && equal(p,want,n);
        p=q+1;++i;
    }
    return FALSE;
}
static BOOLEAN check_smbios_table(const UINT8 *p,UINTN size) {
    const UINT8 *end=p+size,*q,*strings;
    BOOLEAN bios=FALSE,board=FALSE,system=FALSE;UINTN records=0;
    if(!size || size>1024*1024 || end<p)return FALSE;
    while(p+4<=end && records++<4096) {
        if(p[1]<4 || (UINTN)(end-p)<(UINTN)p[1]+2)return FALSE;
        strings=p+p[1];q=strings;
        while(q+1<end && (q[0]||q[1]))++q;
        if(q+1>=end)return FALSE;
        if(p[0]==0 && p[1]>8)
            bios=smbios_string(strings,q+1,p[5],"1.47.0") &&
                 smbios_string(strings,q+1,p[8],"05/31/2026");
        if(p[0]==1 && p[1]>5)
            system=smbios_string(strings,q+1,p[4],"Dell Inc.") &&
                   smbios_string(strings,q+1,p[5],"XPS 15 9510");
        if(p[0]==2 && p[1]>5)
            board=smbios_string(strings,q+1,p[4],"Dell Inc.") &&
                  smbios_string(strings,q+1,p[5],"01V4T3");
        if(bios&&board&&system)return TRUE;
        if(p[0]==127)break;
        p=q+2;
    }
    return FALSE;
}
static BOOLEAN correct_machine(VOID) {
    UINTN i;UINT8 *p;UINT64 addr;UINT32 len;
    EFI_GUID g3=SMBIOS3_TABLE_GUID,g2=SMBIOS_TABLE_GUID;
    for(i=0;i<sys->NumberOfTableEntries;i++) {
        EFI_CONFIGURATION_TABLE *c=&sys->ConfigurationTable[i];
        p=c->VendorTable;if(!p)continue;
        if(equal(&c->VendorGuid,&g3,sizeof(g3))) {
            if(!equal(p,"_SM3_",5)||p[6]<24||p[6]>64||!checksum(p,p[6]))continue;
            len=u32(p+12);addr=u64(p+16);
        } else if(equal(&c->VendorGuid,&g2,sizeof(g2))) {
            if(!equal(p,"_SM_",4)||p[5]<31||p[5]>64||!checksum(p,p[5]))continue;
            len=p[22]|((UINT32)p[23]<<8);addr=u32(p+24);
        } else continue;
        if(addr && check_smbios_table((UINT8*)(UINTN)addr,len))return TRUE;
    }
    return FALSE;
}

EFI_STATUS efi_main(EFI_HANDLE image,EFI_SYSTEM_TABLE *system) {
    EFI_LOADED_IMAGE_PROTOCOL *loaded=NULL;
    EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *fs=NULL;
    EFI_FILE_HANDLE root=NULL,arm=NULL,probe=NULL;
    EFI_GUID loaded_guid=EFI_LOADED_IMAGE_PROTOCOL_GUID;
    EFI_GUID fs_guid=EFI_SIMPLE_FILE_SYSTEM_PROTOCOL_GUID;
    EFI_STATUS status;UINTN n;UINT32 attrs;
    UINT8 before[sizeof(expected_cpu)],after[sizeof(expected_cpu)],arm_buf[sizeof(arm_text)];
    sys=system;log_file=NULL;log_ok=TRUE;
    status=sys->BootServices->HandleProtocol(image,&loaded_guid,(VOID**)&loaded);
    if(EFI_ERROR(status)||!loaded)return EFI_SUCCESS;
    status=sys->BootServices->HandleProtocol(loaded->DeviceHandle,&fs_guid,(VOID**)&fs);
    if(EFI_ERROR(status)||!fs)return EFI_SUCCESS;
    status=fs->OpenVolume(fs,&root);
    if(EFI_ERROR(status)||!root)return EFI_SUCCESS;
    status=root->Open(root,&arm,ARM_PATH,EFI_FILE_MODE_READ|EFI_FILE_MODE_WRITE,0);
    if(EFI_ERROR(status)||!arm)goto done; /* Unarmed: no persistent action. */
    n=sizeof(arm_buf);status=arm->Read(arm,&n,arm_buf);
    if(EFI_ERROR(status)||n!=sizeof(arm_text)-1||!equal(arm_buf,arm_text,n))goto done;
    /* Consume the one-shot token before attempting any variable write. */
    status=arm->Delete(arm);arm=NULL;
    if(status!=EFI_SUCCESS)goto done; /* Includes EFI_WARN_DELETE_FAILURE. */
    status=root->Flush(root);if(status!=EFI_SUCCESS)goto done;
    status=root->Open(root,&probe,ARM_PATH,EFI_FILE_MODE_READ,0);
    if(status!=EFI_NOT_FOUND) {if(probe)probe->Close(probe);goto done;}
    /* Installer requires the result file to be absent. Preserve any earlier result. */
    status=root->Open(root,&probe,LOG_PATH,EFI_FILE_MODE_READ,0);
    if(status!=EFI_NOT_FOUND) {if(probe)probe->Close(probe);goto done;}
    status=root->Open(root,&log_file,LOG_PATH,EFI_FILE_MODE_READ|EFI_FILE_MODE_WRITE|EFI_FILE_MODE_CREATE,0);
    if(EFI_ERROR(status)||!log_file)goto done;
    log_line("Dell XPS 9510 1.47.0 early CFG attempt v1\nOne-shot token consumed.\n");
    if(!correct_machine()) {log_line("ABORT: SMBIOS board/BIOS/date mismatch.\n");goto done;}
    log_line("Machine identity verified.\n");
    n=sizeof(before);attrs=0;
    status=sys->RuntimeServices->GetVariable(L"CpuSetup",&cpu_guid,&attrs,&n,before);
    log_status("GetVariable status=",status);
    if(EFI_ERROR(status)||n!=sizeof(expected_cpu)||attrs!=7) {
        log_line("ABORT: variable read/size/attributes mismatch.\n");goto done;
    }
    if(!equal(before,expected_cpu,sizeof(before))) {
        log_line("ABORT: CpuSetup differs from captured baseline.\n");goto done;
    }
    if(before[CFG_OFFSET]!=1) {log_line("ABORT: unexpected CFG byte.\n");goto done;}
    log_line("Exact baseline verified; requesting ONLY offset 0x43: 1 -> 0.\n");
    /* Require the pre-write log to be durable before modifying NVRAM. */
    status=log_file->Flush(log_file);
    if(status!=EFI_SUCCESS || !log_ok)goto done;
    before[CFG_OFFSET]=0;
    status=sys->RuntimeServices->SetVariable(L"CpuSetup",&cpu_guid,attrs,sizeof(before),before);
    log_status("SetVariable status=",status);
    n=sizeof(after);attrs=0;
    status=sys->RuntimeServices->GetVariable(L"CpuSetup",&cpu_guid,&attrs,&n,after);
    log_status("Readback status=",status);
    if(!EFI_ERROR(status)&&n==sizeof(after)&&attrs==7&&equal(after,before,n))
        log_line("READBACK EXACT: CFG byte is 0; every other byte preserved.\nA subsequent reboot and MSR 0xE2 bit15 check are required to confirm hardware unlock.\n");
    else if(!EFI_ERROR(status)&&n==sizeof(after)&&attrs==7&&equal(after,expected_cpu,n))
        log_line("UNCHANGED: CFG remains 1. This method did not unlock it.\n");
    else log_line("READBACK MISMATCH: stop and inspect; no retry performed.\n");
done:
    if(arm)arm->Close(arm);
    if(log_file)log_file->Close(log_file);
    if(root)root->Close(root);
    return EFI_SUCCESS;
}
