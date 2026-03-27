/* paging.c - JAYA OS Paging Implementation */
typedef unsigned int u32;

// Must be 4KB aligned!
u32 page_directory[1024] __attribute__((aligned(4096)));
u32 first_page_table[1024] __attribute__((aligned(4096)));

extern void load_page_directory(u32*);
extern void enable_paging();
extern u32 kmalloc_a(u32 size, int align, u32 *phys);

void map_page(u32 physaddr, u32 virtualaddr, u32 flags) {
    // Make sure that both addresses are page-aligned.
    physaddr &= 0xFFFFF000;
    virtualaddr &= 0xFFFFF000;

    u32 pdindex = virtualaddr >> 22;
    u32 ptindex = (virtualaddr >> 12) & 0x03FF;

    // Check if the page table exists in the directory
    if (!(page_directory[pdindex] & 1)) {
        // Allocate a new page table
        u32 *new_pt;
        u32 phys;
        new_pt = (u32 *)kmalloc_a(4096, 1, &phys);

        // Clear the new page table
        for(int i = 0; i < 1024; i++) {
            new_pt[i] = 0;
        }

        // Set the page table into the page directory
        page_directory[pdindex] = phys | 3; // Present, Read/Write
    }

    // Get the page table pointer from the page directory
    u32 *pt = (u32 *)(page_directory[pdindex] & 0xFFFFF000);
    pt[ptindex] = physaddr | flags;
}

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
