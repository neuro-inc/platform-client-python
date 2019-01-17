import pytest

from tests.e2e.utils import FILE_SIZE_MB, hash_hex


FILE_SIZE_B = FILE_SIZE_MB * 1024 * 1024


@pytest.mark.e2e
def test_e2e_copy_recursive_to_platform(
    nested_data,
    run,
    tmpdir,
    tmpstorage,
    check_create_dir_on_storage,
    check_dir_exists_on_storage,
    check_file_exists_on_storage,
    check_rmdir_on_storage,
    check_dir_absent_on_storage,
):
    srcfile, checksum, dir_path = nested_data
    target_file_name = srcfile.split("/")[-1]

    # Upload local file
    captured = run(["store", "cp", "-r", dir_path, tmpstorage])
    assert not captured.err
    assert not captured.out

    check_file_exists_on_storage(
        target_file_name, f"nested/directory/for/test", FILE_SIZE_B
    )

    # Download into local directory and confirm checksum

    targetdir = tmpdir.mkdir("bar")
    run(["store", "cp", "-r", f"{tmpstorage}", str(targetdir)])
    targetfile = targetdir / "nested" / "directory" / "for" / "test" / target_file_name
    print("source file", srcfile)
    print("target file", targetfile)
    assert hash_hex(targetfile) == checksum

    # Remove test dir
    check_rmdir_on_storage("nested")

    # And confirm
    check_dir_absent_on_storage("nested", "")
