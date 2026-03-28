/* paging.c - JAYA OS Paging Implementation */
typedef unsigned int u32;

// Must be 4KB aligned!
u32 page_directory[1024] __attribute__((aligned(4096)));
u32 first_page_table[1024] __attribute__((aligned(4096)));

extern void load_page_directory(u32*);
extern void enable_paging();

extern u32 get_framebuffer_addr();
extern u32 get_framebuffer_size();
extern u32 kmalloc_a(u32 size, int align, u32 *phys);

void init_paging() {
    // 1. Initialize page directory
    for(int i = 0; i < 1024; i++) {
        // Attribute: supervisor level, read/write, not present.
        page_directory[i] = 0x00000002;
    }

    // 2. Map the first 4MB of RAM (1024 pages * 4KB = 4MB)
    for(unsigned int i = 0; i < 1024; i++) {
        // Physical address: i * 0x1000
        // Attribute: supervisor level, read/write, present.
        first_page_table[i] = (i * 0x1000) | 3;
    }

    // 3. Put that page table in the Page Directory
    // Attribute: supervisor level, read/write, present
    page_directory[0] = ((u32)first_page_table) | 3;

    // 4. Map the VESA Framebuffer
    u32 fb_addr = get_framebuffer_addr();
    u32 fb_size = get_framebuffer_size();
    if (fb_addr) {
        u32 num_pages = (fb_size + 4095) / 4096;
        for (u32 i = 0; i < num_pages; i++) {
            u32 phys_addr = fb_addr + (i * 4096);
            u32 pd_index = phys_addr >> 22;
            u32 pt_index = (phys_addr >> 12) & 0x03FF;

            u32 *pt = 0;
            if (page_directory[pd_index] & 1) {
                pt = (u32 *)(page_directory[pd_index] & ~0xFFF);
            } else {
                pt = (u32 *)kmalloc_a(4096, 1, 0);
                for (int j = 0; j < 1024; j++) pt[j] = 0;
                page_directory[pd_index] = ((u32)pt) | 3;
            }
            pt[pt_index] = phys_addr | 3; // Present, R/W, Supervisor
        }
    }

    // 5. Load page directory into CR3 using inline assembly
    asm volatile(
        "mov %0, %%eax\n\t"
        "mov %%eax, %%cr3\n\t"
        : : "r" (page_directory) : "eax"
    );

    // 5. Enable paging by setting the PG bit in CR0
    asm volatile(
        "mov %%cr0, %%eax\n\t"
        "or $0x80000000, %%eax\n\t"
        "mov %%eax, %%cr0\n\t"
        : : : "eax"
    );
}
