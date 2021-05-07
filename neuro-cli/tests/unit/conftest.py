import dataclasses
import io
import logging
from collections import namedtuple
from decimal import Decimal
from difflib import ndiff
from pathlib import Path
from typing import Any, Callable, DefaultDict, Iterator, List, Optional, Set, Union

import click
import pytest
from rich.console import Console, RenderableType
from yarl import URL

from neuro_sdk import Cluster, Factory, Preset
from neuro_sdk.config import _AuthConfig, _AuthToken, _ConfigData

from neuro_cli import __version__
from neuro_cli.const import EX_OK
from neuro_cli.main import main
from neuro_cli.root import Root

SysCapWithCode = namedtuple("SysCapWithCode", ["out", "err", "code"])
log = logging.getLogger(__name__)


@pytest.fixture()
def nmrc_path(tmp_path: Path, token: str, auth_config: _AuthConfig) -> Path:
    nmrc_path = tmp_path / "conftest.nmrc"
    cluster_config = Cluster(
        registry_url=URL("https://registry-dev.neu.ro"),
        storage_url=URL("https://storage-dev.neu.ro"),
        blob_storage_url=URL("https://blob-storage-dev.neu.ro"),
        users_url=URL("https://users-dev.neu.ro"),
        monitoring_url=URL("https://monitoring-dev.neu.ro"),
        secrets_url=URL("https://secrets-dev.neu.ro"),
        disks_url=URL("https://disks-dev.neu.ro"),
        presets={
            "gpu-small": Preset(
                credits_per_hour=Decimal("10"),
                cpu=7,
                memory_mb=30 * 1024,
                gpu=1,
                gpu_model="nvidia-tesla-k80",
            ),
            "gpu-large": Preset(
                credits_per_hour=Decimal("10"),
                cpu=7,
                memory_mb=60 * 1024,
                gpu=1,
                gpu_model="nvidia-tesla-v100",
            ),
            "cpu-small": Preset(
                credits_per_hour=Decimal("10"), cpu=7, memory_mb=2 * 1024
            ),
            "cpu-large": Preset(
                credits_per_hour=Decimal("10"), cpu=7, memory_mb=14 * 1024
            ),
        },
        name="default",
    )
    cluster2_config = Cluster(
        registry_url=URL("https://registry2-dev.neu.ro"),
        storage_url=URL("https://storage2-dev.neu.ro"),
        blob_storage_url=URL("https://blob-storage2-dev.neu.ro"),
        users_url=URL("https://users2-dev.neu.ro"),
        monitoring_url=URL("https://monitoring2-dev.neu.ro"),
        secrets_url=URL("https://secrets2-dev.neu.ro"),
        disks_url=URL("https://disks2-dev.neu.ro"),
        presets={
            "cpu-small": Preset(
                credits_per_hour=Decimal("10"), cpu=7, memory_mb=2 * 1024
            ),
        },
        name="other",
    )
    config = _ConfigData(
        auth_config=auth_config,
        auth_token=_AuthToken.create_non_expiring(token),
        url=URL("https://dev.neu.ro/api/v1"),
        admin_url=URL("https://dev.neu.ro/apis/admin/v1"),
        version=__version__,
        cluster_name="default",
        clusters={
            cluster_config.name: cluster_config,
            cluster2_config.name: cluster2_config,
        },
    )
    Factory(nmrc_path)._save(config)
    return nmrc_path


def create_root(config_path: Path) -> Root:
    return Root(
        color=False,
        tty=False,
        disable_pypi_version_check=True,
        network_timeout=60,
        config_path=config_path,
        verbosity=0,
        trace=False,
        trace_hide_token=True,
        force_trace_all=False,
        command_path="",
        command_params=[],
        skip_gmp_stats=True,
        show_traceback=False,
        iso_datetime_format=False,
    )


@pytest.fixture()
def root(nmrc_path: Path) -> Iterator[Root]:
    root = create_root(config_path=nmrc_path)
    root.run(root.init_client())
    yield root
    root.close()


@pytest.fixture()
def root_no_logged_in(tmp_path: Path) -> Iterator[Root]:
    root = create_root(config_path=tmp_path)
    assert root._client is None
    yield root
    assert root._client is None
    root.close()


@pytest.fixture()
def run_cli(
    nmrc_path: Path, capfd: Any, tmp_path: Path
) -> Callable[[List[str]], SysCapWithCode]:
    def _run_cli(arguments: List[str]) -> SysCapWithCode:
        log.info("Run 'neuro %s'", " ".join(arguments))
        capfd.readouterr()

        code = EX_OK
        try:
            default_args = [
                "--show-traceback",
                "--disable-pypi-version-check",
                "--color=no",
            ]
            if "--neuromation-config" not in arguments:
                for arg in arguments:
                    if arg.startswith("--neuromation-config="):
                        break
                else:
                    default_args.append(f"--neuromation-config={nmrc_path}")

            main(default_args + arguments)
        except SystemExit as e:
            code = e.code
            pass
        out, err = capfd.readouterr()
        return SysCapWithCode(out.strip(), err.strip(), code)

    return _run_cli


@pytest.fixture()
def click_tty_emulation(monkeypatch: Any) -> None:
    monkeypatch.setattr("click._compat.isatty", lambda stream: True)


@dataclasses.dataclass(eq=False)
class Guard:
    arg: str
    path: Path

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Guard):
            return NotImplemented
        return [s.rstrip() for s in self.arg.splitlines()] == [
            s.rstrip() for s in other.arg.splitlines()
        ]


class RichComparator:
    def __init__(self, config: Any) -> None:
        self._regen = config.getoption("--rich-gen")
        self._config = config
        self._reporter = config.pluginmanager.getplugin("terminalreporter")
        assert self._reporter is not None
        self._cwd = Path.cwd()
        self._written_refs: List[Path] = []
        self._checked_refs: Set[Path] = set()
        self._file_pos = DefaultDict[io.StringIO, int](int)

    def mkref(self, request: Any, index: Optional[int]) -> Path:
        folder = Path(request.fspath).parent
        basename = request.function.__qualname__
        if hasattr(request.node, "callspec"):
            parametrize_id = request.node.callspec.id
            # Some characters are forbidden in FS path (on Windows)
            bad_to_good = {
                "/": "#forward_slash#",
                "\\": "#back_slash#",
                "<": "#less#",
                ">": "#more#",
                ":": "#colon#",
                '"': "#double_qoute#",
                "|": "#vertical_bar#",
                "?": "#question_mark#",
                "*": "#star#",
            }
            for bad, good in bad_to_good.items():
                parametrize_id = parametrize_id.replace(bad, good)
            # On windows, some characters are forbidden
            basename += f"[{parametrize_id}]"
        if index is not None:
            basename += "_" + str(index)
        basename += ".ref"
        return folder / "ascii" / basename

    def rel(self, ref: Path) -> Path:
        return ref.relative_to(self._cwd)

    def check_io(self, ref: Path, file: io.StringIO) -> None:
        __tracebackhide__ = True
        tmp = file.getvalue()
        buf = tmp[self._file_pos[file] :]
        self._file_pos[file] = len(tmp)
        self.check(ref, buf)

    def check(self, ref: Path, buf: str) -> None:
        __tracebackhide__ = True

        if ref in self._checked_refs:
            pytest.fail(
                f"{self.rel(ref)} is already checked. "
                "Hint: use index when generating refs automatically"
            )
        else:
            self._checked_refs.add(ref)

        buf = buf.strip()
        buf = click.unstyle(buf)

        if self._regen:
            self.write_ref(ref, buf)
        else:
            orig = self.read_ref(ref)
            tmp = ref.with_suffix(".orig")
            self.write_file(tmp, buf)
            # reading from file is important, file writer replaces \r with \n
            actual = self.read_file(tmp)
            assert Guard(actual, tmp) == Guard(orig, ref)

    def read_file(self, ref: Path) -> str:
        return ref.read_text(encoding="utf8").strip()

    def read_ref(self, ref: Path) -> str:
        __tracebackhide__ = True
        if not ref.exists():
            rel_ref = self.rel(ref)
            pytest.fail(
                f"The reference {rel_ref} doesn't exist.\n"
                "Create it yourself or run pytest with '--rich-gen' option."
            )
        else:
            return self.read_file(ref)

    def write_file(self, ref: Path, buf: str) -> None:
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(buf.strip() + "\n", encoding="utf8")

    def write_ref(self, ref: Path, buf: str) -> bool:
        if ref.exists():
            orig = ref.read_text().strip()
            if orig == buf:
                return False
        self.write_file(ref, buf)
        if self._reporter.verbosity > 0:
            rel_ref = self.rel(ref)
            self._reporter.write_line(f"Regenerate {rel_ref}", yellow=True)
        self._written_refs.append(ref)
        return True

    def summary(self) -> None:
        if self._reporter.verbosity == 0:
            if self._written_refs:
                self._reporter.write_line("Regenerated files:", yellow=True)
                for fname in self._written_refs:
                    rel_ref = self.rel(fname)
                    self._reporter.write_line(f"  {rel_ref}", yellow=True)

    def diff(self, lft: Guard, rgt: Guard) -> List[str]:
        # The same as _diff_text from
        # https://github.com/pytest-dev/pytest/blob/master/src/_pytest/assertion/util.py#L200-L245 plus a few extra lines with additional instructions.  # noqa
        explanation: List[str] = []

        left = lft.arg
        right = rgt.arg

        if self._reporter.verbosity < 1:
            i = 0  # just in case left or right has zero length
            for i in range(min(len(left), len(right))):
                if left[i] != right[i]:
                    break
            if i > 42:
                i -= 10  # Provide some context
                explanation = [
                    "Skipping %s identical leading characters in diff, use -v to show"
                    % i
                ]
                left = left[i:]
                right = right[i:]
            if len(left) == len(right):
                for i in range(len(left)):
                    if left[-i] != right[-i]:
                        break
                if i > 42:
                    i -= 10  # Provide some context
                    explanation += [
                        "Skipping {} identical trailing "
                        "characters in diff, use -v to show".format(i)
                    ]
                    left = left[:-i]
                    right = right[:-i]

        keepends = True
        if left.isspace() or right.isspace():
            left = repr(str(left))
            right = repr(str(right))
            explanation += [
                "Strings contain only whitespace, escaping them using repr()"
            ]
        # "right" is the expected base against which we compare "left",
        # see https://github.com/pytest-dev/pytest/issues/3333
        explanation += [
            line.strip("\n")
            for line in ndiff(right.splitlines(keepends), left.splitlines(keepends))
        ]
        explanation.append("")
        explanation.append(f"'cat {self.rel(lft.path)}' to see the test output.")
        explanation.append(f"'cat {self.rel(rgt.path)}' to see the reference.")
        explanation.append(
            f"Use 'pytest ... --rich-gen' to regenerate reference files "
            "from values calculated by tests"
        )
        return explanation


def pytest_assertrepr_compare(
    config: Any, op: str, left: object, right: object
) -> Optional[List[str]]:
    if isinstance(left, Guard) and isinstance(right, Guard):
        plugin = config.pluginmanager.getplugin("rich-comparator")
        return plugin.diff(left, right)
    return None


# run after terminalreporter/capturemanager are configured
@pytest.hookimpl(trylast=True)
def pytest_configure(config: Any) -> None:
    comparator = RichComparator(config)
    config.pluginmanager.register(comparator, "rich-comparator")


def pytest_terminal_summary(terminalreporter: Any) -> None:
    config = terminalreporter.config
    comparator = config.pluginmanager.getplugin("rich-comparator")
    comparator.summary()


@pytest.fixture
def rich_cmp(request: Any) -> Callable[..., None]:
    def comparator(
        src: Union[RenderableType, Console],
        ref: Optional[Path] = None,
        *,
        color: bool = True,
        tty: bool = True,
        index: Optional[int] = 0,
    ) -> None:
        __tracebackhide__ = True
        plugin = request.config.pluginmanager.getplugin("rich-comparator")
        if ref is None:
            ref = plugin.mkref(request, index)

        if isinstance(src, io.StringIO):
            plugin.check_io(ref, src)
        elif isinstance(src, Console):
            if isinstance(src.file, io.StringIO):
                plugin.check_io(ref, src.file)
            else:
                buf = src.export_text(clear=True, styles=True)
                plugin.check(ref, buf)
        else:
            file = io.StringIO()
            console = Console(
                file=file,
                width=160,
                height=24,
                force_terminal=tty,
                color_system="auto" if color else None,
                record=True,
                highlighter=None,
                legacy_windows=False,
            )
            console.print(src)
            plugin.check_io(ref, file)

    return comparator


NewConsole = Callable[..., Console]


@pytest.fixture
def new_console() -> NewConsole:
    def factory(*, tty: bool, color: bool = True) -> Console:
        file = io.StringIO()
        # console doesn't accept the time source,
        # using the real time in tests is not reliable
        return Console(
            file=file,
            width=160,
            height=24,
            force_terminal=tty,
            color_system="auto" if color else None,
            record=True,
            highlighter=None,
            legacy_windows=False,
            log_path=False,
            log_time=False,
        )

    return factory
