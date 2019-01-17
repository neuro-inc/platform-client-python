import os
from pathlib import PurePath

import pytest

from tests.e2e.utils import format_list


FILE_SIZE_MB = 16
FILE_SIZE_B = FILE_SIZE_MB * 1024 * 1024


@pytest.mark.e2e
def test_copy_local_to_platform_single_file_0(
    data,
    check_create_dir_on_storage,
    check_upload_file_to_storage,
    check_file_exists_on_storage,
    check_rm_file_on_storage,
    check_file_absent_on_storage,
):
    srcfile, checksum = data[0]
    file_name = str(PurePath(srcfile).name)

    check_create_dir_on_storage("folder")
    # Upload local file to existing directory
    # case when copy happens with the trailing '/'
    check_upload_file_to_storage(None, "folder/", srcfile)  # tmpstorage/

    # Ensure file is there
    check_file_exists_on_storage(file_name, "folder", FILE_SIZE_B)

    # Remove the file from platform
    check_rm_file_on_storage(file_name, "folder")

    # Ensure file is not there
    check_file_absent_on_storage(file_name, "folder")


@pytest.mark.e2e
def test_copy_local_to_platform_single_file_1(
    data,
    check_create_dir_on_storage,
    check_upload_file_to_storage,
    check_file_exists_on_storage,
    check_rm_file_on_storage,
    check_file_absent_on_storage,
):
    # case when copy happens without the trailing '/'
    srcfile, checksum = data[0]
    file_name = str(PurePath(srcfile).name)

    check_create_dir_on_storage("folder")

    # Upload local file to existing directory
    check_upload_file_to_storage(None, "folder", srcfile)

    # Ensure file is there
    check_file_exists_on_storage(file_name, "folder", FILE_SIZE_B)

    # Remove the file from platform
    check_rm_file_on_storage(file_name, "folder")

    # Ensure file is not there
    check_file_absent_on_storage(file_name, "folder")


@pytest.mark.e2e
def test_copy_local_to_platform_single_file_2(
    data,
    run,
    tmpstorage,
    check_create_dir_on_storage,
    check_upload_file_to_storage,
    check_file_exists_on_storage,
    check_rm_file_on_storage,
    check_file_absent_on_storage,
):
    # case when copy happens with rename to 'different_name.txt'
    srcfile, checksum = data[0]
    file_name = str(PurePath(srcfile).name)

    check_create_dir_on_storage("folder")
    # Upload local file to existing directory
    check_upload_file_to_storage("different_name.txt", "folder", srcfile)

    # Ensure file is there
    check_file_exists_on_storage("different_name.txt", "folder", FILE_SIZE_B)
    captured = run(["store", "ls", tmpstorage + "folder/"])
    split = captured.out.split("\n")
    assert (
        format_list(name="different_name.txt", size=FILE_SIZE_B, type="file") in split
    )
    assert format_list(name=file_name, size=FILE_SIZE_B, type="file") not in split

    # Remove the file from platform
    check_rm_file_on_storage("different_name.txt", "folder")

    # Ensure file is not there
    check_file_absent_on_storage("different_name.txt", "folder")


@pytest.mark.e2e
def test_copy_local_to_platform_single_file_3(
    data, run, tmpstorage, check_dir_absent_on_storage
):
    # case when copy happens with rename to 'different_name.txt'
    srcfile, checksum = data[0]

    # Upload local file to non existing directory
    with pytest.raises(SystemExit, match=str(os.EX_OSFILE)):
        captured = run(["store", "cp", srcfile, tmpstorage + "/non_existing_dir/"])
        assert not captured.err
        assert captured.out == ""

    # Ensure dir is not created
    check_dir_absent_on_storage("non_existing_dir", "")


@pytest.mark.e2e
def test_e2e_copy_non_existing_platform_to_non_existing_local(
    run, tmpdir, capsys, tmpstorage
):
    # Try downloading non existing file
    with pytest.raises(SystemExit, match=str(os.EX_OSFILE)):
        run(
            [
                "store",
                "cp",
                tmpstorage + "/not-exist-foo",
                str(tmpdir / "not-exist-bar"),
            ]
        )


@pytest.mark.e2e
def test_e2e_copy_non_existing_platform_to_____existing_local(
    run, tmpdir, capsys, tmpstorage
):
    # Try downloading non existing file
    with pytest.raises(SystemExit, match=str(os.EX_OSFILE)):
        run(["store", "cp", tmpstorage + "/foo", str(tmpdir)])
