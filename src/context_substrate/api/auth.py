"""Per-consumer bearer token authentication (fail-closed)."""

from __future__ import annotations

import hmac
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


def build_auth_dependency(consumer_tokens: dict[str, str]) -> Callable[..., str]:
    """Return a FastAPI dependency that validates a bearer token and returns the consumer name."""

    def _verify_token(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),  # noqa: B008
    ) -> str:
        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
            or not credentials.credentials
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        provided = credentials.credentials
        for consumer_name, expected_token in consumer_tokens.items():
            if expected_token and hmac.compare_digest(provided, expected_token):
                return consumer_name

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _verify_token
