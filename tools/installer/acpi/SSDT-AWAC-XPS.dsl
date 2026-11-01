// Dell DSDT: AWAC _STA returns zero when STAS=1; legacy RTC is present.
DefinitionBlock ("", "SSDT", 2, "DAVGHZ", "XPSAWAC", 1)
{
    External (STAS, FieldUnitObj)
    Scope (\_SB)
    {
        If (_OSI ("Darwin")) { STAS = One }
    }
}
