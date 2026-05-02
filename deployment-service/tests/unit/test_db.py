import pytest

from deployment_service.db import _decode_config


def test_decode_config_accepts_dict():
    assert _decode_config({"username": "mldlc-user"}) == {"username": "mldlc-user"}


def test_decode_config_accepts_json_string():
    assert _decode_config('{"username": "mldlc-user"}') == {"username": "mldlc-user"}


def test_decode_config_rejects_invalid_json_string():
    with pytest.raises(ValueError):
        _decode_config("{not-json")
