import pytest

import neuromation
from tests.e2e import Helper


@pytest.mark.e2e
def test_print_version(helper: Helper) -> None:
    expected_out = f"Neuromation Platform Client {neuromation.__version__}"

    captured = helper.run_cli(["--version"])
    assert not captured.err
    assert captured.out == expected_out


@pytest.mark.e2e
def test_print_options(helper: Helper) -> None:
    captured = helper.run_cli(["--options"])
    assert not captured.err
    assert "Options" in captured.out


@pytest.mark.e2e
def test_print_config(helper: Helper) -> None:
    captured = helper.run_cli(["config", "show"])
    assert not captured.err
    assert "API URL: https://dev.neu.ro/api/v1" in captured.out


@pytest.mark.e2e
def test_print_config_token(helper: Helper) -> None:
    captured = helper.run_cli(["config", "show-token"])
    assert not captured.err
    assert captured.out  # some secure information was printed
