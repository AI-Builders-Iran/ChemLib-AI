from typing import Any

from pydantic import BaseModel


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic v2 model to JSON-compatible Python values."""
    if not isinstance(model, BaseModel):
        raise TypeError("model must be a Pydantic BaseModel instance.")
    return model.model_dump(mode="json")


def model_to_json(model: BaseModel, **kwargs: Any) -> str:
    """Serialize a Pydantic v2 model to JSON."""
    if not isinstance(model, BaseModel):
        raise TypeError("model must be a Pydantic BaseModel instance.")
    return model.model_dump_json(**kwargs)
