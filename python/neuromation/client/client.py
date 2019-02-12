from types import TracebackType
from typing import Optional, Type, Union

import aiohttp
from yarl import URL

from neuromation.client.utils import create_registry_url

from .api import API
from .config import Config
from .images import Images
from .jobs import Jobs
from .models import Models
from .storage import Storage
from .users import Users


DEFAULT_TIMEOUT = aiohttp.ClientTimeout(None, None, 30, 30)


class Client:
    def __init__(
        self,
        url: Union[URL, str],
        token: str,
        *,
        registry_url: str = "",  # default value is always overwritten
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ) -> None:
        if isinstance(url, str):
            url = URL(url)
        self._url = url
        # this is temporary until we implement getting server configuration dynamically:
        registry_url = registry_url or create_registry_url(str(self._url))
        self._registry_url = URL(registry_url)
        assert token
        self._config = Config(url, self._registry_url, token)
        self._api = API(url, token, timeout)
        self._jobs = Jobs(self._api, token)
        self._models = Models(self._api)
        self._storage = Storage(self._api, self._config)
        self._users = Users(self._api)
        self._images: Optional[Images] = None

    async def close(self) -> None:
        await self._api.close()
        if self._images is not None:
            await self._images.close()

    async def __aenter__(self) -> "Client":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_val: Optional[BaseException] = None,
        exc_tb: Optional[TracebackType] = None,
    ) -> None:
        await self.close()

    @property
    def username(self) -> str:
        return self._config.username

    @property
    def cfg(self) -> Config:
        return self._config

    @property
    def jobs(self) -> Jobs:
        return self._jobs

    @property
    def models(self) -> Models:
        return self._models

    @property
    def storage(self) -> Storage:
        return self._storage

    @property
    def users(self) -> Users:
        return self._users

    @property
    def images(self) -> Images:
        if self._images is None:
            self._images = Images(self._api, self._config)
        return self._images
