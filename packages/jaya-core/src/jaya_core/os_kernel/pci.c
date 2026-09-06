/* pci.c - JAYA OS PCI Bus Driver */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

extern u32 inl(u16 port);
extern void outl(u16 port, u32 val);

#define PCI_CONFIG_ADDRESS 0xCF8
#define PCI_CONFIG_DATA    0xCFC

u32 pci_config_read_dword(u8 bus, u8 slot, u8 func, u8 offset) {
    u32 address;
    u32 lbus  = (u32)bus;
    u32 lslot = (u32)slot;
    u32 lfunc = (u32)func;

    // Create configuration address
    address = (u32)((lbus << 16) | (lslot << 11) |
              (lfunc << 8) | (offset & 0xFC) | ((u32)0x80000000));

    // Write out the address
    outl(PCI_CONFIG_ADDRESS, address);

    // Read in the data
    return inl(PCI_CONFIG_DATA);
}

u16 pci_config_read_word(u8 bus, u8 slot, u8 func, u8 offset) {
    u32 dword = pci_config_read_dword(bus, slot, func, offset);
    return (u16)((dword >> ((offset & 2) * 8)) & 0xFFFF);
}

// Find VirtualBox RTL8139 Ethernet Card
// Vendor 0x10EC, Device 0x8139
int pci_find_rtl8139(u8 *out_bus, u8 *out_slot, u8 *out_func) {
    for (u16 bus = 0; bus < 256; bus++) {
        for (u8 slot = 0; slot < 32; slot++) {
            for (u8 func = 0; func < 8; func++) {
                u16 vendor = pci_config_read_word(bus, slot, func, 0);
                if (vendor == 0xFFFF) {
                    if (func == 0) break; // Device doesn't exist
                    continue;
                }
                u16 device = pci_config_read_word(bus, slot, func, 2);

                if (vendor == 0x10EC && device == 0x8139) {
                    *out_bus = bus;
                    *out_slot = slot;
                    *out_func = func;
                    return 1;
                }
            }
        }
    }
    return 0;
}
