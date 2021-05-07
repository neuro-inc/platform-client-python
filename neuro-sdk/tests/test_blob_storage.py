import asyncio
import base64
import hashlib
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, NoReturn, Optional, Set
from unittest import mock

import pytest
from aiohttp import web
from yarl import URL

import neuro_sdk.blob_storage
from neuro_sdk import (
    Action,
    BlobListing,
    BucketListing,
    Client,
    PrefixListing,
    StorageProgressComplete,
    StorageProgressStart,
    StorageProgressStep,
)
from neuro_sdk.blob_storage import calc_md5

from tests import _TestServerFactory

_MakeClient = Callable[..., Client]


FOLDER = Path(__file__).parent
DATA_FOLDER = FOLDER / "data"


class BlobUrlRotes:

    LIST_BUCKETS = r"/blob/b/"
    PUT_BUCKET = r"/blob/b/{bucket}"
    DELETE_BUCKET = r"/blob/b/{bucket}"

    LIST_OBJECTS = r"/blob/o/{bucket}"
    HEAD_OBJECT = r"/blob/o/{bucket}/{path:.+}"
    GET_OBJECT = r"/blob/o/{bucket}/{path:.+}"
    PUT_OBJECT = r"/blob/o/{bucket}/{path:.+}"
    DELETE_OBJECT = r"/blob/o/{bucket}/{path:.+}"


# Bucket `foo` structure
# foo
# ├── empty/
# ├── folder1/
# │   ├── xxx.txt
# │   └── yyy.json
# ├── folder2/
# │   └── big_file
# ├── test.json
# ├── test1.txt
# └── test2.txt


_ContentsObj = Dict[str, Dict[str, Any]]


def dir_list(path: Path) -> List[Dict[str, Any]]:
    # List all files and folders in directory
    res = []
    for item in path.glob("**/*"):
        if item.is_dir():
            res.append({"path": str(item.relative_to(path)), "dir": True})
        else:
            body = item.read_bytes().replace(b"\n\r", b"\n")
            res.append(
                {
                    "path": item.relative_to(path).as_posix(),
                    "dir": False,
                    "size": len(body),
                    "body": body,  # Fix Windows
                }
            )
    return res


@pytest.fixture
def blob_storage_contents() -> _ContentsObj:
    mtime1 = datetime(2019, 1, 1).timestamp()
    mtime2 = datetime(2019, 1, 2).timestamp()

    contents: Dict[str, Dict[str, Any]] = {
        "empty/": {
            "key": "empty/",
            "size": 0,
            "last_modified": mtime1,
            "body": b"",
        },
        "folder1/xxx.txt": {
            "key": "folder1/xxx.txt",
            "size": 1,
            "last_modified": mtime1,
            "body": b"w",
        },
        "folder1/yyy.json": {
            "key": "folder1/yyy.json",
            "size": 2,
            "last_modified": mtime2,
            "body": b"bb",
        },
        "test.json": {
            "key": "test.json",
            "size": 213,
            "last_modified": mtime1,
            "body": b"w" * 213,
        },
        "test1.txt": {
            "key": "test1.txt",
            "size": 111,
            "last_modified": mtime1,
            "body": b"w" * 111,
        },
        "test2.txt": {
            "key": "test2.txt",
            "size": 222,
            "last_modified": mtime2,
            "body": b"w" * 222,
        },
    }
    return contents


@pytest.fixture
async def blob_storage_server(
    aiohttp_server: _TestServerFactory,
    blob_storage_contents: _ContentsObj,
) -> Any:
    """Minimal functional Blob Storage server implementation"""
    CONTENTS = blob_storage_contents

    def with_keys(d: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
        res = {}
        for k, v in d.items():
            if k in keys:
                res[k] = v
        return res

    LIST_KEYS = ["key", "size", "last_modified"]

    app = web.Application()
    # fill route table

    async def list_buckets(request: web.Request) -> web.Response:
        assert "b3" in request.headers
        return web.json_response(
            [{"name": "foo", "creation_date": datetime(2019, 1, 1).isoformat()}]
        )

    async def list_blobs(request: web.Request) -> web.Response:
        assert "b3" in request.headers
        assert request.match_info["bucket"] == "foo"

        res: Dict[str, Any]
        prefix = request.query.get("prefix", "")
        contents = [
            with_keys(item, LIST_KEYS)
            for item in CONTENTS.values()
            if item["key"].startswith(prefix)
        ]
        common_prefixes: Set[str] = set()
        if request.query["recursive"] == "false":
            new_contents = []
            for item in contents:
                pos = item["key"].find("/", len(prefix))
                if pos != -1:
                    common_prefixes.add(item["key"][: pos + 1])
                else:
                    new_contents.append(item)
            contents = new_contents

        return web.json_response(
            {
                "contents": sorted(contents, key=lambda x: x["key"]),
                "common_prefixes": [{"prefix": p} for p in sorted(common_prefixes)],
                "is_truncated": False,
            }
        )

    async def get_blob(request: web.Request) -> web.StreamResponse:
        assert "b3" in request.headers
        assert request.match_info["bucket"] == "foo"

        key = request.match_info["path"]
        if key not in CONTENTS:
            raise web.HTTPNotFound()
        blob = CONTENTS[key]

        rng = request.http_range
        content = blob["body"]
        resp = web.StreamResponse(status=200)
        etag = hashlib.md5(blob["body"]).hexdigest()
        resp.headers.update({"ETag": repr(etag)})
        resp.last_modified = int(blob["last_modified"])  # type: ignore
        start, stop, _ = rng.indices(len(content))
        if not (rng.start is rng.stop is None):
            if start >= stop:
                raise RuntimeError
            resp.set_status(web.HTTPPartialContent.status_code)
            resp.headers["Content-Range"] = f"bytes {start}-{stop-1}/{len(content)}"
        resp.content_length = stop - start
        resp.content_type = "application/octet-stream"
        await resp.prepare(request)
        if request.method != "HEAD":
            chunk_size = max(len(content) * 2 // 5, 200)
            if stop - start > chunk_size:
                await resp.write(content[start : start + chunk_size])
                raise RuntimeError
            else:
                await resp.write(content[start:stop])
                await resp.write_eof()
        return resp

    async def put_blob(request: web.Request) -> web.Response:
        assert "b3" in request.headers
        assert request.match_info["bucket"] == "foo"

        key = request.match_info["path"]
        body = await request.content.read()
        blob = {
            "key": key,
            "size": len(body),
            "last_modified": time.time(),
            "body": body,
        }
        CONTENTS[key] = blob
        etag = hashlib.md5(body).hexdigest()

        return web.Response(headers={"ETag": repr(etag)})

    async def delete_blob(request: web.Request) -> NoReturn:
        assert "b3" in request.headers
        assert request.match_info["bucket"] == "foo"

        key = request.match_info["path"]
        if key not in CONTENTS:
            raise web.HTTPNotFound()

        del CONTENTS[key]

        raise web.HTTPNoContent()

    app = web.Application()
    app.router.add_get(BlobUrlRotes.LIST_BUCKETS, list_buckets)
    app.router.add_get(BlobUrlRotes.LIST_OBJECTS, list_blobs)
    # HEAD will also use this
    app.router.add_get(BlobUrlRotes.GET_OBJECT, get_blob)
    app.router.add_put(BlobUrlRotes.PUT_OBJECT, put_blob)
    app.router.add_delete(BlobUrlRotes.DELETE_OBJECT, delete_blob)

    return await aiohttp_server(app)


async def test_blob_storage_list_buckets(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    mtime1 = datetime.now()
    mtime2 = datetime.now()
    JSON = [
        {"name": "foo", "creation_date": mtime1.isoformat()},
        {"name": "bar", "creation_date": mtime2.isoformat()},
    ]

    async def handler(request: web.Request) -> web.Response:
        assert "b3" in request.headers
        assert request.path == BlobUrlRotes.LIST_BUCKETS
        assert request.query == {}
        return web.json_response(JSON)

    app = web.Application()
    app.router.add_get(BlobUrlRotes.LIST_BUCKETS, handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        ret = await client.blob_storage.list_buckets()

    assert ret == [
        BucketListing(
            name="foo",
            creation_time=int(mtime1.timestamp()),
            permission=Action.READ,
        ),
        BucketListing(
            name="bar",
            creation_time=int(mtime2.timestamp()),
            permission=Action.READ,
        ),
    ]


async def test_blob_storage_create_bucket(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    name = "my_bucket"

    async def handler(request: web.Request) -> web.Response:
        assert "b3" in request.headers
        assert request.path == BlobUrlRotes.PUT_BUCKET.format(bucket=name)
        assert request.query == {}
        return web.json_response({"location": "ua-east-1"})

    app = web.Application()
    app.router.add_put(BlobUrlRotes.PUT_BUCKET, handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        await client.blob_storage.create_bucket(name)


async def test_blob_storage_delete_bucket(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    name = "my_bucket"

    async def handler(request: web.Request) -> web.Response:
        assert "b3" in request.headers
        assert request.path == BlobUrlRotes.DELETE_BUCKET.format(bucket=name)
        assert request.query == {}
        return web.Response(status=204)

    app = web.Application()
    app.router.add_delete(BlobUrlRotes.DELETE_BUCKET, handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        await client.blob_storage.delete_bucket(name)


async def test_blob_storage_list_blobs(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    bucket_name = "foo"
    continuation_token = "cool_token"
    mtime1 = datetime.now()
    mtime2 = datetime.now()
    PAGE1_JSON = {
        "contents": [
            {"key": "test.json", "size": 213, "last_modified": mtime1.timestamp()}
        ],
        "common_prefixes": [{"prefix": "empty/"}, {"prefix": "folder1/"}],
        "is_truncated": True,
        "continuation_token": continuation_token,
    }
    PAGE2_JSON = {
        "contents": [
            {"key": "test1.txt", "size": 111, "last_modified": mtime1.timestamp()},
            {"key": "test2.txt", "size": 222, "last_modified": mtime2.timestamp()},
        ],
        "common_prefixes": [{"prefix": "folder2/"}],
        "is_truncated": False,
        "continuation_token": None,
    }

    async def handler(request: web.Request) -> web.Response:
        assert "b3" in request.headers
        assert request.path == BlobUrlRotes.LIST_OBJECTS.format(bucket=bucket_name)

        if "continuation_token" not in request.query:
            assert request.query["recursive"] == "false"
            assert request.query["max_keys"] in ("3", "6")
            return web.json_response(PAGE1_JSON)
        else:
            assert request.query == {
                "recursive": "false",
                "max_keys": "3",
                "continuation_token": continuation_token,
            }
            return web.json_response(PAGE2_JSON)

    app = web.Application()
    app.router.add_get(BlobUrlRotes.LIST_OBJECTS, handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        ret = await client.blob_storage.list_blobs(bucket_name, max_keys=3)

    assert ret == (
        [
            BlobListing(
                key="test.json",
                size=213,
                modification_time=int(mtime1.timestamp()),
                bucket_name=bucket_name,
            ),
        ],
        [
            PrefixListing(prefix="empty/", bucket_name=bucket_name),
            PrefixListing(prefix="folder1/", bucket_name=bucket_name),
        ],
    )

    async with make_client(srv.make_url("/")) as client:
        ret = await client.blob_storage.list_blobs(bucket_name, max_keys=6)

    assert ret == (
        [
            BlobListing(
                key="test.json",
                size=213,
                modification_time=int(mtime1.timestamp()),
                bucket_name=bucket_name,
            ),
            BlobListing(
                key="test1.txt",
                size=111,
                modification_time=int(mtime1.timestamp()),
                bucket_name=bucket_name,
            ),
            BlobListing(
                key="test2.txt",
                size=222,
                modification_time=int(mtime2.timestamp()),
                bucket_name=bucket_name,
            ),
        ],
        [
            PrefixListing(prefix="empty/", bucket_name=bucket_name),
            PrefixListing(prefix="folder1/", bucket_name=bucket_name),
            PrefixListing(prefix="folder2/", bucket_name=bucket_name),
        ],
    )


async def test_blob_storage_list_blobs_recursive(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    bucket_name = "foo"
    mtime1 = datetime.now()
    mtime2 = datetime.now()
    PAGE1_JSON = {
        "contents": [
            {"key": "folder1/xxx.txt", "size": 1, "last_modified": mtime1.timestamp()},
            {"key": "folder1/yyy.json", "size": 2, "last_modified": mtime2.timestamp()},
            {
                "key": "folder2/big_file",
                "size": 120 * 1024 * 1024,
                "last_modified": mtime1.timestamp(),
            },
        ],
        "common_prefixes": [],
        "is_truncated": False,
    }

    async def handler(request: web.Request) -> web.Response:
        assert "b3" in request.headers
        assert request.path == BlobUrlRotes.LIST_OBJECTS.format(bucket=bucket_name)
        assert request.query == {
            "recursive": "true",
            "max_keys": "1000",
            "prefix": "folder",
        }
        return web.json_response(PAGE1_JSON)

    app = web.Application()
    app.router.add_get(BlobUrlRotes.LIST_OBJECTS, handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        ret = await client.blob_storage.list_blobs(
            bucket_name, recursive=True, prefix="folder"
        )

    assert ret == (
        [
            BlobListing(
                key="folder1/xxx.txt",
                size=1,
                modification_time=int(mtime1.timestamp()),
                bucket_name=bucket_name,
            ),
            BlobListing(
                key="folder1/yyy.json",
                size=2,
                modification_time=int(mtime2.timestamp()),
                bucket_name=bucket_name,
            ),
            BlobListing(
                key="folder2/big_file",
                size=120 * 1024 * 1024,
                modification_time=int(mtime1.timestamp()),
                bucket_name=bucket_name,
            ),
        ],
        [],
    )


async def test_blob_storage_head_blob(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    bucket_name = "foo"
    key = "text.txt"
    mtime1 = time.time()

    async def handler(request: web.Request) -> web.StreamResponse:
        assert "b3" in request.headers
        assert request.path == f"/blob/o/{bucket_name}/{key}"
        assert request.match_info == {"bucket": bucket_name, "path": key}
        resp = web.StreamResponse(status=200)
        resp.headers.update({"ETag": '"12312908asd"'})
        resp.last_modified = int(mtime1)  # type: ignore
        resp.content_length = 111
        resp.content_type = "plain/text"
        return resp

    app = web.Application()
    app.router.add_head(BlobUrlRotes.HEAD_OBJECT, handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        ret = await client.blob_storage.head_blob(bucket_name, key=key)

    assert ret == BlobListing(
        key=key,
        size=111,
        modification_time=int(mtime1),
        bucket_name=bucket_name,
    )


async def test_blob_storage_get_blob(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    bucket_name = "foo"
    key = "text.txt"
    mtime1 = time.time()
    body = b"W" * 1000

    async def handler(request: web.Request) -> web.StreamResponse:
        assert "b3" in request.headers
        assert request.path == f"/blob/o/{bucket_name}/{key}"
        assert request.match_info == {"bucket": bucket_name, "path": key}
        resp = web.StreamResponse(status=200)
        resp.headers.update({"ETag": '"12312908asd"'})
        resp.last_modified = int(mtime1)  # type: ignore
        resp.content_length = len(body)
        resp.content_type = "plain/text"
        await resp.prepare(request)
        await resp.write(body)
        return resp

    app = web.Application()
    app.router.add_get(BlobUrlRotes.GET_OBJECT, handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        async with client.blob_storage.get_blob(bucket_name, key=key) as ret:
            assert ret.stats == BlobListing(
                key=key,
                size=1000,
                modification_time=int(mtime1),
                bucket_name=bucket_name,
            )
            assert await ret.body_stream.read() == body


async def test_blob_storage_fetch_blob(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    bucket_name = "foo"
    key = "text.txt"
    mtime1 = time.time()
    body = b"W" * 10 * 1024 * 1024

    async def handler(request: web.Request) -> web.StreamResponse:
        assert "b3" in request.headers
        assert request.path == f"/blob/o/{bucket_name}/{key}"
        assert request.match_info == {"bucket": bucket_name, "path": key}
        resp = web.StreamResponse(status=200)
        resp.headers.update({"ETag": '"12312908asd"'})
        resp.last_modified = int(mtime1)  # type: ignore
        resp.content_length = len(body)
        resp.content_type = "plain/text"
        await resp.prepare(request)
        await resp.write(body)
        return resp

    app = web.Application()
    app.router.add_get(BlobUrlRotes.GET_OBJECT, handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        buf = b""
        async for data in client.blob_storage.fetch_blob(bucket_name, key=key):
            buf += data
        assert buf == body


async def test_blob_storage_fetch_blob_partial_read(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    bucket_name = "foo"
    key = "text.txt"
    mtime1 = time.time()
    body = b"ababahalamaha"

    async def handler(request: web.Request) -> web.StreamResponse:
        assert "b3" in request.headers
        assert request.path == f"/blob/o/{bucket_name}/{key}"
        assert request.match_info == {"bucket": bucket_name, "path": key}
        rng = request.http_range
        start, stop, _ = rng.indices(len(body))
        resp = web.StreamResponse(status=web.HTTPPartialContent.status_code)
        resp.headers["ETag"] = '"12312908asd"'
        resp.headers["Content-Range"] = f"bytes {start}-{stop-1}/{len(body)}"
        resp.last_modified = int(mtime1)  # type: ignore
        resp.content_length = stop - start
        resp.content_type = "plain/text"
        await resp.prepare(request)
        await resp.write(body[start:stop])
        return resp

    app = web.Application()
    app.router.add_get(BlobUrlRotes.GET_OBJECT, handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        buf = bytearray()
        async for chunk in client.blob_storage.fetch_blob(bucket_name, key, 5):
            buf.extend(chunk)
        assert buf == b"halamaha"

        buf = bytearray()
        async for chunk in client.blob_storage.fetch_blob(bucket_name, key, 5, 4):
            buf.extend(chunk)
        assert buf == b"hala"

        buf = bytearray()
        async for chunk in client.blob_storage.fetch_blob(bucket_name, key, 5, 20):
            buf.extend(chunk)
        assert buf == b"halamaha"

        with pytest.raises(ValueError):
            async for chunk in client.blob_storage.fetch_blob(bucket_name, key, 5, 0):
                pass


async def test_blob_storage_fetch_blob_unsupported_partial_read(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    bucket_name = "foo"
    key = "text.txt"
    mtime1 = time.time()
    body = b"ababahalamaha"

    async def handler(request: web.Request) -> web.StreamResponse:
        assert "b3" in request.headers
        assert request.path == f"/blob/o/{bucket_name}/{key}"
        assert request.match_info == {"bucket": bucket_name, "path": key}
        resp = web.StreamResponse(status=200)
        resp.headers.update({"ETag": '"12312908asd"'})
        resp.last_modified = int(mtime1)  # type: ignore
        resp.content_length = len(body)
        resp.content_type = "plain/text"
        await resp.prepare(request)
        await resp.write(body)
        return resp

    app = web.Application()
    app.router.add_get(BlobUrlRotes.GET_OBJECT, handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        buf = b""
        async for data in client.blob_storage.fetch_blob(bucket_name, key):
            buf += data
        assert buf == body

        with pytest.raises(RuntimeError):
            async for data in client.blob_storage.fetch_blob(bucket_name, key, 5):
                pass


async def test_blob_storage_put_blob(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    bucket_name = "foo"
    key = "text.txt"
    body = b"W" * 10 * 1024 * 1024
    md5 = base64.b64encode(hashlib.md5(body).digest()).decode()
    etag = repr(hashlib.md5(body).hexdigest())

    async def handler(request: web.Request) -> web.StreamResponse:
        assert "b3" in request.headers
        assert request.path == f"/blob/o/{bucket_name}/{key}"
        assert request.match_info == {"bucket": bucket_name, "path": key}
        assert request.headers["X-Content-Length"] == str(len(body))
        assert await request.content.read() == body
        return web.Response(headers={"ETag": etag})

    app = web.Application()
    app.router.add_put(BlobUrlRotes.PUT_OBJECT, handler)

    srv = await aiohttp_server(app)

    async def async_iter() -> AsyncIterator[bytes]:
        yield body

    async with make_client(srv.make_url("/")) as client:
        resp_etag = await client.blob_storage.put_blob(
            bucket_name=bucket_name,
            key=key,
            body=async_iter(),
            size=len(body),
            content_md5=md5,
        )
        assert resp_etag == etag


async def test_blob_storage_delete_blob(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    bucket_name = "foo"
    key = "text.txt"

    async def handler(request: web.Request) -> web.StreamResponse:
        assert "b3" in request.headers
        assert request.path == f"/blob/o/{bucket_name}/{key}"
        return web.Response(status=204)

    app = web.Application()
    app.router.add_delete(BlobUrlRotes.DELETE_OBJECT, handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        res = await client.blob_storage.delete_blob(
            bucket_name=bucket_name,
            key=key,
        )
        assert res is None


async def test_blob_storage_calc_md5(tmp_path: Path) -> None:
    txt_file = tmp_path / "test.txt"
    body = b"""
    This is the greatest day of my whole life!!!
    """
    body_md5 = base64.b64encode(hashlib.md5(body).digest()).decode("ascii")
    with txt_file.open("wb") as f:
        f.write(body)
    assert (await calc_md5(txt_file))[0] == body_md5


async def test_blob_storage_large_calc_md5(tmp_path: Path) -> None:
    txt_file = tmp_path / "test.txt"
    size_mb = 20
    body = b"W" * (1024 * 1024)
    md5 = hashlib.md5()
    for _ in range(size_mb):
        md5.update(body)
    body_md5 = base64.b64encode(md5.digest()).decode("ascii")

    # Will write 100MB file
    with txt_file.open("wb") as f:
        for _ in range(size_mb):
            f.write(body)
    assert (await calc_md5(txt_file))[0] == body_md5


# high level API


async def test_blob_storage_upload_file_does_not_exists(
    make_client: _MakeClient,
) -> None:
    async with make_client("https://example.com") as client:
        with pytest.raises(FileNotFoundError):
            await client.blob_storage.upload_file(
                URL("file:///not-exists-file"), URL("blob://host/path/to/file.txt")
            )


async def test_blob_storage_upload_dir_doesnt_exist(make_client: _MakeClient) -> None:
    async with make_client("https://example.com") as client:
        with pytest.raises(IsADirectoryError):
            await client.blob_storage.upload_file(
                URL(FOLDER.as_uri()), URL("blob://host/path/to")
            )


async def test_blob_storage_upload_not_a_file(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
) -> None:

    file_path = Path(os.devnull).absolute()
    progress = mock.Mock()

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_file(
            URL(file_path.as_uri()), URL("blob:foo/file.txt"), progress=progress
        )

    uploaded = blob_storage_contents["file.txt"]
    assert uploaded["body"] == b""

    src = URL(file_path.as_uri())
    dst = URL("blob://default/foo/file.txt")
    progress.start.assert_called_with(StorageProgressStart(src, dst, 0))
    progress.step.assert_not_called()
    progress.complete.assert_called_with(StorageProgressComplete(src, dst, 0))


async def test_blob_storage_upload_regular_file_new_file(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
) -> None:
    file_path = DATA_FOLDER / "file.txt"
    file_size = file_path.stat().st_size
    progress = mock.Mock()

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_file(
            URL(file_path.as_uri()), URL("blob:foo/file.txt"), progress=progress
        )

    expected = file_path.read_bytes()
    uploaded = blob_storage_contents["file.txt"]
    assert uploaded["body"] == expected

    src = URL(file_path.as_uri())
    dst = URL("blob://default/foo/file.txt")
    progress.start.assert_called_with(StorageProgressStart(src, dst, file_size))
    progress.step.assert_called_with(
        StorageProgressStep(src, dst, file_size, file_size)
    )
    progress.complete.assert_called_with(StorageProgressComplete(src, dst, file_size))


async def test_blob_storage_upload_large_file(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
) -> None:
    local_dir = tmp_path / "local"
    local_dir.mkdir(exist_ok=True)
    local_file = local_dir / "file.txt"

    with local_file.open("wb") as f:
        for _ in range(1024):
            f.write(b"yncuNRzU0xhKSqIh" * (4 * 1024))

    progress = mock.Mock()

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_file(
            URL(local_file.as_uri()),
            URL("blob:foo/folder2/big_file"),
            progress=progress,
        )

    expected = local_file.read_bytes()
    uploaded = blob_storage_contents["folder2/big_file"]
    assert uploaded["body"] == expected

    src = URL(local_file.as_uri())
    dst = URL("blob://default/foo/folder2/big_file")
    file_size = len(expected)
    progress.start.assert_called_with(StorageProgressStart(src, dst, file_size))
    progress.step.assert_called_with(
        StorageProgressStep(src, dst, file_size, file_size)
    )
    progress.complete.assert_called_with(StorageProgressComplete(src, dst, file_size))


async def test_blob_storage_upload_regular_file_to_existing_file(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
) -> None:
    file_path = DATA_FOLDER / "file.txt"

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_file(
            URL(file_path.as_uri()), URL("blob:foo/test1.txt")
        )

    expected = file_path.read_bytes()
    uploaded = blob_storage_contents["test1.txt"]
    assert uploaded["body"] == expected


async def test_blob_storage_upload_regular_file_to_existing_dir_with_slash(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
) -> None:
    file_path = DATA_FOLDER / "file.txt"

    async with make_client(blob_storage_server.make_url("/")) as client:
        with pytest.raises(IsADirectoryError):
            await client.blob_storage.upload_file(
                URL(file_path.as_uri()), URL("blob:foo/empty/")
            )


async def test_blob_storage_upload_regular_file_to_existing_dir_without_slash(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
) -> None:
    file_path = DATA_FOLDER / "file.txt"

    async with make_client(blob_storage_server.make_url("/")) as client:
        with pytest.raises(IsADirectoryError):
            await client.blob_storage.upload_file(
                URL(file_path.as_uri()), URL("blob:foo/empty")
            )


async def test_blob_storage_upload_regular_file_to_existing_non_dir(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
) -> None:
    file_path = DATA_FOLDER / "file.txt"

    async with make_client(blob_storage_server.make_url("/")) as client:
        with pytest.raises(NotADirectoryError):
            await client.blob_storage.upload_file(
                URL(file_path.as_uri()), URL("blob:foo/test1.txt/subfile.txt")
            )


async def test_blob_storage_upload_regular_file_to_not_existing(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
) -> None:
    # In blob storage it's perfectly fine to upload on non-exising path
    file_path = DATA_FOLDER / "file.txt"

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_file(
            URL(file_path.as_uri()), URL("blob:foo/absent-dir/absent-file.txt")
        )

    expected = file_path.read_bytes()
    uploaded = blob_storage_contents["absent-dir/absent-file.txt"]
    assert uploaded["body"] == expected


async def test_blob_storage_upload_recursive_src_doesnt_exist(
    make_client: _MakeClient,
) -> None:
    async with make_client("https://example.com") as client:
        with pytest.raises(FileNotFoundError):
            await client.blob_storage.upload_dir(
                URL("file:does_not_exist"), URL("blob://host/path/to")
            )


async def test_blob_storage_upload_recursive_src_is_a_file(
    make_client: _MakeClient,
) -> None:
    file_path = DATA_FOLDER / "file.txt"

    async with make_client("https://example.com") as client:
        with pytest.raises(NotADirectoryError):
            await client.blob_storage.upload_dir(
                URL(file_path.as_uri()), URL("blob://host/path/to")
            )


async def test_blob_storage_upload_recursive_target_is_a_file(
    blob_storage_server: Any,
    make_client: _MakeClient,
) -> None:

    async with make_client(blob_storage_server.make_url("/")) as client:
        with pytest.raises(NotADirectoryError):
            await client.blob_storage.upload_dir(
                URL(DATA_FOLDER.as_uri()), URL("blob:foo/test1.txt")
            )


async def test_blob_storage_upload_empty_dir(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
) -> None:
    src_dir = tmp_path / "empty"
    src_dir.mkdir()
    assert list(src_dir.iterdir()) == []

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_dir(
            URL(src_dir.as_uri()), URL("blob:foo/folder")
        )

    assert "folder" not in blob_storage_contents
    uploaded = blob_storage_contents["folder/"]
    assert uploaded == {
        "key": "folder/",
        "size": 0,
        "last_modified": mock.ANY,
        "body": b"",
    }


async def test_blob_storage_upload_recursive_ok(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
) -> None:

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_dir(
            URL(DATA_FOLDER.as_uri()) / "nested", URL("blob:foo/folder")
        )

    keys = [v for k, v in blob_storage_contents.items() if k.startswith("folder/")]
    body = (DATA_FOLDER / "nested" / "folder" / "file.txt").read_bytes()
    assert keys == [
        {"key": "folder/", "size": 0, "last_modified": mock.ANY, "body": b""},
        {"key": "folder/folder/", "size": 0, "last_modified": mock.ANY, "body": b""},
        {
            "key": "folder/folder/file.txt",
            "size": len(body),
            "last_modified": mock.ANY,
            "body": body,
        },
    ]


async def test_blob_storage_upload_recursive_slash_ending(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
) -> None:

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_dir(
            URL(DATA_FOLDER.as_uri()) / "nested", URL("blob:foo/folder/")
        )

    keys = [v for k, v in blob_storage_contents.items() if k.startswith("folder/")]
    body = (DATA_FOLDER / "nested" / "folder" / "file.txt").read_bytes()
    assert keys == [
        {"key": "folder/", "size": 0, "last_modified": mock.ANY, "body": b""},
        {"key": "folder/folder/", "size": 0, "last_modified": mock.ANY, "body": b""},
        {
            "key": "folder/folder/file.txt",
            "size": len(body),
            "last_modified": mock.ANY,
            "body": body,
        },
    ]


async def test_blob_storage_upload_to_bucket_root(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
) -> None:

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_dir(
            URL(DATA_FOLDER.as_uri()) / "nested", URL("blob:foo/")
        )

    keys = [v for k, v in blob_storage_contents.items() if k.startswith("folder/")]
    body = (DATA_FOLDER / "nested" / "folder" / "file.txt").read_bytes()
    assert keys == [
        {"key": "folder/", "size": 0, "last_modified": mock.ANY, "body": b""},
        {
            "key": "folder/file.txt",
            "size": len(body),
            "last_modified": mock.ANY,
            "body": body,
        },
    ]


async def test_blob_storage_download_regular_file_to_absent_file(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
) -> None:
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_file = local_dir / "file.txt"
    progress = mock.Mock()

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(
            URL("blob:foo/test1.txt"), URL(local_file.as_uri()), progress=progress
        )

    expected = blob_storage_contents["test1.txt"]["body"]
    downloaded = local_file.read_bytes()
    assert downloaded == expected

    src = URL("blob://default/foo/test1.txt")
    dst = URL(local_file.as_uri())
    file_size = len(expected)
    progress.start.assert_called_with(StorageProgressStart(src, dst, file_size))
    progress.step.assert_called_with(
        StorageProgressStep(src, dst, file_size, file_size)
    )
    progress.complete.assert_called_with(StorageProgressComplete(src, dst, file_size))


async def test_blob_storage_download_large_file(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
) -> None:
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_file = local_dir / "file.txt"
    progress = mock.Mock()

    # 16 * 4 = 64 MB of data
    large_payload = b"yncuNRzU0xhKSqIh" * (4 * 1024 * 1024)
    blob_storage_contents["folder2/big_file"] = {
        "key": "folder2/big_file",
        "size": len(large_payload),
        "last_modified": datetime(2019, 1, 3).timestamp(),
        "body": large_payload,
    }

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(
            URL("blob:foo/folder2/big_file"),
            URL(local_file.as_uri()),
            progress=progress,
        )

    downloaded = local_file.read_bytes()
    assert downloaded == large_payload

    src = URL("blob://default/foo/folder2/big_file")
    dst = URL(local_file.as_uri())
    file_size = len(large_payload)
    progress.start.assert_called_with(StorageProgressStart(src, dst, file_size))
    progress.step.assert_called_with(
        StorageProgressStep(src, dst, file_size, file_size)
    )
    progress.complete.assert_called_with(StorageProgressComplete(src, dst, file_size))


async def test_blob_storage_download_regular_file_to_existing_file(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
) -> None:
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_file = local_dir / "file.txt"
    local_file.write_bytes(b"Previous data")

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(
            URL("blob:foo/test1.txt"), URL(local_file.as_uri())
        )

    expected = blob_storage_contents["test1.txt"]["body"]
    downloaded = local_file.read_bytes()
    assert downloaded == expected


async def test_blob_storage_download_regular_file_to_dir(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
) -> None:
    local_dir = tmp_path / "local"
    local_dir.mkdir()

    async with make_client(blob_storage_server.make_url("/")) as client:
        # On Windows it will be signaled as PermissionError instead...
        with pytest.raises((IsADirectoryError, PermissionError)):
            await client.blob_storage.download_file(
                URL("blob:foo/test1.txt"), URL(local_dir.as_uri())
            )


async def test_blob_storage_download_regular_file_to_dir_slash_ended(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
) -> None:
    local_dir = tmp_path / "local"
    local_dir.mkdir()

    async with make_client(blob_storage_server.make_url("/")) as client:
        # On Windows it will be signaled as PermissionError instead...
        with pytest.raises((IsADirectoryError, PermissionError)):
            await client.blob_storage.download_file(
                URL("blob:foo/test1.txt"), URL(local_dir.as_uri() + "/")
            )


async def test_blob_storage_download_regular_file_to_non_file(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
) -> None:

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(
            URL("blob:foo/test1.txt"), URL(Path(os.devnull).absolute().as_uri())
        )


async def test_blob_storage_download_empty_dir(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
) -> None:
    target_dir = tmp_path / "empty"
    assert not target_dir.exists()

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_dir(
            URL("blob:foo/empty"), URL(target_dir.as_uri())
        )

    assert list(target_dir.iterdir()) == []


async def test_blob_storage_download_dir(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
) -> None:
    local_dir = tmp_path / "local"
    local_dir.mkdir()

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_dir(URL("blob:foo"), URL(local_dir.as_uri()))

    files = sorted(dir_list(local_dir), key=lambda x: x["path"])
    assert files == [
        {"dir": True, "path": "empty"},
        {"dir": True, "path": "folder1"},
        {"body": b"w", "dir": False, "path": "folder1/xxx.txt", "size": 1},
        {"body": b"bb", "dir": False, "path": "folder1/yyy.json", "size": 2},
        {"body": b"w" * 213, "dir": False, "path": "test.json", "size": 213},
        {"body": b"w" * 111, "dir": False, "path": "test1.txt", "size": 111},
        {"body": b"w" * 222, "dir": False, "path": "test2.txt", "size": 222},
    ]


async def test_blob_storage_download_dir_with_slash(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
) -> None:
    local_dir = tmp_path / "local"
    local_dir.mkdir()

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_dir(
            URL("blob:foo"), URL(local_dir.as_uri() + "/")
        )

    files = sorted(dir_list(local_dir), key=lambda x: x["path"])
    assert files == [
        {"dir": True, "path": "empty"},
        {"dir": True, "path": "folder1"},
        {"body": b"w", "dir": False, "path": "folder1/xxx.txt", "size": 1},
        {"body": b"bb", "dir": False, "path": "folder1/yyy.json", "size": 2},
        {"body": b"w" * 213, "dir": False, "path": "test.json", "size": 213},
        {"body": b"w" * 111, "dir": False, "path": "test1.txt", "size": 111},
        {"body": b"w" * 222, "dir": False, "path": "test2.txt", "size": 222},
    ]


@pytest.mark.parametrize(
    "pattern,expected_keys",
    [
        ("folder1/*", ["folder1/xxx.txt", "folder1/yyy.json"]),
        ("folder?/*", ["folder1/xxx.txt", "folder1/yyy.json", "folder2/big_file"]),
        ("**/*.json", ["folder1/yyy.json", "test.json"]),
        ("*/*.txt", ["folder1/xxx.txt"]),
        ("test[1-9].*", ["test1.txt", "test2.txt"]),
        ("test[2-3].*", ["test2.txt"]),
        # Should not match `/` for deep paths
        ("*.txt", ["test1.txt", "test2.txt"]),
        ("folder*", []),
        # Only glob style recursive supported:
        #   **/file
        #   folder/**/file
        #   folder/**
        ("folder**", []),
    ],
)
async def test_blob_storage_glob_blobs(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    pattern: str,
    expected_keys: List[str],
) -> None:
    bucket_name = "foo"
    blob_storage_contents["folder2/big_file"] = {
        "key": "folder2/big_file",
        "size": 2 * 1024,
        "last_modified": datetime(2019, 1, 2).timestamp(),
        "body": b"bb" * 1024,
    }

    async with make_client(blob_storage_server.make_url("/")) as client:
        ret = [
            x.key
            async for x in client.blob_storage.glob_blobs(bucket_name, pattern=pattern)
        ]
        assert ret == expected_keys


@pytest.fixture
def zero_time_threshold(monkeypatch: Any) -> None:
    monkeypatch.setattr(neuro_sdk.blob_storage, "TIME_THRESHOLD", 0.0)


@pytest.fixture
def small_block_size(monkeypatch: Any) -> None:
    monkeypatch.setattr(neuro_sdk.blob_storage, "READ_SIZE", 300)


async def test_storage_upload_file_update(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
    zero_time_threshold: None,
    small_block_size: None,
) -> None:
    # storage_file = storage_path / "file.txt"
    local_file = tmp_path / "file.txt"
    src = URL(local_file.as_uri())
    dst = URL("blob:foo/file.txt")

    # No destination file
    assert blob_storage_contents.get("file.txt") is None
    local_file.write_bytes(b"old content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_file(src, dst, update=True)
    assert blob_storage_contents["file.txt"]["body"] == b"old content"

    # Source file is newer
    local_file.write_bytes(b"new content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_file(src, dst, update=True)
    assert blob_storage_contents["file.txt"]["body"] == b"new content"

    # Destination file is newer, same size
    await asyncio.sleep(5)
    add_blob(blob_storage_contents, "file.txt", b"old")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_file(src, dst, update=True)
    assert blob_storage_contents["file.txt"]["body"] == b"old"


async def test_storage_upload_dir_update(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
    zero_time_threshold: None,
) -> None:
    local_dir = tmp_path / "folder"
    local_file = local_dir / "nested" / "file.txt"
    local_file.parent.mkdir(parents=True)
    src = URL(local_dir.as_uri())
    dst = URL("blob:foo")

    # No destination file
    assert blob_storage_contents.get("nested/file.txt") is None
    # assert not storage_file.exists()
    local_file.write_bytes(b"old content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_dir(src, dst, update=True)
    assert blob_storage_contents["nested/file.txt"]["body"] == b"old content"

    # Source file is newer
    local_file.write_bytes(b"new content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_dir(src, dst, update=True)
    assert blob_storage_contents["nested/file.txt"]["body"] == b"new content"

    # Destination file is newer, same size
    await asyncio.sleep(5)
    add_blob(blob_storage_contents, "nested/file.txt", b"old")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_dir(src, dst, update=True)
    assert blob_storage_contents["nested/file.txt"]["body"] == b"old"


async def test_storage_download_file_update(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
    zero_time_threshold: None,
) -> None:
    local_file = tmp_path / "file.txt"
    src = URL("blob:foo/file.txt")
    dst = URL(local_file.as_uri())

    # No destination file
    assert not local_file.exists()
    add_blob(blob_storage_contents, "file.txt", b"old content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(src, dst, update=True)
    assert local_file.read_bytes() == b"old content"

    # Source file is newer
    add_blob(blob_storage_contents, "file.txt", b"new content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(src, dst, update=True)
    assert local_file.read_bytes() == b"new content"

    # Destination file is newer
    await asyncio.sleep(2)
    local_file.write_bytes(b"old")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(src, dst, update=True)
    assert local_file.read_bytes() == b"old"


async def test_storage_download_file_continue(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
    zero_time_threshold: None,
    small_block_size: None,
) -> None:
    local_file = tmp_path / "file.txt"
    src = URL("blob:foo/file.txt")
    dst = URL(local_file.as_uri())

    # No destination file
    assert not local_file.exists()
    add_blob(blob_storage_contents, "file.txt", b"content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(src, dst, continue_=True)
    assert local_file.read_bytes() == b"content"

    # Source file is newer
    add_blob(blob_storage_contents, "file.txt", b"new content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(src, dst, continue_=True)
    assert local_file.read_bytes() == b"new content"

    # Destination file is newer, same size
    await asyncio.sleep(2)
    local_file.write_bytes(b"old content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(src, dst, continue_=True)
    assert local_file.read_bytes() == b"old content"

    # Destination file is shorter
    local_file.write_bytes(b"old")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(src, dst, continue_=True)
    assert local_file.read_bytes() == b"old content"

    # Destination file is longer
    local_file.write_bytes(b"old long content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_file(src, dst, continue_=True)
    assert local_file.read_bytes() == b"new content"


async def test_storage_download_dir_update(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
    zero_time_threshold: None,
) -> None:
    local_dir = tmp_path / "folder"
    local_file = local_dir / "nested" / "file.txt"
    src = URL("blob:foo")
    dst = URL(local_dir.as_uri())

    # No destination file
    assert not local_file.exists()
    add_blob(blob_storage_contents, "nested/file.txt", b"old content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_dir(src, dst, update=True)
    assert local_file.read_bytes() == b"old content"

    # Source file is newer
    add_blob(blob_storage_contents, "nested/file.txt", b"new content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_dir(src, dst, update=True)
    assert local_file.read_bytes() == b"new content"

    # Destination file is newer
    await asyncio.sleep(2)
    local_file.write_bytes(b"old")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_dir(src, dst, update=True)
    assert local_file.read_bytes() == b"old"


async def test_storage_download_dir_continue(
    blob_storage_server: Any,
    make_client: _MakeClient,
    blob_storage_contents: _ContentsObj,
    tmp_path: Path,
    zero_time_threshold: None,
) -> None:
    local_dir = tmp_path / "folder"
    local_file = local_dir / "nested" / "file.txt"
    src = URL("blob:foo")
    dst = URL(local_dir.as_uri())

    # No destination file
    assert not local_file.exists()
    add_blob(blob_storage_contents, "nested/file.txt", b"content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_dir(src, dst, continue_=True)
    assert local_file.read_bytes() == b"content"

    # Source file is newer
    add_blob(blob_storage_contents, "nested/file.txt", b"new content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_dir(src, dst, continue_=True)
    assert local_file.read_bytes() == b"new content"

    # Destination file is newer, same size
    await asyncio.sleep(2)
    local_file.write_bytes(b"old content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_dir(src, dst, continue_=True)
    assert local_file.read_bytes() == b"old content"

    # Destination file is shorter
    local_file.write_bytes(b"old")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_dir(src, dst, continue_=True)
    assert local_file.read_bytes() == b"old content"

    # Destination file is longer
    local_file.write_bytes(b"old long content")
    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.download_dir(src, dst, continue_=True)
    assert local_file.read_bytes() == b"new content"


async def test_storage_upload_dir_with_ignore_file_names(
    blob_storage_server: Any,
    make_client: _MakeClient,
    tmp_path: Path,
    blob_storage_contents: _ContentsObj,
) -> None:
    local_dir = tmp_path / "folder"
    local_dir2 = local_dir / "nested"
    local_dir2.mkdir(parents=True)
    for name in "one", "two", "three":
        (local_dir / name).write_bytes(b"")
        (local_dir2 / name).write_bytes(b"")
    (local_dir / ".neuroignore").write_text("one")
    (local_dir2 / ".gitignore").write_text("two")

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_dir(
            URL(local_dir.as_uri()),
            URL("blob:foo/folder"),
            ignore_file_names={".neuroignore", ".gitignore"},
        )

    keys = sorted(k for k in blob_storage_contents if k.startswith("folder/"))
    assert keys == [
        "folder/",
        "folder/.neuroignore",
        "folder/nested/",
        "folder/nested/.gitignore",
        "folder/nested/three",
        "folder/three",
        "folder/two",
    ]


async def test_storage_upload_dir_with_parent_ignore_file_names(
    blob_storage_server: Any,
    make_client: _MakeClient,
    tmp_path: Path,
    blob_storage_contents: _ContentsObj,
) -> None:
    parent_dir = tmp_path / "parent"
    local_dir = parent_dir / "folder"
    local_dir2 = local_dir / "nested"
    local_dir2.mkdir(parents=True)
    for name in "one", "two", "three":
        (local_dir / name).write_bytes(b"")
        (local_dir2 / name).write_bytes(b"")
    (tmp_path / ".neuroignore").write_text("one")
    (parent_dir / ".gitignore").write_text("*/two")

    async with make_client(blob_storage_server.make_url("/")) as client:
        await client.blob_storage.upload_dir(
            URL(local_dir.as_uri()),
            URL("blob:foo/folder"),
            ignore_file_names={".neuroignore", ".gitignore"},
        )

    keys = sorted(k for k in blob_storage_contents if k.startswith("folder/"))
    assert keys == [
        "folder/",
        "folder/nested/",
        "folder/nested/three",
        "folder/nested/two",
        "folder/three",
    ]


def add_blob(
    contents: Dict[str, Any], key: str, body: bytes, mtime: Optional[float] = None
) -> None:
    contents[key] = {}
    contents[key]["key"] = key
    contents[key]["body"] = body
    contents[key]["size"] = len(body)
    if mtime is None:
        mtime = time.time()
    contents[key]["last_modified"] = mtime
