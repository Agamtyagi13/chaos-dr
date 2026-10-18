from abc import ABC, abstractmethod
from typing import List

from ..catalog import FaultSpec, ACTION_COST
from ..models import Probe


class Backend(ABC):
    """Where faults are injected and recoveries executed."""
    name = "base"

    @abstractmethod
    def now(self) -> float: ...
    @abstractmethod
    def tick(self, dt: float = 1.0) -> None: ...
    @abstractmethod
    def probe(self) -> Probe: ...
    @abstractmethod
    def inject(self, spec: FaultSpec) -> None: ...
    @abstractmethod
    def cleanup(self) -> None: ...
    @abstractmethod
    def signals(self) -> List[str]: ...
    @abstractmethod
    def start_action(self, action: str) -> None: ...
    @abstractmethod
    def finish_action(self, action: str) -> bool: ...

    def action_duration(self, action: str) -> float:
        return ACTION_COST.get(action, 20)

    def data_loss(self) -> int:
        return 0
