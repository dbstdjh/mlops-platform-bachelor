from __future__ import annotations

import io
import pickle
import tempfile
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np
import pandas as pd

from mldlc.errors import SerializationError

DatasetAsType = Literal["auto", "bytes", "path", "dataframe", "ndarray"]


def normalize_file_type(file_type: str | None) -> str | None:
    if file_type is None:
        return None
    normalized = file_type.strip().lower().lstrip(".")
    if not normalized:
        raise SerializationError("file_type must not be empty")
    return normalized


def infer_file_type_from_path(path: str | Path) -> str | None:
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix or None


def infer_file_name_from_path(path: str | Path) -> str:
    return Path(path).name


def read_file_like(file_like: BinaryIO) -> bytes:
    position = file_like.tell() if hasattr(file_like, "tell") else None
    payload = file_like.read()
    if position is not None and hasattr(file_like, "seek"):
        file_like.seek(position)
    if isinstance(payload, str):
        return payload.encode()
    return payload


def serialize_dataset(data, file_type: str | None = None) -> tuple[bytes, str]:
    normalized_type = normalize_file_type(file_type)

    if isinstance(data, pd.DataFrame):
        resolved_type = normalized_type or "parquet"
        buffer = io.BytesIO()
        if resolved_type == "parquet":
            data.to_parquet(buffer, index=False)
        elif resolved_type == "csv":
            buffer.write(data.to_csv(index=False).encode())
        else:
            raise SerializationError("DataFrame datasets only support parquet or csv output")
        return buffer.getvalue(), resolved_type

    if isinstance(data, np.ndarray):
        resolved_type = normalized_type or "npy"
        if resolved_type != "npy":
            raise SerializationError("NumPy datasets only support npy output")
        buffer = io.BytesIO()
        np.save(buffer, data, allow_pickle=False)
        return buffer.getvalue(), resolved_type

    if isinstance(data, (str, Path)):
        path = Path(data)
        resolved_type = normalized_type or infer_file_type_from_path(path)
        if resolved_type is None:
            raise SerializationError("Could not infer dataset file_type from the path")
        return path.read_bytes(), resolved_type

    if isinstance(data, bytes):
        if normalized_type is None:
            raise SerializationError("bytes datasets require an explicit file_type")
        return data, normalized_type

    if hasattr(data, "read"):
        if normalized_type is None:
            raise SerializationError("file-like datasets require an explicit file_type")
        return read_file_like(data), normalized_type

    raise SerializationError(f"Unsupported dataset type: {type(data)!r}")


def deserialize_dataset(
    payload: bytes,
    file_type: str | None,
    as_type: DatasetAsType = "auto",
    destination: str | Path | None = None,
):
    resolved_type = normalize_file_type(file_type)

    if as_type == "bytes":
        return payload

    if as_type == "path":
        return write_payload(payload, destination, resolved_type)

    if as_type == "auto":
        if resolved_type in {"csv", "parquet"}:
            as_type = "dataframe"
        elif resolved_type == "npy":
            as_type = "ndarray"
        elif destination is not None:
            return write_payload(payload, destination, resolved_type)
        else:
            return payload

    if as_type == "dataframe":
        buffer = io.BytesIO(payload)
        if resolved_type == "parquet":
            return pd.read_parquet(buffer)
        if resolved_type == "csv":
            return pd.read_csv(buffer)
        raise SerializationError("Only csv and parquet datasets can be loaded as DataFrames")

    if as_type == "ndarray":
        if resolved_type != "npy":
            raise SerializationError("Only npy datasets can be loaded as NumPy arrays")
        return np.load(io.BytesIO(payload), allow_pickle=False)

    raise SerializationError(f"Unsupported as_type: {as_type!r}")


def serialize_model_artifact(artifact, serializer: str = "auto") -> bytes:
    serializer = serializer.strip().lower()

    if isinstance(artifact, (str, Path)):
        return Path(artifact).read_bytes()

    if isinstance(artifact, bytes):
        return artifact

    if hasattr(artifact, "read"):
        return read_file_like(artifact)

    if serializer in {"auto", "pickle"}:
        return pickle.dumps(artifact)

    raise SerializationError(f"Unsupported model serializer: {serializer!r}")


def infer_model_artifact_file_name(
    artifact,
    *,
    name: str,
    version: str,
    serializer: str = "auto",
    file_name: str | None = None,
) -> str:
    if file_name is not None:
        resolved = Path(str(file_name)).name
        if not resolved:
            raise SerializationError("file_name must contain a filename")
        return resolved

    if isinstance(artifact, (str, Path)):
        return infer_file_name_from_path(artifact)

    artifact_name = getattr(artifact, "name", None)
    if isinstance(artifact_name, str):
        stripped = artifact_name.strip()
        if stripped and not (stripped.startswith("<") and stripped.endswith(">")):
            return Path(stripped).name

    normalized_serializer = serializer.strip().lower()
    if normalized_serializer in {"", "auto", "pickle"} and not isinstance(artifact, bytes) and not hasattr(artifact, "read"):
        return f"{name}-v{version}.pkl"

    return f"{name}-v{version}.bin"


def infer_model_artifact_file_type(
    artifact,
    *,
    name: str,
    version: str,
    serializer: str = "auto",
    file_name: str | None = None,
) -> str:
    resolved_name = infer_model_artifact_file_name(
        artifact,
        name=name,
        version=version,
        serializer=serializer,
        file_name=file_name,
    ).lower()
    if resolved_name.endswith(".pkl") or resolved_name.endswith(".pickle"):
        return "pickle"
    return "undefined"


def write_payload(
    payload: bytes,
    destination: str | Path | None,
    file_type: str | None,
    *,
    prefix: str = "mldlc-",
) -> Path:
    if destination is None:
        suffix = f".{file_type}" if file_type else ".bin"
        with tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=False) as handle:
            handle.write(payload)
            return Path(handle.name)

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path
