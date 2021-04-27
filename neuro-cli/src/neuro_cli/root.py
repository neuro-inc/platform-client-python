import asyncio
import contextlib
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from http.cookies import Morsel  # noqa
from pathlib import Path
from types import SimpleNamespace
from typing import (
    Any,
    Awaitable,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Tuple,
    TypeVar,
)

import aiohttp
import click
from rich.console import Console, PagerContext, RenderableType
from rich.pager import Pager
from rich.spinner import Spinner
from rich.status import Status as RichStatus
from rich.style import StyleType
from rich.text import Text as RichText

from neuro_sdk import Client, ConfigError, Factory, gen_trace_id
from neuro_sdk.config import _ConfigData, load_user_config

from .asyncio_utils import Runner

log = logging.getLogger(__name__)


TEXT_TYPE = ("application/json", "text", "application/x-www-form-urlencoded")

HEADER_TOKEN_PATTERN = re.compile(
    r"(Bearer|Basic|Digest|Mutual)\s+(?P<token>[^ ]+\.[^ ]+\.[^ ]+)"
)


_T = TypeVar("_T")


class MaybePager(Pager):
    """Uses the pager installed on the system."""

    def __init__(self, console: Console) -> None:
        self._console = console
        self._limit = console.size[1] * 2 / 3

    def show(self, content: str) -> None:
        """Use the same pager used by pydoc."""
        if self._console.is_terminal and len(content.splitlines()) > self._limit:
            # Enforce ANSI sequence handling (colors etc.)
            os.environ["LESS"] = "-R"
            click.echo_via_pager(content)
        else:
            print(content, end="")


class Status(RichStatus):
    # Patched version of library class, avoid spinner animation
    # reset on updates that do not change spinner style

    def update(
        self,
        status: Optional[RenderableType] = None,
        *,
        spinner: Optional[str] = None,
        spinner_style: Optional[StyleType] = None,
        speed: Optional[float] = None,
    ) -> None:
        if status is not None:
            self.status = status
        if spinner is not None:
            self.spinner = spinner
        if spinner_style is not None:
            self.spinner_style = spinner_style
        if speed is not None:
            self.speed = speed
        if spinner is not None or spinner_style is not None or speed is not None:
            self._spinner = Spinner(
                self.spinner, style=self.spinner_style, speed=self.speed
            )
        self._live.update(self.renderable, refresh=True)


@dataclass
class Root:
    color: bool
    tty: bool
    disable_pypi_version_check: bool
    network_timeout: float
    config_path: Path
    trace: bool
    force_trace_all: bool
    verbosity: int
    trace_hide_token: bool
    command_path: str
    command_params: List[Dict[str, Optional[str]]]
    skip_gmp_stats: bool
    show_traceback: bool
    iso_datetime_format: bool

    _client: Optional[Client] = None
    _factory: Optional[Factory] = None
    _runner: Runner = field(init=False)
    console: Console = field(init=False)

    def __post_init__(self) -> None:
        self._runner = Runner(debug=self.verbosity >= 2)
        self._runner.__enter__()
        self.console = Console(
            color_system="auto" if self.color else None,
            force_terminal=self.tty,
            markup=False,
            emoji=False,
            highlight=False,
            log_path=False,
        )
        if not self.console.is_terminal or self.console.is_dumb_terminal:
            # resize with wider width to prevent wrapping/cropping
            self.console = Console(
                color_system="auto" if self.color else None,
                force_terminal=self.tty,
                highlight=False,
                log_path=False,
                width=2048,
            )

        self.err_console = Console(
            file=sys.stderr,
            color_system="auto" if self.color else None,
            force_terminal=self.tty,
            markup=False,
            emoji=False,
            highlight=False,
            log_path=False,
        )
        if not self.err_console.is_terminal or self.err_console.is_dumb_terminal:
            # resize with wider width to prevent wrapping/cropping
            self.err_console = Console(
                file=sys.stderr,
                color_system="auto" if self.color else None,
                force_terminal=self.tty,
                markup=False,
                emoji=False,
                highlight=False,
                log_path=False,
                width=2048,
            )

    def close(self) -> None:
        if self._client is not None:
            self.run(self._client.close())

        try:
            # Suppress prints unhandled exceptions
            # on event loop closing
            sys.stderr = None  # type: ignore
            self._runner.__exit__(*sys.exc_info())
        finally:
            sys.stderr = sys.__stderr__

    def run(self, main: Awaitable[_T]) -> _T:
        return self._runner.run(main)

    @property
    def _config(self) -> _ConfigData:
        assert self._client is not None
        return self._client.config._config_data

    @property
    def quiet(self) -> bool:
        return self.verbosity < 0

    @property
    def terminal_size(self) -> Tuple[int, int]:
        return self.console.size

    @property
    def timeout(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(
            None, None, self.network_timeout, self.network_timeout
        )

    @property
    def client(self) -> Client:
        assert self._client is not None
        return self._client

    @property
    def factory(self) -> Factory:
        if self._factory is None:
            trace_configs: Optional[List[aiohttp.TraceConfig]]
            if self.trace:
                trace_configs = [self._create_trace_config()]
            else:
                trace_configs = None
            self._factory = Factory(
                path=self.config_path,
                trace_configs=trace_configs,
                trace_id=gen_trace_id(),
                trace_sampled=True if self.force_trace_all else None,
            )
        return self._factory

    async def init_client(self) -> Client:
        if self._client is not None:
            return self._client
        client = await self.factory.get(timeout=self.timeout)

        self._client = client
        return self._client

    async def get_user_config(self) -> Mapping[str, Any]:
        try:
            client = await self.init_client()
        except ConfigError:
            return load_user_config(self.config_path.expanduser())
        else:
            return await client.config.get_user_config()

    def _create_trace_config(self) -> aiohttp.TraceConfig:
        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(self._on_request_start)
        trace_config.on_request_chunk_sent.append(self._on_request_chunk_sent)
        trace_config.on_request_end.append(self._on_request_end)
        trace_config.on_response_chunk_received.append(self._on_response_chunk_received)
        return trace_config

    def _print_debug(self, lines: List[str]) -> None:
        for line in lines:
            self.print(line, style="dim", err=True)

    def _process_chunk(self, chunk: bytes, printable: bool) -> List[str]:
        if not chunk:
            return []
        if printable:
            return chunk.decode(errors="replace").split("\n")
        else:
            return [f"[binary {len(chunk)} bytes]"]

    async def _on_request_start(
        self,
        session: aiohttp.ClientSession,
        context: SimpleNamespace,
        data: aiohttp.TraceRequestStartParams,
    ) -> None:
        path = data.url.raw_path
        if data.url.raw_query_string:
            path += "?" + data.url.raw_query_string
        lines = [f"> {data.method} {path} HTTP/1.1"]
        for key, val in data.headers.items():
            if self.trace_hide_token:
                val = self._sanitize_header_value(val)
            lines.append(f"> {key}: {val}")
        lines.append("> ")
        self._print_debug(lines)

        content_type = data.headers.get("Content-Type", "")
        context.request_printable = content_type.startswith(TEXT_TYPE)

    async def _on_request_chunk_sent(
        self,
        session: aiohttp.ClientSession,
        context: SimpleNamespace,
        data: aiohttp.TraceRequestChunkSentParams,
    ) -> None:
        chunk = data.chunk
        lines = [
            "> " + line
            for line in self._process_chunk(chunk, context.request_printable)
        ]
        self._print_debug(lines)

    async def _on_request_end(
        self,
        session: aiohttp.ClientSession,
        context: SimpleNamespace,
        data: aiohttp.TraceRequestEndParams,
    ) -> None:
        lines = [f"< HTTP/1.1 {data.response.status} {data.response.reason}"]
        for key, val in data.response.headers.items():
            lines.append(f"< {key}: {val}")
        self._print_debug(lines)

        content_type = data.response.headers.get("Content-Type", "")
        context.response_printable = content_type.startswith(TEXT_TYPE)

    async def _on_response_chunk_received(
        self,
        session: aiohttp.ClientSession,
        context: SimpleNamespace,
        data: aiohttp.TraceResponseChunkReceivedParams,
    ) -> None:
        chunk = data.chunk
        lines = [
            "< " + line
            for line in self._process_chunk(chunk, context.response_printable)
        ]
        self._print_debug(lines)

    def _sanitize_header_value(self, text: str) -> str:
        for token in self._find_all_tokens(text):
            token_safe = self._sanitize_token(token)
            text = text.replace(token, token_safe)
        return text

    def _sanitize_token(self, token: str) -> str:
        tail_len: int = 5
        # at least a third part of the token should be hidden
        if tail_len >= len(token) // 3:
            return f"<hidden {len(token)} chars>"
        hidden = f"<hidden {len(token) - tail_len * 2} chars>"
        return token[:tail_len] + hidden + token[-tail_len:]

    def _find_all_tokens(self, text: str) -> Iterator[str]:
        for match in HEADER_TOKEN_PATTERN.finditer(text):
            yield match.group("token")

    async def cancel_with_logging(self, task: "asyncio.Task[Any]") -> None:
        if not task.done():
            task.cancel()
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        except Exception as exc:
            if self.show_traceback:
                log.exception(str(exc), stack_info=True)
            else:
                log.error(str(exc))

    def soft_reset_tty(self) -> None:
        if self.tty:
            # Soft reset the terminal.
            # For example, Midnight Commander often leaves
            # scrolling margins (DECSTBM) aligned only
            # to a part of the screen size
            sys.stdout.write("\x1b[!p")
            sys.stdout.flush()

    @contextlib.contextmanager
    def status(self, message: str) -> Iterator[Status]:
        status = Status(
            RichText.from_markup(message), console=self.console, spinner="dots"
        )
        if self.verbosity >= 0:
            with status:
                yield status
        else:
            yield status

    def pager(self) -> PagerContext:
        return self.console.pager(MaybePager(self.console), styles=True, links=True)

    def print(self, *objects: Any, err: bool = False, **kwargs: Any) -> None:
        console = self.err_console if err else self.console
        console.print(*objects, **kwargs)
