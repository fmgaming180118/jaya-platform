#!/bin/bash
rm *.o jaya.bin isodir/boot/jaya.bin JAYA_PRODUCTION.iso || true

as --32 boot.S -o boot.o
as --32 isr.S -o isr.o

gcc -m32 -c io.c -o io.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c idt.c -o idt.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c keyboard.c -o keyboard.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c jbcx_vm.c -o jbcx_vm.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c math_core.c -o math_core.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c ata.c -o ata.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c vector_fs.c -o vector_fs.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c parser.c -o parser.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c pci.c -o pci.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c rtl8139.c -o rtl8139.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c paging.c -o paging.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c kheap.c -o kheap.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c gui.c -o gui.o -std=gnu99 -ffreestanding -O2 -Wall
gcc -m32 -c kernel.c -o kernel.o -std=gnu99 -ffreestanding -O2 -Wall

gcc -m32 -T linker.ld -o jaya.bin -ffreestanding -O2 -nostdlib boot.o isr.o io.o idt.o keyboard.o jbcx_vm.o math_core.o ata.o vector_fs.o parser.o pci.o rtl8139.o paging.o kheap.o gui.o kernel.o -lgcc

mkdir -p isodir/boot/grub
cp jaya.bin isodir/boot/jaya.bin

echo 'menuentry "JAYA BARE-METAL OS V1.6 - Jules GUI Edition" {' > isodir/boot/grub/grub.cfg
echo '    multiboot /boot/jaya.bin' >> isodir/boot/grub/grub.cfg
echo '}' >> isodir/boot/grub/grub.cfg

grub-mkrescue -o JAYA_PRODUCTION.iso isodir
