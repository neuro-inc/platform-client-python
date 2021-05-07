from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, NoReturn
from unittest import mock

import click
import pytest
import toml
from aiohttp import web
from yarl import URL

from neuro_sdk import Action, Client, JobStatus

from neuro_cli.parse_utils import parse_timedelta
from neuro_cli.root import Root
from neuro_cli.utils import (
    calc_life_span,
    pager_maybe,
    parse_file_resource,
    parse_permission_action,
    parse_resource_for_sharing,
    resolve_job,
    resolve_job_ex,
)

from tests import _TestServerFactory

_MakeClient = Callable[..., Client]


def _job_entry(job_id: str, cluster_name: str = "default") -> Dict[str, Any]:
    return {
        "id": job_id,
        "owner": "job-owner",
        "cluster_name": cluster_name,
        "uri": f"job://{cluster_name}/job-owner/{job_id}",
        "status": "running",
        "history": {
            "status": "running",
            "reason": None,
            "description": None,
            "created_at": "2019-03-18T12:41:10.573468+00:00",
            "started_at": "2019-03-18T12:41:16.804040+00:00",
        },
        "container": {
            "image": "ubuntu:latest",
            "env": {},
            "volumes": [],
            "command": "sleep 1h",
            "resources": {"cpu": 0.1, "memory_mb": 1024, "shm": True},
        },
        "ssh_auth_server": "ssh://nobody@ssh-auth-dev.neu.ro:22",
        "scheduler_enabled": True,
        "pass_config": False,
        "name": "my-job-name",
        "internal_hostname": f"job-id.{cluster_name}",
        "internal_hostname_named": f"my-job-name--job-owner.{cluster_name}",
    }


def _check_params(request: web.Request, **expected: str) -> None:
    # Since `resolve_job` excepts any Exception, `assert` will be caught there
    for key, value in expected.items():
        got = request.query.get(key)
        if got != value:
            pytest.fail(f"received: {key}={got!r} (expected {value!r})")


async def test_resolve_job_id__from_string__no_jobs_found(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    JSON: Dict[str, Any] = {"jobs": []}
    job_id = "job-81839be3-3ecf-4ec5-80d9-19b1588869db"

    async def handler(request: web.Request) -> web.Response:
        _check_params(
            request,
            name=job_id,
            owner="user",
            cluster_name="default",
            reverse="1",
            limit="1",
        )
        return web.json_response(JSON)

    app = web.Application()
    app.router.add_get("/jobs", handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        resolved = await resolve_job(job_id, client=client, status={JobStatus.RUNNING})
        assert resolved == job_id
        resolved_ex = await resolve_job_ex(
            job_id, client=client, status={JobStatus.RUNNING}
        )
        assert resolved_ex == (job_id, "default")


@pytest.mark.parametrize("cluster_name", ["default", "other"])
async def test_resolve_job_id__from_uri_with_owner_same_user__no_jobs_found(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient, cluster_name: str
) -> None:
    job_owner = "user"
    job_name = "my-job-name"
    uri = f"job://{cluster_name}/{job_owner}/{job_name}"
    JSON: Dict[str, Any] = {"jobs": []}

    async def handler(request: web.Request) -> web.Response:
        _check_params(
            request,
            name=job_name,
            owner=job_owner,
            cluster_name=cluster_name,
            reverse="1",
            limit="1",
        )
        return web.json_response(JSON)

    app = web.Application()
    app.router.add_get("/jobs", handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        resolved = await resolve_job(uri, client=client, status={JobStatus.RUNNING})
        assert resolved == job_name
        resolved_ex = await resolve_job_ex(
            uri, client=client, status={JobStatus.RUNNING}
        )
        assert resolved_ex == (job_name, cluster_name)


async def test_resolve_job_id__from_uri_with_owner_other_user__no_jobs_found(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    job_owner = "job-owner"
    job_name = "my-job-name"
    uri = f"job://default/{job_owner}/{job_name}"
    JSON: Dict[str, Any] = {"jobs": []}

    async def handler(request: web.Request) -> web.Response:
        _check_params(
            request,
            name=job_name,
            owner=job_owner,
            cluster_name="default",
            reverse="1",
            limit="1",
        )
        return web.json_response(JSON)

    app = web.Application()
    app.router.add_get("/jobs", handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        with pytest.raises(ValueError):
            await resolve_job(uri, client=client, status={JobStatus.RUNNING})
        with pytest.raises(ValueError):
            await resolve_job_ex(uri, client=client, status={JobStatus.RUNNING})


async def test_resolve_job_id__from_uri_without_owner__no_jobs_found(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    job_name = "my-job-name"
    uri = f"job:{job_name}"
    JSON: Dict[str, Any] = {"jobs": []}

    async def handler(request: web.Request) -> web.Response:
        _check_params(
            request,
            name=job_name,
            owner="user",
            cluster_name="default",
            reverse="1",
            limit="1",
        )
        return web.json_response(JSON)

    app = web.Application()
    app.router.add_get("/jobs", handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        resolved = await resolve_job(uri, client=client, status={JobStatus.RUNNING})
        assert resolved == job_name
        resolved_ex = await resolve_job_ex(
            uri, client=client, status={JobStatus.RUNNING}
        )
        assert resolved_ex == (job_name, "default")


async def test_resolve_job_id__from_string__single_job_found(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    job_name = "test-job-name-555"
    job_id = "job-id-1"
    JSON = {"jobs": [_job_entry(job_id)]}

    async def handler(request: web.Request) -> web.Response:
        _check_params(
            request,
            name=job_name,
            owner="user",
            cluster_name="default",
            reverse="1",
            limit="1",
        )
        return web.json_response(JSON)

    app = web.Application()
    app.router.add_get("/jobs", handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        resolved = await resolve_job(
            job_name, client=client, status={JobStatus.RUNNING}
        )
        assert resolved == job_id
        resolved_ex = await resolve_job_ex(
            job_name, client=client, status={JobStatus.RUNNING}
        )
        assert resolved_ex == (job_id, "default")


@pytest.mark.parametrize("cluster_name", ["default", "other"])
async def test_resolve_job_id__from_uri_with_owner__single_job_found(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient, cluster_name: str
) -> None:
    job_owner = "job-owner"
    job_name = "my-job-name"
    uri = f"job://{cluster_name}/{job_owner}/{job_name}"
    job_id = "job-id-1"
    JSON = {"jobs": [_job_entry(job_id, cluster_name=cluster_name)]}

    async def handler(request: web.Request) -> web.Response:
        _check_params(
            request,
            name=job_name,
            owner=job_owner,
            cluster_name=cluster_name,
            reverse="1",
            limit="1",
        )
        return web.json_response(JSON)

    app = web.Application()
    app.router.add_get("/jobs", handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        resolved = await resolve_job(uri, client=client, status={JobStatus.RUNNING})
        assert resolved == job_id
        resolved_ex = await resolve_job_ex(
            uri, client=client, status={JobStatus.RUNNING}
        )
        assert resolved_ex == (job_id, cluster_name)


async def test_resolve_job_id__from_uri_without_owner__single_job_found(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    job_name = "my-job-name"
    uri = f"job:{job_name}"
    job_id = "job-id-1"
    JSON = {"jobs": [_job_entry(job_id)]}

    async def handler(request: web.Request) -> web.Response:
        _check_params(
            request,
            name=job_name,
            owner="user",
            cluster_name="default",
            reverse="1",
            limit="1",
        )
        return web.json_response(JSON)

    app = web.Application()
    app.router.add_get("/jobs", handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        resolved = await resolve_job(uri, client=client, status={JobStatus.RUNNING})
        assert resolved == job_id
        resolved_ex = await resolve_job_ex(
            uri, client=client, status={JobStatus.RUNNING}
        )
        assert resolved_ex == (job_id, "default")


async def test_resolve_job_id__server_error(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    job_id = "job-81839be3-3ecf-4ec5-80d9-19b1588869db"
    job_name = job_id

    async def handler(request: web.Request) -> NoReturn:
        _check_params(
            request,
            name=job_name,
            owner="user",
            cluster_name="default",
            reverse="1",
            limit="1",
        )
        raise web.HTTPError()

    app = web.Application()
    app.router.add_get("/jobs", handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        resolved = await resolve_job(
            job_name, client=client, status={JobStatus.RUNNING}
        )
        assert resolved == job_id
        resolved_ex = await resolve_job_ex(
            job_name, client=client, status={JobStatus.RUNNING}
        )
        assert resolved_ex == (job_id, "default")


@pytest.mark.parametrize("cluster_name", ["default", "other"])
async def test_resolve_job_id__from_uri_with_owner_same_user__server_error(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient, cluster_name: str
) -> None:
    job_owner = "user"
    job_name = "my-job-name"
    uri = f"job://{cluster_name}/{job_owner}/{job_name}"

    async def handler(request: web.Request) -> NoReturn:
        _check_params(
            request,
            name=job_name,
            owner=job_owner,
            cluster_name=cluster_name,
            reverse="1",
            limit="1",
        )
        raise web.HTTPError()

    app = web.Application()
    app.router.add_get("/jobs", handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        resolved = await resolve_job(uri, client=client, status={JobStatus.RUNNING})
        assert resolved == job_name
        resolved_ex = await resolve_job_ex(
            uri, client=client, status={JobStatus.RUNNING}
        )
        assert resolved_ex == (job_name, cluster_name)


async def test_resolve_job_id__from_uri_with_owner_other_user__server_error(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    job_owner = "job-owner"
    job_name = "my-job-name"
    uri = f"job://default/{job_owner}/{job_name}"

    async def handler(request: web.Request) -> NoReturn:
        _check_params(
            request,
            name=job_name,
            owner=job_owner,
            cluster_name="default",
            reverse="1",
            limit="1",
        )
        raise web.HTTPError()

    app = web.Application()
    app.router.add_get("/jobs", handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        with pytest.raises(ValueError):
            await resolve_job(uri, client=client, status={JobStatus.RUNNING})
        with pytest.raises(ValueError):
            await resolve_job_ex(uri, client=client, status={JobStatus.RUNNING})


async def test_resolve_job_id__from_uri_without_owner__server_error(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient
) -> None:
    job_name = "my-job-name"
    uri = f"job:{job_name}"

    async def handler(request: web.Request) -> NoReturn:
        _check_params(
            request,
            name=job_name,
            owner="user",
            cluster_name="default",
            reverse="1",
            limit="1",
        )
        raise web.HTTPError()

    app = web.Application()
    app.router.add_get("/jobs", handler)

    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        resolved = await resolve_job(uri, client=client, status={JobStatus.RUNNING})
        assert resolved == job_name
        resolved_ex = await resolve_job_ex(
            uri, client=client, status={JobStatus.RUNNING}
        )
        assert resolved_ex == (job_name, "default")


@pytest.mark.parametrize(
    "uri", ["job://default/user", "job://default/user/", "job:", "job://"]
)
async def test_resolve_job_id__from_uri__missing_job_id(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient, uri: str
) -> None:

    app = web.Application()
    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        with pytest.raises(
            ValueError,
            match="Invalid job URI: missing job-id or job-name",
        ):
            await resolve_job(uri, client=client, status={JobStatus.RUNNING})
        with pytest.raises(
            ValueError,
            match="Invalid job URI: missing job-id or job-name",
        ):
            await resolve_job_ex(uri, client=client, status={JobStatus.RUNNING})


@pytest.mark.parametrize("uri", ["job://default", "job://default/", "job:/", "job:///"])
async def test_resolve_job_id__from_uri__missing_owner(
    aiohttp_server: _TestServerFactory, make_client: _MakeClient, uri: str
) -> None:

    app = web.Application()
    srv = await aiohttp_server(app)

    async with make_client(srv.make_url("/")) as client:
        with pytest.raises(
            ValueError,
            match="Invalid job URI: missing owner",
        ):
            await resolve_job(uri, client=client, status={JobStatus.RUNNING})
        with pytest.raises(
            ValueError,
            match="Invalid job URI: missing owner",
        ):
            await resolve_job_ex(uri, client=client, status={JobStatus.RUNNING})


def test_parse_file_resource_no_scheme(root: Root) -> None:
    parsed = parse_file_resource("scheme-less/resource", root)
    assert parsed == URL((Path.cwd() / "scheme-less/resource").as_uri())
    parsed = parse_file_resource("c:scheme-less/resource", root)
    assert parsed == URL((Path("c:scheme-less").resolve() / "resource").as_uri())


def test_parse_file_resource_unsupported_scheme(root: Root) -> None:
    with pytest.raises(ValueError, match=r"Unsupported URI scheme"):
        parse_file_resource("http://neu.ro", root)
    with pytest.raises(ValueError, match=r"Unsupported URI scheme"):
        parse_file_resource("image:ubuntu", root)


def test_parse_file_resource_user_less(root: Root) -> None:
    user_less_permission = parse_file_resource("storage:resource", root)
    assert user_less_permission == URL(
        f"storage://{root.client.cluster_name}/{root.client.username}/resource"
    )


def test_parse_file_resource_with_user(root: Root) -> None:
    full_permission = parse_file_resource(
        f"storage://{root.client.cluster_name}/{root.client.username}/resource", root
    )
    assert full_permission == URL(
        f"storage://{root.client.cluster_name}/{root.client.username}/resource"
    )
    full_permission = parse_file_resource(f"storage://default/alice/resource", root)
    assert full_permission == URL(f"storage://default/alice/resource")


def test_parse_file_resource_with_tilde(root: Root) -> None:
    with pytest.raises(ValueError, match=r"Cannot expand user for "):
        parse_file_resource(f"storage://~/resource", root)


def test_parse_resource_for_sharing_image_no_tag(root: Root) -> None:
    uri = "image:ubuntu"
    parsed = parse_resource_for_sharing(uri, root)
    assert parsed == URL(
        f"image://{root.client.cluster_name}/{root.client.username}/ubuntu"
    )


def test_parse_resource_for_sharing_image_non_ascii(root: Root) -> None:
    uri = "image:образ"
    parsed = parse_resource_for_sharing(uri, root)
    assert parsed == URL(
        f"image://{root.client.cluster_name}/{root.client.username}/образ"
    )
    assert parsed.path == f"/{root.client.username}/образ"


def test_parse_resource_for_sharing_image_percent_encoded(root: Root) -> None:
    uri = "image:%252d%3f%23"
    parsed = parse_resource_for_sharing(uri, root)
    assert parsed == URL(
        f"image://{root.client.cluster_name}/{root.client.username}/%252d%3f%23"
    )
    assert parsed.path == f"/{root.client.username}/%2d?#"


def test_parse_resource_for_sharing_image_with_tag_fail(root: Root) -> None:
    uri = "image:ubuntu:latest"
    with pytest.raises(ValueError, match="tag is not allowed"):
        parse_resource_for_sharing(uri, root)


def test_parse_resource_for_sharing_all_user_images(root: Root) -> None:
    uri = "image:/otheruser"
    parsed = parse_resource_for_sharing(uri, root)
    assert parsed == URL(f"image://{root.client.cluster_name}/otheruser")


def _test_parse_resource_for_sharing_all_cluster_images(root: Root) -> None:
    uri = "image://"
    parsed = parse_resource_for_sharing(uri, root)
    assert parsed == URL(f"image://{root.client.cluster_name}/otheruser")


def test_parse_resource_for_sharing_no_scheme(root: Root) -> None:
    with pytest.raises(ValueError, match=r"URI Scheme not specified"):
        parse_resource_for_sharing("scheme-less/resource", root)


def test_parse_resource_for_sharing_unsupported_scheme(root: Root) -> None:
    with pytest.raises(ValueError, match=r"Unsupported URI scheme"):
        parse_resource_for_sharing("http://neu.ro", root)
    with pytest.raises(ValueError, match=r"Unsupported URI scheme"):
        parse_resource_for_sharing("file:///etc/password", root)
    with pytest.raises(ValueError, match=r"Unsupported URI scheme"):
        parse_resource_for_sharing(r"c:scheme-less/resource", root)


def test_parse_resource_for_sharing_user_less(root: Root) -> None:
    user_less_permission = parse_resource_for_sharing("storage:resource", root)
    assert user_less_permission == URL(
        f"storage://{root.client.cluster_name}/{root.client.username}/resource"
    )


def test_parse_resource_for_sharing_with_user(root: Root) -> None:
    full_permission = parse_resource_for_sharing(
        f"storage://{root.client.cluster_name}/{root.client.username}/resource", root
    )
    assert full_permission == URL(
        f"storage://{root.client.cluster_name}/{root.client.username}/resource"
    )
    full_permission = parse_resource_for_sharing(
        f"storage://default/alice/resource", root
    )
    assert full_permission == URL(f"storage://default/alice/resource")


def test_parse_resource_for_sharing_with_tilde(root: Root) -> None:
    with pytest.raises(ValueError, match=r"Cannot expand user for "):
        parse_resource_for_sharing(f"storage://~/resource", root)


def test_parse_resource_for_sharing_with_tilde_relative(root: Root) -> None:
    with pytest.raises(ValueError, match=r"Cannot expand user for "):
        parse_resource_for_sharing(f"storage:~/resource", root)


def test_parse_permission_action_read_lowercase() -> None:
    action = "read"
    assert parse_permission_action(action) == Action.READ


def test_parse_permission_action_read() -> None:
    action = "READ"
    assert parse_permission_action(action) == Action.READ


def test_parse_permission_action_write_lowercase() -> None:
    action = "write"
    assert parse_permission_action(action) == Action.WRITE


def test_parse_permission_action_write() -> None:
    action = "WRITE"
    assert parse_permission_action(action) == Action.WRITE


def test_parse_permission_action_manage_lowercase() -> None:
    action = "manage"
    assert parse_permission_action(action) == Action.MANAGE


def test_parse_permission_action_manage() -> None:
    action = "MANAGE"
    assert parse_permission_action(action) == Action.MANAGE


def test_parse_permission_action_wrong_string() -> None:
    action = "tosh"
    err = "invalid permission action 'tosh', allowed values: read, write, manage"
    with pytest.raises(ValueError, match=err):
        parse_permission_action(action)


def test_parse_permission_action_wrong_empty() -> None:
    action = ""
    err = "invalid permission action '', allowed values: read, write, manage"
    with pytest.raises(ValueError, match=err):
        parse_permission_action(action)


def test_pager_maybe_no_tty() -> None:
    with mock.patch.multiple(
        "click", echo=mock.DEFAULT, echo_via_pager=mock.DEFAULT
    ) as mocked:
        mock_echo = mocked["echo"]
        mock_echo_via_pager = mocked["echo_via_pager"]

        terminal_size = (100, 10)
        tty = False
        large_input = [f"line {x}" for x in range(20)]

        pager_maybe(large_input, tty, terminal_size)
        assert mock_echo.call_args_list == [mock.call(x) for x in large_input]
        mock_echo_via_pager.assert_not_called()


def test_pager_maybe_terminal_larger() -> None:
    with mock.patch.multiple(
        "click", echo=mock.DEFAULT, echo_via_pager=mock.DEFAULT
    ) as mocked:
        mock_echo = mocked["echo"]
        mock_echo_via_pager = mocked["echo_via_pager"]

        terminal_size = (100, 10)
        tty = True
        small_input = ["line 1", "line 2"]

        pager_maybe(small_input, tty, terminal_size)
        assert mock_echo.call_args_list == [mock.call(x) for x in small_input]
        mock_echo_via_pager.assert_not_called()


def test_pager_maybe_terminal_smaller() -> None:
    with mock.patch.multiple(
        "click", echo=mock.DEFAULT, echo_via_pager=mock.DEFAULT
    ) as mocked:
        mock_echo = mocked["echo"]
        mock_echo_via_pager = mocked["echo_via_pager"]

        terminal_size = (100, 10)
        tty = True
        large_input = [f"line {x}" for x in range(20)]

        pager_maybe(large_input, tty, terminal_size)
        mock_echo.assert_not_called()
        mock_echo_via_pager.assert_called_once()
        lines_it = mock_echo_via_pager.call_args[0][0]
        assert "".join(lines_it) == "\n".join(large_input)

        # Do the same, but call with a generator function for input instead
        mock_echo_via_pager.reset_mock()
        iter_input = iter(large_input)
        next(iter_input)  # Skip first line

        pager_maybe(iter_input, tty, terminal_size)
        mock_echo.assert_not_called()
        mock_echo_via_pager.assert_called_once()
        lines_it = mock_echo_via_pager.call_args[0][0]
        assert "".join(lines_it) == "\n".join(large_input[1:])


async def test_calc_life_span_none_default(
    monkeypatch: Any, tmp_path: Path, make_client: _MakeClient
) -> None:
    async with make_client("https://example.com") as client:
        monkeypatch.chdir(tmp_path)
        local_conf = tmp_path / ".neuro.toml"
        local_conf.write_text(toml.dumps({"job": {"life-span": "1d2h3m4s"}}))
        expected = timedelta(days=1, hours=2, minutes=3, seconds=4)
        assert (
            await calc_life_span(client, None, "1d", "job") == expected.total_seconds()
        )


async def test_calc_life_span_default_life_span_all_keys(
    caplog: Any, monkeypatch: Any, tmp_path: Path, make_client: _MakeClient
) -> None:
    async with make_client("https://example.com") as client:
        monkeypatch.chdir(tmp_path)
        local_conf = tmp_path / ".neuro.toml"
        # empty config
        local_conf.write_text(toml.dumps({"job": {"life-span": "1d2h3m4s"}}))

        expected = timedelta(days=1, hours=2, minutes=3, seconds=4)
        assert (
            await calc_life_span(client, None, "1d", "job") == expected.total_seconds()
        )


async def test_calc_default_life_span_invalid(
    caplog: Any,
    monkeypatch: Any,
    tmp_path: Path,
    make_client: _MakeClient,
) -> None:
    async with make_client("https://example.com") as client:
        monkeypatch.chdir(tmp_path)
        local_conf = tmp_path / ".neuro.toml"
        # empty config
        local_conf.write_text(toml.dumps({"job": {"life-span": "invalid"}}))
        with pytest.raises(
            click.UsageError,
            match="Could not parse time delta",
        ):
            await calc_life_span(client, None, "1d", "job")


async def test_calc_default_life_span_default_value(
    caplog: Any,
    monkeypatch: Any,
    tmp_path: Path,
    make_client: _MakeClient,
) -> None:
    async with make_client("https://example.com") as client:
        monkeypatch.chdir(tmp_path)
        local_conf = tmp_path / ".neuro.toml"
        # empty config
        local_conf.write_text(toml.dumps({}))
        default = parse_timedelta("1d")
        assert (
            await calc_life_span(client, None, "1d", "job") == default.total_seconds()
        )
