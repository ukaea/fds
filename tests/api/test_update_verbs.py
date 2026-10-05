from fastapi.routing import APIRoute

from app.main import app


def test_no_route_updates_with_put():
    """Every update applies only the fields sent, which is PATCH, not PUT."""
    put = [
        r.path
        for r in app.routes
        if isinstance(r, APIRoute) and "PUT" in (r.methods or set())
    ]

    assert put == []
