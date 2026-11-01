// Dell XPS 9510 BIOS 1.47.0. Requires TPD0-local _CRS -> XCRS rename.
// Retain firmware address/speed and HID descriptor methods, using polling on Darwin.
DefinitionBlock ("", "SSDT", 2, "DAVGZ", "XPSI2CP", 0x00000001)
{
    External (\_SB.PC00.I2C1, DeviceObj)
    External (\_SB.PC00.I2C1.TPD0, DeviceObj)
    External (\_SB.PC00.I2C1.TPD0.XCRS, MethodObj)
    External (\_SB.PC00.I2CM, MethodObj)
    External (\_SB.PC00.I2C1.I2CX, IntObj)
    External (\_SB.PC00.I2C1.TPD0.BADR, FieldUnitObj)
    External (\_SB.PC00.I2C1.TPD0.SPED, FieldUnitObj)

    Scope (\_SB.PC00.I2C1.TPD0)
    {
        Method (_CRS, 0, Serialized)
        {
            If (_OSI ("Darwin"))
            {
                Return (\_SB.PC00.I2CM (\_SB.PC00.I2C1.I2CX, BADR, SPED))
            }
            Return (XCRS ())
        }
    }
}
