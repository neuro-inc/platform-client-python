import abc
from typing import Optional


class AbstractProgress(abc.ABC):
    @abc.abstractmethod
    def start(self, file: str, size: int) -> None:  # pragma: no cover
        pass

    @abc.abstractmethod
    def complete(self, file: str) -> None:  # pragma: no cover
        pass

    @abc.abstractmethod
    def progress(self, file: str, current: int) -> None:  # pragma: no cover
        pass


class AbstractImageProgress(abc.ABC):
    @abc.abstractmethod
    def message(self, message: str, layer_id: Optional["str"] = None) -> None:
        pass

    def close(self) -> None:
        pass
