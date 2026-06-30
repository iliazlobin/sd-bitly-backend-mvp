from fastapi import FastAPI

from src.bitly.main import create_app


def test_create_app_returns_fastapi() -> None:
    """Verify create_app() returns a FastAPI instance."""
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "Bitly URL Shortener"
    assert app.version == "0.1.0"


def test_healthz_route_exists() -> None:
    """Verify /healthz route is registered."""
    app = create_app()
    routes = {}
    for route in app.routes:
        if hasattr(route, "path"):
            routes[route.path] = route
    assert "/healthz" in routes
