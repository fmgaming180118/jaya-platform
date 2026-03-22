/* jbcx_vm.c - JAYA OS JBCX Virtual Machine */

typedef unsigned int u32;
typedef unsigned char u8;
typedef unsigned short u16;

#define VM_MEM_SIZE 4096
#define NUM_REGS 8

// Opcodes
#define OP_NOP  0x00
#define OP_LOAD 0x01
#define OP_STORE 0x02
#define OP_ADD  0x03
#define OP_SUB  0x04
#define OP_MUL  0x05
#define OP_DIV  0x06
#define OP_JMP  0x07
#define OP_CMP  0x08
#define OP_JE   0x09
#define OP_HLT  0xFF

struct vm_state {
    u32 regs[NUM_REGS];
    u32 pc;
    u8 memory[VM_MEM_SIZE];
    int running;
    int flags; // 1 = Equal, 0 = Not Equal
};

void vm_init(struct vm_state *vm) {
    for (int i=0; i<NUM_REGS; i++) vm->regs[i] = 0;
    vm->pc = 0;
    vm->running = 1;
    vm->flags = 0;
    for (int i=0; i<VM_MEM_SIZE; i++) vm->memory[i] = 0;
}

void vm_load_program(struct vm_state *vm, u8 *program, u32 size) {
    if (size > VM_MEM_SIZE) return;
    for (u32 i = 0; i < size; i++) {
        vm->memory[i] = program[i];
    }
}

void vm_step(struct vm_state *vm) {
    if (!vm->running || vm->pc >= VM_MEM_SIZE) {
        vm->running = 0;
        return;
    }

    u8 opcode = vm->memory[vm->pc++];

    if (opcode == OP_HLT) {
        vm->running = 0;
        return;
    }

    // Simplistic fetching of reg idxs
    u8 r1 = vm->memory[vm->pc++];
    u8 r2 = vm->memory[vm->pc++];
    u8 val = vm->memory[vm->pc++];

    switch (opcode) {
        case OP_NOP:
            break;
        case OP_LOAD:
            vm->regs[r1] = val;
            break;
        case OP_STORE:
            // Placeholder memory load
            vm->memory[val] = vm->regs[r1] & 0xFF;
            break;
        case OP_ADD:
            vm->regs[r1] = vm->regs[r1] + vm->regs[r2];
            break;
        case OP_SUB:
            vm->regs[r1] = vm->regs[r1] - vm->regs[r2];
            break;
        case OP_CMP:
            if (vm->regs[r1] == vm->regs[r2]) vm->flags = 1;
            else vm->flags = 0;
            break;
        case OP_JE:
            if (vm->flags == 1) {
                vm->pc = val;
            }
            break;
        default:
            vm->running = 0; // Illegal instruction
            break;
    }
}

void vm_run(struct vm_state *vm) {
    while (vm->running) {
        vm_step(vm);
    }
}
