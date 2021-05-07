import asyncio
import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

import click
from aiohttp.client_exceptions import ClientConnectionError
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.markup import escape as rich_escape
from yarl import URL

from neuro_sdk import DEFAULT_API_URL, ConfigError

from neuro_cli.formatters.config import ClustersFormatter, QuotaInfoFormatter

from .alias import list_aliases
from .formatters.config import AliasesFormatter, ConfigFormatter
from .root import Root
from .utils import argument, command, group, option


@group()
def config() -> None:
    """Client configuration."""


@command()
async def show(root: Root) -> None:
    """
    Print current settings.
    """
    cluster_name = root.client.config.cluster_name
    fmt = ConfigFormatter()
    try:
        jobs_capacity = await root.client.jobs.get_capacity(cluster_name=cluster_name)
    except ClientConnectionError:
        jobs_capacity = {}
    root.print(fmt(root.client.config, jobs_capacity))


@command()
async def show_token(root: Root) -> None:
    """
    Print current authorization token.
    """
    root.print(await root.client.config.token())


@command()
@argument("user", required=False, default=None, type=str)
async def show_quota(root: Root, user: Optional[str]) -> None:
    """
    Print quota and remaining computation time for active cluster.
    """
    quotas = await root.client._quota.get(user)
    cluster_name = root.client.config.cluster_name
    if cluster_name not in quotas:
        raise ValueError(
            f"No quota information available for cluster {cluster_name}.\n"
            "Please logout and login again."
        )
    cluster_quota = quotas[cluster_name]
    fmt = QuotaInfoFormatter()
    root.print(fmt(cluster_quota))


@command()
async def add_quota(root: Root) -> None:
    """
    Print instructions for increasing quota for current user
    """
    user_name = root.client.config.username
    cluster_name = root.client.config.cluster_name
    root.print(
        f"In order to increase your quota, please navigate to "
        f"https://neuro.payments.com/{user_name}/{cluster_name}?pay=usd100"
    )


def _print_welcome(root: Root, url: URL) -> None:
    root.print(f"Logged into {url}")
    root.print(
        "Read the docs at https://docs.neu.ro or run `neuro --help` "
        "to see the reference"
    )


async def _show_browser(url: URL) -> None:
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, webbrowser.open_new, str(url))
    if not success:
        raise Exception(
            "No browser found. For non-GUI environments, use "
            "`neuro config login-headless` to login."
        )


@command(init_client=False)
@argument("url", required=False, default=DEFAULT_API_URL, type=URL)
async def login(root: Root, url: URL) -> None:
    """
    Log into Neuro Platform.

    URL is a platform entrypoint URL.
    """

    try:
        await root.factory.login(_show_browser, url=url, timeout=root.timeout)
    except (ConfigError, FileExistsError):
        await root.factory.logout()
        root.print("You were successfully logged out.")
        await root.factory.login(_show_browser, url=url, timeout=root.timeout)
    _print_welcome(root, url)


@command(init_client=False)
@argument("token", required=True, type=str)
@argument("url", required=False, default=DEFAULT_API_URL, type=URL)
async def login_with_token(root: Root, token: str, url: URL) -> None:
    """
    Log into Neuro Platform with token.

    TOKEN is authentication token provided by administration team.
    URL is a platform entrypoint URL.
    """
    try:
        await root.factory.login_with_token(token, url=url, timeout=root.timeout)
    except ConfigError:
        await root.factory.logout()
        root.print("You were successfully logged out.")
        await root.factory.login_with_token(token, url=url, timeout=root.timeout)
    _print_welcome(root, url)


@command(init_client=False)
@argument("url", required=False, default=DEFAULT_API_URL, type=URL)
async def login_headless(root: Root, url: URL) -> None:
    """
    Log into Neuro Platform from non-GUI server environment.

    URL is a platform entrypoint URL.

    The command works similar to "neuro login" but instead of
    opening a browser for performing OAuth registration prints
    an URL that should be open on guest host.

    Then user inputs a code displayed in a browser after successful login
    back in neuro command to finish the login process.
    """

    async def login_callback(url: URL) -> str:
        session: PromptSession[str] = PromptSession()
        root.print(f"Open {url} in a browser")
        root.print("Put the code displayed in a browser after successful login")
        with patch_stdout():
            auth_code = await session.prompt_async("Code (empty for exit)-> ")
        if not auth_code:
            sys.exit()
        return auth_code

    try:
        await root.factory.login_headless(login_callback, url=url, timeout=root.timeout)
    except ConfigError:
        await root.factory.logout()
        root.print("You were successfully logged out.")
        await root.factory.login_headless(login_callback, url=url, timeout=root.timeout)
    _print_welcome(root, url)


@command(init_client=False)
async def logout(root: Root) -> None:
    """
    Log out.
    """
    await root.factory.logout(_show_browser)
    root.print("Logged out")


@command(init_client=False)
async def aliases(root: Root) -> None:
    """
    List available command aliases.
    """
    aliases = await list_aliases(root)
    root.print(AliasesFormatter()(aliases))


@command(name="docker")
@option(
    "--docker-config",
    metavar="PATH",
    type=click.Path(file_okay=False),
    help="Specifies the location of the Docker client configuration files",
    default=lambda: os.environ.get("DOCKER_CONFIG", Path.home() / ".docker"),
    show_default=False,
)
async def docker(root: Root, docker_config: str) -> None:
    """
    Configure docker client to fit the Neuro Platform.
    """
    config_path = Path(docker_config)
    if not config_path.exists():
        config_path.mkdir(parents=True)
    elif not config_path.is_dir():
        raise ValueError(f"Specified path is not a directory: {config}")

    json_path = config_path / "config.json"
    payload: Dict[str, Any] = {}
    if json_path.exists():
        with json_path.open("rb") as file:
            payload = json.load(file)
    if "credHelpers" not in payload:
        payload["credHelpers"] = {}

    registry = URL(root.client.config.registry_url).host or ""
    payload["credHelpers"][registry] = "neuro"
    with json_path.open("w", encoding="utf-8") as file2:
        json.dump(payload, file2, indent=2)

    root.print(f"Configuration file {json_path} updated.")
    root.print(
        f"You can use docker client with neuro registry: "
        f"[b]{rich_escape(registry)}[/b]",
        markup=True,
    )


@command()
async def get_clusters(root: Root) -> None:
    """
    Fetch and display the list of available clusters.

    """
    root.print("Fetch the list of available clusters...", style="dim")
    await root.client.config.fetch()
    fmt = ClustersFormatter()
    with root.pager():
        root.print(
            fmt(root.client.config.clusters.values(), root.client.config.cluster_name)
        )


@command()
@argument("cluster_name", required=False, default=None, type=str)
async def switch_cluster(root: Root, cluster_name: Optional[str]) -> None:
    """Switch the active cluster.

    CLUSTER_NAME is the cluster name to select.  The interactive prompt is used if the
    name is omitted (default).

    """
    root.print("Fetch the list of available clusters...", style="dim")
    await root.client.config.fetch()
    if cluster_name is None:
        if not root.tty:
            raise click.BadArgumentUsage(
                "Interactive mode is disabled for non-TTY mode, "
                "please specify the CLUSTER_NAME"
            )
        real_cluster_name = await prompt_cluster(root)
    else:
        real_cluster_name = cluster_name
    await root.client.config.switch_cluster(real_cluster_name)
    root.print(
        f"The current cluster is [u]{rich_escape(real_cluster_name)}[/u]", markup=True
    )


async def prompt_cluster(
    root: Root, *, session: Optional[PromptSession[str]] = None
) -> str:
    if session is None:
        session = PromptSession()
    clusters = root.client.config.clusters
    while True:
        fmt = ClustersFormatter()
        root.print(fmt(clusters.values(), root.client.config.cluster_name))
        with patch_stdout():
            answer = await session.prompt_async(
                f"Select cluster to switch [{root.client.config.cluster_name}]: "
            )
        answer = answer.strip()
        if not answer:
            answer = root.client.config.cluster_name
        if answer not in clusters:
            root.print(
                f"Selected cluster [u]{rich_escape(answer)}[/u] "
                f"doesn't exist, please try again.",
                markup=True,
            )
        else:
            return answer


config.add_command(login)
config.add_command(login_with_token)
config.add_command(login_headless)
config.add_command(show)
config.add_command(show_token)
config.add_command(show_quota)
config.add_command(aliases)
config.add_command(get_clusters)
config.add_command(switch_cluster)

config.add_command(docker)

config.add_command(logout)
