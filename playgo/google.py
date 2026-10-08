"""Login com Google (OAuth 2.0 / OpenID Connect, fluxo de código de autorização).

Fluxo: /auth/google/iniciar → tela do Google → /auth/google/retorno?code=… → trocamos o código por um id_token direto com o
Google (servidor a servidor, por TLS) e conferimos emissor, público, validade, nonce e e-mail verificado.
Conta nova entra sem @usuario e sem aceite dos termos: o portão de `deps.py` leva a pessoa a escolher o @ e aceitar os termos.
A foto do Google NÃO é copiada (a foto de perfil é escolha da pessoa)."""

import base64
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session as SessaoORM

from . import auditoria, seguranca
from .config import settings
from .erros import ErroNegocio
from .models import Usuario

AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
EMISSORES = ("https://accounts.google.com", "accounts.google.com")


def _http() -> httpx.Client:
    """Os testes substituem esta função por um transporte simulado."""
    return httpx.Client(timeout=15)


def configurado() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def url_autorizacao(redirect_uri: str, state: str, nonce: str) -> str:
    return AUTORIZAR + "?" + urlencode({
        "client_id": settings.google_client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": "openid email profile",
        "state": state, "nonce": nonce, "prompt": "select_account",
    })


def novo_estado() -> tuple[str, str]:
    return secrets.token_urlsafe(24), secrets.token_urlsafe(24)


def _claims(id_token: str) -> dict:
    try:
        corpo = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)))
    except (IndexError, ValueError):
        raise ErroNegocio("Resposta inválida do Google. Tente de novo.") from None


def trocar_codigo(codigo: str, redirect_uri: str, nonce: str) -> dict:
    """Troca o código pelo id_token e devolve os dados da conta Google já conferidos."""
    if not configurado():
        raise ErroNegocio("O login com Google ainda não está ativo neste ambiente.")
    try:
        with _http() as c:
            r = c.post(TOKEN, data={"code": codigo, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret, "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
    except httpx.HTTPError:
        raise ErroNegocio("Não foi possível falar com o Google agora. Tente de novo em instantes.") from None
    if r.status_code != 200 or "id_token" not in r.json():
        raise ErroNegocio("O Google recusou o login. Tente de novo.")
    d = _claims(r.json()["id_token"])
    if d.get("iss") not in EMISSORES or d.get("aud") != settings.google_client_id or int(d.get("exp", 0)) < time.time():
        raise ErroNegocio("Resposta do Google inválida ou vencida. Tente de novo.")
    if not secrets.compare_digest(str(d.get("nonce", "")), nonce):
        raise ErroNegocio("Não foi possível confirmar o login. Tente de novo.")
    if not d.get("sub") or not d.get("email") or d.get("email_verified") not in (True, "true"):
        raise ErroNegocio("Sua conta Google precisa ter um e-mail verificado.")
    return d


def entrar_ou_criar(s: SessaoORM, d: dict) -> Usuario:
    """Acha a conta pelo id Google; senão pelo e-mail (verificado) e vincula; senão cria uma nova (pendente de @ e termos)."""
    sub, email = str(d["sub"]), str(d["email"]).strip().lower()
    u = s.scalar(select(Usuario).where(Usuario.google_sub == sub))
    if u is None:
        u = s.scalar(select(Usuario).where(Usuario.email == email))
        if u is not None:
            if u.google_sub and u.google_sub != sub:
                raise ErroNegocio("Este e-mail já está ligado a outra conta Google.")
            u.google_sub = sub
            auditoria.registrar(s, u.id, "google_vinculado", "usuario", u.id)
    if u is None:
        primeiro = not s.scalar(select(func.count()).select_from(Usuario))
        nome = (d.get("name") or email.split("@")[0]).strip()[:200]
        u = Usuario(nome=nome, email=email, senha_hash=seguranca.gerar_hash(secrets.token_urlsafe(32)), google_sub=sub, admin=primeiro)
        s.add(u)
        s.flush()
        auditoria.registrar(s, u.id, "cadastro_google", "usuario", u.id)
    if not u.ativo:
        raise ErroNegocio("Esta conta está desativada.")
    auditoria.registrar(s, u.id, "login_google", "usuario", u.id)
    s.commit()
    return u
