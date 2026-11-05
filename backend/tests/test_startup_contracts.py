from uuid import UUID

from sqlalchemy.orm import configure_mappers

from app.core.security import create_refresh_token, decode_token
from app import models  # noqa: F401


def test_application_imports_all_routes():
    from app.main import app
    assert "/api/v1/auth/login" in {route.path for route in app.routes}


def test_all_orm_relationships_can_be_configured():
    configure_mappers()


def test_refresh_token_identifier_matches_database_uuid_column():
    first = decode_token(create_refresh_token(1, "demo"))
    second = decode_token(create_refresh_token(1, "demo"))
    assert str(UUID(first["jti"])) == first["jti"]
    assert first["jti"] != second["jti"]
    assert first["typ"] == "refresh"
