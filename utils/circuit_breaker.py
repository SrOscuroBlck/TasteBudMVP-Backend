import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Callable, Any

from utils.logger import setup_logger

logger = setup_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: int = 60,
        expected_exception: type = Exception
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                logger.info(
                    f"Circuit breaker {self.name} attempting reset to HALF_OPEN",
                    extra={"circuit_breaker": self.name}
                )
                self.state = CircuitState.HALF_OPEN
            else:
                logger.warning(
                    f"Circuit breaker {self.name} is OPEN, rejecting call",
                    extra={
                        "circuit_breaker": self.name,
                        "failure_count": self.failure_count
                    }
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker {self.name} is open"
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        if self.last_failure_time is None:
            return True
        
        elapsed_seconds = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed_seconds >= self.recovery_timeout_seconds
    
    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            logger.info(
                f"Circuit breaker {self.name} recovered, transitioning to CLOSED",
                extra={"circuit_breaker": self.name}
            )
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = None
    
    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.state == CircuitState.HALF_OPEN:
            logger.warning(
                f"Circuit breaker {self.name} failed during HALF_OPEN, reopening",
                extra={
                    "circuit_breaker": self.name,
                    "failure_count": self.failure_count
                }
            )
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            logger.error(
                f"Circuit breaker {self.name} threshold reached, opening circuit",
                extra={
                    "circuit_breaker": self.name,
                    "failure_count": self.failure_count,
                    "threshold": self.failure_threshold
                }
            )
            self.state = CircuitState.OPEN
    
    def reset(self):
        logger.info(
            f"Circuit breaker {self.name} manually reset",
            extra={"circuit_breaker": self.name}
        )
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
    
    def get_state(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "recovery_timeout_seconds": self.recovery_timeout_seconds
        }


openai_circuit_breaker = CircuitBreaker(
    name="openai_api",
    failure_threshold=5,
    recovery_timeout_seconds=60
)


embedding_circuit_breaker = CircuitBreaker(
    name="embedding_service",
    failure_threshold=3,
    recovery_timeout_seconds=30
)
