import os
from typing import Callable
from string import printable
from sshkeyboard import listen_keyboard_manual

from .constants import *
from .types import Message
from .formatting import *

# initialize ANSI escape codes
# without this, they don't work
os.system("")


class TerminalMessage:
    """
    Message that the terminal prints
    """

    def __init__(self, **kwargs):
        self.content: str | None = kwargs.get("content")

    def __str__(self) -> str:
        return character_wrap(self.content)

    def lines(self) -> list[str]:
        """
        Returns list of lines in message
        """

        return self.__str__().split("\n")


class Term:
    """
    Terminal rendering class
    """

    message_field: int = TERM_HEIGHT - 2

    def __init__(self):
        # terminal stuff
        self.messages: list[TerminalMessage] = []       # terminal rendered messages
        self.print_buffer: str = ""                     # terminal buffer
        self.lines: list[str] = []                      # terminal lines
        self.line_offset: int = 0                       # offset to rendered lines
        self.line_ptr: int = 0                          # current line

        # terminal user input
        self.input_callback = None
        self.user_input: list[str] = [" " for _ in range(TERM_WIDTH)]
        self.user_cursor: int = 0

    async def start_listening(self):
        """
        Start listening to user input
        """

        await listen_keyboard_manual(
            on_press=self.key_press_callout, on_release=self.key_release_callout,
            delay_second_char=0.05, lower=False
        )

    async def key_press_callout(self, key: str):
        """
        Callout message when any key is pressed
        """

        if key in printable:
            self._insert_user_input(key)
        elif key == "space":
            self._insert_user_input(" ")
        elif key == "backspace":
            self._pop_user_input()
        elif key == "enter":
            await self.input_callback(self.user_input)
            self._clear_user_input()
        elif key == "up":
            self.change_line(-5)
        elif key == "down":
            self.change_line(5)
        elif key == "left":
            self._move_user_cursor(-1)
        elif key == "right":
            self._move_user_cursor(1)
        elif key == "pageup":
            self.change_line(-self.message_field)
        elif key == "pagedown":
            self.change_line(self.message_field)
        else:
            self._insert_user_input(key)

    async def key_release_callout(self, key: str):
        """
        Callout message when any key is released
        """

        pass

    def _print(self, value, flush=False):
        """
        Internal print method
        """

        self.print_buffer += value.__str__()
        if flush:
            print(self.print_buffer, flush=True, end="")
            self.print_buffer = ""

    def _update_user_input(self):
        """
        Updates user input
        """

        self._print(f"\33[{self.message_field+1};0H", False)
        to_print = self.user_input[:self.user_cursor]
        to_print += TERM_CURSOR + self.user_input[self.user_cursor] + TERM_INPUT_FIELD
        to_print += self.user_input[self.user_cursor+1:]
        self._print("".join(to_print), True)

    def _insert_user_input(self, key: str):
        """
        Inserts a character at user cursor
        """

        self.user_input.insert(self.user_cursor, key)
        self.user_input.pop()
        self._move_user_cursor(1)
        self._update_user_input()

    def _pop_user_input(self):
        """
        Removes a character at user cursor
        """

        self.user_input.pop(self.user_cursor-1)
        self._move_user_cursor(-1)
        self.user_input.append(" ")

    def _clear_user_input(self):
        """
        Clears the user input
        """

        self.user_input = [" " for _ in range(TERM_WIDTH)]
        self.user_cursor = 0

    def _move_user_cursor(self, offset: int):
        """
        Moves user cursor
        """

        self.user_cursor += offset
        self.user_cursor = max(0, min(len(self.user_input), self.user_cursor))
        self._update_user_input()

    def clear_terminal(self):
        """
        Just clears the terminal
        """

        os.system("cls" if os.name == "nt" else "clear")
        self.line_ptr = 0
