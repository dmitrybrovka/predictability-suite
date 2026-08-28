"""Typed errors mapped to CLI exit codes."""


class PredictabilityError(Exception):
    """Base error. `exit_code` is used by the CLI."""

    exit_code: int = 1

    def __init__(self, message: str) -> None:
        """Store `message` for structured CLI JSON on stderr."""
        super().__init__(message)
        self.message = message


class UsageError(PredictabilityError):
    """Invalid arguments, unknown plugin, or factor-set mismatch (CLI exit 2)."""

    exit_code = 2


class AdapterError(PredictabilityError):
    """Tracker adapter failed (CLI exit 3)."""

    exit_code = 3


class AdapterAuthError(AdapterError):
    """Tracker authentication or authorization failed (run-level)."""


class AdapterTransientError(AdapterError):
    """Rate limit or transient tracker failure."""


class EmptyTrainSetError(PredictabilityError):
    """No completed epics with deadlines available to train (CLI exit 4)."""

    exit_code = 4


class NoActiveModelError(PredictabilityError):
    """predict ran with no active artifact (CLI exit 5)."""

    exit_code = 5


class ExtraMissingError(UsageError):
    """Optional extra (catboost/gbm) is not installed."""
