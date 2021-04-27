import pathlib

from neuro_cli.formatters.secrets import (
    BaseSecretsFormatter,
    SecretsFormatter,
    SimpleSecretsFormatter,
)
from neuro_cli.formatters.utils import URIFormatter, uri_formatter

from .root import Root
from .utils import argument, command, group, option


@group()
def secret() -> None:
    """
    Operations with secrets.
    """


@command()
@option("--full-uri", is_flag=True, help="Output full disk URI.")
async def ls(root: Root, full_uri: bool) -> None:
    """
    List secrets.
    """
    if root.quiet:
        secrets_fmtr: BaseSecretsFormatter = SimpleSecretsFormatter()
    else:
        if full_uri:
            uri_fmtr: URIFormatter = str
        else:
            uri_fmtr = uri_formatter(
                username=root.client.username, cluster_name=root.client.cluster_name
            )
        secrets_fmtr = SecretsFormatter(
            uri_fmtr,
        )

    secrets = []
    with root.status("Fetching secrets") as status:
        async for secret in root.client.secrets.list():
            secrets.append(secret)
            status.update(f"Fetching secrets ({len(secrets)} loaded)")

    with root.pager():
        root.print(secrets_fmtr(secrets))


@command()
@argument("key")
@argument("value")
async def add(root: Root, key: str, value: str) -> None:
    """
    Add secret KEY with data VALUE.

    If VALUE starts with @ it points to a file with secrets content.

    Examples:

      neuro secret add KEY_NAME VALUE
      neuro secret add KEY_NAME @path/to/file.txt
    """
    await root.client.secrets.add(key, read_data(value))


@command()
@argument("key")
async def rm(root: Root, key: str) -> None:
    """
    Remove secret KEY.
    """

    await root.client.secrets.rm(key)
    if root.verbosity > 0:
        root.print(f"Secret with key '{key}' was successfully removed")


secret.add_command(ls)
secret.add_command(add)
secret.add_command(rm)


def read_data(value: str) -> bytes:
    if value.startswith("@"):
        # Read from file
        data = pathlib.Path(value[1:]).expanduser().read_bytes()
    else:
        data = value.encode("utf-8")
    return data
