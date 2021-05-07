import asyncio
import functools
import inspect
import itertools
import logging
import os
import re
import shlex
import shutil
import sys
from datetime import timedelta
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

import click
import humanize
from aiohttp import ClientResponseError
from click.types import convert_type
from yarl import URL

from neuro_sdk import Action, Client, JobStatus, Volume
from neuro_sdk.url_utils import uri_from_cli

from .parse_utils import parse_timedelta
from .root import Root
from .stats import upload_gmp_stats
from .version_utils import run_version_checker

log = logging.getLogger(__name__)

_T = TypeVar("_T")

DEPRECATED_HELP_NOTICE = " " + click.style("(DEPRECATED)", fg="red")
DEPRECATED_INVOKE_NOTICE = "DeprecationWarning: The command {name} is deprecated."


async def _run_async_function(
    init_client: bool,
    func: Callable[..., Awaitable[_T]],
    root: Root,
    *args: Any,
    **kwargs: Any,
) -> _T:
    loop = asyncio.get_event_loop()

    if init_client:
        await root.init_client()

        pypi_task: "asyncio.Task[None]" = loop.create_task(
            run_version_checker(root.client, root.disable_pypi_version_check)
        )
        stats_task: "asyncio.Task[None]" = loop.create_task(
            upload_gmp_stats(
                root.client, root.command_path, root.command_params, root.skip_gmp_stats
            )
        )
    else:
        pypi_task = loop.create_task(asyncio.sleep(0))  # do nothing
        stats_task = loop.create_task(asyncio.sleep(0))  # do nothing

    try:
        return await func(root, *args, **kwargs)
    finally:
        stats_task.cancel()
        try:
            await stats_task
        except asyncio.CancelledError:
            pass
        except Exception:
            log.debug("Usage stats sending has failed", exc_info=True)
        pypi_task.cancel()
        try:
            await pypi_task
        except asyncio.CancelledError:
            pass
        except Exception:
            log.debug("PyPI checker has failed", exc_info=True)


def _wrap_async_callback(
    callback: Callable[..., Awaitable[_T]],
    init_client: bool = True,
) -> Callable[..., _T]:
    assert inspect.iscoroutinefunction(callback)

    # N.B. the decorator implies @click.pass_obj
    @click.pass_obj
    @functools.wraps(callback)
    def wrapper(root: Root, *args: Any, **kwargs: Any) -> _T:
        return root.run(
            _run_async_function(init_client, callback, root, *args, **kwargs),
        )

    return wrapper


class HelpFormatter(click.HelpFormatter):
    def write_usage(self, prog: str, args: str = "", prefix: str = "Usage:") -> None:
        super().write_usage(prog, args, prefix=click.style(prefix, bold=True) + " ")

    def write_heading(self, heading: str) -> None:
        self.write(
            click.style(
                "%*s%s:\n" % (self.current_indent, "", heading),
                bold=True,
                underline=False,
            )
        )


class Context(click.Context):
    def make_formatter(self) -> click.HelpFormatter:
        return HelpFormatter(
            width=self.terminal_width, max_width=self.max_content_width
        )


def split_examples(help: str) -> List[str]:
    return re.split("Example[s]:\n", help, re.IGNORECASE)


def format_example(example: str, formatter: click.HelpFormatter) -> None:
    with formatter.section(click.style("Examples", bold=True, underline=False)):
        for line in example.splitlines():
            is_comment = line.startswith("#")
            if is_comment:
                formatter.write_text("\b\n" + click.style(line, dim=True))
            else:
                formatter.write_text("\b\n" + " ".join(shlex.split(line)))


class NeuroClickMixin:
    def get_params(self, ctx: click.Context) -> List[click.Parameter]:
        # super() is available after using as a mixin
        ret = super().get_params(ctx)  # type: ignore
        args = [i for i in ret if not isinstance(i, click.Option)]
        opts = [i for i in ret if isinstance(i, click.Option)]

        help_names = self.get_help_option_names(ctx)  # type: ignore

        def sort_key(opt: click.Option) -> Tuple[bool, str]:
            flag = set(opt.opts) & help_names or set(opt.secondary_opts) & help_names
            return (not flag, opt.name)

        return args + sorted(opts, key=sort_key)

    def get_help_option(self, ctx: click.Context) -> Optional[click.Option]:
        help_options = self.get_help_option_names(ctx)  # type: ignore
        if not help_options or not self.add_help_option:  # type: ignore
            return None

        def show_help(ctx: click.Context, param: Any, value: Any) -> None:
            if value and not ctx.resilient_parsing:
                print_help(ctx)

        return Option(
            help_options,
            is_flag=True,
            is_eager=True,
            expose_value=False,
            callback=show_help,
            help="Show this message and exit.",
        )

    def get_short_help_str(self, limit: int = 45) -> str:
        text = super().get_short_help_str(limit=limit)  # type: ignore
        if text.endswith(".") and not text.endswith("..."):
            text = text[:-1]
        return text

    def format_help_text(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Writes the help text to the formatter if it exists."""
        deprecated = self.deprecated  # type: ignore
        help = self.help  # type: ignore
        if help:
            help_text, *examples = split_examples(help)
            if help_text:
                formatter.write_paragraph()
                with formatter.indentation():
                    if deprecated:
                        help_text += DEPRECATED_HELP_NOTICE
                    formatter.write_text(help_text)
            examples = [example.strip() for example in examples]

            for example in examples:
                format_example(example, formatter)
        elif deprecated:
            formatter.write_paragraph()
            with formatter.indentation():
                formatter.write_text(DEPRECATED_HELP_NOTICE)

    def make_context(
        self,
        info_name: str,
        args: Sequence[str],
        parent: Optional[click.Context] = None,
        **extra: Any,
    ) -> Context:
        for key, value in self.context_settings.items():  # type: ignore
            if key not in extra:
                extra[key] = value
        ctx = Context(self, info_name=info_name, parent=parent, **extra)  # type: ignore
        with ctx.scope(cleanup=False):
            self.parse_args(ctx, args)  # type: ignore
        return ctx


class NeuroGroupMixin(NeuroClickMixin):
    def format_options(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        self.format_commands(ctx, formatter)  # type: ignore


def _collect_params(cmd: click.Command, ctx: click.Context) -> Dict[str, Optional[str]]:
    params = ctx.params.copy()
    for param in cmd.get_params(ctx):
        if param.name not in params:
            continue
        if params[param.name] == param.get_default(ctx):
            # drop default param
            del params[param.name]
            continue
        if param.param_type_name != "option":
            # save name only
            params[param.name] = None
        else:
            if getattr(param, "secure", True):
                params[param.name] = None
            else:
                params[param.name] = str(params[param.name])
    return params


class Command(NeuroClickMixin, click.Command):
    def __init__(
        self,
        callback: Any,
        init_client: bool = True,
        wrap_async: bool = True,
        **kwargs: Any,
    ) -> None:
        if wrap_async:
            callback = _wrap_async_callback(callback, init_client=init_client)
        super().__init__(
            callback=callback,
            **kwargs,
        )
        self.init_client = init_client

    def invoke(self, ctx: click.Context) -> Any:
        """Given a context, this invokes the attached callback (if it exists)
        in the right way.
        """
        root = cast(Root, ctx.obj)
        if self.deprecated:
            root.print(
                DEPRECATED_INVOKE_NOTICE.format(name=self.name), err=True, style="red"
            )
        if self.callback is not None:
            # Collect arguments for sending to google analytics
            ctx2 = ctx
            params = [_collect_params(ctx2.command, ctx2)]
            while ctx2.parent:
                ctx2 = ctx2.parent
                params.append(_collect_params(ctx2.command, ctx2))
            params.reverse()
            root.command_path = ctx.command_path
            root.command_params = params
            return ctx.invoke(self.callback, **ctx.params)


def command(
    name: Optional[str] = None, cls: Type[Command] = Command, **kwargs: Any
) -> Command:
    return click.command(name=name, cls=cls, **kwargs)  # type: ignore


class Group(NeuroGroupMixin, click.Group):
    def command(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Any]], Command]:
        def decorator(f: Callable[..., Any]) -> Command:
            cmd = command(*args, **kwargs)(f)
            self.add_command(cmd)
            return cmd

        return decorator

    def group(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Any]], "Group"]:
        def decorator(f: Callable[..., Any]) -> Group:
            cmd = group(*args, **kwargs)(f)
            self.add_command(cmd)
            return cmd

        return decorator

    def list_commands(self, ctx: click.Context) -> Iterable[str]:
        return self.commands

    def invoke(self, ctx: click.Context) -> None:
        if not ctx.args and not ctx.protected_args:
            print_help(ctx)
        else:
            super().invoke(ctx)


def group(name: Optional[str] = None, **kwargs: Any) -> Group:
    kwargs.setdefault("cls", Group)
    kwargs.setdefault("invoke_without_command", True)
    return click.group(name=name, **kwargs)  # type: ignore


def print_help(ctx: click.Context) -> None:
    root = cast(Root, ctx.obj)
    if root is None:
        tty = all(f.isatty() for f in [sys.stdin, sys.stdout, sys.stderr])
        terminal_size = shutil.get_terminal_size()
    else:
        tty = root.tty
        terminal_size = root.terminal_size

    pager_maybe(ctx.get_help().splitlines(), tty, terminal_size)
    ctx.exit()


class DeprecatedGroup(NeuroGroupMixin, click.MultiCommand):
    def __init__(
        self, origin: click.MultiCommand, name: Optional[str] = None, **attrs: Any
    ) -> None:
        attrs.setdefault("help", f"Alias for {origin.name}")
        attrs.setdefault("deprecated", True)
        super().__init__(name, **attrs)
        self.origin = origin

    def get_command(self, ctx: click.Context, cmd_name: str) -> Optional[click.Command]:
        return self.origin.get_command(ctx, cmd_name)

    def list_commands(self, ctx: click.Context) -> Iterable[str]:
        return self.origin.list_commands(ctx)


def alias(
    origin: click.Command,
    name: str,
    *,
    deprecated: bool = True,
    hidden: Optional[bool] = None,
    help: Optional[str] = None,
) -> click.Command:
    if help is None:
        help = f"Alias for {origin.name}."
    if hidden is None:
        hidden = origin.hidden

    return Command(
        name=name,
        context_settings=origin.context_settings,
        callback=origin.callback,
        params=origin.params,
        help=help,
        epilog=origin.epilog,
        short_help=origin.short_help,
        options_metavar=origin.options_metavar,
        add_help_option=origin.add_help_option,
        hidden=hidden,
        deprecated=deprecated,
        wrap_async=False,
    )


class Option(click.Option):
    def __init__(self, *args: Any, secure: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.secure = secure


def option(*param_decls: Any, **attrs: Any) -> Callable[..., Any]:
    option_attrs = attrs.copy()
    option_attrs.setdefault("cls", Option)
    typ = convert_type(attrs.get("type"), attrs.get("default"))
    autocompletion = getattr(typ, "complete", None)
    option_attrs.setdefault("autocompletion", autocompletion)
    return click.option(*param_decls, **option_attrs)


def argument(*param_decls: Any, **attrs: Any) -> Callable[..., Any]:
    arg_attrs = attrs.copy()
    typ = convert_type(attrs.get("type"), attrs.get("default"))
    autocompletion = getattr(typ, "complete", None)
    arg_attrs.setdefault("autocompletion", autocompletion)
    return click.argument(*param_decls, **arg_attrs)


def volume_to_verbose_str(volume: Volume) -> str:
    return (
        f"'{volume.storage_uri}' mounted to '{volume.container_path}' "
        f"in {('ro' if volume.read_only else 'rw')} mode"
    )


JOB_ID_PATTERN = r"job-[0-9a-z]{8}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12}"


async def resolve_job(
    id_or_name_or_uri: str, *, client: Client, status: Set[JobStatus]
) -> str:
    id, _ = await resolve_job_ex(id_or_name_or_uri, client=client, status=status)
    return id


async def resolve_job_ex(
    id_or_name_or_uri: str, *, client: Client, status: Set[JobStatus]
) -> Tuple[str, str]:
    default_user = client.username
    default_cluster = client.cluster_name
    if id_or_name_or_uri.startswith("job:"):
        uri = uri_from_cli(
            id_or_name_or_uri,
            username=default_user,
            cluster_name=default_cluster,
            allowed_schemes=("job",),
        )
        assert uri.host
        cluster_name = uri.host
        owner, _, id_or_name = uri.path.lstrip("/").partition("/")
        if not owner:
            raise ValueError("Invalid job URI: missing owner")
        if not id_or_name:
            raise ValueError("Invalid job URI: missing job-id or job-name")
    else:
        id_or_name = id_or_name_or_uri
        owner = default_user
        cluster_name = default_cluster

    # Temporary fast path.
    if re.fullmatch(JOB_ID_PATTERN, id_or_name):
        return id_or_name, cluster_name

    try:
        async for job in client.jobs.list(
            name=id_or_name,
            owners={owner},
            reverse=True,
            limit=1,
            cluster_name=cluster_name,
        ):
            log.debug(f"Job name '{id_or_name}' resolved to job ID '{job.id}'")
            return job.id, cluster_name
    except asyncio.CancelledError:
        raise
    except ClientResponseError as e:
        log.error(
            f"Failed to resolve job-name {id_or_name_or_uri} resolved as "
            f"name={id_or_name}, owner={owner} to a job-ID: {e}"
        )

    if owner != default_user:
        raise ValueError(f"Failed to resolve job {id_or_name_or_uri}")
    return id_or_name, cluster_name


DISK_ID_PATTERN = r"disk-[0-9a-z]{8}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12}"


async def resolve_disk(id_or_name: str, *, client: Client) -> str:
    # Temporary fast path.
    if re.fullmatch(DISK_ID_PATTERN, id_or_name):
        return id_or_name

    disk = await client.disks.get(id_or_name)
    return disk.id


SHARE_SCHEMES = ("storage", "image", "job", "blob", "role", "secret", "disk")


def parse_resource_for_sharing(uri: str, root: Root) -> URL:
    """Parses the neuro resource URI string.
    Available schemes: storage, image, job. For image URIs, tags are not allowed.
    """
    uri_res = uri_from_cli(
        uri,
        root.client.username,
        root.client.cluster_name,
        allowed_schemes=SHARE_SCHEMES,
    )
    if uri_res.scheme == "image" and ":" in uri_res.path:
        raise ValueError("tag is not allowed")

    # URI's for object storage can only operate on bucket level
    if uri_res.scheme == "blob" and "/" in uri_res.path.strip("/"):
        raise ValueError("Only bucket level permissions are supported for Blob Storage")
    return uri_res


def parse_file_resource(uri: str, root: Root) -> URL:
    """Parses the neuro resource URI string.
    Available schemes: file, storage.
    """
    return uri_from_cli(
        uri,
        root.client.username,
        root.client.cluster_name,
        allowed_schemes=("file", "storage"),
    )


def parse_blob_resource(uri: str, root: Root) -> URL:
    # Username will not be used, just part of the signature
    return uri_from_cli(
        uri, root.client.username, root.client.cluster_name, allowed_schemes=("blob",)
    )


def parse_blob_or_file_resource(uri: str, root: Root) -> URL:
    # Username will not be used, just part of the signature
    return uri_from_cli(
        uri,
        root.client.username,
        root.client.cluster_name,
        allowed_schemes=("blob", "file"),
    )


def parse_secret_resource(uri: str, root: Root) -> URL:
    return uri_from_cli(
        uri,
        root.client.username,
        root.client.cluster_name,
        allowed_schemes=("secret"),
    )


def parse_permission_action(action: str) -> Action:
    try:
        return Action[action.upper()]
    except KeyError:
        valid_actions = ", ".join([a.value for a in Action])
        raise ValueError(
            f"invalid permission action '{action}', allowed values: {valid_actions}"
        )


def do_deprecated_quiet(
    ctx: click.Context, param: Union[click.Option, click.Parameter], value: Any
) -> Any:
    if value and not ctx.obj.quiet:
        ctx.obj.verbosity = -2
        click.echo(
            click.style(
                "DeprecationWarning: "
                "The local option --quiet is deprecated. "
                "Use global option --quiet instead.",
                fg="red",
            ),
            err=True,
        )
        # Patch the logger as it was set up with verbosity=-2.
        root_logger = logging.getLogger()
        handler = root_logger.handlers[-1]
        assert handler.formatter
        format_class = type(handler.formatter)
        handler.setFormatter(format_class())
        handler.setLevel(logging.ERROR)


deprecated_quiet_option: Any = option(
    "-q",
    "--quiet",
    is_flag=True,
    callback=do_deprecated_quiet,
    help="Run command in quiet mode (DEPRECATED)",
    expose_value=False,
    is_eager=True,
)

if sys.version_info >= (3, 7):  # pragma: no cover
    from contextlib import AsyncExitStack
else:
    from async_exit_stack import AsyncExitStack  # noqa


def format_size(value: Optional[float]) -> str:
    if value is None:
        return ""
    return humanize.naturalsize(value, gnu=True)


def pager_maybe(
    lines: Iterable[str], tty: bool, terminal_size: Tuple[int, int]
) -> None:
    if not tty:
        for line in lines:
            click.echo(line)
        return

    # Enforce ANSI sequence handling (colors etc.)
    os.environ["LESS"] = "-R"

    lines_it: Iterator[str] = iter(lines)
    count = int(terminal_size[1] * 2 / 3)
    handled = list(itertools.islice(lines_it, count))
    if len(handled) < count:
        # lines list is short, just print it
        for line in handled:
            click.echo(line)
    else:
        click.echo_via_pager(
            itertools.chain(["\n".join(handled)], (f"\n{line}" for line in lines_it))
        )


async def _calc_timedelta_key(
    client: Client, value: Optional[str], default: str, config_section: str, key: str
) -> float:
    async def _calc_default_life_span(client: Client) -> timedelta:
        config = await client.config.get_user_config()
        section = config.get(config_section)
        life_span = default
        if section is not None:
            value = section.get(key)
            if value is not None:
                life_span = value
        return parse_timedelta(life_span)

    delta = (
        parse_timedelta(value)
        if value is not None
        else await _calc_default_life_span(client)
    )
    return delta.total_seconds()


async def calc_life_span(
    client: Client, value: Optional[str], default: str, config_section: str
) -> Optional[float]:
    seconds = await _calc_timedelta_key(
        client, value, default, config_section, "life-span"
    )
    if seconds == 0:
        click.secho(
            "Zero job's life-span (--life-span=0) is deprecated "
            "and will be removed in the future neuro CLI release,"
            "use a positive value to avoid resource leakage",
            fg="yellow",
        )
        return None
    assert seconds > 0
    return seconds


async def calc_timeout_unused(
    client: Client, value: Optional[str], default: str, config_section: str
) -> Optional[float]:
    return await _calc_timedelta_key(
        client, value, default, config_section, "timeout-unused"
    )
