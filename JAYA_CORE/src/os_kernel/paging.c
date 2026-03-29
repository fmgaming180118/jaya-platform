/* paging.c - JAYA OS Paging Implementation */
typedef unsigned int u32;

// Must be 4KB aligned!
u32 page_directory[1024] __attribute__((aligned(4096)));
u32 first_page_table[1024] __attribute__((aligned(4096)));

// Array of page tables for mapping the VESA framebuffer dynamically
// Max 10 page tables = 40MB of framebuffer, more than enough for 800x600x32 (approx 1.83MB)
u32 fb_page_tables[10][1024] __attribute__((aligned(4096)));

extern void load_page_directory(u32*);
extern void enable_paging();

void init_paging(u32 fb_phys, u32 fb_size) {
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

    // Identity-Map the VESA Framebuffer
    if (fb_phys != 0 && fb_size != 0) {
        u32 start_page = fb_phys / 4096;
        u32 end_page = (fb_phys + fb_size + 4095) / 4096;

        u32 current_page = start_page;
        u32 pt_index = 0;
        u32 last_pd_index = 0xFFFFFFFF; // Invalid initial value

        while (current_page < end_page && pt_index < 10) {
            u32 pd_index = current_page / 1024;
            u32 pt_offset = current_page % 1024;

            // If we crossed into a new page directory entry, link a new page table
            if (pd_index != last_pd_index) {
                if (last_pd_index != 0xFFFFFFFF) {
                    pt_index++;
                }
                if (pt_index >= 10) break; // Out of pre-allocated page tables

                page_directory[pd_index] = ((u32)fb_page_tables[pt_index]) | 3;
                last_pd_index = pd_index;
            }

            fb_page_tables[pt_index][pt_offset] = (current_page * 4096) | 3;
            current_page++;
        }
    }

    // 4. Load page directory into CR3 using inline assembly
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
