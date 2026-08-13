/* idt.c - JAYA OS Interrupt Descriptor Tables */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

extern void outb(u16 port, u8 val);
extern u8 inb(u16 port);
extern void outl(u16 port, u32 val);
extern u32 inl(u16 port);

struct idt_entry_struct {
    u16 base_lo;
    u16 sel;
    u8 always0;
    u8 flags;
    u16 base_hi;
} __attribute__((packed));

struct idt_ptr_struct {
    u16 limit;
    u32 base;
} __attribute__((packed));

struct registers {
    u32 ds;
    u32 edi, esi, ebp, esp, ebx, edx, ecx, eax;
    u32 int_no, err_code;
    u32 eip, cs, eflags, useresp, ss;
};

struct idt_entry_struct idt_entries[256];
struct idt_ptr_struct   idt_ptr;

extern void isr0(); extern void isr1(); extern void isr2(); extern void isr3();
extern void isr4(); extern void isr5(); extern void isr6(); extern void isr7();
extern void isr8(); extern void isr9(); extern void isr10(); extern void isr11();
extern void isr12(); extern void isr13(); extern void isr14(); extern void isr15();
extern void isr16(); extern void isr17(); extern void isr18(); extern void isr19();
extern void isr20(); extern void isr21(); extern void isr22(); extern void isr23();
extern void isr24(); extern void isr25(); extern void isr26(); extern void isr27();
extern void isr28(); extern void isr29(); extern void isr30(); extern void isr31();

extern void irq0(); extern void irq1(); extern void irq2(); extern void irq3();
extern void irq4(); extern void irq5(); extern void irq6(); extern void irq7();
extern void irq8(); extern void irq9(); extern void irq10(); extern void irq11();
extern void irq12(); extern void irq13(); extern void irq14(); extern void irq15();

void init_idt_desc(u8 num, u32 base, u16 sel, u8 flags) {
    idt_entries[num].base_lo = base & 0xFFFF;
    idt_entries[num].base_hi = (base >> 16) & 0xFFFF;
    idt_entries[num].sel     = sel;
    idt_entries[num].always0 = 0;
    idt_entries[num].flags   = flags /* | 0x60 */;
}

void isr_handler(struct registers *regs) {
    (void)regs;
    // Basic exception handler
}

typedef void (*isr_t)(struct registers*);
isr_t interrupt_handlers[256];

void register_interrupt_handler(u8 n, isr_t handler) {
    interrupt_handlers[n] = handler;
}

void irq_handler(struct registers *regs) {
    if (regs->int_no >= 40) outb(0xA0, 0x20); // EOI to slave
    outb(0x20, 0x20); // EOI to master

    if (interrupt_handlers[regs->int_no] != 0) {
        isr_t handler = interrupt_handlers[regs->int_no];
        handler(regs);
    }
}

void init_idt() {
    idt_ptr.limit = sizeof(struct idt_entry_struct) * 256 - 1;
    idt_ptr.base  = (u32)&idt_entries;

    for (int i=0; i<256; i++) {
        idt_entries[i].base_lo = 0;
        idt_entries[i].base_hi = 0;
        idt_entries[i].sel = 0;
        idt_entries[i].always0 = 0;
        idt_entries[i].flags = 0;
        interrupt_handlers[i] = 0;
    }

    outb(0x20, 0x11); outb(0xA0, 0x11);
    outb(0x21, 0x20); outb(0xA1, 0x28);
    outb(0x21, 0x04); outb(0xA1, 0x02);
    outb(0x21, 0x01); outb(0xA1, 0x01);
    outb(0x21, 0x00); outb(0xA1, 0x00);

    init_idt_desc(0, (u32)isr0, 0x08, 0x8E); init_idt_desc(1, (u32)isr1, 0x08, 0x8E);
    init_idt_desc(2, (u32)isr2, 0x08, 0x8E); init_idt_desc(3, (u32)isr3, 0x08, 0x8E);
    init_idt_desc(4, (u32)isr4, 0x08, 0x8E); init_idt_desc(5, (u32)isr5, 0x08, 0x8E);
    init_idt_desc(6, (u32)isr6, 0x08, 0x8E); init_idt_desc(7, (u32)isr7, 0x08, 0x8E);
    init_idt_desc(8, (u32)isr8, 0x08, 0x8E); init_idt_desc(9, (u32)isr9, 0x08, 0x8E);
    init_idt_desc(10, (u32)isr10, 0x08, 0x8E); init_idt_desc(11, (u32)isr11, 0x08, 0x8E);
    init_idt_desc(12, (u32)isr12, 0x08, 0x8E); init_idt_desc(13, (u32)isr13, 0x08, 0x8E);
    init_idt_desc(14, (u32)isr14, 0x08, 0x8E); init_idt_desc(15, (u32)isr15, 0x08, 0x8E);
    init_idt_desc(16, (u32)isr16, 0x08, 0x8E); init_idt_desc(17, (u32)isr17, 0x08, 0x8E);
    init_idt_desc(18, (u32)isr18, 0x08, 0x8E); init_idt_desc(19, (u32)isr19, 0x08, 0x8E);
    init_idt_desc(20, (u32)isr20, 0x08, 0x8E); init_idt_desc(21, (u32)isr21, 0x08, 0x8E);
    init_idt_desc(22, (u32)isr22, 0x08, 0x8E); init_idt_desc(23, (u32)isr23, 0x08, 0x8E);
    init_idt_desc(24, (u32)isr24, 0x08, 0x8E); init_idt_desc(25, (u32)isr25, 0x08, 0x8E);
    init_idt_desc(26, (u32)isr26, 0x08, 0x8E); init_idt_desc(27, (u32)isr27, 0x08, 0x8E);
    init_idt_desc(28, (u32)isr28, 0x08, 0x8E); init_idt_desc(29, (u32)isr29, 0x08, 0x8E);
    init_idt_desc(30, (u32)isr30, 0x08, 0x8E); init_idt_desc(31, (u32)isr31, 0x08, 0x8E);

    init_idt_desc(32, (u32)irq0, 0x08, 0x8E); init_idt_desc(33, (u32)irq1, 0x08, 0x8E);
    init_idt_desc(34, (u32)irq2, 0x08, 0x8E); init_idt_desc(35, (u32)irq3, 0x08, 0x8E);
    init_idt_desc(36, (u32)irq4, 0x08, 0x8E); init_idt_desc(37, (u32)irq5, 0x08, 0x8E);
    init_idt_desc(38, (u32)irq6, 0x08, 0x8E); init_idt_desc(39, (u32)irq7, 0x08, 0x8E);
    init_idt_desc(40, (u32)irq8, 0x08, 0x8E); init_idt_desc(41, (u32)irq9, 0x08, 0x8E);
    init_idt_desc(42, (u32)irq10, 0x08, 0x8E); init_idt_desc(43, (u32)irq11, 0x08, 0x8E);
    init_idt_desc(44, (u32)irq12, 0x08, 0x8E); init_idt_desc(45, (u32)irq13, 0x08, 0x8E);
    init_idt_desc(46, (u32)irq14, 0x08, 0x8E); init_idt_desc(47, (u32)irq15, 0x08, 0x8E);

    asm volatile("lidt %0" : : "m"(idt_ptr));
    asm volatile("sti");
}
