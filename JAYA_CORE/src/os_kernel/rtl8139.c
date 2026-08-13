/* rtl8139.c - JAYA OS RTL8139 Network Driver */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

extern u32 inl(u16 port);
extern void outl(u16 port, u32 val);
extern u8 inb(u16 port);
extern void outb(u16 port, u8 val);
extern u32 pci_config_read_dword(u8 bus, u8 slot, u8 func, u8 offset);
extern u32 kmalloc(u32 size);

// We need a MAC buffer and an RX buffer
static u8 mac_addr[6];
static u32 io_base = 0;
static u8 *rx_buffer = 0;

void init_rtl8139(u8 bus, u8 slot, u8 func) {
    // 1. Get the I/O base address from PCI BAR0
    u32 bar0 = pci_config_read_dword(bus, slot, func, 0x10);
    io_base = bar0 & ~3; // Remove the lower bits (flags)

    // 2. Power on the device
    outb(io_base + 0x52, 0x00);

    // 3. Software reset
    outb(io_base + 0x37, 0x10);
    while((inb(io_base + 0x37) & 0x10) != 0) {
        // Wait for reset to complete
    }

    // 4. Allocate Receive Buffer (8192 + 16 bytes is recommended, we allocate 16KB for alignment)
    rx_buffer = (u8*)kmalloc(16384);

    // Set the Receive Buffer Start Address
    outl(io_base + 0x30, (u32)rx_buffer);

    // 5. Configure the Receive Configuration Register (RCR)
    // Accept Broadcast (0x08), Multicast (0x04), Physical Match (0x02), ALL Multicast (0x01)
    // And set the wrap bit (0x80)
    outl(io_base + 0x44, 0x0F | 0x80);

    // 6. Enable Receiver and Transmitter
    outb(io_base + 0x37, 0x0C);

    // Get MAC Address
    u32 mac1 = inl(io_base + 0x00);
    u16 mac2 = inl(io_base + 0x04) & 0xFFFF;
    mac_addr[0] = mac1 & 0xFF;
    mac_addr[1] = (mac1 >> 8) & 0xFF;
    mac_addr[2] = (mac1 >> 16) & 0xFF;
    mac_addr[3] = (mac1 >> 24) & 0xFF;
    mac_addr[4] = mac2 & 0xFF;
    mac_addr[5] = (mac2 >> 8) & 0xFF;
}

void rtl8139_send_packet(u8 *packet, u32 len) {
    // RTL8139 has 4 transmit descriptors (TSD0..3)
    // We just use TSD0 for simplicity in this primitive driver

    // Check if TX is available
    if ((inl(io_base + 0x10) & 0x2000) == 0) {
        // Transmitter is busy (bit 13 is OWN)
    }

    // Tell the card where the packet is
    outl(io_base + 0x20, (u32)packet);

    // Tell the card the size and trigger transmission
    outl(io_base + 0x10, len);
}
