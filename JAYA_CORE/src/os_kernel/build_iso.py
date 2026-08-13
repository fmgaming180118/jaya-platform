import subprocess
from pathlib import Path

# WSL gcc cross-compilation pipeline documentation script
# This script documents how to compile the microkernel.
# A full build requires i686-elf-gcc on WSL or local gcc with 32-bit support.

KERNEL_DIR = Path(__file__).resolve().parent
BUILD_DIR = KERNEL_DIR.parents[1] / "build"


def _error_text(error: subprocess.CalledProcessError) -> str:
    stderr = error.stderr
    if isinstance(stderr, bytes):
        return stderr.decode(errors="replace")
    return str(stderr or error)


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # Find all .c and .S files
    c_files = sorted(KERNEL_DIR.glob("*.c"))
    s_files = sorted(KERNEL_DIR.glob("*.S"))

    objects: list[Path] = []

    # Compile Assembly
    for s_file in s_files:
        obj_file = BUILD_DIR / f"{s_file.stem}.o"
        print(f"Compiling {s_file}...")
        # Compile as 32-bit ELF
        # A missing 32-bit toolchain is reported without creating fake output.
        cmd = ["gcc", "-m32", "-c", s_file, "-o", obj_file]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            objects.append(obj_file)
        except subprocess.CalledProcessError as e:
            print(
                f"Warning: Failed to compile {s_file}; verify i686-elf-gcc "
                f"or local 32-bit support. Error: {_error_text(e)}"
            )

    # Compile C
    for c_file in c_files:
        obj_file = BUILD_DIR / f"{c_file.stem}.o"
        print(f"Compiling {c_file}...")
        # ZERO LIBC, NO BUILTINS
        cmd = [
            "gcc",
            "-m32",
            "-c",
            c_file,
            "-o",
            obj_file,
            "-std=gnu99",
            "-ffreestanding",
            "-O2",
            "-Wall",
            "-Wextra",
            "-fno-exceptions",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            objects.append(obj_file)
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to compile {c_file}. Error: {_error_text(e)}")

    # Link
    if len(objects) == len(c_files) + len(s_files):
        print("Linking kernel...")
        linker_script = KERNEL_DIR / "linker.ld"
        kernel_bin = BUILD_DIR / "jayaos.bin"
        cmd = [
            "gcc",
            "-m32",
            "-T",
            linker_script,
            "-o",
            kernel_bin,
            "-ffreestanding",
            "-O2",
            "-nostdlib",
        ] + objects
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"Successfully linked {kernel_bin}!")
            # ISO creation remains an explicit grub-mkrescue step.
            print("To build ISO: grub-mkrescue -o jayaos.iso isodir")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to link kernel. Error: {_error_text(e)}")
    else:
        print("Compilation step failed, skipping linking.")


if __name__ == "__main__":
    main()
