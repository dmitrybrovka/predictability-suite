"""Typed errors mapped to CLI exit codes."""


class PredictabilityError(Exception):
    """Base error. `exit_code` is used by the CLI."""

    exit_code: int = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UsageError(PredictabilityError):
    exit_code = 2


class AdapterError(PredictabilityError):
    exit_code = 3


class AdapterAuthError(AdapterError):
    """Tracker authentication/authorization failed (run-level)."""


class AdapterTransientError(AdapterError):
    """Rate limit or transient tracker failure."""


class EmptyTrainSetError(PredictabilityError):
    exit_code = 4


class NoActiveModelError(PredictabilityError):
    exit_code = 5


class ExtraMissingError(UsageError):
    """Optional extra (catboost/gbm) is not installed."""
