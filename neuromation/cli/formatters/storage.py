import abc
import enum
import operator
import os
import pathlib
import time
from fnmatch import fnmatch
from math import ceil
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import click
import humanize
from click import style, unstyle
from yarl import URL

from neuromation.api import (
    AbstractRecursiveFileProgress,
    Action,
    FileStatus,
    FileStatusType,
    StorageProgressComplete,
    StorageProgressEnterDir,
    StorageProgressFail,
    StorageProgressLeaveDir,
    StorageProgressStart,
    StorageProgressStep,
)
from neuromation.api.url_utils import _extract_path
from neuromation.cli.printer import TTYPrinter
from neuromation.cli.root import Root


RECENT_TIME_DELTA = 365 * 24 * 60 * 60 / 2
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def chunks(list: Sequence[Any], size: int) -> Sequence[Any]:
    result = []
    for i in range(0, len(list), size):
        result.append(list[i : i + size])
    return result


def transpose(columns: Sequence[Sequence[Any]]) -> Sequence[Sequence[Any]]:
    height = len(columns)
    width = len(columns[0])
    result: Sequence[List[Any]] = [[] for _ in range(width)]
    for i in range(width):
        for j in range(height):
            if i < len(columns[j]):
                result[i].append(columns[j][i])
    return result


class GnuIndicators(str, enum.Enum):
    LEFT = "lc"
    RIGHT = "rc"
    END = "ec"
    RESET = "rs"
    NORM = "no"
    FILE = "fi"
    DIR = "di"
    LINK = "ln"
    FIFO = "pi"
    SOCKET = "so"
    BLK = "bd"
    CHR = "cd"
    MISSING = "mi"
    ORPHAN = "or"
    EXEC = "ex"
    DOOR = "do"
    SETUID = "su"
    SETGID = "sg"
    STICKY = "st"
    OTHER_WRITABLE = "ow"
    STICKY_OTHER_WRITABLE = "tw"
    CAP = "ca"
    MULTI_HARD_LINK = "mh"
    CLR_TO_EOL = "cl"


class ParseState(enum.Enum):
    PS_START = enum.auto()
    PS_LEFT = enum.auto()
    PS_ESCAPED = enum.auto()
    PS_ESCAPED_END = enum.auto()
    PS_RIGHT = enum.auto()
    PS_OCTAL = enum.auto()
    PS_HEX = enum.auto()
    PS_CARRET = enum.auto()


class BasePainter(abc.ABC):
    @abc.abstractmethod
    def paint(self, label: str, type: FileStatusType) -> str:  # pragma: no cover
        pass


class NonePainter(BasePainter):
    def paint(self, label: str, type: FileStatusType) -> str:
        return label


class QuotedPainter(BasePainter):
    def paint(self, label: str, type: FileStatusType) -> str:
        if "'" not in label:
            return "'" + label + "'"
        else:
            return '"' + label + '"'


class GnuPainter(BasePainter):
    def __init__(self, ls_colors: str, *, underline: bool = False):
        self._defaults()
        self._parse_ls_colors(ls_colors)
        self._underline = underline

    def _defaults(self) -> None:
        self.color_indicator: Dict[GnuIndicators, str] = {
            GnuIndicators.LEFT: "\033[",
            GnuIndicators.RIGHT: "m",
            GnuIndicators.END: "",
            GnuIndicators.RESET: "0",
            GnuIndicators.NORM: "",
            GnuIndicators.FILE: "",
            GnuIndicators.DIR: "01;34",
            GnuIndicators.LINK: "01;36",
            GnuIndicators.FIFO: "33",
            GnuIndicators.SOCKET: "01;35",
            GnuIndicators.BLK: "01;33",
            GnuIndicators.CHR: "01;33",
            GnuIndicators.MISSING: "",
            GnuIndicators.ORPHAN: "",
            GnuIndicators.EXEC: "01;32",
            GnuIndicators.DOOR: "01;35",
            GnuIndicators.SETUID: "37;41",
            GnuIndicators.SETGID: "30;43",
            GnuIndicators.STICKY: "37;44",
            GnuIndicators.OTHER_WRITABLE: "34;42",
            GnuIndicators.STICKY_OTHER_WRITABLE: "30;42",
            GnuIndicators.CAP: "30;41",
            GnuIndicators.MULTI_HARD_LINK: "",
            GnuIndicators.CLR_TO_EOL: "\033[K",
        }
        self.color_ext_type: Dict[str, str] = {}

    def _parse_ls_colors(self, ls_colors: str) -> None:
        def process(left: str, right: str) -> None:
            try:
                self.color_indicator[GnuIndicators(left)] = right
            except ValueError:
                self.color_ext_type[left] = right

        pos = 0
        left = right = escaped = ""
        num = 0
        state = ParseState.PS_START
        stack: List[ParseState] = []
        while pos < len(ls_colors):
            char = ls_colors[pos]
            if state == ParseState.PS_START:
                if char == ":":  # ignore colon
                    pos += 1
                else:
                    left = ""
                    state = ParseState.PS_LEFT
            elif state == ParseState.PS_OCTAL:
                if char in ["0", "1", "2", "3", "4", "5", "6", "7"]:
                    num = num * 8 + ord(char) - ord("0")
                    if num > 7:
                        state = ParseState.PS_ESCAPED_END
                        escaped = chr(num)
                    pos += 1
                else:
                    state = ParseState.PS_ESCAPED_END
                    escaped = chr(num)
            elif state == ParseState.PS_HEX:
                if char in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]:
                    num = num * 16 + ord(char) - ord("0")
                    if num > 15:
                        state = ParseState.PS_ESCAPED_END
                        escaped = chr(num)
                    pos += 1
                elif char.upper() in ["A", "B", "C", "D", "E", "F"]:
                    num = num * 16 + 10 + ord(char.upper()) - ord("A")
                    if num > 15:
                        state = ParseState.PS_ESCAPED_END
                        escaped = chr(num)
                    pos += 1
                else:
                    state = ParseState.PS_ESCAPED_END
                    escaped = chr(num)

            elif state == ParseState.PS_ESCAPED_END:
                stack.pop()
                state = stack.pop()
                if state == ParseState.PS_LEFT:
                    left += escaped
                else:
                    right += escaped
                escaped = ""
            elif state == ParseState.PS_ESCAPED:
                if char in ["0", "1", "2", "3", "4", "5", "6", "7"]:
                    stack.append(state)
                    state = ParseState.PS_OCTAL
                    num = 0
                elif char.upper() == "X":
                    stack.append(state)
                    state = ParseState.PS_HEX
                    num = 0
                    pos += 1

                elif char == "a":
                    escaped = "\a"
                    stack.append(state)
                    state = ParseState.PS_ESCAPED_END
                    pos += 1
                elif char == "b":
                    escaped = "\b"
                    stack.append(state)
                    state = ParseState.PS_ESCAPED_END
                    pos += 1
                elif char == "e":
                    escaped = chr(27)
                    stack.append(state)
                    state = ParseState.PS_ESCAPED_END
                    pos += 1
                elif char == "f":
                    escaped = "\f"
                    stack.append(state)
                    state = ParseState.PS_ESCAPED_END
                    pos += 1
                elif char == "n":
                    escaped = "\n"
                    stack.append(state)
                    state = ParseState.PS_ESCAPED_END
                    pos += 1
                elif char == "r":
                    escaped = "\r"
                    stack.append(state)
                    state = ParseState.PS_ESCAPED_END
                    pos += 1
                elif char == "t":
                    escaped = "\t"
                    stack.append(state)
                    state = ParseState.PS_ESCAPED_END
                    pos += 1
                elif char == "v":
                    escaped = "\v"
                    stack.append(state)
                    state = ParseState.PS_ESCAPED_END
                    pos += 1
                elif char == "?":
                    escaped = chr(127)
                    stack.append(state)
                    state = ParseState.PS_ESCAPED_END
                    pos += 1
                elif char == "_":
                    escaped = " "
                    stack.append(state)
                    state = ParseState.PS_ESCAPED_END
                    pos += 1
                elif char == chr(0):  # pragma: no cover
                    raise EnvironmentError("Cannot parse coloring scheme")
                else:
                    escaped = char
                    stack.append(state)
                    state = ParseState.PS_ESCAPED_END
                    pos += 1
            elif state == ParseState.PS_CARRET:
                if "@" <= char <= "~":
                    escaped = chr(ord(char) & 0o37)
                elif char == "?":
                    escaped = chr(127)
                else:
                    raise EnvironmentError("Cannot parse coloring scheme")
                stack.append(state)
                state = ParseState.PS_ESCAPED_END
                pos += 1

            elif state == ParseState.PS_LEFT:
                if char == "\\":
                    stack.append(state)
                    state = ParseState.PS_ESCAPED
                    pos += 1
                    escaped = ""
                elif char == "=":
                    right = ""
                    state = ParseState.PS_RIGHT
                    pos += 1
                elif char == "^":
                    stack.append(state)
                    state = ParseState.PS_CARRET
                    pos += 1
                    escaped = ""
                else:
                    left += char
                    pos = pos + 1
            elif state == ParseState.PS_RIGHT:
                if char == "\\":
                    stack.append(state)
                    state = ParseState.PS_ESCAPED
                    pos += 1
                    escaped = ""
                elif char == ":":
                    if right:
                        process(left, right)
                    state = ParseState.PS_START
                    pos += 1
                elif char == "^":
                    stack.append(state)
                    state = ParseState.PS_CARRET
                    pos += 1
                    escaped = ""
                else:
                    right += char
                    pos += 1

        if state == ParseState.PS_CARRET:
            raise EnvironmentError("Cannot parse coloring scheme")
        if state in [ParseState.PS_HEX, ParseState.PS_OCTAL]:
            escaped = chr(num)
            state = stack.pop()
        if state == ParseState.PS_ESCAPED:
            stack.append(ParseState.PS_ESCAPED)
            state = ParseState.PS_ESCAPED_END
        if state == ParseState.PS_ESCAPED_END:
            stack.pop()
            state = stack.pop()
            if state == ParseState.PS_RIGHT:  # pragma no branch
                right += escaped
        if state == ParseState.PS_RIGHT and len(right):
            process(left, right)

    def paint(self, label: str, type: FileStatusType) -> str:
        mapping = {
            FileStatusType.FILE: self.color_indicator[GnuIndicators.FILE],
            FileStatusType.DIRECTORY: self.color_indicator[GnuIndicators.DIR],
        }
        color = mapping[type]
        if not color:
            color = self.color_indicator[GnuIndicators.NORM]
        if type == FileStatusType.FILE:
            for pattern, value in self.color_ext_type.items():
                if fnmatch(label, pattern):
                    color = value
                    break
        if color:
            if self._underline:
                underline = (
                    self.color_indicator[GnuIndicators.LEFT]
                    + "4"
                    + self.color_indicator[GnuIndicators.RIGHT]
                )
            else:
                underline = ""
            return (
                self.color_indicator[GnuIndicators.LEFT]
                + color
                + self.color_indicator[GnuIndicators.RIGHT]
                + underline
                + label
                + self.color_indicator[GnuIndicators.LEFT]
                + self.color_indicator[GnuIndicators.RESET]
                + self.color_indicator[GnuIndicators.RIGHT]
            )
        if self._underline:
            return style(label, underline=self._underline)
        else:
            return label


class BSDAttributes(enum.Enum):
    DIRECTORY = 1
    LINK = 2
    SOCKET = 3
    PIPE = 4
    EXECUTABLE = 5
    BLOCK = 6
    CHARACTER = 7
    EXECUTABLE_SETUID = 8
    EXECUTABLE_SETGID = 9
    DIRECTORY_WRITABLE_OTHERS_WITH_STICKY = 10
    DIRECTORY_WRITABLE_OTHERS_WITHOUT_STICKY = 11


class BSDPainter(BasePainter):
    def __init__(self, lscolors: str, *, underline: bool = False):
        self._underline = underline
        self._parse_lscolors(lscolors)

    def _parse_lscolors(self, lscolors: str) -> None:
        parts = chunks(lscolors, 2)
        self._colors: Dict[BSDAttributes, str] = {}
        num = 0
        for attr in BSDAttributes:
            self._colors[attr] = parts[num]
            num += 1

    def paint(self, label: str, type: FileStatusType) -> str:
        color = ""
        if type == FileStatusType.DIRECTORY:
            color = self._colors[BSDAttributes.DIRECTORY]
        if color:
            char_to_color = {
                "a": "black",
                "b": "red",
                "c": "green",
                "d": "brown",
                "e": "blue",
                "f": "magenta",
                "g": "cyan",
                "h": "white",
            }
            bold = None
            fg = bg = None
            if color[0].lower() in char_to_color.keys():
                fg = char_to_color[color[0].lower()]
                if color[0].isupper():
                    bold = True
            if color[1] in char_to_color.keys():
                bg = char_to_color[color[1]]
            if self._underline:
                underline: Optional[bool] = True
            else:
                underline = None
            if fg or bg or bold or underline:
                return style(label, fg=fg, bg=bg, bold=bold, underline=underline)
        if self._underline:
            return style(label, underline=self._underline)
        return label


def get_painter(color: bool, *, quote: bool = False) -> BasePainter:
    if color:
        ls_colors = os.getenv("LS_COLORS")
        if ls_colors:
            return GnuPainter(ls_colors, underline=quote)
        lscolors = os.getenv("LSCOLORS")
        if lscolors:
            return BSDPainter(lscolors, underline=quote)
    if quote:
        return QuotedPainter()
    else:
        return NonePainter()


class BaseFilesFormatter:
    @abc.abstractmethod
    def __call__(
        self, files: Sequence[FileStatus]
    ) -> Iterator[str]:  # pragma: no cover
        pass


class LongFilesFormatter(BaseFilesFormatter):
    permissions_mapping = {Action.MANAGE: "m", Action.WRITE: "w", Action.READ: "r"}

    file_types_mapping = {FileStatusType.FILE: "-", FileStatusType.DIRECTORY: "d"}

    def __init__(self, human_readable: bool, color: bool):
        self.human_readable = human_readable
        self.painter = get_painter(color)

    def _columns_for_file(self, file: FileStatus) -> Sequence[str]:

        type = self.file_types_mapping[file.type]
        permission = self.permissions_mapping[Action(file.permission)]

        date = time.strftime(TIME_FORMAT, time.localtime(file.modification_time))

        size = file.size
        if self.human_readable:
            size = humanize.naturalsize(size, gnu=True).rstrip("B")

        name = self.painter.paint(file.name, file.type)

        return [f"{type}{permission}", f"{size}", f"{date}", f"{name}"]

    def __call__(self, files: Sequence[FileStatus]) -> Iterator[str]:
        if not files:
            return
        table = [self._columns_for_file(file) for file in files]
        widths = [0 for _ in table[0]]
        for row in table:
            for x in range(len(row)):
                cell_width = len(unstyle(row[x]))
                if widths[x] < cell_width:
                    widths[x] = cell_width
        for row in table:
            line = []
            for x in range(len(row)):
                if x == len(row) - 1:
                    line.append(row[x])
                else:
                    line.append(row[x].rjust(widths[x]))
            yield " ".join(line)


class SimpleFilesFormatter(BaseFilesFormatter):
    def __init__(self, color: bool):
        self.painter = get_painter(color)

    def __call__(self, files: Sequence[FileStatus]) -> Iterator[str]:
        for file in files:
            yield self.painter.paint(file.name, file.type)


class VerticalColumnsFilesFormatter(BaseFilesFormatter):
    def __init__(self, width: int, color: bool):
        self.width = width
        self.painter = get_painter(color)

    def __call__(self, files: Sequence[FileStatus]) -> Iterator[str]:
        if not files:
            return
        items = [self.painter.paint(file.name, file.type) for file in files]
        widths = [len(unstyle(item)) for item in items]
        # let`s check how many columns we can use
        test_count = 1
        while True:
            test_columns = chunks(widths, ceil(len(items) / test_count))
            test_columns_widths = [max(column) for column in test_columns]
            test_total_width = sum(test_columns_widths) + 2 * (len(test_columns) - 1)
            if test_count == 1 or test_total_width <= self.width:
                count = test_count
                columns_widths = test_columns_widths
                if test_total_width == self.width:
                    break

            if test_total_width >= self.width or len(test_columns) == len(items):
                break
            test_count = test_count + 1

        rows = transpose(chunks(items, ceil(len(items) / count)))
        for row in rows:
            formatted_row = []
            for i in range(len(row)):
                formatted = row[i]
                if i < len(row) - 1:
                    formatted = formatted.ljust(columns_widths[i])
                formatted_row.append(formatted)
            yield "  ".join(formatted_row)


class FilesSorter(str, enum.Enum):
    NAME = "name"
    SIZE = "size"
    TIME = "time"

    def key(self) -> Any:
        field = None
        if self == self.NAME:
            field = "name"
        elif self == self.SIZE:
            field = "size"
        elif self == self.TIME:
            field = "modification_time"
        assert field
        return operator.attrgetter(field)


# progress indicator


class BaseStorageProgress(AbstractRecursiveFileProgress):
    @abc.abstractmethod
    def begin(self, src: URL, dst: URL) -> None:  # pragma: no cover
        pass


def create_storage_progress(root: Root, show_progress: bool) -> BaseStorageProgress:
    if show_progress:
        return TTYProgress(root)
    else:
        return StreamProgress(root)


def format_url(url: URL) -> str:
    if url.scheme == "file":
        path = _extract_path(url)
        return str(path)
    else:
        return str(url)


class StreamProgress(BaseStorageProgress):
    def __init__(self, root: Root) -> None:
        self.painter = get_painter(root.color, quote=True)
        self.verbose = root.verbosity > 0

    def fmt_url(self, url: URL, type: FileStatusType) -> str:
        label = format_url(url)
        return self.painter.paint(label, type)

    def begin(self, src: URL, dst: URL) -> None:
        if self.verbose:
            src_label = self.fmt_url(src, FileStatusType.DIRECTORY)
            dst_label = self.fmt_url(dst, FileStatusType.DIRECTORY)
            click.echo(f"Copy {src_label} -> {dst_label}")

    def start(self, data: StorageProgressStart) -> None:
        pass

    def complete(self, data: StorageProgressComplete) -> None:
        if not self.verbose:
            return
        src = self.fmt_url(data.src, FileStatusType.FILE)
        dst = self.fmt_url(data.dst, FileStatusType.FILE)
        click.echo(f"{src} -> {dst}")

    def step(self, data: StorageProgressStep) -> None:
        pass

    def enter(self, data: StorageProgressEnterDir) -> None:
        if not self.verbose:
            return
        src = self.fmt_url(data.src, FileStatusType.FILE)
        dst = self.fmt_url(data.dst, FileStatusType.FILE)
        click.echo(f"{src} -> {dst}")

    def leave(self, data: StorageProgressLeaveDir) -> None:
        pass

    def fail(self, data: StorageProgressFail) -> None:
        src = self.fmt_url(data.src, FileStatusType.FILE)
        dst = self.fmt_url(data.dst, FileStatusType.FILE)
        click.echo(
            click.style("Failure:", fg="red") + f" {src} -> {dst} [{data.message}]",
            err=True,
        )


class TTYProgress(BaseStorageProgress):
    HEIGHT = 10

    def __init__(self, root: Root) -> None:
        self.painter = get_painter(root.color, quote=True)
        self.printer = TTYPrinter()
        self.half_width = (root.terminal_size[0] - 10) // 2
        self.full_width = root.terminal_size[0] - 20
        self.lines: List[Tuple[bool, str]] = []
        self.dir_stack: List[str] = []
        self.verbose = root.verbosity > 0

    def fmt_url(self, url: URL, type: FileStatusType, *, half: bool) -> str:
        label = str(url)
        if half:
            width = self.half_width
        else:
            width = self.full_width
        while len(label) > width:
            parts = list(url.parts)
            if len(parts) > 1:
                if parts[0] == "/":
                    if len(parts) < 3:
                        break
                    slash, first, second, *last = parts
                    if first == "...":
                        if last:
                            parts = ["..."] + last
                    else:
                        parts = ["...", second] + last
                else:
                    first, second, *last = parts
                    if first == "...":
                        if last:
                            parts = ["..."] + last
                    else:
                        parts = ["...", second] + last
            else:
                break
            url = URL(f"{url.scheme}://{url.host or ''}/{'/'.join(parts)}")
            label = str(url)
        return self.fmt_str(label, type)

    def fmt_str(self, label: str, type: FileStatusType) -> str:
        return self.painter.paint(label, type)

    def fmt_size(self, size: int) -> str:
        return humanize.naturalsize(size, gnu=True)

    def begin(self, src: URL, dst: URL) -> None:
        if self.verbose:
            click.echo("Copy")
            click.echo(self.fmt_str(str(src), FileStatusType.DIRECTORY))
            click.echo("=>")
            click.echo(self.fmt_str(str(dst), FileStatusType.DIRECTORY))
        else:
            src_label = self.fmt_url(src, FileStatusType.DIRECTORY, half=True)
            dst_label = self.fmt_url(dst, FileStatusType.DIRECTORY, half=True)
            click.echo(f"Copy {src_label} => {dst_label}")

    def enter(self, data: StorageProgressEnterDir) -> None:
        src = self.fmt_url(data.src, FileStatusType.DIRECTORY, half=False)
        self.dir_stack.append(src)
        self.append(f"{src}", is_dir=True)

    def leave(self, data: StorageProgressLeaveDir) -> None:
        del self.dir_stack[-1]
        if self.dir_stack:
            self.append(f"{self.dir_stack[-1]}", is_dir=True)

    def start(self, data: StorageProgressStart) -> None:
        src = self.fmt_str(data.src.name, FileStatusType.FILE)
        progress = 0
        current = self.fmt_size(0)
        total = self.fmt_size(data.size)
        self.append(f"{src} [{progress:.2f}%] {current} of {total}")

    def complete(self, data: StorageProgressComplete) -> None:
        src = self.fmt_str(data.src.name, FileStatusType.FILE)
        total = self.fmt_size(data.size)
        self.replace(f"{src} {total}")

    def step(self, data: StorageProgressStep) -> None:
        src = self.fmt_str(data.src.name, FileStatusType.FILE)
        progress = (100 * data.current) / data.size
        current = self.fmt_size(data.current)
        total = self.fmt_size(data.size)
        self.replace(f"{src} [{progress:.2f}%] {current} of {total}")

    def fail(self, data: StorageProgressFail) -> None:
        src = self.fmt_str(str(data.src), FileStatusType.FILE)
        dst = self.fmt_str(str(data.dst), FileStatusType.FILE)
        click.echo(
            click.style("Failure:", fg="red") + f" {src} -> {dst} [{data.message}]",
            err=True,
        )
        # clear lines to sync with writing to stderr
        self.lines = []

    def append(self, msg: str, is_dir: bool = False) -> None:
        self.lines.append((is_dir, msg))
        if len(self.lines) > self.HEIGHT:
            if not self.lines[0][0]:
                # top line is not a dir, drop it.
                del self.lines[0]
            else:
                if any(line[0] for line in self.lines[1:]):
                    # there are folder lines below
                    del self.lines[0]
                else:
                    # there is only top folder line, drop next file line
                    del self.lines[1]
        for lineno, line in enumerate(self.lines):
            self.printer.print(line[1], lineno)

    def replace(self, msg: str) -> None:
        # replace last line
        self.lines[-1] = (False, msg)
        self.printer.print(msg, len(self.lines) - 1)
