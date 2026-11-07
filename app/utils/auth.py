import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Literal, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, AUTH_ALGORITHM, AUTH_SECRET_KEY
from app.sql import ApiKey, User, get_session, split_scopes

DEFAULT_TENANT = "default"


class Token(BaseModel):
    access_token: str
    token_type: str


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    scopes: tuple[str, ...]
    kind: Literal["api_key", "jwt"]
    subject: str


# bcrypt para passwords (specs §4.1); la sal va incluida en el hash.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# auto_error=False: la ausencia de un mecanismo no corta antes de probar el otro.
security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(key: str) -> str:
    """SHA-256 hex (64 chars) de la key completa (specs §4.1)."""
    return hashlib.sha256(key.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


_DUMMY_HASH = pwd_context.hash("dummy-password-for-timing")


def authenticate_user(session: Session, username: str, password: str) -> Optional[User]:
    """Devuelve el usuario activo si las credenciales son correctas."""
    user = session.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        verify_password(password, _DUMMY_HASH)  # igualar tiempos
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Autenticación requerida",
    headers={"WWW-Authenticate": "Bearer"},
)


async def validate_access(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key: Optional[str] = Depends(api_key_header),
    session: Session = Depends(get_session),
) -> Principal:
    """Acepta X-API-Key (tabla api_keys) o Bearer JWT (usuario activo en users). 401 si ninguna es válida."""
    if api_key:
        row = session.scalar(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key(api_key), ApiKey.is_active.is_(True))
        )
        if row is not None:
            return Principal(row.tenant_id, split_scopes(row.scopes), "api_key", str(row.id))

    if credentials is not None:
        try:
            payload = jwt.decode(credentials.credentials, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
        except JWTError:
            payload = None
        username = payload.get("sub") if payload else None
        if username:
            user = session.scalar(select(User).where(User.username == username))
            if user is not None and user.is_active:
                return Principal(DEFAULT_TENANT, split_scopes(user.scopes), "jwt", user.username)

    raise _UNAUTHORIZED


def require_scope(scope: str) -> Callable:
    """Dependencia FastAPI: valida credencial y exige el scope; devuelve el Principal."""

    async def _dependency(principal: Principal = Depends(validate_access)) -> Principal:
        if scope not in principal.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso insuficiente. Se requiere: {scope}",
            )
        return principal

    return _dependency
