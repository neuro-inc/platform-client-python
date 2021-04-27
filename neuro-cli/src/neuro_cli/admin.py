import asyncio
import configparser
import json
import logging
import os
import pathlib
from dataclasses import replace
from decimal import Decimal
from typing import IO, Any, Mapping, Optional

import click
import yaml
from prompt_toolkit import PromptSession
from rich.markup import escape as rich_escape

from neuro_sdk import Preset
from neuro_sdk.admin import _ClusterUserRoleType

from .click_types import MEGABYTE
from .defaults import JOB_CPU_NUMBER, JOB_MEMORY_AMOUNT, PRESET_PRICE
from .formatters.admin import ClustersFormatter, ClusterUserFormatter
from .formatters.config import QuotaFormatter
from .root import Root
from .utils import argument, command, group, option

log = logging.getLogger(__name__)


@group()
def admin() -> None:
    """Cluster administration commands."""


@command()
async def get_clusters(root: Root) -> None:
    """
    Print the list of available clusters.
    """
    fmt = ClustersFormatter()
    with root.status("Fetching the list of clusters"):
        clusters = await root.client._admin.list_clusters()
    with root.pager():
        root.print(fmt(clusters.values()))


@command()
@argument("cluster_name", required=True, type=str)
@argument("config", required=True, type=click.File(encoding="utf8", lazy=False))
async def add_cluster(root: Root, cluster_name: str, config: IO[str]) -> None:
    """
    Create a new cluster and start its provisioning.
    """
    config_dict = yaml.safe_load(config)
    await root.client._admin.add_cluster(cluster_name, config_dict)
    if not root.quiet:
        root.print(
            f"Cluster {cluster_name} successfully added "
            "and will be set up within 24 hours"
        )


@command()
@option(
    "--type", prompt="Select cluster type", type=click.Choice(["aws", "gcp", "azure"])
)
async def show_cluster_options(root: Root, type: str) -> None:
    """
    Create a cluster configuration file.
    """
    config_options = await root.client._admin.get_cloud_provider_options(type)
    root.print(
        json.dumps(config_options, sort_keys=True, indent=2),
        crop=False,
        overflow="ignore",
    )


@command()
@argument(
    "config",
    required=False,
    type=click.Path(exists=False, path_type=str),
    default="cluster.yml",
)
@option(
    "--type", prompt="Select cluster type", type=click.Choice(["aws", "gcp", "azure"])
)
async def generate_cluster_config(root: Root, config: str, type: str) -> None:
    """
    Create a cluster configuration file.
    """
    config_path = pathlib.Path(config)
    if config_path.exists():
        raise ValueError(
            f"Config path {config_path} already exists, "
            "please remove the file or pass the new file name explicitly."
        )
    session: PromptSession[str] = PromptSession()
    if type == "aws":
        content = await generate_aws(session)
    elif type == "gcp":
        content = await generate_gcp(session)
    elif type == "azure":
        content = await generate_azure(session)
    else:
        assert False, "Prompt should prevent this case"
    config_path.write_text(content, encoding="utf-8")
    if not root.quiet:
        root.print(f"Cluster config {config_path} is generated.")


AWS_TEMPLATE = """\
type: aws
region: us-east-1
zones:
- us-east-1a
- us-east-1b
vpc_id: {vpc_id}
credentials:
  access_key_id: {access_key_id}
  secret_access_key: {secret_access_key}
node_pools:
- id: m5_2xlarge
  min_size: 1
  max_size: 4
- id: p2_xlarge_1x_nvidia_tesla_k80
  min_size: 1
  max_size: 4
- id: p3_2xlarge_1x_nvidia_tesla_v100
  min_size: 0
  max_size: 1
storage:
  id: generalpurpose_bursting
"""


async def generate_aws(session: PromptSession[str]) -> str:
    args = {}
    args["vpc_id"] = await session.prompt_async("AWS VPC ID: ")
    access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if access_key_id is None or secret_access_key is None:
        aws_config_file = pathlib.Path(
            os.environ.get("AWS_SHARED_CREDENTIALS_FILE", "~/.aws/credentials")
        )
        aws_config_file = aws_config_file.expanduser().absolute()
        parser = configparser.ConfigParser()
        parser.read(aws_config_file)
        profile = await session.prompt_async(
            "AWS profile name: ", default=os.environ.get("AWS_PROFILE", "default")
        )
        if access_key_id is None:
            access_key_id = parser[profile]["aws_access_key_id"]
        if secret_access_key is None:
            secret_access_key = parser[profile]["aws_secret_access_key"]
    access_key_id = await session.prompt_async(
        "AWS Access Key: ", default=access_key_id
    )
    secret_access_key = await session.prompt_async(
        "AWS Secret Key: ", default=secret_access_key
    )
    args["access_key_id"] = access_key_id
    args["secret_access_key"] = secret_access_key
    return AWS_TEMPLATE.format_map(args)


GCP_TEMPLATE = """\
type: gcp
location_type: multi_zonal
region: us-central1
zones:
- us-central1-a
- us-central1-c
project: {project_name}
credentials: {credentials}
node_pools:
- id: n1_highmem_8
  min_size: 1
  max_size: 4
- id: n1_highmem_8_1x_nvidia_tesla_k80
  min_size: 1
  max_size: 4
- id: n1_highmem_8_1x_nvidia_tesla_v100
  min_size: 0
  max_size: 1
storage:
  id: gcs-nfs
"""


async def generate_gcp(session: PromptSession[str]) -> str:
    args = {}
    args["project_name"] = await session.prompt_async("GCP project name: ")
    credentials_file = await session.prompt_async(
        "Service Account Key File (.json): ",
        default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""),
    )
    with open(credentials_file, "rb") as fp:
        data = json.load(fp)
    out = yaml.dump(data)
    args["credentials"] = "\n" + "\n".join("  " + line for line in out.splitlines())
    return GCP_TEMPLATE.format_map(args)


AZURE_TEMPLATE = """\
type: azure
region: centralus
resource_group: {resource_group}
credentials:
  subscription_id: {subscription_id}
  tenant_id: {tenant_id}
  client_id: {client_id}
  client_secret: {client_secret}
node_pools:
- id: standard_d8s_v3
  min_size: 1
  max_size: 4
- id: standard_nc6_1x_nvidia_tesla_k80
  min_size: 1
  max_size: 4
- id: standard_nc6s_v3_1x_nvidia_tesla_v100
  min_size: 0
  max_size: 1
storage:
  id: premium_lrs
  file_share_size_gib: {file_share_size_gib}
"""


async def generate_azure(session: PromptSession[str]) -> str:
    args = {}
    args["subscription_id"] = await session.prompt_async(
        "Azure subscription ID: ", default=os.environ.get("AZURE_SUBSCRIPTION_ID", "")
    )
    args["client_id"] = await session.prompt_async(
        "Azure client ID: ", default=os.environ.get("AZURE_CLIENT_ID", "")
    )
    args["tenant_id"] = await session.prompt_async(
        "Azure tenant ID: ", default=os.environ.get("AZURE_TENANT_ID", "")
    )
    args["client_secret"] = await session.prompt_async(
        "Azure client secret: ", default=os.environ.get("AZURE_CLIENT_SECRET", "")
    )
    args["resource_group"] = await session.prompt_async("Azure resource group: ")
    args["file_share_size_gib"] = await session.prompt_async(
        "Azure Files storage size (Gib): "
    )
    return AZURE_TEMPLATE.format_map(args)


@command()
@argument("cluster_name", required=False, default=None, type=str)
async def get_cluster_users(root: Root, cluster_name: Optional[str]) -> None:
    """
    Print the list of all users in the cluster with their assigned role.
    """
    fmt = ClusterUserFormatter()
    cluster_name = cluster_name or root.client.config.cluster_name
    with root.status(
        f"Fetching the list of cluster users of cluster [b]cluster_name[/b]"
    ):
        clusters = await root.client._admin.list_cluster_users(cluster_name)
    with root.pager():
        root.print(fmt(clusters))


@command()
@argument("cluster_name", required=True, type=str)
@argument("user_name", required=True, type=str)
@argument(
    "role",
    required=False,
    default=_ClusterUserRoleType.USER.value,
    metavar="[ROLE]",
    type=click.Choice(list(_ClusterUserRoleType)),
)
async def add_cluster_user(
    root: Root, cluster_name: str, user_name: str, role: str
) -> None:
    """
    Add user access to specified cluster.

    The command supports one of 3 user roles: admin, manager or user.
    """
    user = await root.client._admin.add_cluster_user(cluster_name, user_name, role)
    if not root.quiet:
        root.print(
            f"Added [bold]{rich_escape(user.user_name)}[/bold] to cluster "
            f"[bold]{rich_escape(cluster_name)}[/bold] as "
            f"[bold]{rich_escape(user.role)}[/bold]",
            markup=True,
        )


def _parse_quota_value(
    value: Optional[str], allow_infinity: bool = False
) -> Optional[int]:
    if value is None:
        return None
    try:
        if value[-1] not in ("h", "m"):
            raise ValueError(f"Unable to parse: '{value}'")
        result = float(value[:-1]) * {"h": 60, "m": 1}[value[-1]]
        if result < 0:
            raise ValueError(f"Negative quota values ({value}) are not allowed")
        if result == float("inf"):
            if allow_infinity:
                return None
            else:
                raise ValueError("Infinite quota values are not allowed")
    except (ValueError, LookupError):
        raise
    return int(result)


def _parse_credits_value(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(value)
    except (ValueError, LookupError):
        raise click.BadParameter(f"{value} is not valid decimal number")


@command()
@argument("cluster_name", required=True, type=str)
@argument("user_name", required=True, type=str)
async def remove_cluster_user(root: Root, cluster_name: str, user_name: str) -> None:
    """
    Remove user access from the cluster.
    """
    await root.client._admin.remove_cluster_user(cluster_name, user_name)
    if not root.quiet:
        root.print(
            f"Removed [bold]{rich_escape(user_name)}[/bold] from cluster "
            f"[bold]{rich_escape(cluster_name)}[/bold]",
            markup=True,
        )


@command()
@argument("cluster_name", required=True, type=str)
@argument("user_name", required=True, type=str)
@option(
    "-c",
    "--credits",
    metavar="AMOUNT",
    type=str,
    help="Maximum running jobs quota",
)
@option(
    "-j",
    "--jobs",
    metavar="AMOUNT",
    type=int,
    help="Maximum running jobs quota",
)
@option(
    "-g",
    "--gpu",
    metavar="AMOUNT",
    type=str,
    help="GPU quota value in hours (h) or minutes (m).",
)
@option(
    "-n",
    "--non-gpu",
    metavar="AMOUNT",
    type=str,
    help="Non-GPU quota value in hours (h) or minutes (m).",
)
async def set_user_quota(
    root: Root,
    cluster_name: str,
    user_name: str,
    credits: Optional[str],
    jobs: Optional[int],
    gpu: Optional[str],
    non_gpu: Optional[str],
) -> None:
    """
    Set user quota to given values
    """
    credits_decimal = _parse_credits_value(credits)
    gpu_value_minutes = _parse_quota_value(gpu, allow_infinity=True)
    non_gpu_value_minutes = _parse_quota_value(non_gpu, allow_infinity=True)
    user_with_quota = await root.client._admin.set_user_quota(
        cluster_name=cluster_name,
        user_name=user_name,
        credits=credits_decimal,
        total_running_jobs=jobs,
        gpu_value_minutes=gpu_value_minutes,
        non_gpu_value_minutes=non_gpu_value_minutes,
    )
    fmt = QuotaFormatter()
    root.print(
        f"New quotas for [u]{rich_escape(user_with_quota.user_name)}[/u] "
        f"on cluster [u]{rich_escape(cluster_name)}[/u]:",
        markup=True,
    )
    root.print(fmt(user_with_quota.quota))


@command()
@argument("cluster_name", required=True, type=str)
@argument("user_name", required=True, type=str)
@option(
    "-c",
    "--credits",
    metavar="AMOUNT",
    type=str,
    help="Maximum running jobs quota",
)
@option(
    "-g",
    "--gpu",
    metavar="AMOUNT",
    type=str,
    help="Additional GPU quota value in hours (h) or minutes (m).",
)
@option(
    "-n",
    "--non-gpu",
    metavar="AMOUNT",
    type=str,
    help="Additional non-GPU quota value in hours (h) or minutes (m).",
)
async def add_user_quota(
    root: Root,
    cluster_name: str,
    user_name: str,
    credits: str,
    gpu: Optional[str],
    non_gpu: Optional[str],
) -> None:
    """
    Add given values to user quota
    """
    additional_credits = _parse_credits_value(credits)
    additional_gpu_value_minutes = _parse_quota_value(gpu, False)
    additional_non_gpu_value_minutes = _parse_quota_value(non_gpu, False)
    user_with_quota = await root.client._admin.add_user_quota(
        cluster_name,
        user_name,
        additional_credits=additional_credits,
        additional_gpu_value_minutes=additional_gpu_value_minutes,
        additional_non_gpu_value_minutes=additional_non_gpu_value_minutes,
    )
    fmt = QuotaFormatter()
    root.print(
        f"New quotas for [u]{rich_escape(user_with_quota.user_name)}[/u] "
        f"on cluster [u]{rich_escape(cluster_name)}[/u]:",
        markup=True,
    )
    root.print(fmt(user_with_quota.quota))


async def _update_presets_and_fetch(root: Root, presets: Mapping[str, Preset]) -> None:
    cluster_name = root.client.config.cluster_name
    await root.client._admin.update_cluster_resource_presets(cluster_name, presets)

    if root.verbosity >= 1:
        _print = root.print
    else:

        def _print(*args: Any, **kwargs: Any) -> None:
            pass

    _print("Requested presets update")

    async def _sync_local_config() -> None:
        _print("Fetching new server config", end="")
        try:
            while dict(root.client.config.presets) != presets:
                _print(".", end="")
                await root.client.config.fetch()
                await asyncio.sleep(0.5)
        finally:
            _print("")

    try:
        await asyncio.wait_for(_sync_local_config(), 10)
    except asyncio.TimeoutError:
        log.warning(
            "Fetched server presets are not same as new values. "
            "Maybe there was some concurrent update?"
        )


@command()
@argument("preset_name")
@option(
    "--credits-per-hour",
    metavar="AMOUNT",
    type=str,
    help="Price of running job of this preset for an hour in credits",
    default=PRESET_PRICE,
    show_default=True,
)
@option(
    "-c",
    "--cpu",
    metavar="NUMBER",
    type=float,
    help="Number of CPUs",
    default=JOB_CPU_NUMBER,
    show_default=True,
)
@option(
    "-m",
    "--memory",
    metavar="AMOUNT",
    type=MEGABYTE,
    help="Memory amount",
    default=JOB_MEMORY_AMOUNT,
    show_default=True,
)
@option(
    "-g",
    "--gpu",
    metavar="NUMBER",
    type=int,
    help="Number of GPUs",
)
@option(
    "--gpu-model",
    metavar="MODEL",
    help="GPU model",
)
@option("--tpu-type", metavar="TYPE", type=str, help="TPU type")
@option(
    "tpu_software_version",
    "--tpu-sw-version",
    metavar="VERSION",
    type=str,
    help="TPU software version",
)
@option(
    "--scheduler/--no-scheduler",
    "-p/-P",
    help="Use round robin scheduler for jobs",
    default=False,
    show_default=True,
)
@option(
    "--preemptible-node/--non-preemptible-node",
    help="Use a lower-cost preemptible instance",
    default=False,
    show_default=True,
)
async def add_resource_preset(
    root: Root,
    preset_name: str,
    credits_per_hour: str,
    cpu: float,
    memory: int,
    gpu: Optional[int],
    gpu_model: Optional[str],
    tpu_type: Optional[str],
    tpu_software_version: Optional[str],
    scheduler: bool,
    preemptible_node: bool,
) -> None:
    """
    Add new resource preset
    """
    presets = dict(root.client.config.presets)
    if preset_name in presets:
        raise ValueError(f"Preset '{preset_name}' already exists")
    presets[preset_name] = Preset(
        credits_per_hour=Decimal(credits_per_hour),
        cpu=cpu,
        memory_mb=memory,
        gpu=gpu,
        gpu_model=gpu_model,
        tpu_type=tpu_type,
        tpu_software_version=tpu_software_version,
        scheduler_enabled=scheduler,
        preemptible_node=preemptible_node,
    )
    await _update_presets_and_fetch(root, presets)
    if not root.quiet:
        root.print(
            f"Added resource preset [b]{rich_escape(preset_name)}[/b] "
            f"in cluster [b]{rich_escape(root.client.config.cluster_name)}[/b]",
            markup=True,
        )


@command()
@argument("preset_name")
@option(
    "--credits-per-hour",
    metavar="AMOUNT",
    type=str,
    help="Price of running job of this preset for an hour in credits",
)
@option(
    "-c",
    "--cpu",
    metavar="NUMBER",
    type=float,
    help="Number of CPUs",
)
@option(
    "-m",
    "--memory",
    metavar="AMOUNT",
    type=MEGABYTE,
    help="Memory amount",
)
@option(
    "-g",
    "--gpu",
    metavar="NUMBER",
    type=int,
    help="Number of GPUs",
)
@option(
    "--gpu-model",
    metavar="MODEL",
    help="GPU model",
)
@option("--tpu-type", metavar="TYPE", type=str, help="TPU type")
@option(
    "tpu_software_version",
    "--tpu-sw-version",
    metavar="VERSION",
    type=str,
    help="TPU software version",
)
@option(
    "--scheduler/--no-scheduler",
    "-p/-P",
    help="Use round robin scheduler for jobs",
)
@option(
    "--preemptible-node/--non-preemptible-node",
    help="Use a lower-cost preemptible instance",
)
async def update_resource_preset(
    root: Root,
    preset_name: str,
    credits_per_hour: Optional[str],
    cpu: Optional[float],
    memory: Optional[int],
    gpu: Optional[int],
    gpu_model: Optional[str],
    tpu_type: Optional[str],
    tpu_software_version: Optional[str],
    scheduler: Optional[bool],
    preemptible_node: Optional[bool],
) -> None:
    """
    Update existing resource preset
    """
    presets = dict(root.client.config.presets)
    try:
        preset = presets[preset_name]
    except KeyError:
        raise ValueError(f"Preset '{preset_name}' does not exists")

    kwargs = {
        "credits_per_hour": Decimal(credits_per_hour)
        if credits_per_hour is not None
        else None,
        "cpu": cpu,
        "memory_mb": memory,
        "gpu": gpu,
        "gpu_model": gpu_model,
        "tpu_type": tpu_type,
        "tpu_software_version": tpu_software_version,
        "scheduler_enabled": scheduler,
        "preemptible_node": preemptible_node,
    }
    kwargs = {key: value for key, value in kwargs.items() if value is not None}

    presets[preset_name] = replace(preset, **kwargs)

    await _update_presets_and_fetch(root, presets)

    if not root.quiet:
        root.print(
            f"Updated resource preset [b]{rich_escape(preset_name)}[/b] "
            f"in cluster [b]{rich_escape(root.client.config.cluster_name)}[/b]",
            markup=True,
        )


@command()
@argument("preset_name")
async def remove_resource_preset(root: Root, preset_name: str) -> None:
    """
    Remove resource preset
    """
    presets = dict(root.client.config.presets)
    if preset_name not in presets:
        raise ValueError(f"Preset '{preset_name}' not found")
    del presets[preset_name]
    await _update_presets_and_fetch(root, presets)
    if not root.quiet:
        root.print(
            f"Removed resource preset [b]{rich_escape(preset_name)}[/b] "
            f"from cluster [b]{rich_escape(root.client.config.cluster_name)}[/b]",
            markup=True,
        )


admin.add_command(get_clusters)
admin.add_command(generate_cluster_config)
admin.add_command(add_cluster)
admin.add_command(show_cluster_options)

admin.add_command(get_cluster_users)
admin.add_command(add_cluster_user)
admin.add_command(remove_cluster_user)

admin.add_command(set_user_quota)
admin.add_command(add_user_quota)

admin.add_command(add_resource_preset)
admin.add_command(update_resource_preset)
admin.add_command(remove_resource_preset)
