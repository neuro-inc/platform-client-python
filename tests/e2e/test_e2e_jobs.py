import asyncio
import os
import re
import subprocess
from pathlib import Path
from time import sleep, time
from typing import Any, AsyncIterator, Callable, Dict, Iterator, Tuple
from uuid import uuid4

import aiohttp
import pytest
from aiohttp.test_utils import unused_port
from yarl import URL

from neuromation.api import Container, JobStatus, Resources, get as api_get
from neuromation.utils import run as run_async
from tests.e2e import Helper


UBUNTU_IMAGE_NAME = "ubuntu:latest"
NGINX_IMAGE_NAME = "nginx:latest"
MIN_PORT = 49152
MAX_PORT = 65535


@pytest.mark.e2e
def test_job_lifecycle(helper: Helper) -> None:

    job_name = f"job-{os.urandom(5).hex()}"

    # Kill another active jobs with same name, if any
    captured = helper.run_cli(["-q", "job", "ls", "--name", job_name])
    if captured.out:
        jobs_same_name = captured.out.split("\n")
        assert len(jobs_same_name) == 1, f"found multiple active jobs named {job_name}"
        job_id = jobs_same_name[0]
        helper.run_cli(["job", "kill", job_name])
        helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)
        captured = helper.run_cli(["-q", "job", "ls", "--name", job_name])
        assert not captured.out

    # Remember original running jobs
    captured = helper.run_cli(
        ["job", "ls", "--status", "running", "--status", "pending"]
    )
    store_out_list = captured.out.split("\n")[1:]
    jobs_orig = [x.split("  ")[0] for x in store_out_list]

    command = 'bash -c "sleep 10m; false"'
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "--http",
            "80",
            "--non-preemptible",
            "--no-wait-start",
            "--name",
            job_name,
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    match = re.match("Job ID: (.+) Status:", captured.out)
    assert match is not None
    job_id = match.group(1)
    assert job_id.startswith("job-")
    assert job_id not in jobs_orig
    assert f"Name: {job_name}" in captured.out
    assert re.search("Http URL: http", captured.out), captured.out

    # Check it is in a running,pending job list now
    captured = helper.run_cli(
        ["job", "ls", "--status", "running", "--status", "pending"]
    )
    store_out_list = captured.out.split("\n")[1:]
    jobs_updated = [x.split("  ")[0] for x in store_out_list]
    assert job_id in jobs_updated

    # Wait until the job is running
    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    # Check that it is in a running job list
    captured = helper.run_cli(["job", "ls", "--status", "running"])
    store_out = captured.out
    assert job_id in store_out
    # Check that the command is in the list
    assert command in store_out

    # Check that no command is in the list if quite
    captured = helper.run_cli(["-q", "job", "ls", "--status", "running"])
    store_out = captured.out
    assert job_id in store_out
    assert command not in store_out

    # Kill the job by name
    captured = helper.run_cli(["job", "kill", job_name])

    # Currently we check that the job is not running anymore
    # TODO(adavydow): replace to succeeded check when racecon in
    # platform-api fixed.
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    # Check that it is not in a running job list anymore
    captured = helper.run_cli(["job", "ls", "--status", "running"])
    store_out = captured.out
    assert job_id not in store_out

    # Check job ls by name
    captured = helper.run_cli(["job", "ls", "-n", job_name, "-s", "succeeded"])
    store_out = captured.out
    assert job_id in store_out
    assert job_name in store_out

    # Check job status by id
    captured = helper.run_cli(["job", "status", job_id])
    store_out = captured.out
    assert store_out.startswith(f"Job: {job_id}\nName: {job_name}")
    # Check correct exit code is returned
    # assert "Exit code: 0" in store_out

    # Check job status by name
    captured = helper.run_cli(["job", "status", job_name])
    store_out = captured.out
    assert store_out.startswith(f"Job: {job_id}\nName: {job_name}")


@pytest.mark.e2e
def test_job_description(helper: Helper) -> None:
    # Remember original running jobs
    captured = helper.run_cli(
        ["job", "ls", "--status", "running", "--status", "pending"]
    )
    store_out_list = captured.out.split("\n")[1:]
    jobs_orig = [x.split("  ")[0] for x in store_out_list]
    description = "Test description for a job"
    # Run a new job
    command = 'bash -c "sleep 10m; false"'
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "--http",
            "80",
            "--description",
            description,
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    match = re.match("Job ID: (.+) Status:", captured.out)
    assert match is not None
    job_id = match.group(1)

    # Check it was not running before
    assert job_id.startswith("job-")
    assert job_id not in jobs_orig

    # Check it is in a running,pending job list now
    captured = helper.run_cli(
        ["job", "ls", "--status", "running", "--status", "pending"]
    )
    store_out_list = captured.out.split("\n")[1:]
    jobs_updated = [x.split("  ")[0] for x in store_out_list]
    assert job_id in jobs_updated

    # Wait until the job is running
    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING, JobStatus.FAILED)

    # Check that it is in a running job list
    captured = helper.run_cli(["job", "ls", "--status", "running"])
    store_out = captured.out
    assert job_id in store_out
    # Check that description is in the list
    assert description in store_out
    assert command in store_out

    # Check that no description is in the list if quite
    captured = helper.run_cli(["-q", "job", "ls", "--status", "running"])
    store_out = captured.out
    assert job_id in store_out
    assert description not in store_out
    assert command not in store_out

    # Kill the job
    captured = helper.run_cli(["job", "kill", job_id])

    # Currently we check that the job is not running anymore
    # TODO(adavydow): replace to succeeded check when racecon in
    # platform-api fixed.
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    # Check that it is not in a running job list anymore
    captured = helper.run_cli(["job", "ls", "--status", "running"])
    store_out = captured.out
    assert job_id not in store_out


@pytest.mark.e2e
def test_job_kill_non_existing(helper: Helper) -> None:
    # try to kill non existing job
    phantom_id = "NOT_A_JOB_ID"
    expected_out = f"Cannot kill job {phantom_id}"
    captured = helper.run_cli(["job", "kill", phantom_id])
    killed_jobs = [x.strip() for x in captured.out.split("\n")]
    assert len(killed_jobs) == 1
    assert killed_jobs[0].startswith(expected_out)


@pytest.mark.e2e
def test_e2e_no_env(helper: Helper) -> None:
    bash_script = 'echo "begin"$VAR"end"  | grep beginend'
    command = f"bash -c '{bash_script}'"
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )

    out = captured.out
    match = re.match("Job ID: (.+) Status:", out)
    assert match is not None
    job_id = match.group(1)

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    helper.assert_job_state(job_id, JobStatus.SUCCEEDED)


@pytest.mark.e2e
def test_e2e_env(helper: Helper) -> None:
    bash_script = 'echo "begin"$VAR"end"  | grep beginVALend'
    command = f"bash -c '{bash_script}'"
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "-e",
            "VAR=VAL",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )

    out = captured.out
    match = re.match("Job ID: (.+) Status:", out)
    assert match is not None
    job_id = match.group(1)

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    helper.assert_job_state(job_id, JobStatus.SUCCEEDED)


@pytest.mark.e2e
def test_e2e_env_from_local(helper: Helper) -> None:
    os.environ["VAR"] = "VAL"
    bash_script = 'echo "begin"$VAR"end"  | grep beginVALend'
    command = f"bash -c '{bash_script}'"
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "-e",
            "VAR",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )

    out = captured.out
    match = re.match("Job ID: (.+) Status:", out)
    assert match is not None
    job_id = match.group(1)

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    helper.assert_job_state(job_id, JobStatus.SUCCEEDED)


@pytest.mark.e2e
def test_e2e_multiple_env(helper: Helper) -> None:
    bash_script = 'echo begin"$VAR""$VAR2"end  | grep beginVALVAL2end'
    command = f"bash -c '{bash_script}'"
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "-e",
            "VAR=VAL",
            "-e",
            "VAR2=VAL2",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )

    out = captured.out
    match = re.match("Job ID: (.+) Status:", out)
    assert match is not None
    job_id = match.group(1)

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    helper.assert_job_state(job_id, JobStatus.SUCCEEDED)


@pytest.mark.e2e
def test_e2e_multiple_env_from_file(helper: Helper, tmp_path: Path) -> None:
    env_file = tmp_path / "env_file"
    env_file.write_text("VAR2=LAV2\nVAR3=VAL3\n")
    bash_script = 'echo begin"$VAR""$VAR2""$VAR3"end  | grep beginVALVAL2VAL3end'
    command = f"bash -c '{bash_script}'"
    captured = helper.run_cli(
        [
            "-q",
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "-e",
            "VAR=VAL",
            "-e",
            "VAR2=VAL2",
            "--env-file",
            str(env_file),
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )

    job_id = captured.out

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    helper.assert_job_state(job_id, JobStatus.SUCCEEDED)


@pytest.mark.e2e
def test_e2e_ssh_exec_true(helper: Helper) -> None:
    job_name = f"test-job-{str(uuid4())[:8]}"
    command = 'bash -c "sleep 15m; false"'
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "--non-preemptible",
            "--no-wait-start",
            "-n",
            job_name,
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    out = captured.out
    match = re.match("Job ID: (.+) Status:", out)
    assert match is not None
    job_id = match.group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    captured = helper.run_cli(
        ["job", "exec", "--no-key-check", "--timeout=60", job_id, "true"]
    )
    assert captured.out == ""

    captured = helper.run_cli(
        ["job", "exec", "--no-key-check", "--timeout=60", job_name, "true"]
    )
    assert captured.out == ""


@pytest.mark.e2e
def test_e2e_ssh_exec_false(helper: Helper) -> None:
    command = 'bash -c "sleep 15m; false"'
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    out = captured.out
    match = re.match("Job ID: (.+) Status:", out)
    assert match is not None
    job_id = match.group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    with pytest.raises(subprocess.CalledProcessError) as cm:
        helper.run_cli(
            ["job", "exec", "--no-key-check", "--timeout=60", job_id, "false"]
        )
    assert cm.value.returncode == 1


@pytest.mark.e2e
def test_e2e_ssh_exec_no_cmd(helper: Helper) -> None:
    command = 'bash -c "sleep 15m; false"'
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    out = captured.out
    match = re.match("Job ID: (.+) Status:", out)
    assert match is not None
    job_id = match.group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    with pytest.raises(subprocess.CalledProcessError) as cm:
        helper.run_cli(["job", "exec", "--no-key-check", "--timeout=60", job_id])
    assert cm.value.returncode == 2


@pytest.mark.e2e
def test_e2e_ssh_exec_echo(helper: Helper) -> None:
    command = 'bash -c "sleep 15m; false"'
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    out = captured.out
    match = re.match("Job ID: (.+) Status:", out)
    assert match is not None
    job_id = match.group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    captured = helper.run_cli(
        ["job", "exec", "--no-key-check", "--timeout=60", job_id, "echo 1"]
    )
    assert captured.out == "1"


@pytest.mark.e2e
def test_e2e_ssh_exec_no_tty(helper: Helper) -> None:
    command = 'bash -c "sleep 15m; false"'
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    out = captured.out
    match = re.match("Job ID: (.+) Status:", out)
    assert match is not None
    job_id = match.group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    with pytest.raises(subprocess.CalledProcessError) as cm:
        helper.run_cli(
            ["job", "exec", "--no-key-check", "--timeout=60", job_id, "[ -t 1 ]"]
        )
    assert cm.value.returncode == 1


@pytest.mark.e2e
def test_e2e_ssh_exec_tty(helper: Helper) -> None:
    command = 'bash -c "sleep 15m; false"'
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    out = captured.out
    match = re.match("Job ID: (.+) Status:", out)
    assert match is not None
    job_id = match.group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    captured = helper.run_cli(
        ["job", "exec", "-t", "--no-key-check", "--timeout=60", job_id, "[ -t 1 ]"]
    )
    assert captured.out == ""


@pytest.mark.e2e
def test_e2e_ssh_exec_no_job(helper: Helper) -> None:
    with pytest.raises(subprocess.CalledProcessError) as cm:
        helper.run_cli(
            ["job", "exec", "--no-key-check", "--timeout=60", "job_id", "true"]
        )
    assert cm.value.returncode == 127


@pytest.mark.e2e
def test_e2e_ssh_exec_dead_job(helper: Helper) -> None:
    command = "true"
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    out = captured.out
    match = re.match("Job ID: (.+) Status:", out)
    assert match is not None
    job_id = match.group(1)

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    with pytest.raises(subprocess.CalledProcessError) as cm:
        helper.run_cli(
            ["job", "exec", "--no-key-check", "--timeout=60", job_id, "true"]
        )
    assert cm.value.returncode == 127


@pytest.fixture
def nginx_job(helper: Helper) -> Iterator[str]:
    command = 'timeout 15m /usr/sbin/nginx -g "daemon off;"'
    captured = helper.run_cli(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "--non-preemptible",
            NGINX_IMAGE_NAME,
            command,
        ]
    )
    match = re.match("Job ID: (.+) Status:", captured.out)
    assert match is not None
    job_id = match.group(1)
    helper.wait_job_change_state_from(job_id, JobStatus.PENDING, JobStatus.FAILED)

    yield job_id

    helper.run_cli(["job", "kill", job_id])


@pytest.fixture
async def nginx_job_async(
    nmrc_path: Path, loop: asyncio.AbstractEventLoop
) -> AsyncIterator[Tuple[str, str]]:
    async with api_get(path=nmrc_path) as client:
        secret = uuid4()
        command = (
            f"bash -c \"echo -n '{secret}' > /usr/share/nginx/html/secret.txt; "
            f"timeout 15m /usr/sbin/nginx -g 'daemon off;'\""
        )
        container = Container(
            image=NGINX_IMAGE_NAME,
            command=command,
            resources=Resources(20, 0.1, None, None, True),
        )

        job = await client.jobs.run(
            container, is_preemptible=False, description="test NGINX job"
        )
        try:
            for i in range(60):
                status = await client.jobs.status(job.id)
                if status.status == JobStatus.RUNNING:
                    break
                await asyncio.sleep(1)
            else:
                raise AssertionError("Cannot start NGINX job")
            yield job.id, str(secret)
        finally:
            await client.jobs.kill(job.id)


@pytest.mark.e2e
async def test_port_forward(nmrc_path: Path, nginx_job_async: str) -> None:
    loop_sleep = 1
    service_wait_time = 60

    async def get_(url: str) -> int:
        status = 999
        start_time = time()
        async with aiohttp.ClientSession() as session:
            while status != 200 and (int(time() - start_time) < service_wait_time):
                try:
                    async with session.get(url) as resp:
                        status = resp.status
                        text = await resp.text()
                        assert text == nginx_job_async[1], (
                            f"Secret not found "
                            f"via {url}. Like as it's not our test server."
                        )
                except aiohttp.ClientConnectionError:
                    status = 599
                if status != 200:
                    sleep(loop_sleep)
        return status

    loop = asyncio.get_event_loop()
    async with api_get(path=nmrc_path) as client:
        port = unused_port()
        # We test client instead of run_cli as asyncio subprocesses do
        # not work if run from thread other than main.
        forwarder = loop.create_task(
            client.jobs.port_forward(nginx_job_async[0], port, 80, no_key_check=True)
        )
        await asyncio.sleep(loop_sleep)

        try:
            url = f"http://127.0.0.1:{port}/secret.txt"
            probe = await get_(url)
            assert probe == 200
        finally:
            forwarder.cancel()
            with pytest.raises(asyncio.CancelledError):
                await forwarder


@pytest.mark.e2e
def test_job_submit_http_auth(
    helper: Helper, secret_job: Callable[..., Dict[str, Any]]
) -> None:
    loop_sleep = 1
    service_wait_time = 60

    async def _test_http_auth_redirect(url: URL) -> None:
        start_time = time()
        async with aiohttp.ClientSession() as session:
            while time() - start_time < service_wait_time:
                try:
                    async with session.get(url, allow_redirects=True) as resp:
                        if resp.status == 200 and re.match(
                            r".+\.auth0\.com$", resp.url.host
                        ):
                            break
                except aiohttp.ClientConnectionError:
                    pass
                sleep(loop_sleep)
            else:
                raise AssertionError("HTTP Auth not detected")

    async def _test_http_auth_with_cookie(
        url: URL, cookies: Dict[str, str], secret: str
    ) -> None:
        start_time = time()
        async with aiohttp.ClientSession(cookies=cookies) as session:  # type: ignore
            while time() - start_time < service_wait_time:
                try:
                    async with session.get(url, allow_redirects=False) as resp:
                        if resp.status == 200:
                            body = await resp.text()
                            if secret == body.strip():
                                break
                        raise AssertionError("Secret not match")
                except aiohttp.ClientConnectionError:
                    pass
                sleep(loop_sleep)
            else:
                raise AssertionError("Cannot fetch secret via forwarded http")

    http_job = secret_job(http_port=True, http_auth=True)
    ingress_secret_url = http_job["ingress_url"].with_path("/secret.txt")

    run_async(_test_http_auth_redirect(ingress_secret_url))

    cookies = {"dat": helper.token}
    run_async(
        _test_http_auth_with_cookie(ingress_secret_url, cookies, http_job["secret"])
    )


@pytest.mark.e2e
def test_job_run(helper: Helper) -> None:
    # Run a new job
    command = 'bash -c "exit 101"'
    captured = helper.run_cli(
        [
            "-q",
            "job",
            "run",
            "-s",
            "cpu-small",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    job_id = captured.out

    # Wait until the job is running
    helper.wait_job_change_state_to(job_id, JobStatus.FAILED)

    # Verify exit code is returned
    captured = helper.run_cli(["job", "status", job_id])
    store_out = captured.out
    assert "Exit code: 101" in store_out


@pytest.mark.e2e
def test_pass_config(helper: Helper) -> None:
    # Run a new job
    command = 'bash -c "neuro config show"'
    captured = helper.run_cli(
        [
            "job",
            "run",
            "-q",
            "-s",
            "cpu-small",
            "--non-preemptible",
            "--no-wait-start",
            "--pass-config",
            "anayden/neuro-cli",
            command,
        ]
    )
    job_id = captured.out

    # Wait until the job is running
    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)

    # Verify exit code is returned
    captured = helper.run_cli(["job", "status", job_id])
    store_out = captured.out
    assert "Exit code: 0" in store_out


@pytest.mark.parametrize("http_auth", ["--http-auth", "--no-http-auth"])
@pytest.mark.e2e
def test_job_submit_bad_http_auth(helper: Helper, http_auth: str) -> None:
    with pytest.raises(subprocess.CalledProcessError) as cm:
        helper.run_cli(
            [
                "job",
                "submit",
                "-m",
                "20M",
                "-c",
                "0.1",
                "-g",
                "0",
                http_auth,
                "--non-preemptible",
                "--no-wait-start",
                UBUNTU_IMAGE_NAME,
                "true",
            ]
        )
    assert cm.value.returncode == 2
    assert f"{http_auth} requires --http" in cm.value.stderr


@pytest.fixture
def fakebrowser(monkeypatch: Any) -> None:
    monkeypatch.setitem(os.environ, "BROWSER", "echo Browsing %s")


@pytest.mark.e2e
def test_job_browse(helper: Helper, fakebrowser: Any) -> None:
    # Run a new job
    captured = helper.run_cli(
        [
            "-q",
            "job",
            "run",
            "-s",
            "cpu-small",
            "--non-preemptible",
            UBUNTU_IMAGE_NAME,
            "true",
        ]
    )
    job_id = captured.out

    captured = helper.run_cli(["-v", "job", "browse", job_id])
    assert "Browsing https://job-" in captured.out
    assert "Open job URL: https://job-" in captured.err


@pytest.mark.e2e
def test_job_browse_named(helper: Helper, fakebrowser: Any) -> None:
    job_name = f"namedjob-{os.urandom(5).hex()}"

    # Run a new job
    captured = helper.run_cli(
        [
            "-q",
            "job",
            "run",
            "-s",
            "cpu-small",
            "--non-preemptible",
            "--name",
            job_name,
            UBUNTU_IMAGE_NAME,
            "true",
        ]
    )
    job_id = captured.out

    captured = helper.run_cli(["-v", "job", "browse", job_id])
    assert f"Browsing https://{job_name}--{helper.username}" in captured.out
    assert f"Open job URL: https://{job_name}--{helper.username}" in captured.err


@pytest.mark.e2e
def test_job_run_browse(helper: Helper, fakebrowser: Any) -> None:
    # Run a new job
    captured = helper.run_cli(
        [
            "-v",
            "job",
            "run",
            "-s",
            "cpu-small",
            "--non-preemptible",
            "--browse",
            UBUNTU_IMAGE_NAME,
            "true",
        ]
    )
    assert "Browsing https://job-" in captured.out
    assert "Open job URL: https://job-" in captured.err


@pytest.mark.e2e
def test_job_submit_browse(helper: Helper, fakebrowser: Any) -> None:
    # Run a new job
    captured = helper.run_cli(
        [
            "-v",
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "--http",
            "80",
            "--non-preemptible",
            "--browse",
            UBUNTU_IMAGE_NAME,
            "true",
        ]
    )
    assert "Browsing https://job-" in captured.out
    assert "Open job URL: https://job-" in captured.err
