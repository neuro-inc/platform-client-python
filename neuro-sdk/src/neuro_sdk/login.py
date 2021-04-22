import abc
import asyncio
import base64
import errno
import hashlib
import secrets
import sys
import time
import warnings
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    List,
    Optional,
    Sequence,
    Type,
    cast,
)
from urllib.parse import urlencode

import aiohttp
from aiohttp import ClientResponseError
from aiohttp.web import (
    Application,
    AppRunner,
    HTTPBadRequest,
    HTTPForbidden,
    HTTPFound,
    HTTPUnauthorized,
    Request,
    Response,
    TCPSite,
)
from yarl import URL

from .errors import AuthError

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", "int_from_bytes is deprecated", UserWarning)
    from jose import JWTError, jwt

if sys.version_info >= (3, 7):  # pragma: no cover
    from contextlib import asynccontextmanager
else:
    from async_generator import asynccontextmanager


def urlsafe_unpadded_b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


JWT_IDENTITY_CLAIM = "https://platform.neuromation.io/user"
JWT_IDENTITY_CLAIM_OPTIONS = ("identity", JWT_IDENTITY_CLAIM)


class AuthCode:
    def __init__(self, callback_url: Optional[URL] = None) -> None:
        self._future: asyncio.Future[str] = asyncio.Future()

        self._verifier = urlsafe_unpadded_b64encode(secrets.token_bytes(32))
        digest = hashlib.sha256(self._verifier.encode()).digest()
        self._challenge = urlsafe_unpadded_b64encode(digest)
        self._challenge_method = "S256"

        self._callback_url = callback_url

    @property
    def verifier(self) -> str:
        return self._verifier

    @property
    def challenge(self) -> str:
        return self._challenge

    @property
    def challenge_method(self) -> str:
        return self._challenge_method

    def set_value(self, value: str) -> None:
        if not self._future.cancelled():
            self._future.set_result(value)

    @property
    def callback_url(self) -> URL:
        assert self._callback_url
        return self._callback_url

    @callback_url.setter
    def callback_url(self, value: URL) -> None:
        self._callback_url = value

    def set_exception(self, exc: Exception) -> None:
        if not self._future.cancelled():
            self._future.set_exception(exc)

    def cancel(self) -> None:
        self._future.cancel()

    async def wait(self, timeout_s: float = 60.0) -> str:
        try:
            await asyncio.wait_for(self._future, timeout_s)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            raise AuthError("failed to get an authorization code")
        return self._future.result()


class AuthCodeCallbackClient(abc.ABC):
    def __init__(self, url: URL, client_id: str, audience: str) -> None:
        self._url = url
        self._client_id = client_id
        self._audience = audience

    async def request(self, code: AuthCode) -> AuthCode:
        url = self._url.with_query(
            response_type="code",
            code_challenge=code.challenge,
            code_challenge_method=code.challenge_method,
            client_id=self._client_id,
            redirect_uri=str(code.callback_url),
            scope="offline_access",
            audience=self._audience,
        )
        await self._request(url, code)
        await code.wait()
        return code

    @abc.abstractmethod
    async def _request(self, url: URL, code: AuthCode) -> None:
        pass


class WebBrowserAuthCodeCallbackClient(AuthCodeCallbackClient):
    def __init__(
        self,
        url: URL,
        client_id: str,
        audience: str,
        show_browser_cb: Callable[[URL], Awaitable[None]],
    ) -> None:
        super().__init__(url=url, client_id=client_id, audience=audience)
        self._show_browser_cb = show_browser_cb

    async def _request(self, url: URL, code: AuthCode) -> None:
        await self._show_browser_cb(url)


class HeadlessAuthCodeCallbackClient(AuthCodeCallbackClient):
    def __init__(
        self,
        url: URL,
        client_id: str,
        audience: str,
        get_auth_code_cb: Callable[[URL], Awaitable[str]],
    ) -> None:
        super().__init__(url=url, client_id=client_id, audience=audience)
        self._get_auth_code_cb = get_auth_code_cb

    async def _request(self, url: URL, code: AuthCode) -> None:
        try:
            auth_code = await self._get_auth_code_cb(url)
            assert auth_code
            code.set_value(auth_code)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            code.set_exception(exc)


class AuthCodeCallbackHandler:
    def __init__(self, code: AuthCode, redirect_url: Optional[URL] = None) -> None:
        self._code = code
        self._redirect_url = redirect_url

    async def handle(self, request: Request) -> Response:
        if "error" in request.query:
            await self._handle_error(request)

        code = request.query.get("code")

        if not code:
            self._code.cancel()
            raise HTTPBadRequest(text="The 'code' query parameter is missing.")

        self._code.set_value(code)

        if self._redirect_url:
            raise HTTPFound(self._redirect_url)
        return Response(text="OK")

    async def _handle_error(self, request: Request) -> None:
        error = request.query["error"]
        description = request.query.get("error_description", "")

        exc_factory: Type[Exception]
        if error == "unauthorized":
            exc_factory = HTTPUnauthorized
        elif error == "access_denied":
            exc_factory = HTTPForbidden
        else:
            exc_factory = HTTPBadRequest

        self._code.set_exception(AuthError(description))
        raise exc_factory(text=description)


def create_auth_code_app(
    code: AuthCode, redirect_url: Optional[URL] = None
) -> Application:
    app = Application()
    handler = AuthCodeCallbackHandler(code, redirect_url=redirect_url)
    app.router.add_get("/", handler.handle)
    return app


@asynccontextmanager
async def create_app_server_once(
    app: Application, *, host: str = "127.0.0.1", port: int = 8080
) -> AsyncIterator[URL]:
    runner = AppRunner(app, access_log=None)
    try:
        await runner.setup()
        site = TCPSite(runner, host, port, shutdown_timeout=0.0)
        await site.start()
        yield URL(site.name)
    finally:
        await runner.shutdown()
        await runner.cleanup()


@asynccontextmanager
async def create_app_server(
    app: Application, *, host: str = "127.0.0.1", ports: Sequence[int] = (8080,)
) -> AsyncIterator[URL]:
    for port in ports:
        try:
            async with create_app_server_once(app, host=host, port=port) as url:
                yield url
            return
        except OSError as err:
            if err.errno != errno.EADDRINUSE:
                raise
    else:
        raise RuntimeError("No free ports.")


@dataclass(frozen=True)
class _AuthToken:
    token: str
    expiration_time: float
    refresh_token: str = field(repr=False)

    def is_expired(self, *, now: Optional[float] = None) -> bool:
        if now is None:
            now = time.time()
        return self.expiration_time <= now

    @property
    def username(self) -> str:
        try:
            claims = jwt.get_unverified_claims(self.token)
        except JWTError as e:
            raise ValueError(
                f"Passed string does not contain valid JWT structure."
            ) from e
        for identity_claim in JWT_IDENTITY_CLAIM_OPTIONS:
            if identity_claim in claims:
                return claims[identity_claim]
        raise ValueError("JWT Claims structure is not correct.")

    @classmethod
    def create(
        cls,
        token: str,
        expires_in: float,
        refresh_token: str,
        expiration_ratio: float = 0.75,
        *,
        now: Optional[float] = None,
    ) -> "_AuthToken":
        if now is None:
            now = time.time()
        expiration_time = now + expires_in * expiration_ratio
        return cls(
            token=token,
            expiration_time=expiration_time,
            refresh_token=refresh_token,
        )

    @classmethod
    def create_non_expiring(cls, token: str) -> "_AuthToken":
        # NOTE: for backward compatibility we assume that manually set token
        # expires in 3 years.
        expires_in = 60 * 60 * 24 * 365 * 3  # 3 years
        return cls.create(token, expires_in=expires_in, refresh_token="")


class AuthTokenClient:
    def __init__(
        self, session: aiohttp.ClientSession, url: URL, client_id: str
    ) -> None:
        self._url = url
        self._client_id = client_id

        self._client = session

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> "AuthTokenClient":
        return self

    async def __aexit__(self, *_: Sequence[Any]) -> None:
        await self.close()

    async def request(self, code: AuthCode) -> _AuthToken:
        payload = dict(
            grant_type="authorization_code",
            code_verifier=code.verifier,
            code=await code.wait(),
            client_id=self._client_id,
            redirect_uri=str(code.callback_url),
        )
        async with self._client.post(
            self._url,
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
            },
            data=urlencode(payload),
        ) as resp:
            try:
                resp.raise_for_status()
            except ClientResponseError as exc:
                raise AuthError("failed to get an access token.") from exc
            resp_payload = await resp.json()
            return _AuthToken.create(
                token=resp_payload["access_token"],
                expires_in=resp_payload["expires_in"],
                refresh_token=resp_payload["refresh_token"],
            )

    async def refresh(self, token: _AuthToken) -> _AuthToken:
        payload = dict(
            grant_type="refresh_token",
            refresh_token=token.refresh_token,
            client_id=self._client_id,
        )
        async with self._client.post(
            self._url,
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
            },
            data=urlencode(payload),
        ) as resp:
            try:
                resp.raise_for_status()
            except ClientResponseError as exc:
                raise AuthError("failed to get an access token.") from exc
            resp_payload = await resp.json()
            return _AuthToken.create(
                token=resp_payload["access_token"],
                expires_in=resp_payload["expires_in"],
                refresh_token=token.refresh_token,
            )


@dataclass(frozen=True)
class _AuthConfig:
    auth_url: URL
    token_url: URL
    logout_url: URL

    client_id: str
    audience: str

    headless_callback_url: URL

    callback_urls: Sequence[URL] = (
        URL("http://127.0.0.1:54540"),
        URL("http://127.0.0.1:54541"),
        URL("http://127.0.0.1:54542"),
    )

    success_redirect_url: Optional[URL] = None

    @property
    def callback_host(self) -> str:
        return cast(str, self.callback_urls[0].host)

    @property
    def callback_ports(self) -> List[int]:
        return [cast(int, url.port) for url in self.callback_urls]

    @classmethod
    def create(
        cls,
        auth_url: URL,
        token_url: URL,
        logout_url: URL,
        client_id: str,
        audience: str,
        headless_callback_url: URL,
        success_redirect_url: Optional[URL] = None,
        callback_urls: Optional[Sequence[URL]] = None,
    ) -> "_AuthConfig":
        return cls(
            auth_url=auth_url,
            token_url=token_url,
            logout_url=logout_url,
            client_id=client_id,
            audience=audience,
            headless_callback_url=headless_callback_url,
            success_redirect_url=success_redirect_url,
            callback_urls=callback_urls or cls.callback_urls,
        )


class BaseNegotiator(abc.ABC):
    def __init__(self, session: aiohttp.ClientSession, config: _AuthConfig) -> None:
        self._config = config
        self._session = session

    @abc.abstractmethod
    async def get_code(self) -> AuthCode:
        pass

    async def get_token(self) -> _AuthToken:
        async with AuthTokenClient(
            self._session, url=self._config.token_url, client_id=self._config.client_id
        ) as token_client:
            code = await self.get_code()
            return await token_client.request(code)


class AuthNegotiator(BaseNegotiator):
    def __init__(
        self,
        session: aiohttp.ClientSession,
        config: _AuthConfig,
        show_browser_cb: Callable[[URL], Awaitable[None]],
    ) -> None:
        super().__init__(session, config)
        self._show_browser_cb = show_browser_cb

    async def get_code(self) -> AuthCode:
        code = AuthCode()
        app = create_auth_code_app(code, redirect_url=self._config.success_redirect_url)

        async with create_app_server(
            app, host=self._config.callback_host, ports=self._config.callback_ports
        ) as url:
            code.callback_url = url
            code_callback_client = WebBrowserAuthCodeCallbackClient(
                url=self._config.auth_url,
                client_id=self._config.client_id,
                audience=self._config.audience,
                show_browser_cb=self._show_browser_cb,
            )
            return await code_callback_client.request(code)


class HeadlessNegotiator(BaseNegotiator):
    def __init__(
        self,
        session: aiohttp.ClientSession,
        config: _AuthConfig,
        get_auth_code_cb: Callable[[URL], Awaitable[str]],
    ) -> None:
        super().__init__(session, config)
        self._get_auth_code_cb = get_auth_code_cb

    async def get_code(self) -> AuthCode:
        code = AuthCode()
        code.callback_url = self._config.headless_callback_url

        code_callback_client = HeadlessAuthCodeCallbackClient(
            url=self._config.auth_url,
            client_id=self._config.client_id,
            audience=self._config.audience,
            get_auth_code_cb=self._get_auth_code_cb,
        )
        return await code_callback_client.request(code)


async def logout_from_browser(
    config: _AuthConfig, show_browser_cb: Callable[[URL], Awaitable[None]]
) -> None:
    logout_url = config.logout_url.update_query(client_id=config.client_id)
    await show_browser_cb(logout_url)
