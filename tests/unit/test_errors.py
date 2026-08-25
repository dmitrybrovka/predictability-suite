from predictability.core.errors import (
    AdapterError,
    EmptyTrainSetError,
    ExtraMissingError,
    NoActiveModelError,
    UsageError,
)


def test_exit_codes() -> None:
    assert UsageError("x").exit_code == 2
    assert AdapterError("x").exit_code == 3
    assert EmptyTrainSetError("x").exit_code == 4
    assert NoActiveModelError("x").exit_code == 5
    assert ExtraMissingError("x").exit_code == 2
    assert str(UsageError("bad")) == "bad"
