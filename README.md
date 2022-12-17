# Opencore-XPS-9510-Hackintosh

I haven't seen anyone try to put hackintosh on the 9510, so I thought I'd give it a try.

First thing first, CFG Lock has to go. I provided modGRUBShell.efi in /Tools, everything is good to go!
Type this is the shell when it boots up.

        setup_var_cv CpuSetup 0x43 0x01 0x00
CFG is now unlocked!

EDIT: 12/16/22
I got it to work til the installation screen. It kept crashing with only like 11 or 12 minutes remaining.
I gave up after a while
