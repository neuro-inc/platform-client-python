import glob as globmodule  # avoid conflict with subcommand "glob"
import logging
from typing import List, Optional, Sequence

import click
from yarl import URL

from neuromation.api.url_utils import _extract_path

from .formatters import (
    BaseFilesFormatter,
    FilesSorter,
    LongFilesFormatter,
    SimpleFilesFormatter,
    VerticalColumnsFilesFormatter,
    create_storage_progress,
)
from .root import Root
from .utils import async_cmd, command, group, parse_file_resource


log = logging.getLogger(__name__)


@group()
def storage() -> None:
    """
    Storage operations.
    """


@command()
@click.argument("paths", nargs=-1, required=True)
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    help="remove directories and their contents recursively",
)
@click.option(
    "--glob/--no-glob",
    is_flag=True,
    default=True,
    show_default=True,
    help="Expand glob patterns in PATHS",
)
@async_cmd()
async def rm(root: Root, paths: Sequence[str], recursive: bool, glob: bool) -> None:
    """
    Remove files or directories.

    Examples:

    neuro rm storage:foo/bar
    neuro rm storage://{username}/foo/bar
    neuro rm --recursive storage://{username}/foo/
    neuro rm storage:foo/**/*.tmp
    """
    for uri in await _expand(paths, root, glob):
        await root.client.storage.rm(uri, recursive=recursive)
        if root.verbosity > 0:
            click.echo(f"removed {str(uri)!r}")


@command()
@click.argument("paths", nargs=-1)
@click.option(
    "--human-readable",
    "-h",
    is_flag=True,
    help="with -l print human readable sizes (e.g., 2K, 540M)",
)
@click.option("-l", "format_long", is_flag=True, help="use a long listing format")
@click.option(
    "--sort",
    type=click.Choice(["name", "size", "time"]),
    default="name",
    help="sort by given field, default is name",
)
@async_cmd()
async def ls(
    root: Root, paths: Sequence[str], human_readable: bool, format_long: bool, sort: str
) -> None:
    """
    List directory contents.

    By default PATH is equal user's home dir (storage:)
    """
    if not paths:
        paths = ["storage:"]
    for path in paths:
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

        uri = parse_file_resource(path, root)
        if root.verbosity > 0:
            click.echo(f"List of {str(uri)!r}:")

        files = await root.client.storage.ls(uri)

        files = sorted(files, key=FilesSorter(sort).key())

        for line in formatter.__call__(files):
            click.echo(line)


@command()
@click.argument("patterns", nargs=-1, required=False)
@async_cmd()
async def glob(root: Root, patterns: Sequence[str]) -> None:
    """
    List resources that match PATTERNS.
    """
    for pattern in patterns:
        uri = parse_file_resource(pattern, root)
        log.info(f"Using pattern {str(uri)!r}:")
        async for file in root.client.storage.glob(uri):
            click.echo(file)


@command()
@click.argument("sources", nargs=-1, required=False)
@click.argument("destination", required=False)
@click.option("-r", "--recursive", is_flag=True, help="Recursive copy, off by default")
@click.option(
    "--glob/--no-glob",
    is_flag=True,
    default=True,
    show_default=True,
    help="Expand glob patterns in SOURCES with explicit scheme",
)
@click.option(
    "-t",
    "--target-directory",
    metavar="DIRECTORY",
    default=None,
    help="Copy all SOURCES into DIRECTORY",
)
@click.option(
    "-T",
    "--no-target-directory",
    is_flag=True,
    help="Treat DESTINATION as a normal file",
)
@click.option("-p", "--progress", is_flag=True, help="Show progress, off by default")
@async_cmd()
async def cp(
    root: Root,
    sources: Sequence[str],
    destination: Optional[str],
    recursive: bool,
    glob: bool,
    target_directory: Optional[str],
    no_target_directory: bool,
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
        if no_target_directory or not await root.client.storage._is_dir(dst):
            target_dir = None
        else:
            target_dir = dst
            dst = None

    srcs = await _expand(sources, root, glob, allow_file=True)
    if no_target_directory and len(srcs) > 1:
        raise click.UsageError(f"Extra operand after {str(srcs[1])!r}")

    for src in srcs:
        if target_dir:
            dst = target_dir / src.name
        assert dst

        progress_obj = create_storage_progress(progress, root.verbosity > 0)

        if src.scheme == "file" and dst.scheme == "storage":
            if recursive:
                await root.client.storage.upload_dir(src, dst, progress=progress_obj)
            else:
                await root.client.storage.upload_file(src, dst, progress=progress_obj)
        elif src.scheme == "storage" and dst.scheme == "file":
            if recursive:
                await root.client.storage.download_dir(src, dst, progress=progress_obj)
            else:
                await root.client.storage.download_file(src, dst, progress=progress_obj)
        else:
            raise RuntimeError(
                f"Copy operation of the file with scheme '{src.scheme}'"
                f" to the file with scheme '{dst.scheme}'"
                f" is not supported"
            )


@command()
@click.argument("paths", nargs=-1, required=True)
@click.option(
    "-p",
    "--parents",
    is_flag=True,
    help="No error if existing, make parent directories as needed",
)
@async_cmd()
async def mkdir(root: Root, paths: Sequence[str], parents: bool) -> None:
    """
    Make directories.
    """

    for path in paths:
        uri = parse_file_resource(path, root)

        await root.client.storage.mkdirs(uri, parents=parents, exist_ok=parents)
        if root.verbosity > 0:
            click.echo(f"created directory {str(uri)!r}")


@command()
@click.argument("sources", nargs=-1, required=False)
@click.argument("destination", required=False)
@click.option(
    "--glob/--no-glob",
    is_flag=True,
    default=True,
    show_default=True,
    help="Expand glob patterns in SOURCES",
)
@click.option(
    "-t",
    "--target-directory",
    metavar="DIRECTORY",
    default=None,
    help="Copy all SOURCES into DIRECTORY",
)
@click.option(
    "-T",
    "--no-target-directory",
    is_flag=True,
    help="Treat DESTINATION as a normal file",
)
@async_cmd()
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
        if no_target_directory or not await root.client.storage._is_dir(dst):
            target_dir = None
        else:
            target_dir = dst
            dst = None

    srcs = await _expand(sources, root, glob)
    if no_target_directory and len(srcs) > 1:
        raise click.UsageError(f"Extra operand after {str(srcs[1])!r}")

    for src in srcs:
        if target_dir:
            dst = target_dir / src.name
        assert dst
        await root.client.storage.mv(src, dst)
        if root.verbosity > 0:
            click.echo(f"{str(src)!r} -> {str(dst)!r}")


async def _expand(
    paths: Sequence[str], root: Root, glob: bool, allow_file: bool = False
) -> List[URL]:
    uris = []
    for path in paths:
        uri = parse_file_resource(path, root)
        log.info(f"Expand {uri!r}")
        uri_path = str(_extract_path(uri))
        if glob and globmodule.has_magic(uri_path):
            if uri.scheme == "storage":
                async for file in root.client.storage.glob(uri):
                    uris.append(file)
            elif allow_file and path.startswith("file:"):
                for p in globmodule.iglob(uri_path, recursive=True):
                    uris.append(uri.with_path(p))
            else:
                uris.append(uri)
        else:
            uris.append(uri)
    return uris


storage.add_command(cp)
storage.add_command(ls)
storage.add_command(glob)
storage.add_command(rm)
storage.add_command(mkdir)
storage.add_command(mv)
