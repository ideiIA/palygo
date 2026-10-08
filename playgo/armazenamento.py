"""Onde ficam os arquivos (fotos, vídeos, fotos de perfil).

  local     disco da máquina (`uploads/`) — desenvolvimento.
  supabase  Supabase Storage, bucket PRIVADO — produção (Vercel não tem disco persistente).

Em produção ninguém acessa o bucket direto: o servidor confere a permissão e só então redireciona para uma URL
assinada de curta duração (5 min). Escolha automática: se houver `PLAYGO_SUPABASE_URL` e `PLAYGO_SUPABASE_SERVICE_KEY`, usa o Supabase."""

import logging
from urllib.parse import quote

import httpx
from fastapi.responses import FileResponse, RedirectResponse

from .config import settings
from .erros import ErroNegocio, NaoEncontrado

log = logging.getLogger(__name__)
VALIDADE_URL_ASSINADA_S = 300


def _http() -> httpx.Client:
    """Cliente HTTP do Storage. Os testes substituem esta função por um transporte simulado."""
    return httpx.Client(timeout=60)


def usa_supabase() -> bool:
    if settings.armazenamento == "local":
        return False
    return bool(settings.supabase_url and settings.supabase_service_key)


def _cabecalhos(extra: dict | None = None) -> dict:
    chave = settings.supabase_service_key
    return {"Authorization": f"Bearer {chave}", "apikey": chave, **(extra or {})}


def _base() -> str:
    return f"{settings.supabase_url.rstrip('/')}/storage/v1"


def _caminho_local(rel: str):
    from . import midia

    return midia.caminho(rel)


def salvar(rel: str, dados: bytes, mime: str) -> None:
    if not usa_supabase():
        alvo = settings.pasta_uploads / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(dados)
        return
    try:
        with _http() as c:
            r = c.post(f"{_base()}/object/{settings.supabase_bucket}/{quote(rel)}", headers=_cabecalhos({"Content-Type": mime, "x-upsert": "true"}), content=dados)
            r.raise_for_status()
    except httpx.HTTPError as e:
        log.error("Storage: falha ao salvar %s: %s", rel, e)
        raise ErroNegocio("Não foi possível guardar o arquivo agora. Tente de novo em instantes.") from None


def ler(rel: str) -> bytes:
    if not usa_supabase():
        return _caminho_local(rel).read_bytes()
    with _http() as c:
        r = c.get(f"{_base()}/object/authenticated/{settings.supabase_bucket}/{quote(rel)}", headers=_cabecalhos())
        r.raise_for_status()
        return r.content


def remover(rel: str | None) -> None:
    if not rel:
        return
    if not usa_supabase():
        try:
            _caminho_local(rel).unlink(missing_ok=True)
        except (ErroNegocio, OSError):
            pass
        return
    try:
        with _http() as c:
            c.request("DELETE", f"{_base()}/object/{settings.supabase_bucket}", headers=_cabecalhos(), json={"prefixes": [rel]}).raise_for_status()
    except httpx.HTTPError as e:
        log.warning("Storage: falha ao remover %s: %s", rel, e)


def existe_local(rel: str) -> bool:
    return _caminho_local(rel).exists()


def servir(rel: str, mime: str, cache: str):
    """Resposta HTTP do arquivo. Local: o próprio arquivo. Supabase: redireciona para a URL assinada (a permissão já foi conferida)."""
    cab = {"Cache-Control": cache, "X-Content-Type-Options": "nosniff"}
    if not usa_supabase():
        if not existe_local(rel):
            raise NaoEncontrado("Arquivo não encontrado.")
        return FileResponse(_caminho_local(rel), media_type=mime, headers=cab)
    try:
        with _http() as c:
            r = c.post(f"{_base()}/object/sign/{settings.supabase_bucket}/{quote(rel)}", headers=_cabecalhos(), json={"expiresIn": VALIDADE_URL_ASSINADA_S})
            r.raise_for_status()
            assinada = r.json()["signedURL"]
    except (httpx.HTTPError, KeyError, ValueError):
        raise NaoEncontrado("Arquivo não encontrado.") from None
    return RedirectResponse(f"{_base()}{assinada}", status_code=302, headers={"Cache-Control": "private, max-age=240", "X-Content-Type-Options": "nosniff"})


def garantir_bucket() -> str:
    """Cria o bucket privado, se ainda não existir (usado por `python -m playgo supabase`)."""
    if not usa_supabase():
        return "Armazenamento local: nada a criar."
    with _http() as c:
        r = c.post(f"{_base()}/bucket", headers=_cabecalhos(), json={"id": settings.supabase_bucket, "name": settings.supabase_bucket, "public": False})
        if r.status_code in (200, 201):
            return f"Bucket privado '{settings.supabase_bucket}' criado."
        if r.status_code == 409 or "already exists" in r.text.lower() or "Duplicate" in r.text:
            return f"Bucket '{settings.supabase_bucket}' já existe."
        r.raise_for_status()
    return ""
