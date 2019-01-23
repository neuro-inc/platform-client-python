import os
import re
from time import sleep, time
from urllib.parse import urlparse

import aiohttp
import pytest

from neuromation.cli.rc import ConfigFactory
from neuromation.utils import run as run_async
from tests.e2e.test_e2e_utils import (
    Status,
    assert_job_state,
    wait_job_change_state_from,
    wait_job_change_state_to,
)


UBUNTU_IMAGE_NAME = "ubuntu:latest"
NGINX_IMAGE_NAME = "nginx:latest"


@pytest.mark.e2e
def test_job_complete_lifecycle(run, loop, tmpstorage, check_create_dir_on_storage):
    # Create directory for the test, going to be model and result output
    check_create_dir_on_storage("model")
    check_create_dir_on_storage("result")

    # remember original set or running jobs
    captured = run(["job", "list", "--status", "running,pending"])
    store_out_list = captured.out.strip().split("\n")[1:]  # cut out the header line
    jobs_orig = [x.split("\t")[0] for x in store_out_list]

    # Start the jobs
    command_first = 'bash -c "sleep 1m; false"'
    captured = run(
        [
            "model",
            "train",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "--http",
            "80",
            UBUNTU_IMAGE_NAME,
            tmpstorage + "model",
            tmpstorage + "result",
            command_first,
        ]
    )
    job_id_first = re.match("Job ID: (.+) Status:", captured.out).group(1)
    assert job_id_first.startswith("job-")
    assert job_id_first not in jobs_orig

    command_second = 'bash -c "sleep 2m; false"'
    captured = run(
        [
            "job",
            "submit",
            "--cpu",
            "0.1",
            "--memory",
            "20M",
            "--gpu",
            "0",
            "--http",
            "80",
            "--quiet",
            UBUNTU_IMAGE_NAME,
            "--volume",
            f"{tmpstorage}model:/model:ro",
            "--volume",
            f"{tmpstorage}result:/result:rw",
            command_second,
        ]
    )
    job_id_second = captured.out.strip()
    assert job_id_second.startswith("job-")
    assert job_id_second not in jobs_orig

    captured = run(
        [
            "job",
            "submit",
            UBUNTU_IMAGE_NAME,
            "--memory",
            "2000000000000M",
            "-g",
            "0",
            "-q",
            "--non-preemptible",
        ]
    )
    job_id_third = captured.out.strip()
    assert job_id_third.startswith("job-")

    # wait jobs for becoming running
    wait_job_change_state_from(run, job_id_first, Status.PENDING, Status.NOT_ENOUGH)
    wait_job_change_state_from(run, job_id_second, Status.PENDING, Status.NOT_ENOUGH)
    with pytest.raises(Exception) as e:
        wait_job_change_state_from(run, job_id_third, Status.PENDING, Status.NOT_ENOUGH)
        assert Status.NOT_ENOUGH in str(e), str(e)

    wait_job_change_state_to(run, job_id_first, Status.RUNNING)
    wait_job_change_state_to(run, job_id_second, Status.RUNNING)

    # check running via job list
    captured = run(["job", "list", "--status", "running"])
    store_out = captured.out.strip()
    assert command_first in store_out
    assert command_second in store_out
    jobs_before_killing = [x.split("\t")[0] for x in store_out.split("\n")]
    assert job_id_first in jobs_before_killing
    assert job_id_second in jobs_before_killing

    # do the same with job list -q
    captured = run(["job", "list", "--status", "running", "-q"])
    jobs_before_killing_q = [x.strip() for x in captured.out.strip().split("\n")]
    assert job_id_first in jobs_before_killing_q
    assert job_id_second in jobs_before_killing_q

    # kill multiple jobs
    captured = run(["job", "kill", job_id_first, job_id_second, job_id_third])
    kill_output_list = [x.strip() for x in captured.out.strip().split("\n")]
    assert kill_output_list == [job_id_first, job_id_second, job_id_third]

    # TODO (A Yushkovskiy, 6.12.2018): when the flaky tests in try-catch block below
    # are fixed, we don't need to wait 'wait_for_job_to_change_state_from',
    # so leave here only 'wait_for_job_to_change_state_to'

    wait_job_change_state_from(run, job_id_first, Status.RUNNING, Status.FAILED)
    wait_job_change_state_from(run, job_id_second, Status.RUNNING, Status.FAILED)
    wait_job_change_state_from(run, job_id_third, Status.RUNNING, Status.FAILED)

    wait_job_change_state_to(run, job_id_first, Status.SUCCEEDED, Status.FAILED)
    wait_job_change_state_to(run, job_id_second, Status.SUCCEEDED, Status.FAILED)
    wait_job_change_state_to(run, job_id_third, Status.SUCCEEDED, Status.FAILED)

    # check killed running,pending
    captured = run(["job", "list", "--status", "running,pending", "-q"])
    jobs_after_kill_q = [x.strip() for x in captured.out.strip().split("\n")]
    assert job_id_first not in jobs_after_kill_q
    assert job_id_second not in jobs_after_kill_q
    assert job_id_third not in jobs_after_kill_q

    # try to kill already killed: same output
    captured = run(["job", "kill", job_id_first])
    kill_output_list = [x.strip() for x in captured.out.strip().split("\n")]
    assert kill_output_list == [job_id_first]


@pytest.mark.e2e
def test_job_kill_non_existing(run):
    # try to kill non existing job
    phantom_id = "NOT_A_JOB_ID"
    expected_out = f"Cannot kill job {phantom_id}"
    captured = run(["job", "kill", phantom_id])
    killed_jobs = [x.strip() for x in captured.out.strip().split("\n")]
    assert len(killed_jobs) == 1
    assert killed_jobs[0].startswith(expected_out)


@pytest.mark.e2e
def test_model_train_with_http(run, tmpstorage, check_create_dir_on_storage):
    loop_sleep = 1
    service_wait_time = 60

    async def get_(platform_url):
        succeeded = None
        start_time = time()
        while not succeeded and (int(time() - start_time) < service_wait_time):
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://{job_id}.jobs.{platform_url}") as resp:
                    succeeded = resp.status == 200
            if not succeeded:
                sleep(loop_sleep)
        return succeeded

    # Create directory for the test, going to be model and result output
    check_create_dir_on_storage("model")
    check_create_dir_on_storage("result")

    # Start the job
    command = '/usr/sbin/nginx -g "daemon off;"'
    captured = run(
        [
            "model",
            "train",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "--http",
            "80",
            NGINX_IMAGE_NAME,
            f"{tmpstorage}/model",
            f"{tmpstorage}/result",
            command,
            "-d",
            "simple test job",
        ]
    )
    job_id = re.match("Job ID: (.+) Status:", captured.out).group(1)
    wait_job_change_state_from(run, job_id, Status.PENDING)

    config = ConfigFactory.load()
    parsed_url = urlparse(config.url)

    assert run_async(get_(parsed_url.netloc))

    run(["job", "kill", job_id])
    wait_job_change_state_from(run, job_id, Status.RUNNING)


@pytest.mark.e2e
def test_model_without_command(run, tmpstorage, check_create_dir_on_storage):
    loop_sleep = 1
    service_wait_time = 60

    async def get_(platform_url):
        succeeded = None
        start_time = time()
        while not succeeded and (int(time() - start_time) < service_wait_time):
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://{job_id}.jobs.{platform_url}") as resp:
                    succeeded = resp.status == 200
            if not succeeded:
                sleep(loop_sleep)
        return succeeded

    # Create directory for the test, going to be model and result output
    check_create_dir_on_storage("model")
    check_create_dir_on_storage("result")

    # Start the job
    captured = run(
        [
            "model",
            "train",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            "--http",
            "80",
            NGINX_IMAGE_NAME,
            f"{tmpstorage}/model",
            f"{tmpstorage}/result",
            "-d",
            "simple test job",
        ]
    )
    job_id = re.match("Job ID: (.+) Status:", captured.out).group(1)
    wait_job_change_state_from(run, job_id, Status.PENDING)

    config = ConfigFactory.load()
    parsed_url = urlparse(config.url)

    assert run_async(get_(parsed_url.netloc))

    captured = run(["job", "kill", job_id])
    wait_job_change_state_from(run, job_id, Status.RUNNING)


@pytest.mark.e2e
def test_e2e_no_env(run):
    bash_script = 'echo "begin"$VAR"end"  | grep beginend'
    command = f"bash -c '{bash_script}'"
    captured = run(
        [
            "job",
            "submit",
            "-m",
            "20M",
            "-c",
            "0.1",
            "-g",
            "0",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )

    out = captured.out
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    wait_job_change_state_from(run, job_id, Status.PENDING)
    wait_job_change_state_from(run, job_id, Status.RUNNING)

    assert_job_state(run, job_id, "Status: succeeded")


@pytest.mark.e2e
def test_e2e_env(run):
    bash_script = 'echo "begin"$VAR"end"  | grep beginVALend'
    command = f"bash -c '{bash_script}'"
    captured = run(
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
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )

    out = captured.out
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    wait_job_change_state_from(run, job_id, Status.PENDING)
    wait_job_change_state_from(run, job_id, Status.RUNNING)

    assert_job_state(run, job_id, "Status: succeeded")


@pytest.mark.e2e
def test_e2e_env_from_local(run):
    os.environ["VAR"] = "VAL"
    bash_script = 'echo "begin"$VAR"end"  | grep beginVALend'
    command = f"bash -c '{bash_script}'"
    captured = run(
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
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )

    out = captured.out
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    wait_job_change_state_from(run, job_id, Status.PENDING)
    wait_job_change_state_from(run, job_id, Status.RUNNING)

    assert_job_state(run, job_id, "Status: succeeded")


@pytest.mark.e2e
def test_e2e_multiple_env(run):
    bash_script = 'echo begin"$VAR""$VAR2"end  | grep beginVALVAL2end'
    command = f"bash -c '{bash_script}'"
    captured = run(
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
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )

    out = captured.out
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    wait_job_change_state_from(run, job_id, Status.PENDING)
    wait_job_change_state_from(run, job_id, Status.RUNNING)

    assert_job_state(run, job_id, "Status: succeeded")


@pytest.mark.e2e
def test_e2e_multiple_env_from_file(run, tmp_path):
    env_file = tmp_path / "env_file"
    env_file.write_text("VAR2=LAV2\nVAR3=VAL3\n")
    bash_script = 'echo begin"$VAR""$VAR2""$VAR3"end  | grep beginVALVAL2VAL3end'
    command = f"bash -c '{bash_script}'"
    captured = run(
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
            "--env-file",
            str(env_file),
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )

    out = captured.out
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    wait_job_change_state_from(run, job_id, Status.PENDING)
    wait_job_change_state_from(run, job_id, Status.RUNNING)

    assert_job_state(run, job_id, "Status: succeeded")


@pytest.mark.e2e
def test_e2e_ssh_exec_true(run):
    command = 'bash -c "sleep 1m; false"'
    captured = run(
        ["job", "submit", "-m", "20M", "-c", "0.1", UBUNTU_IMAGE_NAME, command]
    )
    out = captured.out
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    wait_job_change_state_from(run, job_id, Status.PENDING)

    captured = run(["job", "exec", "--no-key-check", job_id, "true"])
    assert captured.out == ""
