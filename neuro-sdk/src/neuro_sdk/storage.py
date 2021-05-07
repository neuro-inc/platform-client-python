import asyncio
import enum
import errno
import fnmatch
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from stat import S_ISREG
from typing import (
    AbstractSet,
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    Mapping,
    Optional,
    Tuple,
    Union,
    cast,
)

import aiohttp
import attr
from yarl import URL

from .abc import (
    AbstractDeleteProgress,
    AbstractFileProgress,
    AbstractRecursiveFileProgress,
    StorageProgressComplete,
    StorageProgressDelete,
    StorageProgressEnterDir,
    StorageProgressFail,
    StorageProgressLeaveDir,
    StorageProgressStart,
    StorageProgressStep,
    _AsyncAbstractDeleteProgress,
    _AsyncAbstractFileProgress,
    _AsyncAbstractRecursiveFileProgress,
)
from .config import Config
from .core import _Core
from .errors import ResourceNotFound
from .file_filter import AsyncFilterFunc, FileFilter
from .url_utils import (
    _extract_path,
    normalize_local_path_uri,
    normalize_storage_path_uri,
)
from .users import Action
from .utils import NoPublicConstructor, QueuedCall, queue_calls, retries

log = logging.getLogger(__name__)

MAX_OPEN_FILES = 20
READ_SIZE = 2 ** 20  # 1 MiB
TIME_THRESHOLD = 1.0

Printer = Callable[[str], None]


class FileStatusType(str, enum.Enum):
    DIRECTORY = "DIRECTORY"
    FILE = "FILE"


@dataclass(frozen=True)
class FileStatus:
    path: str
    size: int
    type: FileStatusType
    modification_time: int
    permission: Action
    uri: URL

    def is_file(self) -> bool:
        return self.type == FileStatusType.FILE

    def is_dir(self) -> bool:
        return self.type == FileStatusType.DIRECTORY

    @property
    def name(self) -> str:
        return Path(self.path).name


class Storage(metaclass=NoPublicConstructor):
    def __init__(self, core: _Core, config: Config) -> None:
        self._core = core
        self._config = config
        self._file_sem = asyncio.BoundedSemaphore(MAX_OPEN_FILES)
        self._min_time_diff = 0.0
        self._max_time_diff = 0.0

    def _normalize_uri(self, uri: URL) -> URL:
        return normalize_storage_path_uri(
            uri, self._config.username, self._config.cluster_name
        )

    def _get_storage_url(self, uri: URL, *, normalized: bool = False) -> URL:
        if not normalized:
            uri = self._normalize_uri(uri)
        assert uri.host is not None
        return self._config.get_cluster(uri.host).storage_url / uri.path.lstrip("/")

    def _set_time_diff(self, request_time: float, resp: aiohttp.ClientResponse) -> None:
        response_time = time.time()
        try:
            server_dt = parsedate_to_datetime(resp.headers.get("Date", ""))
        except ValueError:
            return
        server_time = server_dt.timestamp()
        # Remove 1 because server time has been truncated
        # and can be up to 1 second less than the actual value.
        self._min_time_diff = request_time - server_time - 1.0
        self._max_time_diff = response_time - server_time

    def _check_upload(
        self, local: os.stat_result, remote: FileStatus, update: bool, continue_: bool
    ) -> Optional[int]:
        if (
            local.st_mtime - remote.modification_time
            > self._min_time_diff - TIME_THRESHOLD
        ):
            # Local is likely newer.
            return 0
        # Remote is definitely newer.
        if update:
            return None
        if continue_:
            if local.st_size == remote.size:  # complete
                return None
            if local.st_size > remote.size:  # partial
                return remote.size
        return 0

    def _check_download(
        self, local: os.stat_result, remote: FileStatus, update: bool, continue_: bool
    ) -> Optional[int]:
        # Add 1 because remote.modification_time has been truncated
        # and can be up to 1 second less than the actual value.
        if (
            local.st_mtime - remote.modification_time
            < self._max_time_diff + TIME_THRESHOLD + 1.0
        ):
            # Remote is likely newer.
            return 0
        # Local is definitely newer.
        if update:
            return None
        if continue_:
            if local.st_size == remote.size:  # complete
                return None
            if local.st_size < remote.size:  # partial
                return local.st_size
        return 0

    async def ls(self, uri: URL) -> AsyncIterator[FileStatus]:
        uri = self._normalize_uri(uri)
        url = self._get_storage_url(uri, normalized=True)
        url = url.with_query(op="LISTSTATUS")
        headers = {"Accept": "application/x-ndjson"}

        request_time = time.time()
        auth = await self._config._api_auth()
        # NB: the storage server returns file names in FileStatus for LISTSTATUS
        # but full path for GETFILESTATUS
        async with self._core.request("GET", url, headers=headers, auth=auth) as resp:
            self._set_time_diff(request_time, resp)
            if resp.headers.get("Content-Type", "").startswith("application/x-ndjson"):
                async for line in resp.content:
                    server_message = json.loads(line)
                    self.check_for_server_error(server_message)
                    status = server_message["FileStatus"]
                    yield _file_status_from_api_ls(uri, status)
            else:
                res = await resp.json()
                for status in res["FileStatuses"]["FileStatus"]:
                    yield _file_status_from_api_ls(uri, status)

    async def glob(self, uri: URL, *, dironly: bool = False) -> AsyncIterator[URL]:
        if not _has_magic(uri.path):
            yield uri
            return
        basename = uri.name
        glob_in_dir: Callable[[URL, str, bool], AsyncIterator[URL]]
        if not _has_magic(basename):
            glob_in_dir = self._glob0
        elif not _isrecursive(basename):
            glob_in_dir = self._glob1
        else:
            glob_in_dir = self._glob2
        async for parent in self.glob(uri.parent, dironly=True):
            async for x in glob_in_dir(parent, basename, dironly):
                yield x

    async def _glob2(
        self, parent: URL, pattern: str, dironly: bool
    ) -> AsyncIterator[URL]:
        assert _isrecursive(pattern)
        yield parent
        async for x in self._rlistdir(parent, dironly):
            yield x

    async def _glob1(
        self, parent: URL, pattern: str, dironly: bool
    ) -> AsyncIterator[URL]:
        allow_hidden = _ishidden(pattern)
        match = re.compile(fnmatch.translate(pattern)).fullmatch
        async for stat in self._iterdir(parent, dironly):
            name = stat.path
            if (allow_hidden or not _ishidden(name)) and match(name):
                yield parent / name

    async def _glob0(
        self, parent: URL, basename: str, dironly: bool
    ) -> AsyncIterator[URL]:
        uri = parent / basename
        try:
            await self.stat(uri)
        except ResourceNotFound:
            return
        yield uri

    async def _iterdir(self, uri: URL, dironly: bool) -> AsyncIterator[FileStatus]:
        async for stat in self.ls(uri):
            if not dironly or stat.is_dir():
                yield stat

    async def _rlistdir(self, uri: URL, dironly: bool) -> AsyncIterator[URL]:
        async for stat in self._iterdir(uri, dironly):
            name = stat.path
            if not _ishidden(name):
                x = uri / name
                yield x
                if stat.is_dir():
                    async for y in self._rlistdir(x, dironly):
                        yield y

    async def mkdir(
        self, uri: URL, *, parents: bool = False, exist_ok: bool = False
    ) -> None:
        if not exist_ok:
            try:
                await self.stat(uri)
            except ResourceNotFound:
                pass
            else:
                raise FileExistsError(errno.EEXIST, "File exists", str(uri))

        if not parents:
            parent = uri
            while not parent.name and parent != parent.parent:
                parent = parent.parent
            parent = parent.parent
            if parent != parent.parent:
                try:
                    await self.stat(parent)
                except ResourceNotFound:
                    raise FileNotFoundError(
                        errno.ENOENT, "No such directory", str(parent)
                    )

        url = self._get_storage_url(uri)
        url = url.with_query(op="MKDIRS")
        auth = await self._config._api_auth()

        async with self._core.request("PUT", url, auth=auth) as resp:
            resp  # resp.status == 201

    async def create(self, uri: URL, data: Union[bytes, AsyncIterator[bytes]]) -> None:
        url = self._get_storage_url(uri)
        url = url.with_query(op="CREATE")
        timeout = attr.evolve(self._core.timeout, sock_read=None)
        auth = await self._config._api_auth()

        async with self._core.request(
            "PUT", url, data=data, timeout=timeout, auth=auth
        ) as resp:
            resp  # resp.status == 201

    async def write(self, uri: URL, data: bytes, offset: int) -> None:
        if not data:
            raise ValueError("empty data")
        url = self._get_storage_url(uri)
        url = url.with_query(op="WRITE")
        timeout = attr.evolve(self._core.timeout, sock_read=None)
        auth = await self._config._api_auth()
        headers = {"Content-Range": f"bytes {offset}-{offset + len(data) - 1}/*"}

        async with self._core.request(
            "PATCH", url, data=data, timeout=timeout, auth=auth, headers=headers
        ) as resp:
            resp  # resp.status == 200

    async def stat(self, uri: URL) -> FileStatus:
        uri = self._normalize_uri(uri)
        assert uri.host is not None
        url = self._get_storage_url(uri, normalized=True)
        url = url.with_query(op="GETFILESTATUS")
        auth = await self._config._api_auth()

        request_time = time.time()
        # NB: the storage server returns file names in FileStatus for LISTSTATUS
        # but full path for GETFILESTATUS
        async with self._core.request("GET", url, auth=auth) as resp:
            self._set_time_diff(request_time, resp)
            res = await resp.json()
            return _file_status_from_api_stat(uri.host, res["FileStatus"])

    async def open(
        self, uri: URL, offset: int = 0, size: Optional[int] = None
    ) -> AsyncIterator[bytes]:
        url = self._get_storage_url(uri)
        url = url.with_query(op="OPEN")
        timeout = attr.evolve(self._core.timeout, sock_read=None)
        auth = await self._config._api_auth()
        if offset < 0:
            raise ValueError("offset should be >= 0")
        if size is None:
            if offset:
                partial = True
                headers = {"Range": f"bytes={offset}-"}
            else:
                partial = False
                headers = {}
        elif size > 0:
            partial = True
            headers = {"Range": f"bytes={offset}-{offset + size - 1}"}
        elif not size:
            return
        else:
            raise ValueError("size should be >= 0")

        async with self._core.request(
            "GET", url, timeout=timeout, auth=auth, headers=headers
        ) as resp:
            if partial:
                if resp.status != aiohttp.web.HTTPPartialContent.status_code:
                    raise RuntimeError(f"Unexpected status code {resp.status}")
                rng = _parse_content_range(resp.headers.get("Content-Range"))
                if rng.start != offset:
                    raise RuntimeError("Invalid header Content-Range")

            async for data in resp.content.iter_any():
                yield data

    async def rm(
        self,
        uri: URL,
        *,
        recursive: bool = False,
        progress: Optional[AbstractDeleteProgress] = None,
    ) -> None:
        # TODO (asvetlov): add a minor protection against deleting everything from root
        # or user volume root, however force operation here should allow user to delete
        # everything.
        #
        # Now it doesn't make sense because URL for root folder (storage:///) is not
        # supported
        #
        # parts = path.split('/')
        # if final_path == root_data_path or final_path.parent == root_data_path:
        #     raise ValueError("Invalid path value.")

        async_progress: _AsyncAbstractDeleteProgress
        queue, async_progress = queue_calls(progress)
        await run_progress(
            queue, self._rm(uri, recursive=recursive, progress=async_progress)
        )

    def check_for_server_error(self, server_message: Mapping[str, Any]) -> None:
        if "error" in server_message:
            err_text = server_message["error"]
            os_errno = server_message.get("errno", None)
            if os_errno is not None:
                os_errno = errno.__dict__.get(os_errno, os_errno)
                raise OSError(os_errno, err_text)
            raise Exception(err_text)

    async def _rm(
        self, uri: URL, *, recursive: bool, progress: _AsyncAbstractDeleteProgress
    ) -> None:
        uri = self._normalize_uri(uri)
        assert uri.host is not None
        url = self._get_storage_url(uri, normalized=True)
        url = url.with_query(op="DELETE", recursive="true" if recursive else "false")
        auth = await self._config._api_auth()
        base_uri = URL.build(scheme="storage", authority=uri.host)

        headers = {"Accept": "application/x-ndjson"}

        async with self._core.request(
            "DELETE", url, headers=headers, auth=auth
        ) as resp:
            if resp.headers.get("Content-Type", "").startswith("application/x-ndjson"):
                async for line in resp.content:
                    server_message = json.loads(line)
                    self.check_for_server_error(server_message)
                    await progress.delete(
                        StorageProgressDelete(
                            uri=base_uri / server_message["path"].lstrip("/"),
                            is_dir=server_message["is_dir"],
                        )
                    )
            else:
                pass  # Old server versions do not support delete status streaming

    async def mv(self, src: URL, dst: URL) -> None:
        src = self._normalize_uri(src)
        dst = self._normalize_uri(dst)
        assert src.host is not None
        assert dst.host is not None
        if src.host != dst.host:
            raise ValueError("Cannot move cross-cluster")
        url = self._get_storage_url(src)
        url = url.with_query(op="RENAME", destination="/" + dst.path.lstrip("/"))
        auth = await self._config._api_auth()

        async with self._core.request("POST", url, auth=auth) as resp:
            resp  # resp.status == 204

    # high-level helpers

    async def upload_file(
        self,
        src: URL,
        dst: URL,
        *,
        update: bool = False,
        continue_: bool = False,
        progress: Optional[AbstractFileProgress] = None,
    ) -> None:
        src = normalize_local_path_uri(src)
        dst = normalize_storage_path_uri(
            dst, self._config.username, self._config.cluster_name
        )
        path = _extract_path(src)
        try:
            if not path.exists():
                raise FileNotFoundError(errno.ENOENT, "No such file", str(path))
            if path.is_dir():
                raise IsADirectoryError(
                    errno.EISDIR, "Is a directory, use recursive copy", str(path)
                )
        except OSError as e:
            if getattr(e, "winerror", None) not in (1, 87):
                raise
            # Ignore stat errors for device files like NUL or CON on Windows.
            # See https://bugs.python.org/issue37074
        offset: Optional[int] = 0
        try:
            dst_stat = await self.stat(dst)
            if dst_stat.is_dir():
                raise IsADirectoryError(errno.EISDIR, "Is a directory", str(dst))
        except ResourceNotFound:
            # target doesn't exist, lookup for parent dir
            try:
                dst_parent_stat = await self.stat(dst.parent)
                if not dst_parent_stat.is_dir():
                    # parent path should be a folder
                    raise NotADirectoryError(
                        errno.ENOTDIR, "Not a directory", str(dst.parent)
                    )
            except ResourceNotFound:
                raise NotADirectoryError(
                    errno.ENOTDIR, "Not a directory", str(dst.parent)
                )
        else:
            if update or continue_:
                try:
                    src_stat = path.stat()
                except OSError:
                    pass
                else:
                    if S_ISREG(src_stat.st_mode):
                        offset = self._check_upload(
                            src_stat, dst_stat, update, continue_
                        )
        if offset is None:
            return

        async_progress: _AsyncAbstractFileProgress
        queue, async_progress = queue_calls(progress)
        await run_progress(
            queue, self._upload_file(path, dst, offset, progress=async_progress)
        )

    async def _upload_file(
        self,
        src_path: Path,
        dst: URL,
        offset: int,
        *,
        progress: _AsyncAbstractFileProgress,
    ) -> None:
        src = URL(src_path.as_uri())
        loop = asyncio.get_event_loop()
        async with self._file_sem:
            with src_path.open("rb") as stream:
                size = os.stat(stream.fileno()).st_size
                await progress.start(StorageProgressStart(src, dst, size))

                if offset:
                    stream.seek(offset)
                else:
                    chunk = await loop.run_in_executor(None, stream.read, READ_SIZE)
                    for retry in retries(f"Fail to upload {dst}"):
                        async with retry:
                            await self.create(dst, chunk)
                    offset = len(chunk)

                if offset:
                    while True:
                        await progress.step(StorageProgressStep(src, dst, offset, size))
                        chunk = await loop.run_in_executor(None, stream.read, READ_SIZE)
                        if not chunk:
                            break
                        for retry in retries(f"Fail to upload {dst}"):
                            async with retry:
                                await self.write(dst, chunk, offset)
                        offset += len(chunk)

                await progress.complete(StorageProgressComplete(src, dst, size))

    async def upload_dir(
        self,
        src: URL,
        dst: URL,
        *,
        update: bool = False,
        continue_: bool = False,
        filter: Optional[AsyncFilterFunc] = None,
        ignore_file_names: AbstractSet[str] = frozenset(),
        progress: Optional[AbstractRecursiveFileProgress] = None,
    ) -> None:
        src = normalize_local_path_uri(src)
        dst = normalize_storage_path_uri(
            dst, self._config.username, self._config.cluster_name
        )
        path = _extract_path(src).resolve()
        if not path.exists():
            raise FileNotFoundError(errno.ENOENT, "No such file", str(path))
        if not path.is_dir():
            raise NotADirectoryError(errno.ENOTDIR, "Not a directory", str(path))

        if filter is None:
            filter = _always
        if ignore_file_names:
            filter = load_parent_ignore_files(filter, ignore_file_names, path)

        async_progress: _AsyncAbstractRecursiveFileProgress
        queue, async_progress = queue_calls(progress)
        await run_progress(
            queue,
            self._upload_dir(
                src,
                path,
                dst,
                "",
                update=update,
                continue_=continue_,
                filter=filter,
                ignore_file_names=ignore_file_names,
                progress=async_progress,
            ),
        )

    async def _upload_dir(
        self,
        src: URL,
        src_path: Path,
        dst: URL,
        rel_path: str,
        *,
        update: bool,
        continue_: bool,
        filter: AsyncFilterFunc,
        ignore_file_names: AbstractSet[str],
        progress: _AsyncAbstractRecursiveFileProgress,
    ) -> None:
        tasks = []
        try:
            exists = False
            if update or continue_:
                try:
                    for retry in retries(f"Fail to list {dst}"):
                        async with retry:
                            dst_files = {
                                item.name: item
                                async for item in self.ls(dst)
                                if item.is_file()
                            }
                    exists = True
                except ResourceNotFound:
                    update = continue_ = False
            if not exists:
                for retry in retries(f"Fail to create {dst}"):
                    async with retry:
                        await self.mkdir(dst, exist_ok=True)
        except FileExistsError:
            raise NotADirectoryError(errno.ENOTDIR, "Not a directory", str(dst))

        await progress.enter(StorageProgressEnterDir(src, dst))
        loop = asyncio.get_event_loop()
        async with self._file_sem:
            folder = await loop.run_in_executor(None, lambda: list(src_path.iterdir()))

        if ignore_file_names:
            for child in folder:
                if child.name in ignore_file_names and child.is_file():
                    log.debug(f"Load ignore file {rel_path}{child.name}")
                    file_filter = FileFilter(filter)
                    file_filter.read_from_file(child, prefix=rel_path)
                    filter = file_filter.match

        for child in folder:
            name = child.name
            child_rel_path = f"{rel_path}{name}"
            if child.is_dir():
                child_rel_path += "/"
            if not await filter(child_rel_path):
                log.debug(f"Skip {child_rel_path}")
                continue
            if child.is_file():
                offset: Optional[int] = 0
                if (update or continue_) and name in dst_files:
                    offset = self._check_upload(
                        child.stat(), dst_files[name], update, continue_
                    )
                if offset is None:
                    continue
                tasks.append(
                    self._upload_file(
                        src_path / name, dst / name, offset, progress=progress
                    )
                )
            elif child.is_dir():
                tasks.append(
                    self._upload_dir(
                        src / name,
                        src_path / name,
                        dst / name,
                        child_rel_path,
                        update=update,
                        continue_=continue_,
                        filter=filter,
                        ignore_file_names=ignore_file_names,
                        progress=progress,
                    )
                )
            else:
                # This case is for uploading non-regular file,
                # e.g. blocking device or unix socket
                # Coverage temporary skipped, the line is waiting for a champion
                await progress.fail(
                    StorageProgressFail(
                        src / name,
                        dst / name,
                        f"Cannot upload {child}, not regular file/directory",
                    ),
                )  # pragma: no cover
        await run_concurrently(tasks)
        await progress.leave(StorageProgressLeaveDir(src, dst))

    async def download_file(
        self,
        src: URL,
        dst: URL,
        *,
        update: bool = False,
        continue_: bool = False,
        progress: Optional[AbstractFileProgress] = None,
    ) -> None:
        src = normalize_storage_path_uri(
            src, self._config.username, self._config.cluster_name
        )
        dst = normalize_local_path_uri(dst)
        path = _extract_path(dst)
        src_stat = await self.stat(src)
        if not src_stat.is_file():
            raise IsADirectoryError(errno.EISDIR, "Is a directory", str(src))
        offset: Optional[int] = 0
        if update or continue_:
            try:
                dst_stat = path.stat()
            except OSError:
                pass
            else:
                if S_ISREG(dst_stat.st_mode):
                    offset = self._check_download(dst_stat, src_stat, update, continue_)
        if offset is None:
            return

        async_progress: _AsyncAbstractFileProgress
        queue, async_progress = queue_calls(progress)
        await run_progress(
            queue,
            self._download_file(
                src, dst, path, src_stat.size, offset, progress=async_progress
            ),
        )

    async def _download_file(
        self,
        src: URL,
        dst: URL,
        dst_path: Path,
        size: int,
        offset: int,
        *,
        progress: _AsyncAbstractFileProgress,
    ) -> None:
        loop = asyncio.get_event_loop()
        async with self._file_sem:
            await progress.start(StorageProgressStart(src, dst, size))
            with dst_path.open("rb+" if offset else "wb") as stream:
                if offset:
                    stream.seek(offset)
                for retry in retries(f"Fail to download {src}"):
                    pos = stream.tell()
                    if pos >= size:
                        break
                    async with retry:
                        it = self.open(src, offset=pos)
                        async for chunk in it:
                            pos += len(chunk)
                            await progress.step(
                                StorageProgressStep(src, dst, pos, size)
                            )
                            await loop.run_in_executor(None, stream.write, chunk)
                            if chunk:
                                retry.reset()

            await progress.complete(StorageProgressComplete(src, dst, size))

    async def download_dir(
        self,
        src: URL,
        dst: URL,
        *,
        update: bool = False,
        continue_: bool = False,
        filter: Optional[AsyncFilterFunc] = None,
        progress: Optional[AbstractRecursiveFileProgress] = None,
    ) -> None:
        if filter is None:
            filter = _always
        src = normalize_storage_path_uri(
            src, self._config.username, self._config.cluster_name
        )
        dst = normalize_local_path_uri(dst)
        path = _extract_path(dst)

        async_progress: _AsyncAbstractRecursiveFileProgress
        queue, async_progress = queue_calls(progress)
        await run_progress(
            queue,
            self._download_dir(
                src,
                dst,
                path,
                "",
                update=update,
                continue_=continue_,
                filter=filter,
                progress=async_progress,
            ),
        )

    async def _download_dir(
        self,
        src: URL,
        dst: URL,
        dst_path: Path,
        rel_path: str,
        *,
        update: bool,
        continue_: bool,
        filter: AsyncFilterFunc,
        progress: _AsyncAbstractRecursiveFileProgress,
    ) -> None:
        dst_path.mkdir(parents=True, exist_ok=True)
        await progress.enter(StorageProgressEnterDir(src, dst))
        tasks = []
        if update or continue_:
            loop = asyncio.get_event_loop()
            async with self._file_sem:
                dst_files = await loop.run_in_executor(
                    None,
                    lambda: {
                        item.name: item for item in dst_path.iterdir() if item.is_file()
                    },
                )

        for retry in retries(f"Fail to list {src}"):
            async with retry:
                folder = [item async for item in self.ls(src)]

        for child in folder:
            name = child.name
            child_rel_path = f"{rel_path}{name}"
            if child.is_dir():
                child_rel_path += "/"
            if not await filter(child_rel_path):
                log.debug(f"Skip {child_rel_path}")
                continue
            if child.is_file():
                offset: Optional[int] = 0
                if (update or continue_) and name in dst_files:
                    offset = self._check_download(
                        dst_files[name].stat(), child, update, continue_
                    )
                if offset is None:
                    continue
                tasks.append(
                    self._download_file(
                        src / name,
                        dst / name,
                        dst_path / name,
                        child.size,
                        offset,
                        progress=progress,
                    )
                )
            elif child.is_dir():
                tasks.append(
                    self._download_dir(
                        src / name,
                        dst / name,
                        dst_path / name,
                        child_rel_path,
                        update=update,
                        continue_=continue_,
                        filter=filter,
                        progress=progress,
                    )
                )
            else:
                await progress.fail(
                    StorageProgressFail(
                        src / name,
                        dst / name,
                        f"Cannot download {child}, not regular file/directory",
                    ),
                )  # pragma: no cover
        await run_concurrently(tasks)
        await progress.leave(StorageProgressLeaveDir(src, dst))


_magic_check = re.compile("(?:[*?[])")


def _has_magic(s: str) -> bool:
    return _magic_check.search(s) is not None


def _ishidden(name: str) -> bool:
    return name.startswith(".")


def _isrecursive(pattern: str) -> bool:
    return pattern == "**"


def _file_status_from_api_ls(base_uri: URL, values: Dict[str, Any]) -> FileStatus:
    return FileStatus(
        path=values["path"],
        type=FileStatusType(values["type"]),
        size=int(values["length"]),
        modification_time=int(values["modificationTime"]),
        permission=Action(values["permission"]),
        uri=base_uri / values["path"],
    )


def _file_status_from_api_stat(cluster_name: str, values: Dict[str, Any]) -> FileStatus:
    base_uri = URL.build(scheme="storage", authority=cluster_name)
    return FileStatus(
        path=values["path"],
        type=FileStatusType(values["type"]),
        size=int(values["length"]),
        modification_time=int(values["modificationTime"]),
        permission=Action(values["permission"]),
        uri=base_uri / values["path"].lstrip("/"),
    )


def _parse_content_range(rng_str: Optional[str]) -> slice:
    if rng_str is None:
        raise RuntimeError("Missed header Content-Range")
    m = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", rng_str)
    if not m:
        raise RuntimeError("Invalid header Content-Range")
    start = int(m[1])
    end = int(m[2])
    if end < start:
        raise RuntimeError("Invalid header Content-Range" + rng_str)
    return slice(start, end + 1)


ProgressQueueItem = Optional[Tuple[Callable[[Any], None], Any]]


async def run_progress(
    queue: "asyncio.Queue[QueuedCall]", coro: Awaitable[None]
) -> None:
    async def wrapped() -> None:
        try:
            await coro
        finally:
            # Add special marker to queue to allow loop below to exit
            await queue.put(cast(QueuedCall, None))

    loop = asyncio.get_event_loop()
    task = loop.create_task(wrapped())
    while True:
        item = await queue.get()
        if item is None:
            break
        item()
    await task


async def run_concurrently(coros: Iterable[Awaitable[Any]]) -> None:
    loop = asyncio.get_event_loop()
    tasks: "Iterable[asyncio.Future[Any]]" = [loop.create_task(coro) for coro in coros]
    if not tasks:
        return
    try:
        done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in done:
            await task
    except:  # noqa: E722
        for task in tasks:
            task.cancel()
        # wait for actual cancellation, ignore all exceptions raised from tasks
        if tasks:
            await asyncio.wait(tasks)
        raise  # pragma: no cover


async def _always(path: str) -> bool:
    return True


def load_parent_ignore_files(
    filter: AsyncFilterFunc,
    ignore_file_names: AbstractSet[str],
    path: Path,
    rel_path: str = "",
) -> AsyncFilterFunc:
    if path == path.parent:
        return filter
    rel_path = f"{path.name}/{rel_path}"
    path = path.parent
    filter = load_parent_ignore_files(filter, ignore_file_names, path, rel_path)
    for name in ignore_file_names:
        config_path = path / name
        if config_path.exists():
            log.debug(f"Load ignore file {str(config_path)!r}")
            file_filter = FileFilter(filter)
            file_filter.read_from_file(config_path, "", rel_path)
            filter = file_filter.match
    return filter
