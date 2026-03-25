/* paging.c - JAYA OS Paging Implementation */
typedef unsigned int u32;

// Must be 4KB aligned!
u32 page_directory[1024] __attribute__((aligned(4096)));
u32 first_page_table[1024] __attribute__((aligned(4096)));
u32 fb_page_table1[1024] __attribute__((aligned(4096)));
u32 fb_page_table2[1024] __attribute__((aligned(4096)));

extern void load_page_directory(u32*);
extern void enable_paging();

void init_paging(u32 fb_phys_addr) {
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

    // 4. Identity map the VESA Framebuffer (up to 8MB to cover boundaries)
    if (fb_phys_addr != 0) {
        u32 fb_pd_index = fb_phys_addr >> 22; // 4MB chunk index
        u32 fb_pt_base = (fb_phys_addr >> 22) << 22; // Align down to 4MB boundary

        for(int i = 0; i < 1024; i++) {
            fb_page_table1[i] = (fb_pt_base + (i * 0x1000)) | 3;
            fb_page_table2[i] = (fb_pt_base + 0x400000 + (i * 0x1000)) | 3;
        }

        if (fb_pd_index != 0) {
            page_directory[fb_pd_index] = ((u32)fb_page_table1) | 3;
        }
        if (fb_pd_index + 1 < 1024 && (fb_pd_index + 1) != 0) {
            page_directory[fb_pd_index + 1] = ((u32)fb_page_table2) | 3;
        }
    }

    // 5. Load page directory into CR3 using inline assembly
    asm volatile(
        "mov %0, %%eax\n\t"
        "mov %%eax, %%cr3\n\t"
        : : "r" (page_directory) : "eax"
    );

    // 6. Enable paging by setting the PG bit in CR0
    asm volatile(
        "mov %%cr0, %%eax\n\t"
        "or $0x80000000, %%eax\n\t"
        "mov %%eax, %%cr0\n\t"
        : : : "eax"
    );
}
