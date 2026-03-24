/* paging.c - JAYA OS Paging Implementation */
typedef unsigned int u32;

// Must be 4KB aligned!
u32 page_directory[1024] __attribute__((aligned(4096)));
u32 first_page_table[1024] __attribute__((aligned(4096)));

extern void load_page_directory(u32*);
extern void enable_paging();

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

extern u32 kmalloc_a(u32 size, int align, u32 *phys);

void map_page(u32 phys_addr, u32 virt_addr) {
    // Make sure addresses are page aligned
    phys_addr &= 0xFFFFF000;
    virt_addr &= 0xFFFFF000;

    u32 pd_idx = virt_addr >> 22;
    u32 pt_idx = (virt_addr >> 12) & 0x03FF;

    if (!(page_directory[pd_idx] & 1)) {
        // Page table not present, allocate one
        u32 pt_phys;
        u32 *new_pt = (u32*)kmalloc_a(4096, 1, &pt_phys);
        for (int i = 0; i < 1024; i++) {
            new_pt[i] = 0; // Not present
        }
        page_directory[pd_idx] = pt_phys | 3; // Present, R/W, Supervisor
    }

    u32 *pt = (u32*)(page_directory[pd_idx] & 0xFFFFF000);
    pt[pt_idx] = phys_addr | 3; // Present, R/W, Supervisor
}
