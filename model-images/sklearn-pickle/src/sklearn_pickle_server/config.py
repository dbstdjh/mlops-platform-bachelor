from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

InputMode = Literal["auto", "raw", "array", "dataframe"]
PredictMethod = Literal["predict", "predict_proba", "decision_function", "transform", "call"]

INPUT_MODES: set[str] = {"auto", "raw", "array", "dataframe"}
PREDICT_METHODS: set[str] = {"predict", "predict_proba", "decision_function", "transform", "call"}


@dataclass(frozen=True)
class Settings:
    model_path: Path = Path("/models/model.pkl")
    input_key: str | None = None
    input_mode: InputMode = "auto"
    predict_method: PredictMethod = "predict"
    response_key: str = "predictions"

    @classmethod
    def from_env(cls) -> "Settings":
        input_key = _clean_optional(os.getenv("MLDLC_INPUT_KEY"))
        input_mode = _validated_env(
            "MLDLC_INPUT_MODE",
            default="auto",
            allowed=INPUT_MODES,
        )
        predict_method = _validated_env(
            "MLDLC_PREDICT_METHOD",
            default="predict",
            allowed=PREDICT_METHODS,
        )
        response_key = os.getenv("MLDLC_RESPONSE_KEY", "predictions").strip() or "predictions"
        return cls(
            model_path=Path(os.getenv("MODEL_PATH", "/models/model.pkl")),
            input_key=input_key,
            input_mode=input_mode,  # type: ignore[arg-type]
            predict_method=predict_method,  # type: ignore[arg-type]
            response_key=response_key,
        )


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _validated_env(name: str, *, default: str, allowed: set[str]) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {allowed_values}")
    return value
