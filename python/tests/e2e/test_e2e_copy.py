import asyncio
import os
import platform
from math import ceil
from os.path import join
from pathlib import PurePath
from uuid import uuid4 as uuid

import pytest

from _sha1 import sha1


BLOCK_SIZE_MB = 16
FILE_COUNT = 1
FILE_SIZE_MB = 16
GENERATION_TIMEOUT_SEC = 120
RC_TEXT = "url: http://platform.dev.neuromation.io/api/v1\n" "auth: {token}"

UBUNTU_IMAGE_NAME = "ubuntu:latest"


format_list = "{type:<15}{size:<15,}{name:<}".format


def hash_hex(file):
    _hash = sha1()
    with open(file, "rb") as f:
        for block in iter(lambda: f.read(BLOCK_SIZE_MB * 1024 * 1024), b""):
            _hash.update(block)

    return _hash.hexdigest()


async def generate_test_data(root, count, size_mb):
    async def generate_file(name):
        exec_sha_name = "sha1sum" if platform.platform() == "linux" else "shasum"

        process = await asyncio.create_subprocess_shell(
            f"""(dd if=/dev/urandom \
                    bs={BLOCK_SIZE_MB * 1024 * 1024} \
                    count={ceil(size_mb / BLOCK_SIZE_MB)} \
                    2>/dev/null) | \
                    tee {name} | \
                    {exec_sha_name}""",
            stdout=asyncio.subprocess.PIPE,
        )

        stdout, _ = await asyncio.wait_for(
            process.communicate(), timeout=GENERATION_TIMEOUT_SEC
        )

        # sha1sum appends file name to the output
        return name, stdout.decode()[:40]

    return await asyncio.gather(
        *[
            generate_file(join(root, name))
            for name in (str(uuid()) for _ in range(count))
        ]
    )


@pytest.fixture(scope="session")
def nested_data(tmpdir_factory):
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    root_tmp_dir = tmpdir_factory.mktemp("data")
    tmp_dir = root_tmp_dir.mkdir("nested").mkdir("directory").mkdir("for").mkdir("test")
    data = loop.run_until_complete(
        generate_test_data(tmp_dir, FILE_COUNT, FILE_SIZE_MB)
    )
    return data[0][0], data[0][1], root_tmp_dir.strpath


@pytest.fixture(scope="session")
def data(tmpdir_factory):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(
        generate_test_data(tmpdir_factory.mktemp("data"), FILE_COUNT, FILE_SIZE_MB)
    )


@pytest.mark.e2e
def test_e2e_copy_non_existing_platform_to_non_existing_local(run, tmpdir):
    _dir = f"e2e-{uuid()}"
    _path = f"/tmp/{_dir}"

    # Create directory for the test
    _, captured = run(["store", "mkdir", f"storage://{_path}"])
    assert not captured.err
    assert captured.out == f"storage://{_path}" + "\n"

    # Try downloading non existing file
    _local = join(tmpdir, "bar")
    with pytest.raises(SystemExit, match=str(os.EX_OSFILE)):
        _, _ = run(["store", "cp", "storage://" + _path + "/foo", _local])

    # Remove test dir
    _, captured = run(["store", "rm", f"storage://{_path}"])
    assert not captured.err

    # And confirm
    _, captured = run(["store", "ls", f"storage:///tmp"])

    split = captured.out.split("\n")
    assert format_list(name=_dir, size=0, type="directory") not in split

    assert not captured.err


@pytest.mark.e2e
def test_e2e_copy_non_existing_platform_to_____existing_local(run, tmpdir):
    _dir = f"e2e-{uuid()}"
    _path = f"/tmp/{_dir}"

    # Create directory for the test
    _, captured = run(["store", "mkdir", f"storage://{_path}"])
    assert not captured.err
    assert captured.out == f"storage://{_path}" + "\n"

    # Try downloading non existing file
    _local = join(tmpdir)
    with pytest.raises(SystemExit, match=str(os.EX_OSFILE)):
        _, captured = run(["store", "cp", "storage://" + _path + "/foo", _local])

    # Remove test dir
    _, captured = run(["store", "rm", f"storage://{_path}"])
    assert not captured.err

    # And confirm
    _, captured = run(["store", "ls", f"storage:///tmp"])

    split = captured.out.split("\n")
    assert format_list(name=_dir, size=0, type="directory") not in split

    assert not captured.err


@pytest.mark.e2e
def test_e2e_copy_recursive_to_platform(nested_data, run, tmpdir):
    file, checksum, dir_path = nested_data

    target_file_name = file.split("/")[-1]
    _dir = f"e2e-{uuid()}"
    _path = f"/tmp/{_dir}"
    dir_name = PurePath(dir_path).name

    # Create directory for the test
    _, captured = run(["store", "mkdir", f"storage://{_path}"])
    assert not captured.err
    assert captured.out == f"storage://{_path}" + "\n"

    # Upload local file
    _, captured = run(["store", "cp", "-r", dir_path, "storage://" + _path + "/"])
    assert not captured.err
    assert _path in captured.out

    # Check directory structure
    _, captured = run(["store", "ls", f"storage://{_path}/{dir_name}"])
    captured_output_list = captured.out.split("\n")
    assert f"directory      0              nested" in captured_output_list
    assert not captured.err

    _, captured = run(["store", "ls", f"storage://{_path}/{dir_name}/nested"])
    captured_output_list = captured.out.split("\n")
    assert f"directory      0              directory" in captured_output_list
    assert not captured.err

    _, captured = run(["store", "ls", f"storage://{_path}/{dir_name}/nested/directory"])
    captured_output_list = captured.out.split("\n")
    assert f"directory      0              for" in captured_output_list
    assert not captured.err

    _, captured = run(
        ["store", "ls", f"storage://{_path}/{dir_name}/nested/directory/for"]
    )
    captured_output_list = captured.out.split("\n")
    assert f"directory      0              test" in captured_output_list
    assert not captured.err

    # Confirm file has been uploaded
    _, captured = run(
        ["store", "ls", f"storage://{_path}/{dir_name}/nested/directory/for/test"]
    )
    captured_output_list = captured.out.split("\n")
    assert f"file           16,777,216     {target_file_name}" in captured_output_list
    assert not captured.err

    # Download into local directory and confirm checksum
    tmpdir.mkdir("bar")
    _local = join(tmpdir, "bar")
    _, captured = run(["store", "cp", "-r", "storage://" + _path + "/", _local])
    assert (
        hash_hex(
            _local + f"/{dir_name}/nested/directory/for/" f"test/{target_file_name}"
        )
        == checksum
    )

    # Remove test dir
    _, captured = run(["store", "rm", f"storage://{_path}"])
    assert not captured.err

    # And confirm
    _, captured = run(["store", "ls", f"storage:///tmp"])

    split = captured.out.split("\n")
    assert format_list(name=_dir, size=0, type="directory") not in split

    assert not captured.err
