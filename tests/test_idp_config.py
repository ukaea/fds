import pytest
from pydantic import ValidationError

from app.core.config import Config


def _make_config(**kwargs):
    """Build a Config instance with all required fields defaulted."""
    return Config.model_validate(kwargs)


def test_trusted_idps_duplicate_issuer_rejected():
    with pytest.raises(ValidationError, match="duplicate issuer"):
        _make_config(
            FDS_TRUSTED_IDPS=[
                {"issuer": "https://idp.example.com", "allowed_scopes": ["*"]},
                {"issuer": "https://idp.example.com", "allowed_scopes": ["read"]},
            ]
        )


def test_trusted_idps_blank_issuer_rejected():
    with pytest.raises(ValidationError, match="non-empty and not whitespace-only"):
        _make_config(
            FDS_TRUSTED_IDPS=[
                {"issuer": "   ", "allowed_scopes": ["*"]},
            ]
        )


def test_trusted_idps_empty_string_issuer_rejected():
    with pytest.raises(ValidationError, match="non-empty and not whitespace-only"):
        _make_config(
            FDS_TRUSTED_IDPS=[
                {"issuer": "", "allowed_scopes": ["*"]},
            ]
        )


def test_trusted_idps_duplicate_issuer_rejected_after_normalization():
    with pytest.raises(ValidationError, match="duplicate issuer"):
        _make_config(
            FDS_TRUSTED_IDPS=[
                {
                    "issuer": " https://idp.example.com/ ",
                    "allowed_scopes": ["*"],
                },
                {"issuer": "https://idp.example.com", "allowed_scopes": ["read"]},
            ]
        )


def test_trusted_idps_malformed_entry_rejected_at_startup():
    with pytest.raises(ValidationError):
        _make_config(
            FDS_TRUSTED_IDPS=[
                {"issuer": "https://idp-a.example.com", "allowed_scopes": ["*"]},
                object(),
            ]
        )


def test_trusted_idps_empty_list_accepted():
    cfg = _make_config(FDS_TRUSTED_IDPS=[])
    assert cfg.TRUSTED_IDPS == []


def test_trusted_idps_distinct_issuers_accepted():
    cfg = _make_config(
        FDS_TRUSTED_IDPS=[
            {"issuer": "https://idp-a.example.com", "allowed_scopes": ["*"]},
            {"issuer": "https://idp-b.example.com", "allowed_scopes": ["read"]},
        ]
    )
    assert len(cfg.TRUSTED_IDPS) == 2
