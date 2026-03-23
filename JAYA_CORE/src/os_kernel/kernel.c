/* kernel.c - JAYA OS Microkernel Entry Point */
typedef unsigned int u32;

typedef unsigned short u16;
typedef unsigned char u8;

struct multiboot_info {
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
    u16 vbe_mode;
    u16 vbe_interface_seg;
    u16 vbe_interface_off;
    u16 vbe_interface_len;
    unsigned long long framebuffer_addr;
    u32 framebuffer_pitch;
    u32 framebuffer_width;
    u32 framebuffer_height;
    u8 framebuffer_bpp;
    u8 framebuffer_type;
    union {
        struct {
            u32 framebuffer_palette_addr;
            u16 framebuffer_palette_num_colors;
        };
        struct {
            u8 framebuffer_red_field_position;
            u8 framebuffer_red_mask_size;
            u8 framebuffer_green_field_position;
            u8 framebuffer_green_mask_size;
            u8 framebuffer_blue_field_position;
            u8 framebuffer_blue_mask_size;
        };
    };
} __attribute__((packed));

extern void init_idt();
extern void init_keyboard();
extern void init_paging(u32 fb_phys_addr);
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

    u32 fb_addr = 0;
    if (mbi->flags & (1 << 12)) {
        fb_addr = (u32)(mbi->framebuffer_addr & 0xFFFFFFFF);
    }
    init_paging(fb_addr);

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
