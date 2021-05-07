import asyncio
import enum
import json
import logging
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from typing import (
    Any,
    AsyncIterator,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Union,
    overload,
)

import aiohttp
import attr
from aiodocker.exceptions import DockerError
from aiohttp import WSMsgType, WSServerHandshakeError
from dateutil.parser import isoparse
from multidict import MultiDict
from yarl import URL

from .abc import (
    AbstractDockerImageProgress,
    ImageCommitFinished,
    ImageCommitStarted,
    ImageProgressPush,
    ImageProgressSave,
)
from .config import Config
from .core import _Core
from .images import (
    _DummyProgress,
    _raise_on_error_chunk,
    _try_parse_image_progress_step,
)
from .parser import DiskVolume, Parser, SecretFile, Volume
from .parsing_utils import LocalImage, RemoteImage, _as_repo_str, _is_in_neuro_registry
from .url_utils import (
    normalize_disk_uri,
    normalize_secret_uri,
    normalize_storage_path_uri,
)
from .utils import NoPublicConstructor

if sys.version_info >= (3, 7):  # pragma: no cover
    from contextlib import asynccontextmanager
else:
    from async_generator import asynccontextmanager


log = logging.getLogger(__name__)

INVALID_IMAGE_NAME = "INVALID-IMAGE-NAME"


@dataclass(frozen=True)
class Resources:
    memory_mb: int
    cpu: float
    gpu: Optional[int] = None
    gpu_model: Optional[str] = None
    shm: bool = True
    tpu_type: Optional[str] = None
    tpu_software_version: Optional[str] = None


class JobStatus(str, enum.Enum):
    """An Enum subclass that represents job statuses.

    PENDING: a job is being created and scheduled. This includes finding (and
    possibly waiting for) sufficient amount of resources, pulling an image
    from a registry etc.
    SUSPENDED: a preemptible job is paused to allow other jobs to run.
    RUNNING: a job is being run.
    SUCCEEDED: a job terminated with the 0 exit code.
    CANCELLED: a running job was manually terminated/deleted.
    FAILED: a job terminated with a non-0 exit code.
    """

    PENDING = "pending"
    SUSPENDED = "suspended"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"  # invalid status code, a default value is status is not sent

    @property
    def is_pending(self) -> bool:
        return self in (self.PENDING, self.SUSPENDED)

    @property
    def is_running(self) -> bool:
        return self == self.RUNNING

    @property
    def is_finished(self) -> bool:
        return self in (self.SUCCEEDED, self.FAILED, self.CANCELLED)

    @classmethod
    def items(cls) -> Set["JobStatus"]:
        return {item for item in cls if item != cls.UNKNOWN}

    @classmethod
    def active_items(cls) -> Set["JobStatus"]:
        return {item for item in cls.items() if not item.is_finished}

    @classmethod
    def finished_items(cls) -> Set["JobStatus"]:
        return {item for item in cls.items() if item.is_finished}


@dataclass(frozen=True)
class HTTPPort:
    port: int
    requires_auth: bool = True


@dataclass(frozen=True)
class Container:
    image: RemoteImage
    resources: Resources
    entrypoint: Optional[str] = None
    command: Optional[str] = None
    working_dir: Optional[str] = None
    http: Optional[HTTPPort] = None
    env: Mapping[str, str] = field(default_factory=dict)
    volumes: Sequence[Volume] = field(default_factory=list)
    secret_env: Mapping[str, URL] = field(default_factory=dict)
    secret_files: Sequence[SecretFile] = field(default_factory=list)
    disk_volumes: Sequence[DiskVolume] = field(default_factory=list)
    tty: bool = False


@dataclass(frozen=True)
class JobStatusItem:
    status: JobStatus
    transition_time: datetime
    reason: str = ""
    description: str = ""
    exit_code: Optional[int] = None


@dataclass(frozen=True)
class JobStatusHistory:
    status: JobStatus
    reason: str
    description: str
    restarts: int = 0
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    transitions: Sequence[JobStatusItem] = field(default_factory=list)

    @property
    def changed_at(self) -> datetime:
        if self.status == JobStatus.PENDING:
            when = self.created_at
        elif self.status == JobStatus.RUNNING:
            when = self.started_at
        elif self.status == JobStatus.RUNNING or self.status == JobStatus.SUSPENDED:
            when = self.started_at
        elif self.status.is_finished:
            when = self.finished_at
        else:
            when = self.transitions[-1].transition_time
        assert when is not None
        return when


class JobRestartPolicy(str, enum.Enum):
    NEVER = "never"
    ON_FAILURE = "on-failure"
    ALWAYS = "always"

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return repr(self.value)


@dataclass(frozen=True)
class JobDescription:
    id: str
    owner: str
    cluster_name: str
    status: JobStatus
    history: JobStatusHistory
    container: Container
    scheduler_enabled: bool
    pass_config: bool
    uri: URL
    name: Optional[str] = None
    tags: Sequence[str] = ()
    description: Optional[str] = None
    http_url: URL = URL()
    internal_hostname: Optional[str] = None
    internal_hostname_named: Optional[str] = None
    restart_policy: JobRestartPolicy = JobRestartPolicy.NEVER
    life_span: Optional[float] = None
    schedule_timeout: Optional[float] = None
    preset_name: Optional[str] = None
    preemptible_node: bool = False
    privileged: bool = False


@dataclass(frozen=True)
class JobTelemetry:
    cpu: float
    memory: float
    timestamp: float
    gpu_duty_cycle: Optional[int] = None
    gpu_memory: Optional[float] = None


@dataclass(frozen=True)
class ExecInspect:
    id: str
    running: bool
    exit_code: int
    job_id: str
    tty: bool
    entrypoint: str
    command: str


@dataclass(frozen=True)
class Message:
    fileno: int
    data: bytes


class StdStream:
    def __init__(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self._ws = ws
        self._closing = False

    async def close(self) -> None:
        self._closing = True
        await self._ws.close()

    async def read_out(self) -> Optional[Message]:
        if self._closing:
            return None
        msg = await self._ws.receive()
        if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
            self._closing = True
            return None
        return Message(msg.data[0], msg.data[1:])

    async def write_in(self, data: bytes) -> None:
        if self._closing:
            return
        await self._ws.send_bytes(data)


class Jobs(metaclass=NoPublicConstructor):
    def __init__(self, core: _Core, config: Config, parse: Parser) -> None:
        self._core = core
        self._config = config
        self._parse = parse

    def _get_monitoring_url(self, cluster_name: Optional[str]) -> URL:
        if cluster_name is None:
            cluster_name = self._config.cluster_name
        return self._config.get_cluster(cluster_name).monitoring_url

    async def run(
        self,
        container: Container,
        *,
        name: Optional[str] = None,
        tags: Sequence[str] = (),
        description: Optional[str] = None,
        scheduler_enabled: bool = False,
        pass_config: bool = False,
        wait_for_jobs_quota: bool = False,
        schedule_timeout: Optional[float] = None,
        restart_policy: JobRestartPolicy = JobRestartPolicy.NEVER,
        life_span: Optional[float] = None,
    ) -> JobDescription:
        url = self._config.api_url / "jobs"
        payload = _job_to_api(
            config=self._config,
            name=name,
            tags=tags,
            description=description,
            pass_config=pass_config,
            wait_for_jobs_quota=wait_for_jobs_quota,
            schedule_timeout=schedule_timeout,
            restart_policy=restart_policy,
            life_span=life_span,
        )
        payload["container"] = _container_to_api(
            config=self._config,
            image=container.image,
            entrypoint=container.entrypoint,
            command=container.command,
            working_dir=container.working_dir,
            http=container.http,
            env=container.env,
            volumes=container.volumes,
            secret_env=container.secret_env,
            secret_files=container.secret_files,
            disk_volumes=container.disk_volumes,
            tty=container.tty,
        )
        payload["container"]["resources"] = _resources_to_api(container.resources)
        payload["scheduler_enabled"] = scheduler_enabled
        auth = await self._config._api_auth()
        async with self._core.request("POST", url, json=payload, auth=auth) as resp:
            res = await resp.json()
            return _job_description_from_api(res, self._parse)

    async def start(
        self,
        *,
        image: RemoteImage,
        preset_name: str,
        entrypoint: Optional[str] = None,
        command: Optional[str] = None,
        working_dir: Optional[str] = None,
        http: Optional[HTTPPort] = None,
        env: Optional[Mapping[str, str]] = None,
        volumes: Sequence[Volume] = (),
        secret_env: Optional[Mapping[str, URL]] = None,
        secret_files: Sequence[SecretFile] = (),
        disk_volumes: Sequence[DiskVolume] = (),
        tty: bool = False,
        shm: bool = False,
        name: Optional[str] = None,
        tags: Sequence[str] = (),
        description: Optional[str] = None,
        pass_config: bool = False,
        wait_for_jobs_quota: bool = False,
        schedule_timeout: Optional[float] = None,
        restart_policy: JobRestartPolicy = JobRestartPolicy.NEVER,
        life_span: Optional[float] = None,
        privileged: bool = False,
    ) -> JobDescription:
        url = (self._config.api_url / "jobs").with_query("from_preset")
        container_payload = _container_to_api(
            config=self._config,
            image=image,
            entrypoint=entrypoint,
            command=command,
            working_dir=working_dir,
            http=http,
            env=env,
            volumes=volumes,
            secret_env=secret_env,
            secret_files=secret_files,
            disk_volumes=disk_volumes,
            tty=tty,
            shm=shm,
        )
        payload = _job_to_api(
            config=self._config,
            name=name,
            preset_name=preset_name,
            tags=tags,
            description=description,
            pass_config=pass_config,
            wait_for_jobs_quota=wait_for_jobs_quota,
            schedule_timeout=schedule_timeout,
            restart_policy=restart_policy,
            life_span=life_span,
            privileged=privileged,
        )
        payload.update(**container_payload)
        auth = await self._config._api_auth()
        async with self._core.request("POST", url, json=payload, auth=auth) as resp:
            res = await resp.json()
            return _job_description_from_api(res, self._parse)

    async def list(
        self,
        *,
        statuses: Iterable[JobStatus] = (),
        name: str = "",
        tags: Iterable[str] = (),
        owners: Iterable[str] = (),
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        reverse: bool = False,
        limit: Optional[int] = None,
        cluster_name: Optional[str] = None,
    ) -> AsyncIterator[JobDescription]:
        url = self._config.api_url / "jobs"
        headers = {"Accept": "application/x-ndjson"}
        params: MultiDict[str] = MultiDict()
        for status in statuses:
            params.add("status", status.value)
        if name:
            params.add("name", name)
        for owner in owners:
            params.add("owner", owner)
        for tag in tags:
            params.add("tag", tag)
        if since:
            if since.tzinfo is None:
                # Interpret naive datetime object as local time.
                since = since.astimezone(timezone.utc)
            params.add("since", since.isoformat())
        if until:
            if until.tzinfo is None:
                until = until.astimezone(timezone.utc)
            params.add("until", until.isoformat())
        if cluster_name is None:
            cluster_name = self._config.cluster_name
        params["cluster_name"] = cluster_name
        if reverse:
            params.add("reverse", "1")
        if limit is not None:
            params.add("limit", str(limit))
        auth = await self._config._api_auth()
        async with self._core.request(
            "GET", url, headers=headers, params=params, auth=auth
        ) as resp:
            if resp.headers.get("Content-Type", "").startswith("application/x-ndjson"):
                async for line in resp.content:
                    server_message = json.loads(line)
                    if "error" in server_message:
                        raise Exception(server_message["error"])
                    yield _job_description_from_api(server_message, self._parse)
            else:
                ret = await resp.json()
                for j in ret["jobs"]:
                    yield _job_description_from_api(j, self._parse)

    async def kill(self, id: str) -> None:
        url = self._config.api_url / "jobs" / id
        auth = await self._config._api_auth()
        async with self._core.request("DELETE", url, auth=auth):
            # an error is raised for status >= 400
            return None  # 201 status code

    async def bump_life_span(self, id: str, additional_life_span: float) -> None:
        url = self._config.api_url / "jobs" / id / "max_run_time_minutes"
        payload = {
            "additional_max_run_time_minutes": int(additional_life_span // 60),
        }
        auth = await self._config._api_auth()
        async with self._core.request("PUT", url, json=payload, auth=auth):
            # an error is raised for status >= 400
            return None  # 201 status code

    async def monitor(
        self, id: str, *, cluster_name: Optional[str] = None
    ) -> AsyncIterator[bytes]:
        url = self._get_monitoring_url(cluster_name) / id / "log"
        timeout = attr.evolve(self._core.timeout, sock_read=None)
        auth = await self._config._api_auth()
        async with self._core.request(
            "GET",
            url,
            headers={"Accept-Encoding": "identity"},
            timeout=timeout,
            auth=auth,
        ) as resp:
            async for data in resp.content.iter_any():
                yield data

    async def status(self, id: str) -> JobDescription:
        url = self._config.api_url / "jobs" / id
        auth = await self._config._api_auth()
        async with self._core.request("GET", url, auth=auth) as resp:
            ret = await resp.json()
            return _job_description_from_api(ret, self._parse)

    async def tags(self) -> List[str]:
        url = self._config.api_url / "tags"
        auth = await self._config._api_auth()
        async with self._core.request("GET", url, auth=auth) as resp:
            ret = await resp.json()
            return ret["tags"]

    async def top(
        self, id: str, *, cluster_name: Optional[str] = None
    ) -> AsyncIterator[JobTelemetry]:
        url = self._get_monitoring_url(cluster_name) / id / "top"
        auth = await self._config._api_auth()
        try:
            received_any = False
            async for resp in self._core.ws_connect(url, auth=auth):
                yield _job_telemetry_from_api(resp.json())
                received_any = True
            if not received_any:
                raise ValueError(f"Job is not running. Job Id = {id}")
        except WSServerHandshakeError as e:
            if e.status == 400:
                raise ValueError(f"Job not found. Job Id = {id}")
            raise

    async def save(
        self,
        id: str,
        image: RemoteImage,
        *,
        progress: Optional[AbstractDockerImageProgress] = None,
        cluster_name: Optional[str] = None,
    ) -> None:
        if not _is_in_neuro_registry(image):
            raise ValueError(f"Image `{image}` must be in the neuro registry")
        if progress is None:
            progress = _DummyProgress()

        payload = {"container": {"image": _as_repo_str(image)}}
        url = self._get_monitoring_url(cluster_name) / id / "save"

        auth = await self._config._api_auth()
        timeout = attr.evolve(self._core.timeout, sock_read=None)
        # `self._code.request` implicitly sets `total=3 * 60`
        # unless `sock_read is None`
        async with self._core.request(
            "POST", url, json=payload, timeout=timeout, auth=auth
        ) as resp:
            # first, we expect exactly two docker-commit messages
            progress.save(ImageProgressSave(id, image))

            chunk_1 = await resp.content.readline()
            data_1 = _parse_commit_started_chunk(id, _load_chunk(chunk_1), self._parse)
            progress.commit_started(data_1)

            chunk_2 = await resp.content.readline()
            data_2 = _parse_commit_finished_chunk(id, _load_chunk(chunk_2))
            progress.commit_finished(data_2)

            # then, we expect stream for docker-push
            src = LocalImage(f"{image.owner}/{image.name}", image.tag)
            progress.push(ImageProgressPush(src, dst=image))
            async for chunk in resp.content:
                obj = _load_chunk(chunk)
                push_step = _try_parse_image_progress_step(obj, image.tag)
                if push_step:
                    progress.step(push_step)

    @asynccontextmanager
    async def port_forward(
        self, id: str, local_port: int, job_port: int, *, no_key_check: bool = False
    ) -> AsyncIterator[None]:
        srv = await asyncio.start_server(
            partial(self._port_forward, id=id, job_port=job_port),
            "localhost",
            local_port,
        )
        try:
            yield
        finally:
            srv.close()
            if sys.version_info >= (3, 7):
                await srv.wait_closed()

    async def _port_forward(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        id: str,
        job_port: int,
        *,
        cluster_name: Optional[str] = None,
    ) -> None:
        try:
            loop = asyncio.get_event_loop()
            url = self._get_monitoring_url(cluster_name)
            url = url / id / "port_forward" / str(job_port)
            auth = await self._config._api_auth()
            ws = await self._core._session.ws_connect(
                url,
                headers={"Authorization": auth},
                timeout=None,  # type: ignore
                receive_timeout=None,
                heartbeat=30,
            )
            tasks = []
            tasks.append(loop.create_task(self._port_reader(ws, writer)))
            tasks.append(loop.create_task(self._port_writer(ws, reader)))
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
                writer.close()
                if sys.version_info >= (3, 7):
                    await writer.wait_closed()
                await ws.close()
        except asyncio.CancelledError:
            raise
        except WSServerHandshakeError as e:
            if e.headers and "X-Error" in e.headers:
                log.error(f"Error during port-forwarding: {e.headers['X-Error']}")
            log.exception("Unhandled exception during port-forwarding")
            writer.close()
        except Exception:
            log.exception("Unhandled exception during port-forwarding")
            writer.close()

    async def _port_reader(
        self, ws: aiohttp.ClientWebSocketResponse, writer: asyncio.StreamWriter
    ) -> None:
        async for msg in ws:
            assert msg.type == aiohttp.WSMsgType.BINARY
            writer.write(msg.data)
            await writer.drain()
        writer.close()
        if sys.version_info >= (3, 7):
            await writer.wait_closed()

    async def _port_writer(
        self, ws: aiohttp.ClientWebSocketResponse, reader: asyncio.StreamReader
    ) -> None:
        while True:
            data = await reader.read(4 * 1024 * 1024)
            if not data:
                # EOF
                break
            await ws.send_bytes(data)

    @asynccontextmanager
    async def attach(
        self,
        id: str,
        *,
        stdin: bool = False,
        stdout: bool = False,
        stderr: bool = False,
        logs: bool = False,
        cluster_name: Optional[str] = None,
    ) -> AsyncIterator[StdStream]:
        url = self._get_monitoring_url(cluster_name) / id / "attach"
        url = url.with_query(
            stdin=str(int(stdin)),
            stdout=str(int(stdout)),
            stderr=str(int(stderr)),
            logs=str(int(logs)),
        )
        auth = await self._config._api_auth()
        ws = await self._core._session.ws_connect(
            url,
            headers={"Authorization": auth},
            timeout=None,  # type: ignore
            receive_timeout=None,
            heartbeat=30,
        )

        try:
            yield StdStream(ws)
        finally:
            await ws.close()

    async def resize(
        self, id: str, *, w: int, h: int, cluster_name: Optional[str] = None
    ) -> None:
        url = self._get_monitoring_url(cluster_name) / id / "resize"
        url = url.with_query(w=w, h=h)
        auth = await self._config._api_auth()
        async with self._core.request("POST", url, auth=auth):
            pass

    async def exec_create(
        self,
        id: str,
        cmd: str,
        *,
        tty: bool = False,
        cluster_name: Optional[str] = None,
    ) -> str:
        payload = {
            "command": cmd,
            "stdin": True,
            "stdout": True,
            "stderr": True,
            "tty": tty,
        }
        url = self._get_monitoring_url(cluster_name) / id / "exec_create"
        auth = await self._config._api_auth()
        async with self._core.request("POST", url, json=payload, auth=auth) as resp:
            ret = await resp.json()
            return ret["exec_id"]

    async def exec_resize(
        self,
        id: str,
        exec_id: str,
        *,
        w: int,
        h: int,
        cluster_name: Optional[str] = None,
    ) -> None:
        url = self._get_monitoring_url(cluster_name) / id / exec_id / "exec_resize"
        url = url.with_query(w=w, h=h)
        auth = await self._config._api_auth()
        async with self._core.request("POST", url, auth=auth) as resp:
            resp

    async def exec_inspect(
        self, id: str, exec_id: str, *, cluster_name: Optional[str] = None
    ) -> ExecInspect:
        url = self._get_monitoring_url(cluster_name) / id / exec_id / "exec_inspect"
        auth = await self._config._api_auth()
        async with self._core.request("GET", url, auth=auth) as resp:
            data = await resp.json()
            return ExecInspect(
                id=data["id"],
                running=data["running"],
                exit_code=data["exit_code"],
                job_id=data["job_id"],
                tty=data["tty"],
                entrypoint=data["entrypoint"],
                command=data["command"],
            )

    @asynccontextmanager
    async def exec_start(
        self, id: str, exec_id: str, *, cluster_name: Optional[str] = None
    ) -> AsyncIterator[StdStream]:
        url = self._get_monitoring_url(cluster_name) / id / exec_id / "exec_start"
        auth = await self._config._api_auth()

        ws = await self._core._session.ws_connect(
            url,
            headers={"Authorization": auth},
            timeout=None,  # type: ignore
            receive_timeout=None,
            heartbeat=30,
        )

        try:
            yield StdStream(ws)
        finally:
            await ws.close()

    async def send_signal(
        self, id: str, signal: Union[str, int], *, cluster_name: Optional[str] = None
    ) -> None:
        url = self._get_monitoring_url(cluster_name) / id / "kill"
        url = url.with_query(signal=signal)
        auth = await self._config._api_auth()
        async with self._core.request("POST", url, auth=auth) as resp:
            resp

    async def get_capacity(
        self, *, cluster_name: Optional[str] = None
    ) -> Mapping[str, int]:
        url = self._get_monitoring_url(cluster_name) / "capacity"
        auth = await self._config._api_auth()
        async with self._core.request("GET", url, auth=auth) as resp:
            return await resp.json()


#  ############## Internal helpers ###################


def _load_chunk(chunk: bytes) -> Dict[str, Any]:
    return json.loads(chunk.decode())


def _parse_commit_started_chunk(
    job_id: str, obj: Dict[str, Any], parse: Parser
) -> ImageCommitStarted:
    _raise_for_invalid_commit_chunk(obj, expect_started=True)
    details_json = obj.get("details", {})
    image = details_json.get("image")
    if not image:
        error_details = {"message": "Missing required details: 'image'"}
        raise DockerError(400, error_details)
    return ImageCommitStarted(job_id, parse.remote_image(image))


def _parse_commit_finished_chunk(
    job_id: str, obj: Dict[str, Any]
) -> ImageCommitFinished:
    _raise_for_invalid_commit_chunk(obj, expect_started=False)
    return ImageCommitFinished(job_id)


def _raise_for_invalid_commit_chunk(obj: Dict[str, Any], expect_started: bool) -> None:
    _raise_on_error_chunk(obj)
    if "status" not in obj.keys():
        error_details = {"message": 'Missing required field: "status"'}
        raise DockerError(400, error_details)
    status = obj["status"]
    expected = "CommitStarted" if expect_started else "CommitFinished"
    if status != expected:
        error_details = {
            "message": f"Invalid commit status: '{status}', expecting: '{expected}'"
        }
        raise DockerError(400, error_details)


def _resources_to_api(resources: Resources) -> Dict[str, Any]:
    value: Dict[str, Any] = {
        "memory_mb": resources.memory_mb,
        "cpu": resources.cpu,
        "shm": resources.shm,
    }
    if resources.gpu:
        value["gpu"] = resources.gpu
        value["gpu_model"] = resources.gpu_model
    if resources.tpu_type:
        assert resources.tpu_software_version
        value["tpu"] = {
            "type": resources.tpu_type,
            "software_version": resources.tpu_software_version,
        }
    return value


def _resources_from_api(data: Dict[str, Any]) -> Resources:
    tpu_type = tpu_software_version = None
    if "tpu" in data:
        tpu = data["tpu"]
        tpu_type = tpu["type"]
        tpu_software_version = tpu["software_version"]
    return Resources(
        memory_mb=data["memory_mb"],
        cpu=data["cpu"],
        shm=data.get("shm", True),
        gpu=data.get("gpu", None),
        gpu_model=data.get("gpu_model", None),
        tpu_type=tpu_type,
        tpu_software_version=tpu_software_version,
    )


def _http_port_to_api(port: HTTPPort) -> Dict[str, Any]:
    return {"port": port.port, "requires_auth": port.requires_auth}


def _http_port_from_api(data: Dict[str, Any]) -> HTTPPort:
    return HTTPPort(
        port=data.get("port", -1), requires_auth=data.get("requires_auth", False)
    )


def _container_from_api(data: Dict[str, Any], parse: Parser) -> Container:
    try:
        image = parse.remote_image(data["image"])
    except ValueError:
        image = RemoteImage.new_external_image(name=INVALID_IMAGE_NAME)

    return Container(
        image=image,
        resources=_resources_from_api(data["resources"]),
        entrypoint=data.get("entrypoint", None),
        command=data.get("command", None),
        working_dir=data.get("working_dir"),
        http=_http_port_from_api(data["http"]) if "http" in data else None,
        env=data.get("env", dict()),
        volumes=[_volume_from_api(v) for v in data.get("volumes", [])],
        secret_env={name: URL(val) for name, val in data.get("secret_env", {}).items()},
        secret_files=[_secret_file_from_api(v) for v in data.get("secret_volumes", [])],
        disk_volumes=[_disk_volume_from_api(v) for v in data.get("disk_volumes", [])],
        tty=data.get("tty", False),
    )


def _container_to_api(
    config: Config,
    image: RemoteImage,
    entrypoint: Optional[str] = None,
    command: Optional[str] = None,
    working_dir: Optional[str] = None,
    http: Optional[HTTPPort] = None,
    env: Optional[Mapping[str, str]] = None,
    volumes: Sequence[Volume] = (),
    secret_env: Optional[Mapping[str, URL]] = None,
    secret_files: Sequence[SecretFile] = (),
    disk_volumes: Sequence[DiskVolume] = (),
    tty: bool = False,
    shm: bool = False,
) -> Dict[str, Any]:
    primitive: Dict[str, Any] = {"image": _as_repo_str(image)}
    if shm:
        primitive["resources"] = {"shm": shm}
    if entrypoint:
        primitive["entrypoint"] = entrypoint
    if command:
        primitive["command"] = command
    if working_dir:
        primitive["working_dir"] = working_dir
    if http:
        primitive["http"] = _http_port_to_api(http)
    if env:
        primitive["env"] = env
    if volumes:
        primitive["volumes"] = [_volume_to_api(v, config) for v in volumes]
    if secret_env:
        primitive["secret_env"] = {
            k: str(normalize_secret_uri(v, config.username, config.cluster_name))
            for k, v in secret_env.items()
        }
    if secret_files:
        primitive["secret_volumes"] = [
            _secret_file_to_api(v, config) for v in secret_files
        ]
    if disk_volumes:
        primitive["disk_volumes"] = [
            _disk_volume_to_api(v, config) for v in disk_volumes
        ]
    if tty:
        primitive["tty"] = True
    return primitive


def _calc_status(stat: str) -> JobStatus:
    # Forward-compatible support for CANCELLED status
    try:
        return JobStatus(stat)
    except ValueError:
        return JobStatus.UNKNOWN


def _job_status_item_from_api(res: Dict[str, Any]) -> JobStatusItem:
    return JobStatusItem(
        status=_calc_status(res.get("status", "unknown")),
        transition_time=_parse_datetime(res["transition_time"]),
        reason=res.get("reason", ""),
        description=res.get("description", ""),
        exit_code=res.get("exit_code"),
    )


def _job_description_from_api(res: Dict[str, Any], parse: Parser) -> JobDescription:
    container = _container_from_api(res["container"], parse)
    owner = res["owner"]
    cluster_name = res["cluster_name"]
    name = res.get("name")
    tags = res.get("tags", ())
    description = res.get("description")
    history = JobStatusHistory(
        # Forward-compatible support for CANCELLED status
        status=_calc_status(res["history"].get("status", "unknown")),
        reason=res["history"].get("reason", ""),
        restarts=res["history"].get("restarts", 0),
        description=res["history"].get("description", ""),
        created_at=_parse_datetime(res["history"].get("created_at")),
        started_at=_parse_datetime(res["history"].get("started_at")),
        finished_at=_parse_datetime(res["history"].get("finished_at")),
        exit_code=res["history"].get("exit_code"),
        transitions=[
            _job_status_item_from_api(item_raw) for item_raw in res.get("statuses", [])
        ],
    )
    http_url = URL(res.get("http_url", ""))
    http_url_named = URL(res.get("http_url_named", ""))
    internal_hostname = res.get("internal_hostname", None)
    internal_hostname_named = res.get("internal_hostname_named", None)
    restart_policy = JobRestartPolicy(res.get("restart_policy", JobRestartPolicy.NEVER))
    max_run_time_minutes = res.get("max_run_time_minutes")
    life_span = (
        max_run_time_minutes * 60.0 if max_run_time_minutes is not None else None
    )
    return JobDescription(
        status=_calc_status(res["status"]),
        id=res["id"],
        owner=owner,
        cluster_name=cluster_name,
        history=history,
        container=container,
        scheduler_enabled=res["scheduler_enabled"],
        preemptible_node=res.get("preemptible_node", False),
        pass_config=res["pass_config"],
        name=name,
        tags=tags,
        description=description,
        http_url=http_url_named or http_url,
        internal_hostname=internal_hostname,
        internal_hostname_named=internal_hostname_named,
        uri=URL(res["uri"]),
        restart_policy=restart_policy,
        life_span=life_span,
        schedule_timeout=res.get("schedule_timeout", None),
        preset_name=res.get("preset_name"),
    )


def _job_to_api(
    config: Config,
    name: Optional[str] = None,
    preset_name: Optional[str] = None,
    tags: Sequence[str] = (),
    description: Optional[str] = None,
    pass_config: bool = False,
    wait_for_jobs_quota: bool = False,
    schedule_timeout: Optional[float] = None,
    restart_policy: JobRestartPolicy = JobRestartPolicy.NEVER,
    life_span: Optional[float] = None,
    privileged: bool = False,
) -> Dict[str, Any]:
    primitive: Dict[str, Any] = {"pass_config": pass_config}
    if name:
        primitive["name"] = name
    if preset_name:
        primitive["preset_name"] = preset_name
    if tags:
        primitive["tags"] = tags
    if description:
        primitive["description"] = description
    if schedule_timeout:
        primitive["schedule_timeout"] = schedule_timeout
    if restart_policy != JobRestartPolicy.NEVER:
        primitive["restart_policy"] = str(restart_policy)
    if life_span is not None:
        primitive["max_run_time_minutes"] = int(life_span // 60)
    if wait_for_jobs_quota:
        primitive["wait_for_jobs_quota"] = wait_for_jobs_quota
    if privileged:
        primitive["privileged"] = privileged
    primitive["cluster_name"] = config.cluster_name
    return primitive


def _job_telemetry_from_api(value: Dict[str, Any]) -> JobTelemetry:
    return JobTelemetry(
        cpu=value["cpu"],
        memory=value["memory"],
        timestamp=value["timestamp"],
        gpu_duty_cycle=value.get("gpu_duty_cycle"),
        gpu_memory=value.get("gpu_memory"),
    )


def _volume_to_api(volume: Volume, config: Config) -> Dict[str, Any]:
    uri = normalize_storage_path_uri(
        volume.storage_uri, config.username, config.cluster_name
    )
    resp: Dict[str, Any] = {
        "src_storage_uri": str(uri),
        "dst_path": volume.container_path,
        "read_only": bool(volume.read_only),
    }
    return resp


def _secret_file_to_api(secret_file: SecretFile, config: Config) -> Dict[str, Any]:
    uri = normalize_secret_uri(
        secret_file.secret_uri, config.username, config.cluster_name
    )
    return {
        "src_secret_uri": str(uri),
        "dst_path": secret_file.container_path,
    }


def _disk_volume_to_api(volume: DiskVolume, config: Config) -> Dict[str, Any]:
    uri = normalize_disk_uri(volume.disk_uri, config.username, config.cluster_name)
    resp: Dict[str, Any] = {
        "src_disk_uri": str(uri),
        "dst_path": volume.container_path,
        "read_only": bool(volume.read_only),
    }
    return resp


def _volume_from_api(data: Dict[str, Any]) -> Volume:
    storage_uri = URL(data["src_storage_uri"])
    container_path = data["dst_path"]
    read_only = data.get("read_only", True)
    return Volume(
        storage_uri=storage_uri, container_path=container_path, read_only=read_only
    )


def _secret_file_from_api(data: Dict[str, Any]) -> SecretFile:
    secret_uri = URL(data["src_secret_uri"])
    container_path = data["dst_path"]
    return SecretFile(secret_uri, container_path)


def _disk_volume_from_api(data: Dict[str, Any]) -> DiskVolume:
    disk_uri = URL(data["src_disk_uri"])
    container_path = data["dst_path"]
    read_only = data.get("read_only", True)
    return DiskVolume(disk_uri, container_path, read_only)


@overload
def _parse_datetime(dt: str) -> datetime:
    ...


@overload
def _parse_datetime(dt: Optional[str]) -> Optional[datetime]:
    ...


def _parse_datetime(dt: Optional[str]) -> Optional[datetime]:
    if dt is None:
        return None
    return isoparse(dt)
