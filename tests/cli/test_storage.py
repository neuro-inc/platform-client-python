from pathlib import Path
from typing import Any, Callable
from unittest import mock

import toml
from yarl import URL

from neuromation.api import Client
from neuromation.cli.storage import _expand, calc_filters


_MakeClient = Callable[..., Client]


async def test_calc_filters_section_doesnt_exist(
    monkeypatch: Any, tmp_path: Path, make_client: _MakeClient
) -> None:

    async with make_client("https://example.com") as client:
        monkeypatch.chdir(tmp_path)
        local_conf = tmp_path / ".neuro.toml"
        # empty config
        local_conf.write_text("")
        assert await calc_filters(client, None) == ()


async def test_calc_filters_user_spec(
    monkeypatch: Any, tmp_path: Path, make_client: _MakeClient
) -> None:

    async with make_client("https://example.com") as client:
        monkeypatch.chdir(tmp_path)
        local_conf = tmp_path / ".neuro.toml"
        # empty config
        local_conf.write_text(
            toml.dumps({"storage": {"cp-exclude": ["*.jpg", "!main.jpg"]}})
        )
        assert await calc_filters(client, None) == (
            (True, "*.jpg"),
            (False, "main.jpg"),
        )


async def test_storage__expand_file(
    monkeypatch: Any, tmp_path: Path, make_client: _MakeClient
) -> None:

    async with make_client("https://example.com") as client:
        chdir = tmp_path / "chdir"
        chdir.mkdir()
        monkeypatch.chdir(chdir)
        monkeypatch.setenv("HOME", str(tmp_path))
        root = mock.Mock()
        root.verbosity = 0
        root.client = client

        # Create file structure
        for path in [
            tmp_path / "file1.txt",
            tmp_path / "file2.json",
            tmp_path / "inner" / "xxx.json",
            tmp_path / "inner" / "yyy.txt",
        ]:
            path.parent.mkdir(exist_ok=True)
            with path.open("w"):
                pass
        base_url = URL(tmp_path.as_uri())

        assert await _expand(paths=[], root=root, glob=True, allow_file=True) == []
        # User expand cases
        uris = await _expand(paths=["~/*"], root=root, glob=True, allow_file=True)
        assert sorted(uris) == [
            base_url / "chdir",
            base_url / "file1.txt",
            base_url / "file2.json",
            base_url / "inner",
        ]
        uris = await _expand(paths=["~/**"], root=root, glob=True, allow_file=True)
        assert sorted(uris) == [
            base_url,
            base_url / "chdir",
            base_url / "file1.txt",
            base_url / "file2.json",
            base_url / "inner",
            base_url / "inner" / "xxx.json",
            base_url / "inner" / "yyy.txt",
        ]

        # Relative expand cases
        uris = await _expand(paths=["./**"], root=root, glob=True, allow_file=True)
        assert sorted(uris) == [
            base_url / "chdir",
        ]
        uris = await _expand(paths=["../*"], root=root, glob=True, allow_file=True)
        assert sorted(uris) == [
            base_url / "chdir" / ".." / "chdir",
            base_url / "chdir" / ".." / "file1.txt",
            base_url / "chdir" / ".." / "file2.json",
            base_url / "chdir" / ".." / "inner",
        ]
        uris = await _expand(paths=["../**"], root=root, glob=True, allow_file=True)
        assert sorted(uris) == [
            base_url / "chdir" / "..",
            base_url / "chdir" / ".." / "chdir",
            base_url / "chdir" / ".." / "file1.txt",
            base_url / "chdir" / ".." / "file2.json",
            base_url / "chdir" / ".." / "inner",
            base_url / "chdir" / ".." / "inner" / "xxx.json",
            base_url / "chdir" / ".." / "inner" / "yyy.txt",
        ]

        # File scheme cases
        uris = await _expand(
            paths=[str(base_url / "**" / "*.json")],
            root=root,
            glob=True,
            allow_file=True,
        )
        assert sorted(uris) == [
            base_url / "file2.json",
            base_url / "inner" / "xxx.json",
        ]
