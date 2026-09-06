/* io.c - JAYA OS Port I/O */
typedef unsigned short u16;
typedef unsigned char u8;
typedef unsigned int u32;

void outb(u16 port, u8 val) {
    asm volatile ( "outb %0, %1" : : "a"(val), "Nd"(port) );
}

u8 inb(u16 port) {
    u8 ret;
    asm volatile ( "inb %1, %0" : "=a"(ret) : "Nd"(port) );
    return ret;
}

void outw(u16 port, u16 val) {
    asm volatile ( "outw %0, %1" : : "a"(val), "Nd"(port) );
}

u16 inw(u16 port) {
    u16 ret;
    asm volatile ( "inw %1, %0" : "=a"(ret) : "Nd"(port) );
    return ret;
}

void outl(u16 port, u32 val) {
    asm volatile ( "outl %0, %1" : : "a"(val), "Nd"(port) );
}

u32 inl(u16 port) {
    u32 ret;
    asm volatile ( "inl %1, %0" : "=a"(ret) : "Nd"(port) );
    return ret;
}
