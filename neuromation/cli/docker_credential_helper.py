import sys
from json import dumps

from neuromation.api import get

from .asyncio_utils import run
from .const import EX_UNAVAILABLE, EX_USAGE


def error(message: str, exit_code: int) -> None:
    print(message)
    exit(exit_code)


async def async_main(action: str) -> None:
    if action == "store":
        error("Please use `neuro login` instead `docker login ...`", EX_UNAVAILABLE)
    elif action == "erase":
        print("Please use `neuro logout` instead `docker logout ...`", EX_UNAVAILABLE)
    else:
        registry = sys.stdin.readline().strip()
        try:
            async with get() as client:
                config = client.config
                neuro_registry = config.registry_url.host
                if registry != neuro_registry:
                    print(
                        f"Unknown registry {registry}. "
                        f"neuro configured with {neuro_registry}.",
                        file=sys.stderr,
                    )
                    payload = {"Username": "invalid", "Secret": "invalid"}
                else:
                    token = await config.token()
                    payload = {"Username": "token", "Secret": token}
        except Exception:
            print(
                f"Could not resolve correct credentials for {registry}. "
                f"Please re-login using `neuro login` or switch to related cluster.",
                file=sys.stderr,
            )
            payload = {"Username": "invalid", "Secret": "invalid"}
        print(dumps(payload))


def main() -> None:
    if len(sys.argv) == 1 or sys.argv[1] not in ["store", "get", "erase"]:
        error(
            "Neuro Platform docker credential helper.\n:Service tool, not for use",
            EX_USAGE,
        )
    action = sys.argv[1]
    run(async_main(action))
