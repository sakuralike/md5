from __future__ import annotations

from sqlalchemy import inspect

from password_detective.db.models import (
    OAuthAuthorizationCode,
    OAuthTokenSession,
    ThirdPartyApp,
    ThirdPartyAppRedirectUri,
)


def test_third_party_app_tables_have_future_review_fields(client) -> None:
    with client.app.state.database.session_factory() as db:
        inspector = inspect(db.get_bind())
        tables = set(inspector.get_table_names())
        assert {
            "third_party_apps",
            "third_party_app_redirect_uris",
            "third_party_authorizations",
            "third_party_authorization_codes",
            "third_party_token_sessions",
        }.issubset(tables)
        columns = {column["name"] for column in inspector.get_columns("third_party_apps")}
        assert {
            "application_source",
            "status",
            "trusted_verification_enabled",
            "reviewer_user_id",
        } <= columns


def test_third_party_uniqueness_and_token_family_fields(client) -> None:
    with client.app.state.database.session_factory() as db:
        inspector = inspect(db.get_bind())
        app_indexes = inspector.get_indexes("third_party_apps")
        app_unique_constraints = inspector.get_unique_constraints("third_party_apps")
        assert any(
            index.get("unique") and index.get("column_names") == ["client_id"]
            for index in app_indexes
        ) or any(
            constraint.get("column_names") == ["client_id"] for constraint in app_unique_constraints
        )

        redirect_constraints = inspector.get_unique_constraints("third_party_app_redirect_uris")
        assert any(
            constraint.get("column_names") == ["app_id", "redirect_uri"]
            for constraint in redirect_constraints
        )

        code_indexes = inspector.get_indexes("third_party_authorization_codes")
        code_constraints = inspector.get_unique_constraints("third_party_authorization_codes")
        assert any(
            index.get("unique") and index.get("column_names") == ["code_hash"]
            for index in code_indexes
        ) or any(constraint.get("column_names") == ["code_hash"] for constraint in code_constraints)

        token_columns = {
            column["name"] for column in inspector.get_columns("third_party_token_sessions")
        }
        assert {"token_family_id", "refresh_token_hash", "refresh_rotated_at"} <= token_columns

        assert ThirdPartyApp.__tablename__ == "third_party_apps"
        assert ThirdPartyAppRedirectUri.__tablename__ == "third_party_app_redirect_uris"
        assert OAuthAuthorizationCode.__tablename__ == "third_party_authorization_codes"
        assert OAuthTokenSession.__tablename__ == "third_party_token_sessions"
