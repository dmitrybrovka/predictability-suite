"""Public library callables expose Google-style docstrings for mkdocstrings."""

from pydantic import BaseModel

from predictability import __all__, evaluate, ingest, predict, train
from predictability.core import schema


def _public_schema_models() -> list[type[BaseModel]]:
    models: list[type[BaseModel]] = []
    for name in dir(schema):
        if name.startswith("_"):
            continue
        obj = getattr(schema, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
            models.append(obj)
    return models


def test_library_exports_have_docstrings() -> None:
    for fn in (train, predict, ingest, evaluate):
        assert fn.__doc__, f"{fn.__name__} needs a Google-style docstring"


def test_package_all_matches_documented_surface() -> None:
    assert "train" in __all__
    assert "predict" in __all__
    assert "ingest" in __all__
    assert "evaluate" in __all__


def test_public_models_field_descriptions() -> None:
    found = _public_schema_models()
    assert found, "expected public Pydantic models in schema"
    for model in found:
        for name, field in model.model_fields.items():
            assert field.description, f"{model.__name__}.{name} needs Field(description=...)"
