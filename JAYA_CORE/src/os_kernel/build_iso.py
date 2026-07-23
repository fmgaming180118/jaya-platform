import glob
import os
import subprocess

# WSL gcc cross-compilation pipeline documentation script
# This script documents how to compile the microkernel.
# Realistically, this would require i686-elf-gcc on WSL, but we'll try to use local gcc -m32 if available.

KERNEL_DIR = "JAYA_CORE/src/os_kernel"
BUILD_DIR = "JAYA_CORE/build"

def main():
    if not os.path.exists(BUILD_DIR):
        os.makedirs(BUILD_DIR)

    # Find all .c and .S files
    c_files = glob.glob(os.path.join(KERNEL_DIR, "*.c"))
    s_files = glob.glob(os.path.join(KERNEL_DIR, "*.S"))

    objects = []

    # Compile Assembly
    for s_file in s_files:
        obj_file = os.path.join(BUILD_DIR, os.path.basename(s_file).replace('.S', '.o'))
        print(f"Compiling {s_file}...")
        # Compile as 32-bit ELF
        # If gcc is missing -m32 support, this may fail, but we're documenting the pipeline
        cmd = ["gcc", "-m32", "-c", s_file, "-o", obj_file]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            objects.append(obj_file)
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to compile {s_file} (Likely missing i686-elf-gcc or libc dev on this sandbox). Error: {e.stderr.decode()}")

    # Compile C
    for c_file in c_files:
        obj_file = os.path.join(BUILD_DIR, os.path.basename(c_file).replace('.c', '.o'))
        print(f"Compiling {c_file}...")
        # ZERO LIBC, NO BUILTINS
        cmd = ["gcc", "-m32", "-c", c_file, "-o", obj_file, "-std=gnu99", "-ffreestanding", "-O2", "-Wall", "-Wextra", "-fno-exceptions"]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            objects.append(obj_file)
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to compile {c_file}. Error: {e.stderr.decode()}")

    # Link
    if len(objects) == len(c_files) + len(s_files):
        print("Linking kernel...")
        linker_script = os.path.join(KERNEL_DIR, "linker.ld")
        kernel_bin = os.path.join(BUILD_DIR, "jayaos.bin")
        cmd = ["gcc", "-m32", "-T", linker_script, "-o", kernel_bin, "-ffreestanding", "-O2", "-nostdlib"] + objects
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"Successfully linked {kernel_bin}!")
            # ISO Creation would use grub-mkrescue, omitted here as it requires grub tools
            print("To build ISO: grub-mkrescue -o jayaos.iso isodir")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to link kernel. Error: {e.stderr.decode()}")
    else:
        print("Compilation step failed, skipping linking.")

if __name__ == "__main__":
    main()
