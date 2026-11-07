"""CLI de Quark. Uso: python -m app.cli bootstrap [--rotate-key] [--reset-admin-password]  (specs §4.2).

La API key en claro se imprime SOLO en stdout y solo en la ejecución que la crea.
Los mensajes informativos van a stderr con prefijo [bootstrap]. Nunca se imprime el password.
"""
import argparse
import os
import secrets
import sys
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import inspect, select, update

DEFAULT_TENANT = "default"
KEY_SCOPES = "read,write"
ADMIN_SCOPES = "read,write,admin"


def log(msg: str) -> None:
    print(f"[bootstrap] {msg}", file=sys.stderr)


@dataclass
class BootstrapResult:
    new_key: Optional[str]
    admin_created: bool
    admin_password_reset: bool
    keys_rotated: int


def run_bootstrap(session, admin_username: str, admin_password: str,
                  rotate_key: bool = False, reset_admin_password: bool = False) -> BootstrapResult:
    """Todo en una sola transacción: si algo falla se hace rollback sin escrituras parciales."""
    from app.sql import ApiKey, User
    from app.utils.auth import get_password_hash, hash_api_key

    new_key = None
    admin_created = pw_reset = False
    rotated = 0
    with session.begin():
        admin = session.scalar(select(User).where(User.username == admin_username))
        if admin is None:
            session.add(User(username=admin_username, hashed_password=get_password_hash(admin_password),
                             scopes=ADMIN_SCOPES, is_active=True))
            admin_created = True
        elif reset_admin_password:
            admin.hashed_password = get_password_hash(admin_password)
            pw_reset = True

        active = ApiKey.tenant_id == DEFAULT_TENANT, ApiKey.is_active.is_(True)
        has_active = session.scalar(select(ApiKey.id).where(*active).limit(1)) is not None
        if rotate_key and has_active:
            rotated = session.execute(update(ApiKey).where(*active).values(is_active=False)).rowcount
            has_active = False
        if not has_active:
            new_key = "qk_" + secrets.token_urlsafe(32)
            session.add(ApiKey(key_hash=hash_api_key(new_key), tenant_id=DEFAULT_TENANT,
                               scopes=KEY_SCOPES, is_active=True))
    return BootstrapResult(new_key, admin_created, pw_reset, rotated)


def cmd_bootstrap(args) -> int:
    import app.config  # noqa: F401  (carga .env)

    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        log("error: falta ADMIN_PASSWORD")
        return 2
    if not os.environ.get("DATABASE_URL"):
        log("error: falta DATABASE_URL")
        return 2
    admin_username = os.environ.get("ADMIN_USERNAME") or "admin"

    try:
        from app.sql import SessionLocal, engine

        tables = set(inspect(engine).get_table_names())
        if not {"users", "api_keys"} <= tables:
            log("error: tablas ausentes; ejecuta 'alembic upgrade head' primero")
            return 2
        with SessionLocal() as session:
            res = run_bootstrap(session, admin_username, admin_password,
                                args.rotate_key, args.reset_admin_password)
    except Exception as exc:  # rollback ya hecho por session.begin()
        log(f"error: {type(exc).__name__}; no se realizaron escrituras")
        return 1

    if res.admin_created:
        log(f"admin '{admin_username}' creado")
    if res.admin_password_reset:
        log(f"password de '{admin_username}' actualizado")
    if res.keys_rotated:
        log(f"{res.keys_rotated} key(s) anterior(es) desactivada(s)")
    if res.new_key:
        log("API key creada; se muestra una sola vez en stdout y no se puede recuperar")
        sys.stdout.write(res.new_key + "\n")
        sys.stdout.flush()
    if not (res.admin_created or res.admin_password_reset or res.new_key):
        log("sin cambios (ya inicializado)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("bootstrap", help="crea admin inicial y primera API key (idempotente)")
    b.add_argument("--rotate-key", action="store_true", help="desactiva las keys activas de 'default' y emite una nueva")
    b.add_argument("--reset-admin-password", action="store_true", help="re-hashea ADMIN_PASSWORD en el admin existente")
    args = parser.parse_args(argv)
    return cmd_bootstrap(args)


if __name__ == "__main__":
    sys.exit(main())
