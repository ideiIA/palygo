"""Senhas (scrypt, só biblioteca padrão), chave de assinatura e token do app."""

import base64
import hashlib
import hmac
import os
import secrets

from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import RAIZ, settings

SENHA_MINIMA = 8
_N, _R, _P = 2**14, 8, 1


def _derivar(senha: str, sal: bytes) -> bytes:
    return hashlib.scrypt(senha.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)


def gerar_hash(senha: str) -> str:
    sal = os.urandom(16)
    return "scrypt$" + base64.b64encode(sal).decode() + "$" + base64.b64encode(_derivar(senha, sal)).decode()


def conferir(senha: str, armazenado: str) -> bool:
    try:
        _, sal, esperado = armazenado.split("$")
        return hmac.compare_digest(_derivar(senha, base64.b64decode(sal)), base64.b64decode(esperado))
    except ValueError:
        return False


def chave_sessao() -> str:
    """Chave do .env ou, na falta, uma gerada na primeira execução e guardada fora do git."""
    if settings.chave_sessao:
        return settings.chave_sessao
    arquivo = RAIZ / ".chave_sessao"
    if not arquivo.exists():
        arquivo.write_text(secrets.token_urlsafe(48), encoding="ascii")
    return arquivo.read_text(encoding="ascii").strip()


def _serializador() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(chave_sessao(), salt="playgo-token-app")


def gerar_token(usuario_id: int) -> str:
    """Token Bearer do aplicativo: o mesmo que o cookie de sessão faz para o site."""
    return _serializador().dumps(usuario_id)


def ler_token(token: str) -> int | None:
    try:
        return _serializador().loads(token, max_age=settings.dias_token_app * 86400)
    except BadSignature:
        return None
