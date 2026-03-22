/* keyboard.c - JAYA OS Keyboard Driver */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

extern u8 inb(u16 port);
extern void register_interrupt_handler(u8 n, void* handler);

struct registers {
    u32 ds;
    u32 edi, esi, ebp, esp, ebx, edx, ecx, eax;
    u32 int_no, err_code;
    u32 eip, cs, eflags, useresp, ss;
};

static int shift_state = 0;
static int ctrl_state = 0;

static unsigned char kbdus[128] =
{
    0,  27, '1', '2', '3', '4', '5', '6', '7', '8', /* 9 */
  '9', '0', '-', '=', '\b', /* Backspace */
  '\t',         /* Tab */
  'q', 'w', 'e', 'r',   /* 19 */
  't', 'y', 'u', 'i', 'o', 'p', '[', ']', '\n', /* Enter key */
    0,          /* 29   - Control */
  'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';', /* 39 */
 '\'', '`',   0,        /* Left shift */
 '\\', 'z', 'x', 'c', 'v', 'b', 'n',            /* 49 */
  'm', ',', '.', '/',   0,              /* Right shift */
  '*',
    0,  /* Alt */
  ' ',  /* Space bar */
    0,  /* Caps lock */
    0,  /* 59 - F1 key ... > */
    0,   0,   0,   0,   0,   0,   0,   0,
    0,  /* < ... F10 */
    0,  /* 69 - Num lock*/
    0,  /* Scroll Lock */
    0,  /* Home key */
    0,  /* Up Arrow */
    0,  /* Page Up */
  '-',
    0,  /* Left Arrow */
    0,
    0,  /* Right Arrow */
  '+',
    0,  /* 79 - End key*/
    0,  /* Down Arrow */
    0,  /* Page Down */
    0,  /* Insert Key */
    0,  /* Delete Key */
    0,   0,   0,
    0,  /* F11 Key */
    0,  /* F12 Key */
    0, /* All other keys are undefined */
};

static unsigned char kbdus_shift[128] =
{
    0,  27, '!', '@', '#', '$', '%', '^', '&', '*', /* 9 */
  '(', ')', '_', '+', '\b', /* Backspace */
  '\t',         /* Tab */
  'Q', 'W', 'E', 'R',   /* 19 */
  'T', 'Y', 'U', 'I', 'O', 'P', '{', '}', '\n', /* Enter key */
    0,          /* 29   - Control */
  'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ':', /* 39 */
 '\"', '~',   0,        /* Left shift */
 '|', 'Z', 'X', 'C', 'V', 'B', 'N',            /* 49 */
  'M', '<', '>', '?',   0,              /* Right shift */
  '*',
    0,  /* Alt */
  ' ',  /* Space bar */
    0,  /* Caps lock */
};

void keyboard_handler(struct registers *regs) {
    (void)regs;
    u8 scancode = inb(0x60);

    if (scancode == 0x2A || scancode == 0x36) { // Left or Right Shift Down
        shift_state = 1;
        return;
    }
    if (scancode == 0xAA || scancode == 0xB6) { // Left or Right Shift Up
        shift_state = 0;
        return;
    }
    if (scancode == 0x1D) { // Ctrl down
        ctrl_state = 1;
        return;
    }
    if (scancode == 0x9D) { // Ctrl up
        ctrl_state = 0;
        return;
    }

    if (scancode & 0x80) {
        // Key release
    } else {
        // Key press
        char c = shift_state ? kbdus_shift[scancode] : kbdus[scancode];
        if (ctrl_state && (c == 'c' || c == 'C')) {
            // Handle Ctrl+C (clipboard copy placeholder)
        } else if (ctrl_state && (c == 'v' || c == 'V')) {
            // Handle Ctrl+V (clipboard paste placeholder)
        } else {
            // Basic print placeholder - could map to GUI text renderer later
        }
    }
}

void init_keyboard() {
    register_interrupt_handler(33, keyboard_handler);
}
