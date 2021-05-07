import asyncio
import base64
import errno
import hashlib
import itertools
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePath
from stat import S_ISREG
from typing import (
    AbstractSet,
    Any,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
)

import aiohttp
import attr
from dateutil.parser import isoparse
from yarl import URL

from .abc import (
    AbstractFileProgress,
    AbstractRecursiveFileProgress,
    StorageProgressComplete,
    StorageProgressEnterDir,
    StorageProgressFail,
    StorageProgressLeaveDir,
    StorageProgressStart,
    StorageProgressStep,
    _AsyncAbstractFileProgress,
    _AsyncAbstractRecursiveFileProgress,
)
from .config import Config
from .core import _Core
from .errors import ResourceNotFound
from .file_filter import AsyncFilterFunc, FileFilter, translate
from .storage import (
    TIME_THRESHOLD,
    _always,
    _has_magic,
    _magic_check,
    _parse_content_range,
    load_parent_ignore_files,
    run_concurrently,
    run_progress,
)
from .url_utils import _extract_path, normalize_blob_path_uri, normalize_local_path_uri
from .users import Action
from .utils import NoPublicConstructor, queue_calls, retries

if sys.version_info >= (3, 7):  # pragma: no cover
    from contextlib import asynccontextmanager
else:
    from async_generator import asynccontextmanager


log = logging.getLogger(__name__)

MAX_OPEN_FILES = 20
READ_SIZE = 2 ** 20  # 1 MiB

ProgressQueueItem = Optional[Any]


def _format_bucket_uri(bucket_name: str, key: str = "") -> URL:
    if key:
        return URL("blob:") / bucket_name / key
    else:
        return URL("blob:") / bucket_name


@dataclass(frozen=True)
class BucketListing:
    name: str
    creation_time: int
    # XXX: Add real bucket permission access level
    permission: Action = Action.READ

    @property
    def uri(self) -> URL:
        return _format_bucket_uri(self.name, "")

    def is_file(self) -> bool:
        return False

    def is_dir(self) -> bool:
        # Let's treat buckets as dirs in formatter output
        return True

    @property
    def modification_time(self) -> int:
        return self.creation_time


@dataclass(frozen=True)
class BlobListing:
    key: str
    size: int
    modification_time: int

    @property
    def name(self) -> str:
        return PurePath(self.key).name

    bucket_name: str

    @property
    def uri(self) -> URL:
        return _format_bucket_uri(self.bucket_name, self.key)

    @property
    def path(self) -> str:
        return self.key

    # It common pattern to make treat keys with `/` at the end as folder keys.
    # It may be returned as part of recursive results if created explicitly on
    # the Blob storage backend.

    def is_file(self) -> bool:
        return not self.key.endswith("/")

    def is_dir(self) -> bool:
        return self.key.endswith("/")


@dataclass(frozen=True)
class PrefixListing:
    prefix: str

    @property
    def name(self) -> str:
        return PurePath(self.prefix).name

    bucket_name: str

    @property
    def uri(self) -> URL:
        return _format_bucket_uri(self.bucket_name, self.prefix)

    @property
    def path(self) -> str:
        return self.prefix

    def is_file(self) -> bool:
        return False

    def is_dir(self) -> bool:
        return True


class Blob:
    def __init__(self, resp: aiohttp.ClientResponse, stats: BlobListing):
        self._resp = resp
        self.stats = stats

    @property
    def body_stream(self) -> aiohttp.StreamReader:
        return self._resp.content


class BlobStorage(metaclass=NoPublicConstructor):
    def __init__(self, core: _Core, config: Config) -> None:
        self._core = core
        self._config = config
        self._default_batch_size = 1000
        self._file_sem = asyncio.BoundedSemaphore(MAX_OPEN_FILES)
        self._min_time_diff = 0.0
        self._max_time_diff = 0.0

    async def list_buckets(self) -> List[BucketListing]:
        url = self._config.blob_storage_url / "b" / ""
        auth = await self._config._api_auth()

        async with self._core.request("GET", url, auth=auth) as resp:
            res = await resp.json()
            return [_bucket_status_from_data(bucket) for bucket in res]

    async def create_bucket(self, bucket_name: str) -> None:
        url = self._config.blob_storage_url / "b" / bucket_name
        auth = await self._config._api_auth()

        async with self._core.request("PUT", url, auth=auth) as resp:
            assert resp.status == 200

    async def delete_bucket(self, bucket_name: str) -> None:
        url = self._config.blob_storage_url / "b" / bucket_name
        auth = await self._config._api_auth()

        async with self._core.request("DELETE", url, auth=auth) as resp:
            assert resp.status == 204

    async def list_blobs(
        self,
        bucket_name: str,
        prefix: str = "",
        recursive: bool = False,
        max_keys: Optional[int] = None,
    ) -> Tuple[Sequence[BlobListing], Sequence[PrefixListing]]:
        contents: List[BlobListing] = []
        common_prefixes: List[PrefixListing] = []

        async for blobs, prefixes in self._iter_blob_pages(
            bucket_name, prefix, recursive=recursive, max_keys=max_keys
        ):
            contents.extend(blobs)
            common_prefixes.extend(prefixes)
        return contents, common_prefixes

    async def _iter_blob_pages(
        self,
        bucket_name: str,
        prefix: str = "",
        *,
        recursive: bool = False,
        batch_size: Optional[int] = None,
        max_keys: Optional[int] = None,
    ) -> AsyncIterator[Tuple[Sequence[BlobListing], Sequence[PrefixListing]]]:
        url = self._config.blob_storage_url / "o" / bucket_name
        auth = await self._config._api_auth()
        if batch_size is None:
            batch_size = self._default_batch_size

        # 1st page may be less then max_keys
        next_page_size = batch_size
        if max_keys is not None:
            next_page_size = min(batch_size, max_keys)

        query = {"recursive": str(recursive).lower(), "max_keys": str(next_page_size)}
        if prefix:
            query["prefix"] = prefix
        url = url.with_query(query)

        while True:
            request_time = time.time()
            async with self._core.request("GET", url, auth=auth) as resp:
                self._set_time_diff(request_time, resp)
                res = await resp.json()
            contents = [
                _blob_status_from_key(bucket_name, key) for key in res["contents"]
            ]

            common_prefixes = [
                _blob_status_from_prefix(bucket_name, prefix)
                for prefix in res["common_prefixes"]
            ]
            yield contents, common_prefixes

            if res["is_truncated"]:
                continuation_token = res["continuation_token"]
                url = url.update_query(continuation_token=continuation_token)
                # Limit the next page if we are reaching max_keys limit
                if max_keys is not None:
                    max_keys -= len(contents) + len(common_prefixes)
                    if max_keys <= 0:
                        break
                    next_page_size = min(max_keys, batch_size)
                    url = url.update_query(max_keys=str(next_page_size))
            else:
                break

    async def glob_blobs(
        self, bucket_name: str, pattern: str
    ) -> AsyncIterator[BlobListing]:
        pattern = pattern.lstrip("/")

        async for blob in self._glob_search(bucket_name, "", pattern):
            yield blob

    async def _glob_search(
        self, bucket_name: str, prefix: str, pattern: str
    ) -> AsyncIterator[BlobListing]:
        part, _, remaining = pattern.partition("/")

        # Yield all remaining files recursively, as *all* keys may match the query
        # **/.json
        if _isrecursive(part):
            full_match = re.compile(translate(pattern)).fullmatch
            async for blobs, prefixes in self._iter_blob_pages(
                bucket_name, prefix, recursive=True
            ):
                assert not prefixes, "No prefixes in recursive mode"
                for blob in blobs:
                    if full_match(blob.key[len(prefix) :]):
                        yield blob
            return

        has_magic = _has_magic(part)
        # Optimize the prefix for matching. If we have a pattern `folder1/b*/*.json`
        # it's better to scan with prefix `folder1/b` on the 2nd step, not `folder1/`
        if has_magic:
            opt_prefix = prefix + _glob_safe_prefix(part)
            match = re.compile(translate(part)).fullmatch

        # If this is the last part in the search pattern we have to scan keys, not
        # just prefixes
        if not remaining:
            if has_magic:
                async for blobs, _ in self._iter_blob_pages(
                    bucket_name, opt_prefix, recursive=False
                ):
                    for blob in blobs:
                        if match(blob.name):
                            yield blob
            else:
                try:
                    blob = await self.head_blob(bucket_name, prefix + part)
                    yield blob
                except ResourceNotFound:
                    pass
            return

        # We can be sure no blobs on this level will match the pattern, as results are
        # deeper down the tree. Recursively scan folders only.
        if has_magic:
            async for blobs, prefixes in self._iter_blob_pages(
                bucket_name, opt_prefix, recursive=False
            ):
                for folder in prefixes:
                    if not match(folder.name):
                        continue
                    async for blob in self._glob_search(
                        bucket_name, folder.prefix, remaining
                    ):
                        yield blob

        else:
            async for blob in self._glob_search(
                bucket_name, prefix + part + "/", remaining
            ):
                yield blob

    async def head_blob(self, bucket_name: str, key: str) -> BlobListing:
        url = self._config.blob_storage_url / "o" / bucket_name / key
        auth = await self._config._api_auth()

        request_time = time.time()
        async with self._core.request("HEAD", url, auth=auth) as resp:
            self._set_time_diff(request_time, resp)
            return _blob_status_from_response(bucket_name, key, resp)

    @asynccontextmanager
    async def get_blob(
        self, bucket_name: str, key: str, offset: int = 0, size: Optional[int] = None
    ) -> AsyncIterator[Blob]:
        """Return blob status and body stream of the blob"""
        url = self._config.blob_storage_url / "o" / bucket_name / key
        auth = await self._config._api_auth()

        timeout = attr.evolve(self._core.timeout, sock_read=None)
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
        else:
            raise ValueError("size should be > 0")

        async with self._core.request(
            "GET", url, timeout=timeout, auth=auth, headers=headers
        ) as resp:
            if partial:
                if resp.status != aiohttp.web.HTTPPartialContent.status_code:
                    raise RuntimeError(f"Unexpected status code {resp.status}")
                rng = _parse_content_range(resp.headers.get("Content-Range"))
                if rng.start != offset:
                    raise RuntimeError("Invalid header Content-Range")

            stats = _blob_status_from_response(bucket_name, key, resp)
            yield Blob(resp, stats)

    async def fetch_blob(
        self, bucket_name: str, key: str, offset: int = 0, size: Optional[int] = None
    ) -> AsyncIterator[bytes]:
        """Return only bytes data of the blob"""
        async with self.get_blob(bucket_name, key, offset=offset, size=size) as blob:
            async for data in blob.body_stream.iter_any():
                yield data

    async def put_blob(
        self,
        bucket_name: str,
        key: str,
        body: Union[AsyncIterator[bytes], bytes],
        size: Optional[int] = None,
        content_md5: Optional[str] = None,
    ) -> str:
        url = self._config.blob_storage_url / "o" / bucket_name / key
        auth = await self._config._api_auth()
        timeout = attr.evolve(self._core.timeout, sock_read=None)

        if isinstance(body, bytes):
            size = len(body)
        elif not isinstance(body, AsyncIterator):
            raise ValueError(
                "`body` should be either of type `bytes` or an `AsyncIterator`"
            )
        elif size is None:
            raise ValueError("`size` is required if `body` is an `AsyncIterator`")

        # We don't provide Content-Length as transfer endcoding will be `chunked`.
        # But the server needs to know the decoded length of the file.
        headers = {"X-Content-Length": str(size)}
        if content_md5 is not None:
            headers["Content-MD5"] = content_md5

        async with self._core.request(
            "PUT", url, data=body, timeout=timeout, auth=auth, headers=headers
        ) as resp:
            etag = resp.headers["ETag"]
            return etag

    async def delete_blob(self, bucket_name: str, key: str) -> None:
        url = self._config.blob_storage_url / "o" / bucket_name / key
        auth = await self._config._api_auth()

        async with self._core.request("DELETE", url, auth=auth) as resp:
            assert resp.status == 204

    # high-level helpers

    async def _iterate_file(
        self,
        src: Path,
        dst: URL,
        size: int,
        *,
        progress: _AsyncAbstractFileProgress,
    ) -> AsyncIterator[bytes]:
        loop = asyncio.get_event_loop()
        src_url = URL(src.as_uri())
        async with self._file_sem:
            with src.open("rb") as stream:
                await progress.start(StorageProgressStart(src_url, dst, size))
                chunk = await loop.run_in_executor(None, stream.read, READ_SIZE)
                pos = len(chunk)
                while chunk:
                    await progress.step(StorageProgressStep(src_url, dst, pos, size))
                    yield chunk
                    chunk = await loop.run_in_executor(None, stream.read, READ_SIZE)
                    pos += len(chunk)
                await progress.complete(StorageProgressComplete(src_url, dst, size))

    def _extract_bucket_and_key(self, uri: URL) -> Tuple[str, str]:
        cluster_name = self._config.cluster_name
        uri = normalize_blob_path_uri(uri, cluster_name)
        if uri.host != self._config.cluster_name:
            raise ValueError(
                f"When using full URL's please specify cluster name "
                f"{cluster_name!r} as host part. For example: "
                f"blob://{cluster_name}/my_bucket/path/to/file."
            )
        bucket_name, _, key = uri.path.lstrip("/").partition("/")
        return bucket_name, key

    async def _is_dir(self, uri: URL) -> bool:
        """Check if provided path is an dir or serves as a prefix to a different key,
        as it would result in name conflicts on download.
        """
        if uri.path.endswith("/"):
            return True
        # Check if a folder key exists. As `/` at the end makes a different key, make
        # sure we ask for one with ending slash.
        bucket_name, key = self._extract_bucket_and_key(uri)

        # bucket "root" should always be considered a directory
        if not key:
            return True

        blobs, prefixes = await self.list_blobs(
            bucket_name=bucket_name, prefix=key + "/", recursive=False, max_keys=1
        )
        return bool(blobs) or bool(prefixes)

    async def _mkdir(self, uri: URL) -> None:
        bucket_name, key = self._extract_bucket_and_key(uri)
        assert key.endswith("/"), "Key should end with a trailing slash"
        assert key.strip("/"), "Can not create a bucket root folder"
        await self.put_blob(bucket_name=bucket_name, key=key, body=b"")

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
        self, local: os.stat_result, remote: BlobListing
    ) -> Optional[int]:
        if (
            local.st_mtime - remote.modification_time
            > self._min_time_diff - TIME_THRESHOLD
        ):
            # Local is likely newer.
            return 0
        # Remote is definitely newer.
        return None

    def _check_download(
        self, local: os.stat_result, remote: BlobListing, update: bool, continue_: bool
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

    def make_url(self, bucket_name: str, key: str) -> URL:
        """Helper function to let users create correct URL's for upload/download from
        bucket_name and key.
        """
        return _format_bucket_uri(bucket_name, key)

    async def upload_file(
        self,
        src: URL,
        dst: URL,
        *,
        update: bool = False,
        progress: Optional[AbstractFileProgress] = None,
    ) -> None:
        src = normalize_local_path_uri(src)
        dst = normalize_blob_path_uri(dst, self._config.cluster_name)

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

        # Avoid name conflicts when uploading
        bucket_name, key = self._extract_bucket_and_key(dst)
        parent, _, _ = key.rpartition("/")
        if await self._is_dir(dst):
            # Uploading to keys like `prefix/` is prohibited, as they count as `folder`
            # keys and should only be 0-sized blobs.
            raise IsADirectoryError(errno.EISDIR, "Is a directory", str(dst))
        elif parent:
            # We can't upload files to path like: `path/to/file.txt/new_file.json`
            # if a file `path/to/file.txt` already exists. This is likely an error in
            # the cli command call and will cause confusing behaviour on download.
            assert not parent.endswith("/")
            try:
                await self.head_blob(bucket_name=bucket_name, key=parent)
            except ResourceNotFound:
                pass
            else:
                raise NotADirectoryError(
                    errno.ENOTDIR, "Not a directory", str(dst.parent)
                )

        if update:
            try:
                dst_stat = await self.head_blob(bucket_name=bucket_name, key=key)
            except ResourceNotFound:
                pass
            else:
                try:
                    src_stat = path.stat()
                except OSError:
                    pass
                else:
                    if S_ISREG(src_stat.st_mode):
                        offset = self._check_upload(src_stat, dst_stat)
                        if offset is None:
                            return

        async_progress: _AsyncAbstractFileProgress
        queue, async_progress = queue_calls(progress)
        await run_progress(queue, self._upload_file(path, dst, progress=async_progress))

    async def _upload_file(
        self,
        src_path: Path,
        dst: URL,
        *,
        progress: _AsyncAbstractFileProgress,
    ) -> None:
        bucket_name, key = self._extract_bucket_and_key(dst)
        # Be careful not to have too many opened files.
        async with self._file_sem:
            content_md5, size = await calc_md5(src_path)

        for retry in retries(f"Fail to upload {dst}"):
            async with retry:
                await self.put_blob(
                    bucket_name=bucket_name,
                    key=key,
                    body=self._iterate_file(src_path, dst, size, progress=progress),
                    size=size,
                    content_md5=content_md5,
                )

    async def upload_dir(
        self,
        src: URL,
        dst: URL,
        *,
        update: bool = False,
        filter: Optional[AsyncFilterFunc] = None,
        ignore_file_names: AbstractSet[str] = frozenset(),
        progress: Optional[AbstractRecursiveFileProgress] = None,
    ) -> None:
        src = normalize_local_path_uri(src)
        dst = normalize_blob_path_uri(dst, self._config.cluster_name)
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
        filter: AsyncFilterFunc,
        ignore_file_names: AbstractSet[str],
        progress: _AsyncAbstractRecursiveFileProgress,
    ) -> None:
        tasks = []
        if not dst.path.endswith("/"):
            dst = dst / ""

        bucket_name, key = self._extract_bucket_and_key(dst)
        key = key.strip("/")
        exists = False
        if update:
            if key:
                key += "/"
            try:
                for retry in retries(f"Fail to list {dst}"):
                    async with retry:
                        blobs, _ = await self.list_blobs(
                            bucket_name=bucket_name, prefix=key, recursive=False
                        )
                        dst_files = {x.name: x for x in blobs}
                exists = True
            except ResourceNotFound:
                update = False
        else:
            if key:
                try:
                    # Make sure we don't have name conflicts
                    # We can't upload to folder `/path/to/file.txt/` if
                    # `/path/to/file.txt` already exists
                    await self.head_blob(bucket_name=bucket_name, key=key)
                except ResourceNotFound:
                    pass
                else:
                    raise NotADirectoryError(errno.ENOTDIR, "Not a directory", str(dst))
            else:
                # Only create folder if we are not uploading to bucket root
                exists = True
        if not exists:
            for retry in retries(f"Fail to create {dst}"):
                async with retry:
                    await self._mkdir(dst)

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
                if update and name in dst_files:
                    offset = self._check_upload(child.stat(), dst_files[name])
                    if offset is None:
                        continue
                tasks.append(
                    self._upload_file(src_path / name, dst / name, progress=progress)
                )
            elif child.is_dir():
                tasks.append(
                    self._upload_dir(
                        src / name,
                        src_path / name,
                        dst / name,
                        child_rel_path,
                        update=update,
                        filter=filter,
                        ignore_file_names=ignore_file_names,
                        progress=progress,
                    )
                )
            else:
                await progress.fail(
                    StorageProgressFail(
                        src / name,
                        dst / name,
                        f"Cannot upload {child}, not regular file/directory",
                    )
                )
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
        src = normalize_blob_path_uri(src, self._config.cluster_name)
        dst = normalize_local_path_uri(dst)
        path = _extract_path(dst)
        bucket_name, key = self._extract_bucket_and_key(src)
        src_stat = await self.head_blob(bucket_name=bucket_name, key=key)

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
                        bucket_name, key = self._extract_bucket_and_key(src)
                        async for chunk in self.fetch_blob(
                            bucket_name=bucket_name, key=key, offset=pos
                        ):
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
        src = normalize_blob_path_uri(src, self._config.cluster_name)
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

        bucket_name, folder_key = self._extract_bucket_and_key(src)
        prefix_path = folder_key.strip("/")
        # If we are downloading the whole bucket we need to specify an empty prefix '',
        # not "/", thus only add it if path not empty
        if prefix_path:
            prefix_path += "/"
        for retry in retries(f"Fail to list {src}"):
            async with retry:
                blobs, prefixes = await self.list_blobs(
                    bucket_name=bucket_name, prefix=prefix_path, recursive=False
                )

        for child in itertools.chain(blobs, prefixes):
            child = cast(Union[PrefixListing, BlobListing], child)

            # Skip "folder" keys, as they will be returned as BlobListing results again,
            # previously being a common prefix, ie. PrefixListing.
            if child.path == prefix_path:
                continue

            name = child.name
            assert child.path.startswith(prefix_path)
            child_rel_path = child.path[len(prefix_path) :]
            if child.is_dir():
                child_rel_path += "/"
            if not await filter(child_rel_path):
                log.debug(f"Skip {child_rel_path}")
                continue
            if child.is_file():
                # Only BlobListing can be a file, so it's safe to just cast
                child = cast(BlobListing, child)
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
            else:
                tasks.append(
                    self._download_dir(
                        src / name,
                        dst / name,
                        dst_path / name,
                        update=update,
                        continue_=continue_,
                        filter=filter,
                        progress=progress,
                    )
                )
        await run_concurrently(tasks)
        await progress.leave(StorageProgressLeaveDir(src, dst))


def _glob_safe_prefix(pattern: str) -> str:
    return _magic_check.split(pattern, 1)[0]


def _isrecursive(pattern: str) -> bool:
    return pattern == "**"


def _bucket_status_from_data(data: Dict[str, Any]) -> BucketListing:
    mtime = isoparse(data["creation_date"]).timestamp()
    return BucketListing(
        name=data["name"],
        creation_time=int(mtime),
        permission=Action(data.get("permission", "read")),
    )


def _blob_status_from_key(bucket_name: str, data: Dict[str, Any]) -> BlobListing:
    return BlobListing(
        bucket_name=bucket_name,
        key=data["key"],
        size=int(data["size"]),
        modification_time=int(data["last_modified"]),
    )


def _blob_status_from_prefix(bucket_name: str, data: Dict[str, Any]) -> PrefixListing:
    return PrefixListing(bucket_name=bucket_name, prefix=data["prefix"])


def _blob_status_from_response(
    bucket_name: str, key: str, resp: aiohttp.ClientResponse
) -> BlobListing:
    try:
        dt = parsedate_to_datetime(resp.headers.get("Last-Modified", ""))
        modification_time = int(dt.timestamp())
    except ValueError:
        modification_time = 0
    return BlobListing(
        bucket_name=bucket_name,
        key=key,
        size=resp.content_length or 0,
        modification_time=modification_time,
    )


async def calc_md5(path: Path) -> Tuple[str, int]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _calc_md5_blocking, path)


def _calc_md5_blocking(path: Path) -> Tuple[str, int]:
    md5 = hashlib.md5()
    size = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(READ_SIZE)
            if not chunk:
                break
            md5.update(chunk)
            size += len(chunk)
    return base64.b64encode(md5.digest()).decode("ascii"), size
