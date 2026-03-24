/* kernel.c - JAYA OS Microkernel Entry Point */
typedef unsigned int u32;

struct multiboot_info;

extern void init_idt();
extern void init_keyboard();
extern void init_paging();
extern void init_gui(struct multiboot_info *mbi);
extern void vfs_init();
extern int pci_find_rtl8139(unsigned char *out_bus, unsigned char *out_slot, unsigned char *out_func);
extern void init_rtl8139(unsigned char bus, unsigned char slot, unsigned char func);

void kernel_main(u32 magic, struct multiboot_info* mbi) {
    if (magic != 0x2BADB002) {
        // Not booted by a Multiboot compliant bootloader
        return;
    }

    init_idt();
    init_keyboard();
    init_paging();

    // Initialize GUI from multiboot info
    init_gui(mbi);

    // Mount Vector FS
    vfs_init();

    // Visual Feedback: Gambar layar biru VESA dan Kursor Mouse statis!
    extern void draw_rect(int x, int y, int w, int h, u32 color);
    extern void draw_mouse_cursor(int x, int y);
    draw_rect(0, 0, 800, 600, 0x000000FF); // Layar Biru Muda
    draw_rect(100, 100, 200, 50, 0x00FFFFFF); // Kotak Putih
    draw_mouse_cursor(400, 300); // Kursor Mouse di tengah

    // Initialize networking
    unsigned char bus, slot, func;
    if (pci_find_rtl8139(&bus, &slot, &func)) {
        init_rtl8139(bus, slot, func);
    }

    // Kernel operational, loop forever
    while (1) {
        asm volatile("hlt");
    }
}
