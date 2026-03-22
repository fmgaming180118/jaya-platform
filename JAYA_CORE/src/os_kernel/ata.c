/* ata.c - JAYA OS ATA PIO Driver */
typedef unsigned short u16;
typedef unsigned char u8;
typedef unsigned int u32;

extern void outb(u16 port, u8 val);
extern u8 inb(u16 port);

static inline void insw(u16 port, void* addr, u32 count) {
    asm volatile("rep insw" : "+D"(addr), "+c"(count) : "d"(port) : "memory");
}

static inline void outsw(u16 port, const void* addr, u32 count) {
    asm volatile("rep outsw" : "+S"(addr), "+c"(count) : "d"(port) : "memory");
}

void ata_wait() {
    for (int i = 0; i < 4; i++) {
        inb(0x1F7);
    }
}

void ata_poll() {
    u8 status;
    ata_wait();
    do {
        status = inb(0x1F7);
    } while ((status & 0x80) && !(status & 0x08)); // Wait while BSY, until DRQ
}

void ata_read_sector(u32 lba, u8 *buffer) {
    outb(0x1F6, 0xE0 | ((lba >> 24) & 0x0F)); // Master drive, LBA mode
    outb(0x1F2, 1);                           // Sector count = 1
    outb(0x1F3, (u8)lba);                     // LBA low
    outb(0x1F4, (u8)(lba >> 8));              // LBA mid
    outb(0x1F5, (u8)(lba >> 16));             // LBA high
    outb(0x1F7, 0x20);                        // READ SECTORS command

    ata_poll();

    // Read 256 words (512 bytes)
    insw(0x1F0, buffer, 256);
}

void ata_write_sector(u32 lba, const u8 *buffer) {
    outb(0x1F6, 0xE0 | ((lba >> 24) & 0x0F)); // Master drive, LBA mode
    outb(0x1F2, 1);                           // Sector count = 1
    outb(0x1F3, (u8)lba);                     // LBA low
    outb(0x1F4, (u8)(lba >> 8));              // LBA mid
    outb(0x1F5, (u8)(lba >> 16));             // LBA high
    outb(0x1F7, 0x30);                        // WRITE SECTORS command

    ata_poll();

    // Write 256 words (512 bytes)
    outsw(0x1F0, buffer, 256);

    // Cache flush command
    outb(0x1F7, 0xE7);
    ata_poll();
}
