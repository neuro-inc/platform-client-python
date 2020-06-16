import asyncio
import dataclasses
import glob as globmodule  # avoid conflict with subcommand "glob"
import logging
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

import click
from yarl import URL

from neuromation.api import (
    Client,
    FileStatusType,
    IllegalArgumentError,
    ResourceNotFound,
)
from neuromation.api.file_filter import FileFilter
from neuromation.api.url_utils import _extract_path

from .const import EX_OSFILE
from .formatters.storage import (
    BaseFilesFormatter,
    FilesSorter,
    LongFilesFormatter,
    SimpleFilesFormatter,
    Tree,
    TreeFormatter,
    VerticalColumnsFilesFormatter,
    create_storage_progress,
    get_painter,
)
from .root import Root
from .utils import (
    Option,
    argument,
    command,
    group,
    option,
    pager_maybe,
    parse_file_resource,
)


log = logging.getLogger(__name__)


@group()
def storage() -> None:
    """
    Storage operations.
    """


@command()
@argument("paths", nargs=-1, required=True)
@option(
    "--recursive",
    "-r",
    is_flag=True,
    help="remove directories and their contents recursively",
)
@option(
    "--glob/--no-glob",
    is_flag=True,
    default=True,
    show_default=True,
    help="Expand glob patterns in PATHS",
)
async def rm(root: Root, paths: Sequence[str], recursive: bool, glob: bool) -> None:
    """
    Remove files or directories.

    Examples:

    neuro rm storage:foo/bar
    neuro rm storage://{username}/foo/bar
    neuro rm --recursive storage://{username}/foo/
    neuro rm storage:foo/**/*.tmp
    """
    errors = False
    for uri in await _expand(paths, root, glob):
        try:
            await root.client.storage.rm(uri, recursive=recursive)
        except (OSError, ResourceNotFound, IllegalArgumentError) as error:
            log.error(f"cannot remove {uri}: {error}")
            errors = True
        else:
            if root.verbosity > 0:
                painter = get_painter(root.color, quote=True)
                curi = painter.paint(str(uri), FileStatusType.FILE)
                click.echo(f"removed {curi}")
    if errors:
        sys.exit(EX_OSFILE)


@command()
@argument("paths", nargs=-1)
@option(
    "-a",
    "--all",
    "show_all",
    is_flag=True,
    help="do not ignore entries starting with .",
)
@option(
    "-d",
    "--directory",
    is_flag=True,
    help="list directories themselves, not their contents.",
)
@option(
    "--human-readable",
    "-h",
    is_flag=True,
    help="with -l print human readable sizes (e.g., 2K, 540M).",
)
@option("-l", "format_long", is_flag=True, help="use a long listing format.")
@option(
    "--sort",
    type=click.Choice(["name", "size", "time"]),
    default="name",
    help="sort by given field, default is name.",
)
async def ls(
    root: Root,
    paths: Sequence[str],
    human_readable: bool,
    format_long: bool,
    sort: str,
    directory: bool,
    show_all: bool,
) -> None:
    """
    List directory contents.

    By default PATH is equal user's home dir (storage:)
    """
    if not paths:
        paths = ["storage:"]
    uris = [parse_file_resource(path, root) for path in paths]

    errors = False
    for uri in uris:
        try:
            if directory:
                files = [await root.client.storage.stat(uri)]
            else:
                if root.verbosity > 0:
                    painter = get_painter(root.color, quote=True)
                    curi = painter.paint(str(uri), FileStatusType.DIRECTORY)
                    click.echo(f"List of {curi}:")

                files = [file async for file in root.client.storage.ls(uri)]
                files = sorted(files, key=FilesSorter(sort).key())
        except (OSError, ResourceNotFound, IllegalArgumentError) as error:
            log.error(f"cannot access {uri}: {error}")
            errors = True
        else:
            if format_long:
                formatter: BaseFilesFormatter = LongFilesFormatter(
                    human_readable=human_readable, color=root.color
                )
            else:
                if root.tty:
                    formatter = VerticalColumnsFilesFormatter(
                        width=root.terminal_size[0], color=root.color
                    )
                else:
                    formatter = SimpleFilesFormatter(root.color)

            if not show_all:
                files = [item for item in files if not item.name.startswith(".")]
            pager_maybe(formatter(files), root.tty, root.terminal_size)

    if errors:
        sys.exit(EX_OSFILE)


@command()
@argument("patterns", nargs=-1, required=False)
async def glob(root: Root, patterns: Sequence[str]) -> None:
    """
    List resources that match PATTERNS.
    """
    for pattern in patterns:
        uri = parse_file_resource(pattern, root)
        if root.verbosity > 0:
            painter = get_painter(root.color, quote=True)
            curi = painter.paint(str(uri), FileStatusType.FILE)
            click.echo(f"Using pattern {curi}:")
        async for file in root.client.storage.glob(uri):
            click.echo(file)


class FileFilterParserOption(click.parser.Option):
    def process(self, value: str, state: click.parser.ParsingState) -> None:
        super().process((self.const, value), state)


class FileFilterOption(Option):
    def add_to_parser(self, parser: click.parser.OptionParser, ctx: Any) -> None:
        option = FileFilterParserOption(
            self.opts,
            self.name,
            action="append",
            nargs=self.nargs,
            const=self.flag_value,
            obj=self,
        )
        parser._opt_prefixes.update(option.prefixes)
        for opt in option._short_opts:
            parser._short_opt[opt] = option
        for opt in option._long_opts:
            parser._long_opt[opt] = option


def filter_option(*args: str, flag_value: bool, help: str) -> Callable[[Any], Any]:
    return option(
        *args,
        multiple=True,
        cls=FileFilterOption,
        flag_value=flag_value,
        type=click.UNPROCESSED,
        help=help,
        secure=True,
    )


@command()
@argument("sources", nargs=-1, required=False)
@argument("destination", required=False)
@option("-r", "--recursive", is_flag=True, help="Recursive copy, off by default")
@option(
    "--glob/--no-glob",
    is_flag=True,
    default=True,
    show_default=True,
    help="Expand glob patterns in SOURCES with explicit scheme.",
)
@option(
    "-t",
    "--target-directory",
    metavar="DIRECTORY",
    default=None,
    help="Copy all SOURCES into DIRECTORY.",
)
@option(
    "-T",
    "--no-target-directory",
    is_flag=True,
    help="Treat DESTINATION as a normal file.",
)
@option(
    "-u",
    "--update",
    is_flag=True,
    help="Copy only when the SOURCE file is newer than the destination file "
    "or when the destination file is missing.",
)
@filter_option(
    "--exclude",
    "filters",
    flag_value=True,
    help=(
        "Exclude files and directories that match the specified pattern. "
        "The default can be changed using the storage.cp-exclude "
        'configuration variable documented in "neuro help user-config"'
    ),
)
@filter_option(
    "--include",
    "filters",
    flag_value=False,
    help=(
        "Don't exclude files and directories that match the specified pattern. "
        "The default can be changed using the storage.cp-exclude "
        'configuration variable documented in "neuro help user-config"'
    ),
)
@option(
    "-p/-P",
    "--progress/--no-progress",
    is_flag=True,
    default=True,
    help="Show progress, on by default in TTY mode, off otherwise.",
)
async def cp(
    root: Root,
    sources: Sequence[str],
    destination: Optional[str],
    recursive: bool,
    glob: bool,
    target_directory: Optional[str],
    no_target_directory: bool,
    update: bool,
    filters: Optional[Tuple[Tuple[bool, str], ...]],
    progress: bool,
) -> None:
    """
    Copy files and directories.

    Either SOURCES or DESTINATION should have storage:// scheme.
    If scheme is omitted, file:// scheme is assumed.

    Use /dev/stdin and /dev/stdout file names to copy a file from terminal
    and print the content of file on the storage to console.

    Examples:

    # copy local files into remote storage root
    neuro cp foo.txt bar/baz.dat storage:
    neuro cp foo.txt bar/baz.dat -t storage:

    # copy local directory `foo` into existing remote directory `bar`
    neuro cp -r foo -t storage:bar

    # copy the content of local directory `foo` into existing remote
    # directory `bar`
    neuro cp -r -T storage:foo storage:bar

    # download remote file `foo.txt` into local file `/tmp/foo.txt` with
    # explicit file:// scheme set
    neuro cp storage:foo.txt file:///tmp/foo.txt
    neuro cp -T storage:foo.txt file:///tmp/foo.txt
    neuro cp storage:foo.txt file:///tmp
    neuro cp storage:foo.txt -t file:///tmp

    # download other user's remote file into the current directory
    neuro cp storage://{username}/foo.txt .

    # download only files with extension `.out` into the current directory
    neuro cp storage:results/*.out .
    """
    target_dir: Optional[URL]
    dst: Optional[URL]
    if target_directory:
        if no_target_directory:
            raise click.UsageError(
                "Cannot combine --target-directory (-t) and --no-target-directory (-T)"
            )
        if destination is None:
            raise click.MissingParameter(
                param_type="argument", param_hint='"SOURCES..."'
            )
        sources = *sources, destination
        target_dir = parse_file_resource(target_directory, root)
        dst = None
    else:
        if destination is None:
            raise click.MissingParameter(
                param_type="argument", param_hint='"DESTINATION"'
            )
        if not sources:
            raise click.MissingParameter(
                param_type="argument", param_hint='"SOURCES..."'
            )
        dst = parse_file_resource(destination, root)
        if no_target_directory or not await _is_dir(root, dst):
            target_dir = None
        else:
            target_dir = dst
            dst = None

    filters = await calc_filters(root.client, filters)
    srcs = await _expand(sources, root, glob, allow_file=True)
    if no_target_directory and len(srcs) > 1:
        raise click.UsageError(f"Extra operand after {str(srcs[1])!r}")

    file_filter = FileFilter()
    for exclude, pattern in filters:
        log.debug("%s %s", "Exclude" if exclude else "Include", pattern)
        file_filter.append(exclude, pattern)

    show_progress = root.tty and progress

    errors = False
    for src in srcs:
        if target_dir:
            dst = target_dir / src.name
        assert dst

        progress_obj = create_storage_progress(root, show_progress)
        progress_obj.begin(src, dst)

        try:
            if src.scheme == "file" and dst.scheme == "storage":
                if recursive and await _is_dir(root, src):
                    await root.client.storage.upload_dir(
                        src,
                        dst,
                        update=update,
                        filter=file_filter.match,
                        progress=progress_obj,
                    )
                else:
                    await root.client.storage.upload_file(
                        src, dst, update=update, progress=progress_obj
                    )
            elif src.scheme == "storage" and dst.scheme == "file":
                if recursive and await _is_dir(root, src):
                    await root.client.storage.download_dir(
                        src,
                        dst,
                        update=update,
                        filter=file_filter.match,
                        progress=progress_obj,
                    )
                else:
                    await root.client.storage.download_file(
                        src, dst, update=update, progress=progress_obj
                    )
            else:
                raise RuntimeError(
                    f"Copy operation of the file with scheme '{src.scheme}'"
                    f" to the file with scheme '{dst.scheme}'"
                    f" is not supported"
                )
        except (OSError, ResourceNotFound, IllegalArgumentError) as error:
            log.error(f"cannot copy {src} to {dst}: {error}")
            errors = True

        progress_obj.end()

    if errors:
        sys.exit(EX_OSFILE)


@command()
@argument("paths", nargs=-1, required=True)
@option(
    "-p",
    "--parents",
    is_flag=True,
    help="No error if existing, make parent directories as needed",
)
async def mkdir(root: Root, paths: Sequence[str], parents: bool) -> None:
    """
    Make directories.
    """
    uris = [parse_file_resource(path, root) for path in paths]

    errors = False
    for uri in uris:
        try:
            await root.client.storage.mkdir(uri, parents=parents, exist_ok=parents)
        except (OSError, ResourceNotFound, IllegalArgumentError) as error:
            log.error(f"cannot create directory {uri}: {error}")
            errors = True
        else:
            if root.verbosity > 0:
                painter = get_painter(root.color, quote=True)
                curi = painter.paint(str(uri), FileStatusType.DIRECTORY)
                click.echo(f"created directory {curi}")

    if errors:
        sys.exit(EX_OSFILE)


@command()
@argument("sources", nargs=-1, required=False)
@argument("destination", required=False)
@option(
    "--glob/--no-glob",
    is_flag=True,
    default=True,
    show_default=True,
    help="Expand glob patterns in SOURCES",
)
@option(
    "-t",
    "--target-directory",
    metavar="DIRECTORY",
    default=None,
    help="Copy all SOURCES into DIRECTORY",
)
@option(
    "-T",
    "--no-target-directory",
    is_flag=True,
    help="Treat DESTINATION as a normal file",
)
async def mv(
    root: Root,
    sources: Sequence[str],
    destination: Optional[str],
    glob: bool,
    target_directory: Optional[str],
    no_target_directory: bool,
) -> None:
    """
    Move or rename files and directories.

    SOURCE must contain path to the
    file or directory existing on the storage, and DESTINATION must contain
    the full path to the target file or directory.

    Examples:

    # move and rename remote file
    neuro mv storage:foo.txt storage:bar/baz.dat
    neuro mv -T storage:foo.txt storage:bar/baz.dat

    # move remote files into existing remote directory
    neuro mv storage:foo.txt storage:bar/baz.dat storage:dst
    neuro mv storage:foo.txt storage:bar/baz.dat -t storage:dst

    # move the content of remote directory into other existing
    # remote directory
    neuro mv -T storage:foo storage:bar

    # move remote file into other user's directory
    neuro mv storage:foo.txt storage://{username}/bar.dat

    # move remote file from other user's directory
    neuro mv storage://{username}/foo.txt storage:bar.dat
    """
    target_dir: Optional[URL]
    dst: Optional[URL]
    if target_directory:
        if no_target_directory:
            raise click.UsageError(
                "Cannot combine --target-directory (-t) and --no-target-directory (-T)"
            )
        if destination is None:
            raise click.MissingParameter(
                param_type="argument", param_hint='"SOURCES..."'
            )
        sources = *sources, destination
        target_dir = parse_file_resource(target_directory, root)
        dst = None
    else:
        if destination is None:
            raise click.MissingParameter(
                param_type="argument", param_hint='"DESTINATION"'
            )
        if not sources:
            raise click.MissingParameter(
                param_type="argument", param_hint='"SOURCES..."'
            )
        dst = parse_file_resource(destination, root)
        if no_target_directory or not await _is_dir(root, dst):
            target_dir = None
        else:
            target_dir = dst
            dst = None

    srcs = await _expand(sources, root, glob)
    if no_target_directory and len(srcs) > 1:
        raise click.UsageError(f"Extra operand after {str(srcs[1])!r}")

    errors = False
    for src in srcs:
        if target_dir:
            dst = target_dir / src.name
        assert dst
        try:
            if root.verbosity > 0:
                painter = get_painter(root.color, quote=True)
                src_status = await root.client.storage.stat(src)
            await root.client.storage.mv(src, dst)
        except (OSError, ResourceNotFound, IllegalArgumentError) as error:
            log.error(f"cannot move {src} to {dst}: {error}")
            errors = True
        else:
            if root.verbosity > 0:
                csrc = painter.paint(str(src), src_status.type)
                cdst = painter.paint(str(dst), src_status.type)
                click.echo(f"{csrc} -> {cdst}")

    if errors:
        sys.exit(EX_OSFILE)


@command()
@click.argument("path", required=False)
@option(
    "-a",
    "--all",
    "show_all",
    is_flag=True,
    help="do not ignore entries starting with .",
)
@option(
    "--human-readable",
    "-h",
    is_flag=True,
    help="Print the size in a more human readable way.",
)
@option(
    "--size", "-s", is_flag=True, help="Print the size in bytes of each file.",
)
@option(
    "--sort",
    type=click.Choice(["name", "size", "time"]),
    default="name",
    help="sort by given field, default is name",
)
async def tree(
    root: Root, path: str, size: bool, human_readable: bool, sort: str, show_all: bool
) -> None:
    """List contents of directories in a tree-like format.

    Tree is a recursive directory listing program that produces a depth indented listing
    of files, which is colorized ala dircolors if the LS_COLORS environment variable is
    set and output is to tty.  With no arguments, tree lists the files in the storage:
    directory.  When directory arguments are given, tree lists all the files and/or
    directories found in the given directories each in turn.  Upon completion of listing
    all files/directories found, tree returns the total number of files and/or
    directories listed.

    By default PATH is equal user's home dir (storage:)

    """
    if not path:
        path = "storage:"
    uri = parse_file_resource(path, root)

    errors = False
    try:
        tree = await fetch_tree(root.client, uri, show_all)
        tree = dataclasses.replace(tree, name=str(path))
    except (OSError, ResourceNotFound) as error:
        log.error(f"cannot fetch tree for {uri}: {error}")
        errors = True
    else:
        formatter = TreeFormatter(
            color=root.color, size=size, human_readable=human_readable, sort=sort
        )
        pager_maybe(formatter(tree), root.tty, root.terminal_size)

    if errors:
        sys.exit(EX_OSFILE)


async def _expand(
    paths: Sequence[str], root: Root, glob: bool, allow_file: bool = False
) -> List[URL]:
    uris = []
    for path in paths:
        uri = parse_file_resource(path, root)
        if root.verbosity > 0:
            painter = get_painter(root.color, quote=True)
            curi = painter.paint(str(uri), FileStatusType.FILE)
            click.echo(f"Expand {curi}")
        uri_path = str(_extract_path(uri))
        if glob and globmodule.has_magic(uri_path):
            if uri.scheme == "storage":
                async for file in root.client.storage.glob(uri):
                    uris.append(file)
            elif allow_file and uri.scheme == "file":
                for p in globmodule.iglob(uri_path, recursive=True):
                    uris.append(URL(Path(p).as_uri()))
            else:
                uris.append(uri)
        else:
            uris.append(uri)
    return uris


async def _is_dir(root: Root, uri: URL) -> bool:
    if uri.scheme == "storage":
        try:
            stat = await root.client.storage.stat(uri)
            return stat.is_dir()
        except ResourceNotFound:
            pass
    elif uri.scheme == "file":
        path = _extract_path(uri)
        return path.is_dir()
    return False


storage.add_command(cp)
storage.add_command(ls)
storage.add_command(glob)
storage.add_command(rm)
storage.add_command(mkdir)
storage.add_command(mv)
storage.add_command(tree)


async def calc_filters(
    client: Client, filters: Optional[Tuple[Tuple[bool, str], ...]]
) -> Tuple[Tuple[bool, str], ...]:
    if filters is not None:
        return filters
    ret = []
    config = await client.config.get_user_config()
    section = config.get("storage")
    if section is not None:
        for flt in section.get("cp-exclude", ()):
            if flt.startswith("!"):
                ret.append((False, flt[1:]))
            else:
                ret.append((True, flt))
    return tuple(ret)


async def fetch_tree(client: Client, uri: URL, show_all: bool) -> Tree:
    loop = asyncio.get_event_loop()
    folders = []
    files = []
    tasks = []
    size = 0
    async for item in client.storage.ls(uri):
        if not show_all and item.name.startswith("."):
            continue
        if item.is_dir():
            tasks.append(
                loop.create_task(fetch_tree(client, uri / item.name, show_all))
            )
        else:
            files.append(item)
            size += item.size
    for task in tasks:
        subtree = await task
        folders.append(subtree)
        size += subtree.size
    return Tree(uri.name, size, folders, files)
