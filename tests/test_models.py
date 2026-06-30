from src.bitly.models.url import URL


def test_url_model_columns() -> None:
    """Verify the URL model has the expected columns and table name."""
    assert URL.__tablename__ == "urls"

    columns = {c.name: c for c in URL.__table__.columns}

    assert "id" in columns
    assert "short_code" in columns
    assert "long_url" in columns
    assert "clicks" in columns
    assert "created_at" in columns
    assert "expires_at" in columns

    # short_code should be unique
    assert columns["short_code"].unique is True
    # clicks should default to 0
    assert columns["clicks"].default is not None
    assert columns["clicks"].default.arg == 0


def test_url_model_indexes() -> None:
    """Verify the URL model has the expected index."""
    indexes = {idx.name: idx for idx in URL.__table__.indexes}
    assert "idx_urls_short_code" in indexes
