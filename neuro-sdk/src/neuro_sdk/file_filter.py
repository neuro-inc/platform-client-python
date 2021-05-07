import re
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Tuple, cast

AsyncFilterFunc = Callable[[str], Awaitable[bool]]


async def _always_match(path: str) -> bool:
    return True


class FileFilter:
    def __init__(self, default: AsyncFilterFunc = _always_match) -> None:
        self.filters: List[Tuple[bool, str, str, Callable[[str], Any]]] = []
        self.default = default

    def read_from_buffer(
        self, data: bytes, prefix: str = "", prefix2: str = ""
    ) -> None:
        lines = data.decode("utf-8-sig").split("\n")
        for line in lines:
            if line and line[-1] == "\r":
                line = line[:-1]
            if not line or line.startswith("#"):
                continue
            line = _strip_trailing_spaces(line)
            if line.startswith("!"):
                self.include(line[1:], prefix=prefix, prefix2=prefix2)
            else:
                self.exclude(line, prefix=prefix, prefix2=prefix2)

    def read_from_file(self, path: Path, prefix: str = "", prefix2: str = "") -> None:
        with open(path, "rb") as f:
            self.read_from_buffer(f.read(), prefix, prefix2)

    def append(
        self, exclude: bool, pattern: str, prefix: str = "", prefix2: str = ""
    ) -> None:
        assert not prefix or prefix[-1] == "/"
        assert not prefix2 or prefix2[-1] == "/"
        if "/" not in pattern.rstrip("/"):
            pattern = "**/" + pattern
        else:
            pattern = pattern.lstrip("/")
        re_pattern = translate(pattern)
        matcher = cast(
            Callable[[str], Any], re.compile(re_pattern, re.DOTALL).fullmatch
        )
        self.filters.append((exclude, prefix, prefix2, matcher))

    def exclude(self, pattern: str, prefix: str = "", prefix2: str = "") -> None:
        self.append(True, pattern, prefix=prefix, prefix2=prefix2)

    def include(self, pattern: str, prefix: str = "", prefix2: str = "") -> None:
        self.append(False, pattern, prefix=prefix, prefix2=prefix2)

    async def match(self, path: str) -> bool:
        for exclude, prefix, prefix2, matcher in reversed(self.filters):
            if path.startswith(prefix) and matcher(prefix2 + path[len(prefix) :]):
                return not exclude
        return await self.default(path)


def translate(pat: str) -> str:
    """Translate a shell PATTERN to a regular expression."""

    i = 0
    n = len(pat)
    res = ""
    while i < n:
        c = pat[i]
        i += 1
        if c == "*":
            if (
                (not res or res[-1] == "/")
                and i < n
                and pat[i] == "*"
                and (i + 1 == n or pat[i + 1] == "/")
            ):
                # ** between slashes or ends of the pattern
                if i + 1 == n:
                    res += ".*"
                    return res
                res += "(?:.+/)?"
                i += 2
            else:
                # Any other *
                res += "[^/]*"
        elif c == "?":
            res += "[^/]"
        elif c == "/":
            res += "/"
        elif c == "[":
            j = i
            if j < n and pat[j] == "!":
                j += 1
            if j < n and pat[j] == "]":
                j += 1
            while j < n and pat[j] != "]":
                j += 1
            if j >= n:
                res += "\\["
            else:
                stuff = pat[i:j]
                if "--" not in stuff:
                    stuff = stuff.replace("\\", r"\\")
                else:
                    chunks = []
                    k = i + 2 if pat[i] == "!" else i + 1
                    while True:
                        k = pat.find("-", k, j)
                        if k < 0:
                            break
                        chunks.append(pat[i:k])
                        i = k + 1
                        k = k + 3
                    chunks.append(pat[i:j])
                    # Escape backslashes and hyphens for set difference (--).
                    # Hyphens that create ranges shouldn't be escaped.
                    stuff = "-".join(
                        s.replace("\\", r"\\").replace("-", r"\-") for s in chunks
                    )
                # Escape set operations (&&, ~~ and ||).
                stuff = re.sub(r"([&~|])", r"\\\1", stuff)
                i = j + 1
                if stuff[0] == "!":
                    stuff = "^" + stuff[1:]
                elif stuff[0] in ("^", "["):
                    stuff = "\\" + stuff
                res = f"{res}[{stuff}](?<!/)"
        else:
            if c == "\\" and i < n:
                c = pat[i]
                i += 1
            res += re.escape(c)
    if pat[-1:] != "/":
        res += "/?"
    return res


def _strip_trailing_spaces(s: str) -> str:
    last_space = None
    escaped = False
    for i, c in enumerate(s):
        if escaped:
            escaped = False
        else:
            escaped = c == "\\"
            if c != " ":
                last_space = None
            elif last_space is None:
                last_space = i
    if last_space is not None:
        s = s[:last_space]
    return s


def escape(pathname: str) -> str:
    """Escape all special characters."""
    return re.sub(r"([*?[\\])", r"[\1]", pathname)
