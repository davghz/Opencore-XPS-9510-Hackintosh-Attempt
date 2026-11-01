// XPS 9510 BIOS 1.47.0 exposes native Processor objects at _SB.PR00.
DefinitionBlock ("", "SSDT", 2, "DAVGHZ", "XPSPLUG", 1)
{
    External (_SB_.PR00, ProcessorObj)
    Scope (\_SB.PR00)
    {
        Method (_DSM, 4, NotSerialized)
        {
            If (!Arg2) { Return (Buffer (One) { 0x03 }) }
            If (_OSI ("Darwin")) { Return (Package () { "plugin-type", One }) }
            Return (Buffer (One) { Zero })
        }
    }
}
