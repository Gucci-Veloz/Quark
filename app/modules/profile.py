from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.schemas import ProfileCreate, ProfileOut, ProfileUpdate
from app.sql import Profile, get_session, utcnow
from app.utils.auth import Principal, require_scope

router = APIRouter(
    prefix="/profile",
    tags=["profile"],
    responses={404: {"description": "No encontrado"}},
)


def _get(session: Session, tenant_id: str, key: str) -> Profile:
    row = session.scalar(select(Profile).where(Profile.tenant_id == tenant_id, Profile.key == key))
    if row is None:
        raise HTTPException(status_code=404, detail="Entrada de perfil no encontrada")
    return row


@router.get("", response_model=List[ProfileOut])
@router.get("/", response_model=List[ProfileOut], include_in_schema=False)
def list_profile(principal: Principal = Depends(require_scope("read")), session: Session = Depends(get_session)):
    rows = session.scalars(select(Profile).where(Profile.tenant_id == principal.tenant_id).order_by(Profile.key))
    return list(rows)


@router.get("/{key}", response_model=ProfileOut)
def get_profile(key: str, principal: Principal = Depends(require_scope("read")),
                session: Session = Depends(get_session)):
    return _get(session, principal.tenant_id, key)


@router.post("", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ProfileOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_profile(body: ProfileCreate, principal: Principal = Depends(require_scope("write")),
                   session: Session = Depends(get_session)):
    exists = session.scalar(select(Profile.id).where(Profile.tenant_id == principal.tenant_id, Profile.key == body.key))
    if exists is not None:
        raise HTTPException(status_code=409, detail="La clave ya existe; usa PUT")
    row = Profile(tenant_id=principal.tenant_id, key=body.key, value=body.value, updated_at=utcnow())
    session.add(row)
    session.commit()
    return row


@router.put("/{key}", response_model=ProfileOut)
def update_profile(key: str, body: ProfileUpdate, principal: Principal = Depends(require_scope("write")),
                   session: Session = Depends(get_session)):
    row = _get(session, principal.tenant_id, key)
    row.value = body.value
    row.updated_at = utcnow()
    session.commit()
    return row


@router.delete("/{key}")
def delete_profile(key: str, principal: Principal = Depends(require_scope("write")),
                   session: Session = Depends(get_session)):
    row = _get(session, principal.tenant_id, key)
    session.delete(row)
    session.commit()
    return {"message": "Entrada de perfil eliminada"}
