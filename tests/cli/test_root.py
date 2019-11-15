from pathlib import Path

import aiohttp
import pytest

from neuromation.cli.root import ConfigError, Root


@pytest.fixture
def root_uninitialized() -> Root:
    return Root(
        color=False,
        tty=False,
        terminal_size=(80, 25),
        disable_pypi_version_check=False,
        network_timeout=60,
        config_path=Path("~/.nmrc"),
        verbosity=0,
        trace=False,
    )


def test_auth_uninitialized(root_uninitialized: Root) -> None:
    assert root_uninitialized.auth is None


def test_timeout(root_uninitialized: Root) -> None:
    assert root_uninitialized.timeout == aiohttp.ClientTimeout(None, None, 60, 60)


def test_username_uninitialized(root_uninitialized: Root) -> None:
    with pytest.raises(ConfigError):
        root_uninitialized.username


def test_url_uninitialized(root_uninitialized: Root) -> None:
    with pytest.raises(ConfigError):
        root_uninitialized.url


def test_registry_url_uninitialized(root_uninitialized: Root) -> None:
    with pytest.raises(ConfigError):
        root_uninitialized.registry_url


def test_resource_presets_uninitialized(root_uninitialized: Root) -> None:
    with pytest.raises(ConfigError):
        root_uninitialized.resource_presets


def test_get_session_cookie(root_uninitialized: Root) -> None:
    assert root_uninitialized.get_session_cookie() is None


class TestTokenSanitization:
    @pytest.mark.parametrize(
        "auth", ["Bearer", "Basic", "Digest", "Mutual"],
    )
    def test_sanitize_header_value_single_token(
        self, root_uninitialized: Root, auth: str
    ) -> None:
        line = f"foo Authentication: {auth} eyJhbGciOiJI.eyJzdW0NTY3.SfKxwRJ_SsM bar"
        expected = f"foo Authentication: {auth} eyJhb<hidden 26 chars>J_SsM bar"
        line_safe = root_uninitialized._sanitize_header_value(line)
        assert line_safe == expected

    @pytest.mark.parametrize(
        "auth", ["Bearer", "Basic", "Digest", "Mutual"],
    )
    def test_sanitize_header_value_many_tokens(
        self, root_uninitialized: Root, auth: str
    ) -> None:
        num = 10
        line = f"foo Authentication: {auth} eyJhbGcOiJI.eyJzdTY3.SfKxwRJ_SsM bar " * num
        expected = f"foo Authentication: {auth} eyJhb<hidden 22 chars>J_SsM bar " * num
        line_safe = root_uninitialized._sanitize_header_value(line)
        assert line_safe == expected

    @pytest.mark.parametrize(
        "auth", ["Bearer", "Basic", "Digest", "Mutual"],
    )
    def test_sanitize_header_value_not_a_token(
        self, root_uninitialized: Root, auth: str
    ) -> None:
        line = f"foo Authentication: {auth} not_a_jwt bar"
        line_safe = root_uninitialized._sanitize_header_value(line)
        assert line_safe == f"foo Authentication: {auth} not_a_jwt bar"

    @pytest.mark.parametrize(
        "token,tail_len",
        [
            ("sec.ret.token", -1),
            ("sec.ret.token", 0),
            ("sec.ret.token", len("sec.ret.token") // 2 + 1),
        ],
    )
    def test_sanitize_token_replaced_overall(
        self, root_uninitialized: Root, token: str, tail_len: int
    ) -> None:
        line_safe = root_uninitialized._sanitize_token(token, tail_len)
        assert line_safe == "<hidden 13 chars>"

    def test_sanitize_token_tail_too_long(self, root_uninitialized: Root) -> None:
        token = "eyJhbGciOiJIUz.eyJzdWIjM0NTY3.SflKxwRJ_SsM"
        with pytest.raises(AssertionError, match="tail too long"):
            root_uninitialized._sanitize_token(token, tail_len=len(token) // 2 + 1)
