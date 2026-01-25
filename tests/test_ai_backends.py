import pytest

from ai.backends import InvalidTransformationResponse, _parse_transformation_response


def test_parse_transformation_response_valid():
    resp = _parse_transformation_response('{"text": "ok", "code": "df.head()"}')
    assert resp == {"text": "ok", "code": "df.head()"}


def test_parse_transformation_response_invalid_schema():
    with pytest.raises(InvalidTransformationResponse):
        _parse_transformation_response('{"text": 123, "code": ""}')


def test_parse_transformation_response_non_json():
    with pytest.raises(InvalidTransformationResponse):
        _parse_transformation_response('not json')
