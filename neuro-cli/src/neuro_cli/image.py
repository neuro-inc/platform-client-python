import contextlib
import logging
from dataclasses import replace
from typing import Optional, Sequence

from rich.markup import escape as rich_escape
from rich.progress import Progress

from neuro_sdk import LocalImage, RemoteImage, Tag, TagOption

from neuro_cli.formatters.images import (
    BaseImagesFormatter,
    BaseTagsFormatter,
    DockerImageProgress,
    LongImagesFormatter,
    LongTagsFormatter,
    QuietImagesFormatter,
    ShortImagesFormatter,
    ShortTagsFormatter,
)
from neuro_cli.formatters.utils import ImageFormatter, image_formatter, uri_formatter

from .click_types import RemoteImageType
from .root import Root
from .utils import (
    argument,
    command,
    deprecated_quiet_option,
    format_size,
    group,
    option,
)

log = logging.getLogger(__name__)


@group()
def image() -> None:
    """
    Container image operations.
    """


@command()
@argument("local_image")
@argument("remote_image", required=False)
@deprecated_quiet_option
async def push(root: Root, local_image: str, remote_image: Optional[str]) -> None:
    """
    Push an image to platform registry.

    Remote image must be URL with image:// scheme.
    Image names can contain tag. If tags not specified 'latest' will
    be used as value.

    Examples:

    neuro push myimage
    neuro push alpine:latest image:my-alpine:production
    neuro push alpine image://myfriend/alpine:shared

    """

    progress = DockerImageProgress.create(console=root.console, quiet=root.quiet)
    local_obj = root.client.parse.local_image(local_image)
    if remote_image is not None:
        remote_obj: Optional[RemoteImage] = root.client.parse.remote_image(remote_image)
    else:
        remote_obj = None
    with contextlib.closing(progress):
        result_remote_image = await root.client.images.push(
            local_obj, remote_obj, progress=progress
        )
    root.print(result_remote_image)


@command()
@argument("remote_image")
@argument("local_image", required=False)
@deprecated_quiet_option
async def pull(root: Root, remote_image: str, local_image: Optional[str]) -> None:
    """
    Pull an image from platform registry.

    Remote image name must be URL with image:// scheme.
    Image names can contain tag.

    Examples:

    neuro pull image:myimage
    neuro pull image://myfriend/alpine:shared
    neuro pull image://username/my-alpine:production alpine:from-registry

    """

    progress = DockerImageProgress.create(console=root.console, quiet=root.quiet)
    remote_obj = root.client.parse.remote_image(remote_image)
    if local_image is not None:
        local_obj: Optional[LocalImage] = root.client.parse.local_image(local_image)
    else:
        local_obj = None
    with contextlib.closing(progress):
        result_local_image = await root.client.images.pull(
            remote_obj, local_obj, progress=progress
        )
    root.print(result_local_image)


@command()
@option("-l", "format_long", is_flag=True, help="List in long format.")
@option("--full-uri", is_flag=True, help="Output full image URI.")
async def ls(root: Root, format_long: bool, full_uri: bool) -> None:
    """
    List images.
    """

    with root.status("Fetching images"):
        images = await root.client.images.ls()

    image_fmtr: ImageFormatter
    if full_uri:
        image_fmtr = str
    else:
        uri_fmtr = uri_formatter(
            username=root.client.username, cluster_name=root.client.cluster_name
        )
        image_fmtr = image_formatter(uri_formatter=uri_fmtr)
    formatter: BaseImagesFormatter
    if root.quiet:
        formatter = QuietImagesFormatter(image_formatter=image_fmtr)
    elif format_long:
        formatter = LongImagesFormatter(image_formatter=image_fmtr)
    else:
        formatter = ShortImagesFormatter(image_formatter=image_fmtr)
    with root.pager():
        root.print(formatter(images))


@command()
@option(
    "-l", "format_long", is_flag=True, help="List in long format, with image sizes."
)
@argument("image", type=RemoteImageType(tag_option=TagOption.DENY))
async def tags(root: Root, format_long: bool, image: RemoteImage) -> None:
    """
    List tags for image in platform registry.

    Image name must be URL with image:// scheme.

    Examples:

    neuro image tags image://myfriend/alpine
    neuro image tags -l image:myimage
    """

    with root.status(f"Fetching tags for image [b]{image}[/b]"):
        tags_list = [
            Tag(name=str(img.tag)) for img in await root.client.images.tags(image)
        ]

    formatter: BaseTagsFormatter
    if format_long:
        with Progress() as progress:
            task = progress.add_task("Getting image sizes...", total=len(tags_list))
            tags_with_sizes = []
            for tag in tags_list:
                tag_with_size = await root.client.images.tag_info(
                    replace(image, tag=tag.name)
                )
                progress.update(task, advance=1)
                tags_with_sizes.append(tag_with_size)
        formatter = LongTagsFormatter()
        tags_list = tags_with_sizes
    else:
        formatter = ShortTagsFormatter()
    with root.pager():
        root.print(f"Tags for [bold]{rich_escape(str(image))}[/bold]", markup=True)
        root.print(formatter(image, tags_list))


@command()
@option(
    "-f",
    "force",
    is_flag=True,
    help="Force deletion of all tags referencing the image.",
)
@argument(
    "images", nargs=-1, required=True, type=RemoteImageType(tag_option=TagOption.ALLOW)
)
async def rm(root: Root, force: bool, images: Sequence[RemoteImage]) -> None:
    """
    Remove image from platform registry.

    Image name must be URL with image:// scheme.
    Image name must contain tag.

    Examples:

    neuro image rm image://myfriend/alpine:shared
    neuro image rm image:myimage:latest
    """
    for image in images:
        if image.tag is None:
            await remove_image(root, image)
        else:
            await remove_tag(root, image, force=force)


@command()
@argument("image", type=RemoteImageType())
async def size(root: Root, image: RemoteImage) -> None:
    """
    Get image size

    Image name must be URL with image:// scheme.
    Image name must contain tag.

    Examples:

    neuro image size image://myfriend/alpine:shared
    neuro image size image:myimage:latest
    """
    size = await root.client.images.size(image)
    root.print(format_size(size))


@command()
@argument("image", type=RemoteImageType())
async def digest(root: Root, image: RemoteImage) -> None:
    """
    Get digest of an image from remote registry

    Image name must be URL with image:// scheme.
    Image name must contain tag.

    Examples:

    neuro image digest image://myfriend/alpine:shared
    neuro image digest image:myimage:latest
    """
    res = await root.client.images.digest(image)
    root.print(res)


image.add_command(ls)
image.add_command(push)
image.add_command(pull)
image.add_command(rm)
image.add_command(size)
image.add_command(digest)
image.add_command(tags)


async def remove_image(root: Root, image: RemoteImage) -> None:
    assert image.tag is None
    images = await root.client.images.tags(image)
    for img in images:
        await remove_tag(root, img, force=True)


async def remove_tag(root: Root, image: RemoteImage, *, force: bool) -> None:
    assert image.tag is not None
    digest = await root.client.images.digest(image)
    root.print(
        f"Deleting {image} identified by [bold]{rich_escape(digest)}[/bold]",
        markup=True,
    )
    tags = await root.client.images.tags(replace(image, tag=None))
    # Collect all tags referencing the image to be deleted
    if not force and len(tags) > 1:
        tags_for_image = []
        for tag in tags:
            tag_digest = await root.client.images.digest(tag)
            if tag_digest == digest:
                tags_for_image.append(tag_digest)
        if len(tags_for_image) > 1:
            raise ValueError(
                f"There's more than one tag referencing this digest: "
                f"{', '.join(tags_for_image)}.\n"
                f"Please use -f to force deletion for all of them."
            )
    await root.client.images.rm(image, digest)
