from unittest.mock import patch
import os

from src.bitly.config import Settings


def test_settings_is_pydantic_settings() -> None:
    s = Settings(_env_file='')
    assert hasattr(s, 'database_url')
    assert hasattr(s, 'redis_url')
    assert hasattr(s, 'rate_limit_requests')
    assert hasattr(s, 'rate_limit_window_s')
    assert hasattr(s, 'app_port')
    assert hasattr(s, 'app_host')


def test_settings_defaults_with_clean_env() -> None:
    keys = ['DATABASE_URL', 'REDIS_URL', 'RATE_LIMIT_REQUESTS',
            'RATE_LIMIT_WINDOW_S', 'APP_PORT', 'APP_HOST']
    clean = {k: v for k, v in os.environ.items() if k not in keys}
    with patch.dict(os.environ, clean, clear=True):
        s = Settings(_env_file='')
        assert isinstance(s.database_url, str)
        assert isinstance(s.redis_url, str)
        assert s.rate_limit_requests == 10
        assert s.rate_limit_window_s == 1
        assert s.app_port == 8000
        assert s.app_host == '0.0.0.0'
