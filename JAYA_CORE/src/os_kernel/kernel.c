/* kernel.c - JAYA OS Microkernel Entry Point */
typedef unsigned int u32;

struct multiboot_info;

extern void init_idt();
extern void init_keyboard();
extern void init_paging(u32 fb_phys, u32 fb_size);
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

    // Extract VESA framebuffer info for identity-mapping
    u32 fb_phys = 0;
    u32 fb_size = 0;

    // Check if framebuffer info is available in multiboot info (flag bit 12)
    // Multiboot struct is partially defined in gui.c, we can deduce offsets or define a local struct here.
    // Instead of defining the whole struct, we just read from the pointer with known offsets or include a header.
    // But since there's no header, we can define the relevant parts of the struct here:

    // Alternatively, we define a small struct here:
    struct local_mbi {
        u32 flags;
        u32 mem_lower;
        u32 mem_upper;
        u32 boot_device;
        u32 cmdline;
        u32 mods_count;
        u32 mods_addr;
        u32 syms[4];
        u32 mmap_length;
        u32 mmap_addr;
        u32 drives_length;
        u32 drives_addr;
        u32 config_table;
        u32 boot_loader_name;
        u32 apm_table;
        u32 vbe_control_info;
        u32 vbe_mode_info;
        unsigned short vbe_mode;
        unsigned short vbe_interface_seg;
        unsigned short vbe_interface_off;
        unsigned short vbe_interface_len;
        unsigned long long framebuffer_addr;
        u32 framebuffer_pitch;
        u32 framebuffer_width;
        u32 framebuffer_height;
        unsigned char framebuffer_bpp;
        unsigned char framebuffer_type;
    } __attribute__((packed));

    struct local_mbi *lmbi = (struct local_mbi *)mbi;
    if (lmbi->flags & (1 << 12)) {
        fb_phys = (u32)lmbi->framebuffer_addr;
        fb_size = lmbi->framebuffer_pitch * lmbi->framebuffer_height;
    }

    init_paging(fb_phys, fb_size); // ENABLE PAGING WITH VESA HIGH-MEMORY IDENTITY-MAPPED!

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
