/* gui.c - JAYA OS GUI & VESA Framebuffer Driver */
typedef unsigned int u32;
typedef unsigned char u8;
typedef unsigned short u16;

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
    // Video info fields introduced in multiboot version 1.6
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

static u32 *framebuffer = 0;
static u32 fb_width = 800;
static u32 fb_height = 600;
static u32 fb_pitch = 800 * 4;

extern void map_page(u32 physaddr, u32 virtualaddr, u32 flags);

void init_gui(struct multiboot_info *mbi) {
    if (mbi->flags & (1 << 12)) {
        framebuffer = (u32 *)(unsigned long)mbi->framebuffer_addr;
        fb_width = mbi->framebuffer_width;
        fb_height = mbi->framebuffer_height;
        fb_pitch = mbi->framebuffer_pitch;

        // Calculate total framebuffer size and align to pages
        u32 fb_size = fb_height * fb_pitch;
        u32 num_pages = (fb_size + 4095) / 4096;

        // Identity map the framebuffer to prevent paging collisions
        for (u32 i = 0; i < num_pages; i++) {
            u32 addr = (u32)framebuffer + (i * 4096);
            map_page(addr, addr, 3); // Map as Read/Write, Present
        }
    }
}

void put_pixel(int x, int y, u32 color) {
    if (x < 0 || (u32)x >= fb_width || y < 0 || (u32)y >= fb_height || !framebuffer) return;

    // Calculate offset in bytes: y * pitch + x * 4
    // But since framebuffer is u32 pointer, we divide pitch by 4
    u32 offset = (y * (fb_pitch / 4)) + x;
    framebuffer[offset] = color;
}

void draw_rect(int x, int y, int w, int h, u32 color) {
    for (int i = y; i < y + h; i++) {
        for (int j = x; j < x + w; j++) {
            put_pixel(j, i, color);
        }
    }
}

void draw_mouse_cursor(int x, int y) {
    // Simple 3x3 white square with black border
    u32 white = 0xFFFFFFFF;
    u32 black = 0x00000000;

    // Border
    draw_rect(x-1, y-1, 5, 5, black);
    // Inner
    draw_rect(x, y, 3, 3, white);
}
