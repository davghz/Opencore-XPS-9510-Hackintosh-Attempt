// Leave the real ECDV controller and its Dell methods intact.
DefinitionBlock ("", "SSDT", 2, "DAVGHZ", "XPSEC", 1)
{
    External (_SB_.PC00.LPCB, DeviceObj)
    Scope (\_SB.PC00.LPCB)
    {
        Device (EC)
        {
            Name (_HID, "ACID0001")
            Method (_STA, 0, NotSerialized)
            {
                If (_OSI ("Darwin")) { Return (0x0F) }
                Return (Zero)
            }
        }
    }
}
