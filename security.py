"""Password hashing and token validation, independent of HTTP."""
from datetime import datetime, timedelta, timezone
import re

import jwt
from pwdlib import PasswordHash

from config import settings

ALGORITHM = "HS256"
ISSUER = "course-catalog-api"
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("not-a-real-account-password")


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": str(user_id), "iss": ISSUER, "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }, settings.secret_key, algorithm=ALGORITHM)


def read_access_token(token: str) -> int:
    claims = jwt.decode(
        token, settings.secret_key, algorithms=[ALGORITHM], issuer=ISSUER,
        options={"require": ["exp", "sub", "iss", "iat"]},
    )
    subject = claims["sub"]
    # Prevent malformed signed subjects from reaching PostgreSQL as an invalid bigint.
    if not isinstance(subject, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", subject):
        raise jwt.InvalidTokenError("sub is not a user id")
    user_id = int(subject)
    if user_id > 2**63 - 1:
        raise jwt.InvalidTokenError("sub is outside bigint range")
    return user_id
