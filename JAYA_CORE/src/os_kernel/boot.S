/* boot.S - JAYA OS Multiboot Header */
#define MULTIBOOT_HEADER_MAGIC 0x1BADB002
#define MULTIBOOT_PAGE_ALIGN 0x00000001
#define MULTIBOOT_MEMORY_INFO 0x00000002
#define MULTIBOOT_VIDEO_MODE 0x00000004
#define MULTIBOOT_AOUT_KLUDGE 0x00010000

/* Enable Page Align, Memory Info, and Video Mode */
#define MULTIBOOT_HEADER_FLAGS (MULTIBOOT_PAGE_ALIGN | MULTIBOOT_MEMORY_INFO | MULTIBOOT_VIDEO_MODE)
#define MULTIBOOT_CHECKSUM -(MULTIBOOT_HEADER_MAGIC + MULTIBOOT_HEADER_FLAGS)

.section .multiboot
.align 4
    .long MULTIBOOT_HEADER_MAGIC
    .long MULTIBOOT_HEADER_FLAGS
    .long MULTIBOOT_CHECKSUM
    /* Address fields for aout kludge - unused by ELF but needed if MULTIBOOT_AOUT_KLUDGE is set, which we didn't. Wait, no, we just need to provide video info if MULTIBOOT_VIDEO_MODE is set. */
    /* The video info starts at offset 32. So we need to put 5 long zeroes for the aout kludge fields */
    .long 0 /* header_addr */
    .long 0 /* load_addr */
    .long 0 /* load_end_addr */
    .long 0 /* bss_end_addr */
    .long 0 /* entry_addr */

    /* Video mode fields */
    .long 0 /* mode_type (0 = linear graphics, 1 = text) */
    .long 800 /* width */
    .long 600 /* height */
    .long 32  /* depth */

.section .bss
.align 16
stack_bottom:
.skip 16384 # 16KB stack
stack_top:

.section .text
.global _start
.type _start, @function
_start:
    /* Set up stack */
    mov $stack_top, %esp

    /* Push multiboot magic */
    push %eax
    /* Push multiboot info struct */
    push %ebx

    /* Call kernel_main */
    .extern kernel_main
    call kernel_main

    /* Hang if kernel_main returns */
    cli
1:  hlt
    jmp 1b
