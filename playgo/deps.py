"""Dependências do FastAPI compartilhadas pelo site e pela API: sessão do banco e usuário atual.
O site identifica pelo cookie de sessão; o app, pelo token Bearer (ou pelo mesmo cookie, quando é a PWA).

Todo usuário passa por um portão: sem @usuario ou sem o aceite da versão vigente dos termos, só as telas de
'completar cadastro' funcionam (as dependências *_livre)."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as SessaoORM

from . import contas, seguranca
from .db import Session
from .models import Usuario


def sessao():
    with Session() as s:
        yield s


Sessao = Annotated[SessaoORM, Depends(sessao)]


class PrecisaEntrar(Exception):
    """A página exige login e não há sessão válida."""


class PrecisaCompletar(Exception):
    """Falta escolher o @usuario ou aceitar a versão atual dos termos."""

    def __init__(self, pendencia: str) -> None:
        self.pendencia = pendencia


def _por_cookie(request: Request, s: SessaoORM) -> Usuario | None:
    identificador = request.session.get("usuario_id")
    u = s.get(Usuario, identificador) if identificador else None
    return u if u is not None and u.ativo else None


def _por_token(request: Request, s: SessaoORM) -> Usuario | None:
    cabecalho = request.headers.get("authorization", "")
    if not cabecalho.lower().startswith("bearer "):
        return None
    identificador = seguranca.ler_token(cabecalho[7:].strip())
    u = s.get(Usuario, identificador) if identificador else None
    return u if u is not None and u.ativo else None


# ---- site

def usuario_web_livre(request: Request, s: Sessao) -> Usuario:
    u = _por_cookie(request, s)
    if u is None:
        request.session.clear()
        raise PrecisaEntrar
    return u


def usuario_web(request: Request, s: Sessao) -> Usuario:
    u = usuario_web_livre(request, s)
    pendencia = contas.pendencias(u)
    if pendencia:
        raise PrecisaCompletar(pendencia)
    return u


def usuario_web_opcional(request: Request, s: Sessao) -> Usuario | None:
    return _por_cookie(request, s)


# ---- API

def usuario_api_livre(request: Request, s: Sessao) -> Usuario:
    u = _por_token(request, s) or _por_cookie(request, s)
    if u is None:
        raise HTTPException(401, "Entre para continuar.")
    return u


def usuario_api(request: Request, s: Sessao) -> Usuario:
    u = usuario_api_livre(request, s)
    pendencia = contas.pendencias(u)
    if pendencia:
        mensagem = "Escolha seu nome de usuário para continuar." if pendencia == "usuario" else "Para continuar, aceite a versão atual dos Termos de Uso e da Política de Privacidade."
        raise HTTPException(403, detail={"codigo": "pendencia", "pendencia": pendencia, "mensagem": mensagem})
    return u


Atual = Annotated[Usuario, Depends(usuario_web)]
AtualLivre = Annotated[Usuario, Depends(usuario_web_livre)]
Opcional = Annotated[Usuario | None, Depends(usuario_web_opcional)]
AtualApi = Annotated[Usuario, Depends(usuario_api)]
AtualApiLivre = Annotated[Usuario, Depends(usuario_api_livre)]
