from dataclasses import dataclass
from typing import Optional, Tuple

from yarl import URL


@dataclass(frozen=True)
class RemoteImage:
    name: str
    tag: Optional[str] = None
    owner: Optional[str] = None
    registry: Optional[str] = None

    def __str__(self) -> str:
        pre = f"image://{self.owner}/" if _is_in_neuro_registry(self) else ""
        post = f":{self.tag}" if self.tag else ""
        return pre + self.name + post


def _is_in_neuro_registry(image: RemoteImage) -> bool:
    return bool(image.registry and image.owner)


def _as_repo_str(image: RemoteImage) -> str:
    pre = f"{image.registry}/{image.owner}/" if _is_in_neuro_registry(image) else ""
    post = f":{image.tag}" if image.tag else ""
    return pre + image.name + post


@dataclass(frozen=True)
class LocalImage:
    name: str
    tag: Optional[str] = None

    def __str__(self) -> str:
        post = f":{self.tag}" if self.tag else ""
        return self.name + post


class _ImageNameParser:
    default_tag = "latest"

    def __init__(self, default_user: str, registry_url: URL):
        self._default_user = default_user
        if not registry_url.host:
            raise ValueError(
                f"Empty hostname in registry URL '{registry_url}': "
                "please consider updating configuration"
            )
        self._registry = _get_url_authority(registry_url)

    def parse_as_local_image(self, image: str) -> LocalImage:
        try:
            self._validate_image_name(image)
            return self._parse_as_local_image(image)
        except ValueError as e:
            raise ValueError(f"Invalid local image '{image}': {e}") from e

    def parse_as_neuro_image(self, image: str, allow_tag: bool = True) -> RemoteImage:
        try:
            self._validate_image_name(image)
            tag: Optional[str]
            if allow_tag:
                tag = self.default_tag
            else:
                if self.has_tag(image):
                    raise ValueError("tag is not allowed")
                tag = None
            return self._parse_as_neuro_image(image, default_tag=tag)
        except ValueError as e:
            raise ValueError(f"Invalid remote image '{image}': {e}") from e

    def parse_remote(self, value: str) -> RemoteImage:
        if self.is_in_neuro_registry(value):
            return self.parse_as_neuro_image(value)
        else:
            img = self.parse_as_local_image(value)
            name = img.name
            registry = None
            if ":" in name:
                msg = "here name must contain slash(es). checked by _split_image_name()"
                assert "/" in name, msg
                registry, name = name.split("/", 1)

            return RemoteImage(name=name, tag=img.tag, registry=registry)

    def is_in_neuro_registry(self, image: str) -> bool:
        # not use URL here because URL("ubuntu:v1") is parsed as scheme=ubuntu path=v1
        return image.startswith("image:") or image.startswith(f"{self._registry}/")

    def convert_to_neuro_image(self, image: LocalImage) -> RemoteImage:
        return RemoteImage(
            name=image.name,
            tag=image.tag,
            owner=self._default_user,
            registry=self._registry,
        )

    def convert_to_local_image(self, image: RemoteImage) -> LocalImage:
        return LocalImage(name=image.name, tag=image.tag)

    def normalize(self, image: str) -> str:
        try:
            if self.is_in_neuro_registry(image):
                remote_image = self.parse_as_neuro_image(image)
                image_normalized = str(remote_image)
            else:
                local_image = self.parse_as_local_image(image)
                image_normalized = str(local_image)
        except ValueError:
            image_normalized = image
        return image_normalized

    def has_tag(self, image: str) -> bool:
        prefix = "image:"
        if image.startswith(prefix):
            image = image.lstrip(prefix).lstrip("/")
        name, tag = self._split_image_name(image, default_tag=None)
        return bool(tag)

    def _validate_image_name(self, image: str) -> None:
        if not image:
            raise ValueError("empty image name")
        if image.startswith("-"):
            raise ValueError(f"image cannot start with dash")
        if image == "image:latest":
            raise ValueError(
                "ambiguous value: valid as both local and remote image name"
            )

    def _parse_as_local_image(self, image: str) -> LocalImage:
        if self.is_in_neuro_registry(image):
            raise ValueError("scheme 'image://' is not allowed for local images")
        name, tag = self._split_image_name(image, self.default_tag)
        return LocalImage(name=name, tag=tag)

    def _parse_as_neuro_image(
        self, image: str, default_tag: Optional[str]
    ) -> RemoteImage:
        if not self.is_in_neuro_registry(image):
            raise ValueError("scheme 'image://' is required for remote images")

        url = URL(image)

        if url.scheme and url.scheme != "image":
            # image with port in registry: `localhost:5000/owner/ubuntu:latest`
            url = URL(f"//{url}")

        if not url.scheme:
            parts = url.path.split("/")
            url = URL.build(
                scheme="image",
                host=parts[1],
                path="/".join([""] + parts[2:]),
                query=url.query,
            )

        self._check_allowed_uri_elements(url)

        registry = self._registry
        owner = self._default_user if not url.host or url.host == "~" else url.host
        name, tag = self._split_image_name(url.path.lstrip("/"), default_tag)
        return RemoteImage(name=name, tag=tag, registry=registry, owner=owner)

    def _split_image_name(
        self, image: str, default_tag: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        colon_count = image.count(":")
        if colon_count == 0:
            name, tag = image, default_tag
        elif colon_count == 1:
            # case `ubuntu:latest`
            name, tag = image.split(":")
            if "/" in tag:
                # case `localhost:5000/ubuntu`
                name, tag = image, default_tag
            elif not tag:
                raise ValueError("empty tag is not allowed")
        elif colon_count == 2:
            # case `localhost:9000/owner/ubuntu:latest`
            if "/" not in image:
                # case `ubuntu:v11:latest`
                raise ValueError("too many tags")
            *image_arr, tag = image.split(":")
            name = ":".join(image_arr)
        else:
            raise ValueError("too many tags")
        if not tag:
            tag = default_tag
        elif "/" in tag:
            raise ValueError("invalid tag format")
        return name, tag

    def _check_allowed_uri_elements(self, url: URL) -> None:
        if not url.path or url.path == "/":
            raise ValueError("no image name specified")
        if url.query:
            raise ValueError(f"query is not allowed, found: '{url.query}'")
        if url.fragment:
            raise ValueError(f"fragment is not allowed, found: '{url.fragment}'")
        if url.user:
            raise ValueError(f"user is not allowed, found: '{url.user}'")
        if url.password:
            raise ValueError(f"password is not allowed, found: '{url.password}'")
        if url.port and url.scheme == "image":
            raise ValueError(
                f"port is not allowed with 'image://' scheme, found: '{url.port}'"
            )


def _get_url_authority(url: URL) -> Optional[str]:
    if url.host is None:
        return None
    port = url.explicit_port  # type: ignore
    suffix = f":{port}" if port is not None else ""
    return url.host + suffix
