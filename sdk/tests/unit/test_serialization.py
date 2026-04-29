from __future__ import annotations

import pickle
from io import BytesIO

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from mldlc import SerializationError
from mldlc.serialization import (
    deserialize_dataset,
    infer_model_artifact_file_name,
    infer_model_artifact_file_type,
    serialize_dataset,
    serialize_model_artifact,
)


def test_dataframe_roundtrip_defaults_to_parquet():
    frame = pd.DataFrame({"feature": [1, 2], "target": [0, 1]})
    payload, file_type = serialize_dataset(frame)

    restored = deserialize_dataset(payload, file_type, as_type="auto")

    assert file_type == "parquet"
    pdt.assert_frame_equal(restored, frame)


def test_dataframe_can_roundtrip_as_csv():
    frame = pd.DataFrame({"feature": [1, 2], "target": [0, 1]})
    payload, file_type = serialize_dataset(frame, file_type="csv")

    restored = deserialize_dataset(payload, file_type, as_type="dataframe")

    assert file_type == "csv"
    pdt.assert_frame_equal(restored, frame)


def test_numpy_roundtrip_defaults_to_npy():
    array = np.array([[1, 2], [3, 4]])
    payload, file_type = serialize_dataset(array)

    restored = deserialize_dataset(payload, file_type, as_type="auto")

    assert file_type == "npy"
    assert np.array_equal(restored, array)


def test_bytes_dataset_requires_explicit_file_type():
    with pytest.raises(SerializationError):
        serialize_dataset(b"raw-bytes")


def test_path_dataset_infers_file_type(tmp_path):
    csv_path = tmp_path / "events.csv"
    csv_path.write_text("feature,target\n1,0\n2,1\n")

    payload, file_type = serialize_dataset(csv_path)

    assert file_type == "csv"
    assert payload.startswith(b"feature,target")


def test_unknown_dataset_defaults_to_path_or_bytes(tmp_path):
    payload = b"opaque"

    restored_bytes = deserialize_dataset(payload, "bin", as_type="auto")
    restored_path = deserialize_dataset(payload, "bin", as_type="auto", destination=tmp_path / "opaque.bin")

    assert restored_bytes == payload
    assert restored_path.read_bytes() == payload


def test_file_like_dataset_needs_file_type():
    with pytest.raises(SerializationError):
        serialize_dataset(BytesIO(b"csv,data"))


def test_model_artifact_pickle_serialization_roundtrip():
    payload = serialize_model_artifact({"model": "baseline"}, serializer="pickle")

    assert pickle.loads(payload) == {"model": "baseline"}


def test_infer_model_artifact_file_name_preserves_paths_and_defaults():
    assert infer_model_artifact_file_name("/tmp/crappy-shit.pkl", name="classifier", version="1.0") == "crappy-shit.pkl"
    assert (
        infer_model_artifact_file_name({"weights": [1, 2, 3]}, name="classifier", version="1.0", serializer="pickle")
        == "classifier-v1.0.pkl"
    )
    assert infer_model_artifact_file_name(b"raw", name="classifier", version="1.0") == "classifier-v1.0.bin"


def test_infer_model_artifact_file_type_maps_pickle_and_unknown_names():
    assert infer_model_artifact_file_type("/tmp/crappy-shit.pkl", name="classifier", version="1.0") == "pickle"
    assert (
        infer_model_artifact_file_type(
            {"weights": [1, 2, 3]},
            name="classifier",
            version="1.0",
            serializer="pickle",
        )
        == "pickle"
    )
    assert infer_model_artifact_file_type(b"raw", name="classifier", version="1.0") == "undefined"
