import atexit
import curses
import logging
import os
import re
import sys

from endcord import terminal_utils, tui

EXT_NAME = "Kitty Keyboard"
EXT_VERSION = "0.1.0"
EXT_ENDCORD_VERSION = "1.6.0"
EXT_DESCRIPTION = "An extension that adds support for kitty keyboard protocol"
EXT_SOURCE = "https://github.com/sparklost/endcord-kitty-keyboard"
logger = logging.getLogger(__name__)

KITTY_FLAGS = 1 | 4 | 8 | 16
LETTER_KEYS = {
    "A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT", "H": "HOME", "F": "END",
    "P": "F1", "Q": "F2", "R": "F3", "S": "F4",
}
TILDE_KEYS = {
    1: "HOME", 2: "INS", 3: "DEL", 4: "END", 5: "PGUP", 6: "PGDN", 7: "HOME", 8: "END",
    11: "F1", 12: "F2", 13: "F3", 14: "F4", 15: "F5", 17: "F6", 18: "F7", 19: "F8",
    20: "F9", 21: "F10", 23: "F11", 24: "F12",
}
NAMED_KEYS = {27: "ESC", 13: "ENTER", 9: "TAB", 127: "BACKSPACE", 8: "BACKSPACE"}
KEYPAD_CHARS = {57399 + i: str(i) for i in range(10)}
KEYPAD_CHARS.update({57409: ".", 57410: "/", 57411: "*", 57412: "-", 57413: "+", 57415: "=", 57416: ","})
KEYPAD_NAMED = {
    57414: "ENTER", 57417: "LEFT", 57418: "RIGHT", 57419: "UP", 57420: "DOWN",
    57421: "PGUP", 57422: "PGDN", 57423: "HOME", 57424: "END", 57425: "INS", 57426: "DEL",
}


def check_kitty_keyboard():
    """Check if kitty keyboard protocol is supported"""
    response = terminal_utils.query_terminal(b"\x1b[?u\x1b[c")
    if isinstance(response, bytes):
        response = response.decode("utf-8", errors="replace")
    return re.search(r"\[\?\d+u", response) is not None


kitty_keyboard_active = False


def kitty_keyboard_enable():
    """Enable kitty keyboard protocol on the currently active screen"""
    global kitty_keyboard_active
    if kitty_keyboard_active:
        return
    os.write(sys.stdout.fileno(), f"\033[>{KITTY_FLAGS}u".encode())
    kitty_keyboard_active = True


def kitty_keyboard_disable():
    """Disable kitty keyboard protocol on the currently active screen"""
    global kitty_keyboard_active
    if not kitty_keyboard_active:
        return
    os.write(sys.stdout.fileno(), b"\033[<u")
    kitty_keyboard_active = False


def parse_mods(field):
    """Parse modifiers field"""
    parts = field.split(":")
    value = int(parts[0]) if parts and parts[0] else 1
    event = int(parts[1]) if len(parts) > 1 and parts[1] else 1
    mask = max(value - 1, 0)   # ignore caps lock and num lock
    return (
        bool(mask & 1),
        bool(mask & (2 | 32)),   # alt and meta
        bool(mask & 4),
        bool(mask & (8 | 16)),   # super and hyper
        event,
    )


def mods_prefix(shift, alt, ctrl):
    """Build modifier prefix"""
    return ("C-" if ctrl else "") + ("M-" if alt else "") + ("S-" if shift else "")


def text_key(code, shifted, text, shift, alt, ctrl):
    """Convert a text-producing key into string"""
    if text and not ctrl and not alt:
        return text
    if code == 32:
        if ctrl:
            return mods_prefix(shift, alt, ctrl) + "SPACE"
        if alt:
            return mods_prefix(shift, alt, ctrl) + " "
        return " "
    char = chr(code)
    if shift:
        if char.isalpha():
            if not ctrl and not alt:
                return chr(shifted) if shifted else char.upper()
        else:
            if shifted:
                char = chr(shifted)
            shift = False
    return mods_prefix(shift, alt, ctrl) + char


class Extension:
    """Main extension class"""

    def __init__(self, app):
        if tui.uses_gtkcurses or not check_kitty_keyboard():
            logger.warning("No kitty keyboard protocol support detected in this terminal")
            return
        kitty_keyboard_enable()
        atexit.register(kitty_keyboard_disable)   # to be extra safe
        app.tui.get_key = self.get_key
        if "C-c" not in app.tui.key_map:   # add ctrl+c if its free
            app.tui.key_map["C-c"] = 34
        original_endwin = curses.endwin
        def endwin(*args, **kwargs):
            kitty_keyboard_disable()   # must be before leaving alternate screen
            return original_endwin(*args, **kwargs)
        curses.endwin = endwin
        original_pause_curses = app.tui.pause_curses
        original_resume_curses = app.tui.resume_curses
        def pause_curses(*args, **kwargs):
            kitty_keyboard_disable()   # must be before leaving alternate screen
            return original_pause_curses(*args, **kwargs)
        def resume_curses(*args, **kwargs):
            result = original_resume_curses(*args, **kwargs)
            kitty_keyboard_enable()
            return result
        app.tui.pause_curses = pause_curses
        app.tui.resume_curses = resume_curses


    def get_key(self, screen, backspace_code=127):   # noqa
        """Drop-in replacement for endcord.keybinding.get_key() using kitty keyboard protocol"""
        first = screen.getch()
        if first == -1:
            return -1
        if first == curses.KEY_RESIZE:
            return "RESIZE"
        if first > 255:
            return -1

        # escape sequences
        if first == 27:
            screen.timeout(25)
            try:
                ch = screen.getch()
                if ch == -1 or ch > 255:
                    return "ESC"
                if ch == ord("["):
                    return self.read_csi(screen)
                if ch == ord("O"):
                    final = screen.getch()
                    if final == -1 or final > 255:
                        return -1
                    name = LETTER_KEYS.get(chr(final))
                    return name if name else -1
                return -1
            finally:
                screen.timeout(250)   # restore previous setting

        # ascii
        if 32 <= first <= 126:
            return chr(first)

        # wide characters
        if 0xC0 <= first <= 0xF7:
            if first <= 0xDF:
                n_bytes = 2
            elif first <= 0xEF:
                n_bytes = 3
            else:
                n_bytes = 4
            buf = bytes([first])
            screen.timeout(25)
            try:
                for _ in range(n_bytes - 1):
                    ch = screen.getch()
                    if ch < 0x80 or ch > 0xBF:
                        return -1
                    buf += bytes([ch])
            finally:
                screen.timeout(250)
            try:
                return buf.decode("utf-8")
            except UnicodeDecodeError:
                return -1

        return -1


    def read_csi(self, screen):
        """Read CSI sequence and decode it"""
        buf = []
        final = None
        for _ in range(64):
            ch = screen.getch()
            if ch == -1 or ch > 255:
                return -1
            if 0x40 <= ch <= 0x7E:
                final = chr(ch)
                break
            buf.append(chr(ch))
        if final is None:
            return -1
        params = "".join(buf)

        try:
            # mouse
            if params.startswith("<") and final in ("m", "M"):
                button_str, x_str, y_str = params[1:].split(";")
                return (int(y_str) - 1, int(x_str) - 1, int(button_str), final == "M")

            # bracketed paste
            if final == "~" and params == "200":
                end = b"\x1b[201~"
                data = bytearray()
                screen.timeout(100)
                try:
                    while True:
                        ch = screen.getch()
                        if ch == -1 or ch > 255:
                            break
                        data.append(ch)
                        if data.endswith(end):
                            del data[-len(end):]
                            break
                finally:
                    screen.timeout(250)
                return f"PASTE {data.decode('utf-8', errors='replace')}"

            # focus
            if not params and final == "I":
                return "FOCUS_IN"
            if not params and final == "O":
                return "FOCUS_OUT"

            fields = params.split(";")

            # CSI u
            if final == "u":
                key_parts = fields[0].split(":")
                code = int(key_parts[0]) if key_parts[0] else 0
                shifted = int(key_parts[1]) if len(key_parts) > 1 and key_parts[1] else 0
                shift, alt, ctrl, sup, event = parse_mods(fields[1] if len(fields) > 1 else "")
                text = ""
                if len(fields) > 2 and fields[2]:
                    text = "".join(chr(int(cp)) for cp in fields[2].split(":") if cp)

                if event == 3 or sup:   # key release or super/hyper combos
                    return -1
                if code == 0:
                    return text if text else -1

                prefix = mods_prefix(shift, alt, ctrl)
                if code in NAMED_KEYS:
                    return prefix + NAMED_KEYS[code]
                if code in KEYPAD_NAMED:
                    return prefix + KEYPAD_NAMED[code]
                if code in KEYPAD_CHARS:
                    code = ord(KEYPAD_CHARS[code])
                    shifted = 0
                elif code >= 57344:   # modifier-only, media and lock keys
                    return -1
                return text_key(code, shifted, text, shift, alt, ctrl)

            # shift+tab
            if final == "Z":
                return "S-TAB"

            # arrows, home, end, F1-F4
            if final in LETTER_KEYS:
                shift, alt, ctrl, sup, event = parse_mods(fields[1] if len(fields) > 1 else "")
                if event == 3 or sup:
                    return -1
                return mods_prefix(shift, alt, ctrl) + LETTER_KEYS[final]

            # delete, insert, pgup, pgdn, F5-F12
            if final == "~":
                name = TILDE_KEYS.get(int(fields[0]))
                if not name:
                    return -1
                shift, alt, ctrl, sup, event = parse_mods(fields[1] if len(fields) > 1 else "")
                if event == 3 or sup:
                    return -1
                return mods_prefix(shift, alt, ctrl) + name
        except (ValueError, IndexError):
            return -1
        return -1
