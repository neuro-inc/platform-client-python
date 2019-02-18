import os
import re
from time import sleep, time

import aiohttp
import pytest

from neuromation.client import JobStatus
from neuromation.utils import run as run_async


UBUNTU_IMAGE_NAME = "ubuntu:latest"
NGINX_IMAGE_NAME = "nginx:latest"


@pytest.mark.e2e
def test_job_lifecycle(helper, run_cli):
    # Remember original running jobs
    captured = run_cli(["job", "ls", "--status", "running", "--status", "pending"])
    store_out_list = captured.out.strip().split("\n")[1:]
    jobs_orig = [x.split("\t")[0] for x in store_out_list]

    # Run a new job
    command = 'bash -c "sleep 10m; false"'
    captured = run_cli(
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
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    job_id = re.match("Job ID: (.+) Status:", captured.out).group(1)

    # Check it was not running before
    assert job_id.startswith("job-")
    assert job_id not in jobs_orig

    # Check it is in a running,pending job list now
    captured = run_cli(["job", "ls", "--status", "running", "--status", "pending"])
    store_out_list = captured.out.strip().split("\n")[1:]
    jobs_updated = [x.split("\t")[0] for x in store_out_list]
    assert job_id in jobs_updated

    # Wait until the job is running
    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    # Check that it is in a running job list
    captured = run_cli(["job", "ls", "--status", "running"])
    store_out = captured.out.strip()
    assert job_id in store_out
    # Check that the command is in the list
    assert command in store_out

    # Check that no command is in the list if quite
    captured = run_cli(["job", "ls", "--status", "running", "-q"])
    store_out = captured.out.strip()
    assert job_id in store_out
    assert command not in store_out

    # Kill the job
    captured = run_cli(["job", "kill", job_id])

    # Currently we check that the job is not running anymore
    # TODO(adavydow): replace to succeeded check when racecon in
    # platform-api fixed.
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    # Check that it is not in a running job list anymore
    captured = run_cli(["job", "ls", "--status", "running"])
    store_out = captured.out.strip()
    assert job_id not in store_out


@pytest.mark.e2e
def test_job_description(helper, run_cli):
    # Remember original running jobs
    captured = run_cli(["job", "ls", "--status", "running", "--status", "pending"])
    store_out_list = captured.out.strip().split("\n")[1:]
    jobs_orig = [x.split("\t")[0] for x in store_out_list]
    description = "Test description for a job"
    # Run a new job
    command = 'bash -c "sleep 10m; false"'
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", captured.out).group(1)

    # Check it was not running before
    assert job_id.startswith("job-")
    assert job_id not in jobs_orig

    # Check it is in a running,pending job list now
    captured = run_cli(["job", "ls", "--status", "running", "--status", "pending"])
    store_out_list = captured.out.strip().split("\n")[1:]
    jobs_updated = [x.split("\t")[0] for x in store_out_list]
    assert job_id in jobs_updated

    # Wait until the job is running
    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING, JobStatus.FAILED)

    # Check that it is in a running job list
    captured = run_cli(["job", "ls", "--status", "running"])
    store_out = captured.out.strip()
    assert job_id in store_out
    # Check that description is in the list
    assert description in store_out
    assert command in store_out

    # Check that no description is in the list if quite
    captured = run_cli(["job", "ls", "--status", "running", "-q"])
    store_out = captured.out.strip()
    assert job_id in store_out
    assert description not in store_out
    assert command not in store_out

    # Kill the job
    captured = run_cli(["job", "kill", job_id])

    # Currently we check that the job is not running anymore
    # TODO(adavydow): replace to succeeded check when racecon in
    # platform-api fixed.
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    # Check that it is not in a running job list anymore
    captured = run_cli(["job", "ls", "--status", "running"])
    store_out = captured.out.strip()
    assert job_id not in store_out


@pytest.mark.e2e
def test_unschedulable_job_lifecycle(helper, run_cli):
    # Remember original running jobs
    captured = run_cli(["job", "ls", "--status", "running", "--status", "pending"])
    store_out_list = captured.out.strip().split("\n")[1:]
    jobs_orig = [x.split("\t")[0] for x in store_out_list]

    # Run a new job
    command = 'bash -c "sleep 10m; false"'
    captured = run_cli(
        [
            "job",
            "submit",
            "-m",
            "200000M",
            "-c",
            "0.1",
            "-g",
            "0",
            "--http",
            "80",
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    job_id = re.match("Job ID: (.+) Status:", captured.out).group(1)

    # Check it was not running before
    assert job_id.startswith("job-")
    assert job_id not in jobs_orig

    # Check it is in a running,pending job list now
    captured = run_cli(["job", "ls", "--status", "running", "--status", "pending"])
    store_out_list = captured.out.strip().split("\n")[1:]
    jobs_updated = [x.split("\t")[0] for x in store_out_list]
    assert job_id in jobs_updated
    assert False, "fix the following check"
    helper.wait_job_change_state_to(
        run_cli, job_id, "(Cluster doesn't have resources to fulfill request.)"
    )

    # Kill the job
    captured = run_cli(["job", "kill", job_id])

    # Currently we check that the job is not running anymore
    # TODO(adavydow): replace to succeeded check when racecon in
    # platform-api fixed.
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    # Check that it is not in a running job list anymore
    captured = run_cli(["job", "ls", "--status", "running"])
    store_out = captured.out.strip()
    assert job_id not in store_out


@pytest.mark.e2e
def test_two_jobs_at_once(helper, run_cli):
    # Remember original running jobs
    captured = run_cli(["job", "ls", "--status", "running", "--status", "pending"])
    store_out_list = captured.out.strip().split("\n")[1:]
    jobs_orig = [x.split("\t")[0] for x in store_out_list]

    # Run a new job
    command = 'bash -c "sleep 10m; false"'
    captured = run_cli(
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
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )
    first_job_id = re.match("Job ID: (.+) Status:", captured.out).group(1)

    captured = run_cli(
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
    second_job_id = re.match("Job ID: (.+) Status:", captured.out).group(1)

    # Check it was not running before
    assert first_job_id.startswith("job-")
    assert first_job_id not in jobs_orig
    assert second_job_id.startswith("job-")
    assert second_job_id not in jobs_orig

    # Check it is in a running,pending job list now
    captured = run_cli(["job", "ls", "--status", "running", "--status", "pending"])
    store_out_list = captured.out.strip().split("\n")[1:]
    jobs_updated = [x.split("\t")[0] for x in store_out_list]
    assert first_job_id in jobs_updated
    assert second_job_id in jobs_updated

    # Wait until the job is running
    helper.wait_job_change_state_to(first_job_id, JobStatus.RUNNING, JobStatus.FAILED)
    helper.wait_job_change_state_to(second_job_id, JobStatus.RUNNING, JobStatus.FAILED)

    # Check that it is in a running job list
    captured = run_cli(["job", "ls", "--status", "running"])
    store_out = captured.out.strip()
    assert first_job_id in store_out
    assert second_job_id in store_out
    # Check that the command is in the list
    assert command in store_out

    # Check that no command is in the list if quite
    captured = run_cli(["job", "ls", "--status", "running", "-q"])
    store_out = captured.out.strip()
    assert first_job_id in store_out
    assert second_job_id in store_out
    assert command not in store_out

    # Kill the job
    captured = run_cli(["job", "kill", first_job_id, second_job_id])

    # Currently we check that the job is not running anymore
    # TODO(adavydow): replace to succeeded check when racecon in
    # platform-api fixed.
    helper.wait_job_change_state_from(first_job_id, JobStatus.RUNNING)
    helper.wait_job_change_state_from(second_job_id, JobStatus.RUNNING)

    # Check that it is not in a running job list anymore
    captured = run_cli(["job", "ls", "--status", "running"])
    store_out = captured.out.strip()
    assert first_job_id not in store_out
    assert first_job_id not in store_out


@pytest.mark.e2e
def test_job_kill_non_existing(run_cli):
    # try to kill non existing job
    phantom_id = "NOT_A_JOB_ID"
    expected_out = f"Cannot kill job {phantom_id}"
    captured = run_cli(["job", "kill", phantom_id])
    killed_jobs = [x.strip() for x in captured.out.strip().split("\n")]
    assert len(killed_jobs) == 1
    assert killed_jobs[0].startswith(expected_out)


@pytest.mark.e2e
def test_model_train_with_http(helper, run_cli):
    loop_sleep = 1
    service_wait_time = 60

    async def get_(url):
        succeeded = None
        start_time = time()
        while not succeeded and (int(time() - start_time) < service_wait_time):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    succeeded = resp.status == 200
            if not succeeded:
                sleep(loop_sleep)
        return succeeded

    # Create directory for the test, going to be model and result output
    helper.check_create_dir_on_storage("model")
    helper.check_create_dir_on_storage("result")

    # Start the job
    command = 'timeout 5m /usr/sbin/nginx -g "daemon off;"'
    captured = run_cli(
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
            "--non-preemptible",
            NGINX_IMAGE_NAME,
            f"{helper.tmpstorage}/model",
            f"{helper.tmpstorage}/result",
            command,
        ]
    )
    job_id = re.match("Job ID: (.+) Status:", captured.out).group(1)
    helper.wait_job_change_state_from(job_id, JobStatus.PENDING, JobStatus.FAILED)

    captured = run_cli(["job", "status", job_id])
    url = re.search(r"Http URL:\s+(\S+)", captured.out).group(1)

    probe = run_async(get_(url))

    # job will be killed in run(), but let's kill it twice
    run_cli(["job", "kill", job_id])

    assert probe


@pytest.mark.e2e
def test_model_without_command(helper, run_cli):
    loop_sleep = 1
    service_wait_time = 60

    async def get_(url):
        succeeded = None
        start_time = time()
        while not succeeded and (int(time() - start_time) < service_wait_time):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    succeeded = resp.status == 200
            if not succeeded:
                sleep(loop_sleep)
        return succeeded

    # Create directory for the test, going to be model and result output
    helper.check_create_dir_on_storage("model")
    helper.check_create_dir_on_storage("result")

    # Start the job
    captured = run_cli(
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
            "--non-preemptible",
            NGINX_IMAGE_NAME,
            f"{helper.tmpstorage}/model",
            f"{helper.tmpstorage}/result",
            "-d",
            "simple test job",
        ]
    )
    job_id = re.match("Job ID: (.+) Status:", captured.out).group(1)
    helper.wait_job_change_state_from(job_id, JobStatus.PENDING, JobStatus.FAILED)

    captured = run_cli(["job", "status", job_id])
    url = re.search(r"Http URL:\s+(\S+)", captured.out).group(1)

    probe = run_async(get_(url))

    # job will be killed in run(), but let's kill it twice
    run_cli(["job", "kill", job_id])

    assert probe


@pytest.mark.e2e
def test_e2e_no_env(helper, run_cli):
    bash_script = 'echo "begin"$VAR"end"  | grep beginend'
    command = f"bash -c '{bash_script}'"
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    helper.assert_job_state(job_id, JobStatus.SUCCEEDED)


@pytest.mark.e2e
def test_e2e_env(helper, run_cli):
    bash_script = 'echo "begin"$VAR"end"  | grep beginVALend'
    command = f"bash -c '{bash_script}'"
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    helper.assert_job_state(job_id, JobStatus.SUCCEEDED)


@pytest.mark.e2e
def test_e2e_env_from_local(helper, run_cli):
    os.environ["VAR"] = "VAL"
    bash_script = 'echo "begin"$VAR"end"  | grep beginVALend'
    command = f"bash -c '{bash_script}'"
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    helper.assert_job_state(run_cli, job_id, JobStatus.SUCCEEDED)


@pytest.mark.e2e
def test_e2e_multiple_env(helper, run_cli):
    bash_script = 'echo begin"$VAR""$VAR2"end  | grep beginVALVAL2end'
    command = f"bash -c '{bash_script}'"
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    helper.assert_job_state(job_id, JobStatus.SUCCEEDED)


@pytest.mark.xfail
@pytest.mark.e2e
def test_e2e_multiple_env_from_file(helper, run_cli, tmp_path):
    env_file = tmp_path / "env_file"
    env_file.write_text("VAR2=LAV2\nVAR3=VAL3\n")
    bash_script = 'echo begin"$VAR""$VAR2""$VAR3"end  | grep beginVALVAL2VAL3end'
    command = f"bash -c '{bash_script}'"
    captured = run_cli(
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
            "--non-preemptible",
            "--no-wait-start",
            UBUNTU_IMAGE_NAME,
            command,
        ]
    )

    out = captured.out
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    helper.assert_job_state(job_id, JobStatus.SUCCEEDED)


@pytest.mark.e2e
def test_e2e_ssh_exec_true(helper, run_cli):
    command = 'bash -c "sleep 15m; false"'
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    captured = run_cli(["job", "exec", "--no-key-check", job_id, "true"])
    assert captured.out == ""


@pytest.mark.e2e
def test_e2e_ssh_exec_false(helper, run_cli):
    command = 'bash -c "sleep 15m; false"'
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    with pytest.raises(SystemExit) as cm:
        run_cli(["job", "exec", "--no-key-check", job_id, "false"])
    assert cm.value.code == 1


@pytest.mark.e2e
def test_e2e_ssh_exec_no_cmd(helper, run_cli):
    command = 'bash -c "sleep 15m; false"'
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    with pytest.raises(SystemExit) as cm:
        run_cli(["job", "exec", "--no-key-check", job_id])
    assert cm.value.code == 2


@pytest.mark.e2e
def test_e2e_ssh_exec_echo(helper, run_cli):
    command = 'bash -c "sleep 15m; false"'
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    captured = run_cli(["job", "exec", "--no-key-check", job_id, "echo 1"])
    assert captured.out == "1"


@pytest.mark.e2e
def test_e2e_ssh_exec_no_tty(helper, run_cli):
    command = 'bash -c "sleep 15m; false"'
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    with pytest.raises(SystemExit) as cm:
        run_cli(["job", "exec", "--no-key-check", job_id, "[ -t 1 ]"])
    assert cm.value.code == 1


@pytest.mark.e2e
def test_e2e_ssh_exec_tty(helper, run_cli):
    command = 'bash -c "sleep 15m; false"'
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_to(job_id, JobStatus.RUNNING)

    captured = run_cli(["job", "exec", "-t", "--no-key-check", job_id, "[ -t 1 ]"])
    assert captured.out == ""


@pytest.mark.e2e
def test_e2e_ssh_exec_no_job(run_cli):
    with pytest.raises(SystemExit) as cm:
        run_cli(["job", "exec", "--no-key-check", "job_id", "true"])
    assert cm.value.code == 127


@pytest.mark.e2e
def test_e2e_ssh_exec_dead_job(helper, run_cli):
    command = "true"
    captured = run_cli(
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
    job_id = re.match("Job ID: (.+) Status:", out).group(1)

    helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
    helper.wait_job_change_state_from(job_id, JobStatus.RUNNING)

    with pytest.raises(SystemExit) as cm:
        run_cli(["job", "exec", "--no-key-check", job_id, "true"])
    assert cm.value.code == 127


@pytest.mark.e2e
def test_e2e_job_list_filtered_by_status(helper, run_cli):
    N_JOBS = 5

    # submit N jobs
    jobs = set()
    for _ in range(N_JOBS):
        command = "sleep 10m"
        captured = run_cli(["job", "submit", UBUNTU_IMAGE_NAME, command, "--quiet"])
        job_id = captured.out.strip()
        helper.wait_job_change_state_from(job_id, JobStatus.PENDING)
        jobs.add(job_id)

    # no status filtering (same as running+pending)
    captured = run_cli(["job", "ls", "--quiet"])
    out = captured.out.strip()
    jobs_ls_no_arg = set(out.split("\n"))
    # check '>=' (not '==') multiple builds run in parallel can interfere
    assert jobs_ls_no_arg >= jobs

    # 1 status filter: running
    captured = run_cli(["job", "ls", "--status", "running", "--quiet"])
    out = captured.out.strip()
    jobs_ls_running = set(out.split("\n"))
    # check '>=' (not '==') multiple builds run in parallel can interfere
    assert jobs_ls_running >= jobs

    # 2 status filters: pending+running is the same as without arguments
    captured = run_cli(["job", "ls", "-s", "pending", "-s", "running", "-q"])
    out = captured.out.strip()
    jobs_ls_running = set(out.split("\n"))
    # check '>=' (not '==') multiple builds run in parallel can interfere
    assert jobs_ls_running >= jobs_ls_no_arg

    # "all" status filter is the same as "running+pending+failed+succeeded"
    captured = run_cli(["job", "ls", "-s", "all", "-q"])
    out = captured.out.strip()
    jobs_ls_all = set(out.split("\n"))
    captured = run_cli(
        [
            "job",
            "ls",
            "-s",
            "running",
            "-s",
            "pending",
            "-s",
            "failed",
            "-s",
            "succeeded",
            "-q",
        ]
    )
    out = captured.out.strip()
    jobs_ls_all_explicit = set(out.split("\n"))
    # check '>=' (not '==') multiple builds run in parallel can interfere
    assert jobs_ls_all_explicit >= jobs_ls_all
