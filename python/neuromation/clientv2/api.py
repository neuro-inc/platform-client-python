import logging
from typing import Any, AsyncIterator, Dict, Optional

import aiohttp
from aiohttp import WSMessage
from async_generator import asynccontextmanager
from yarl import URL


log = logging.getLogger(__name__)


class ClientError(Exception):
    pass


class IllegalArgumentError(ValueError):
    pass


class AuthError(ClientError):
    pass


class AuthenticationError(AuthError):
    pass


class AuthorizationError(AuthError):
    pass


class ResourceNotFound(ValueError):
    pass


class API:
    """Transport provider for public API client.

    Internal class.
    """

    def __init__(self, url: URL, token: str, timeout: aiohttp.ClientTimeout) -> None:
        self._url = url
        self._token = token
        self._session = aiohttp.ClientSession(
            timeout=timeout, headers=self._auth_headers()
        )
        self._exception_map = {
            403: AuthorizationError,
            401: AuthenticationError,
            400: IllegalArgumentError,
            404: ResourceNotFound,
            405: ClientError,
        }

    async def close(self) -> None:
        await self._session.close()

    def _auth_headers(self) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        return headers

    @asynccontextmanager
    async def request(
        self,
        method: str,
        rel_url: URL,
        *,
        data: Any = None,
        json: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> AsyncIterator[aiohttp.ClientResponse]:
        assert not rel_url.is_absolute()
        url = (self._url / "").join(rel_url)
        log.debug("Fetch [%s] %s", method, url)
        async with self._session.request(
            method, url, headers=headers, json=json, data=data
        ) as resp:
            try:
                resp.raise_for_status()
            except aiohttp.ClientResponseError as exc:
                code = exc.status
                message = exc.message
                try:
                    error_response = await resp.json()
                    message = error_response["error"]
                except Exception:
                    pass
                err_cls = self._exception_map.get(code, IllegalArgumentError)
                raise err_cls(message)
            else:
                yield resp

    async def web_socket_request(
        self, rel_url: URL, *, headers: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[WSMessage]:
        # TODO: timeout
        assert not rel_url.is_absolute()
        url = (self._url / "").join(rel_url)
        log.debug("Fetch web socket: %s", url)

        async with self._session.ws_connect(url, headers=headers) as ws:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    yield msg
                elif msg.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                    break
