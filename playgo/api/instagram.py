"""API do Instagram do PlayGo: estado da conexão e fila de aprovação (equipe de moderação)."""

from fastapi import APIRouter
from pydantic import BaseModel

from .. import instagram
from ..deps import AtualApi, Sessao

router = APIRouter(prefix="/api/v1/instagram")


class RecusaIn(BaseModel):
    motivo: str | None = None


@router.get("/estado")
def estado(u: AtualApi, s: Sessao):
    if not u.equipe_moderacao:
        return {"ativo": instagram.ativo(s)}
    return {"ativo": instagram.ativo(s)} | instagram.estado(s)


@router.get("/fila")
def fila(u: AtualApi, s: Sessao):
    return instagram.fila(s, u)


@router.post("/{publicacao_id}/aprovar")
def aprovar(publicacao_id: int, u: AtualApi, s: Sessao):
    return instagram.aprovar(s, u, publicacao_id)


@router.post("/{publicacao_id}/recusar")
def recusar(publicacao_id: int, corpo: RecusaIn, u: AtualApi, s: Sessao):
    return instagram.recusar(s, u, publicacao_id, corpo.motivo)


@router.post("/desconectar")
def desconectar(u: AtualApi, s: Sessao):
    return instagram.desconectar(s, u)
