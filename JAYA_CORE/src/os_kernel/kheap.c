/* kheap.c - JAYA OS Primitive Kernel Heap Allocator */
typedef unsigned int u32;

// The placement address starts somewhere after the kernel.
// We'll declare a symbol from linker script if we could, but here
// we just assume a safe physical address after kernel data, e.g. 2MB.
static u32 placement_address = 0;

void init_kheap(u32 start_addr) {
    if (placement_address == 0) {
        placement_address = start_addr;
    }
}

// kmalloc using a simple bump allocator
u32 kmalloc(u32 size) {
    if (placement_address + size >= 0x400000) { // Bound to 4MB for now
        return 0; // Out of memory for primitive allocator
    }
    u32 tmp = placement_address;
    placement_address += size;
    return tmp;
}

// kfree is a no-op for a bump allocator
void kfree(u32 ptr) {
    // In a real heap we would mark the block free.
    // Here we just ignore it.
    (void)ptr;
}

// Optional aligned malloc
u32 kmalloc_a(u32 size, int align, u32 *phys) {
    if (align == 1 && (placement_address & 0xFFFFF000)) {
        // Align placement_address to 4KB page boundary
        placement_address &= 0xFFFFF000;
        placement_address += 0x1000;
    }

    if (phys) {
        *phys = placement_address;
    }

    u32 tmp = placement_address;
    placement_address += size;
    return tmp;
}
