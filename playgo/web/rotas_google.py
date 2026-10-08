"""Rotas do login com Google. Servem o site e o app (PWA): o app recebe o token no fragmento da URL (nunca vai para logs)."""

from fastapi import Request
from fastapi.responses import RedirectResponse

from .. import google, seguranca
from ..config import settings
from ..deps import Opcional, Sessao
from ..erros import ErroNegocio
from .app import app, templates

templates.env.globals["google_ativo"] = google.configurado


def _redirect_uri(request: Request) -> str:
    if settings.url_publica:
        base = settings.url_publica.rstrip("/")
    else:
        proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
        base = f"{proto}://{host}"
    return base + "/auth/google/retorno"


def _falha(request: Request, destino: str, mensagem: str):
    if destino == "app":
        return RedirectResponse("/app/#/entrar?erro=google", status_code=303)
    request.session["erro"] = mensagem
    return RedirectResponse("/entrar", status_code=303)


@app.get("/auth/google/iniciar")
def google_iniciar(request: Request, destino: str = "site"):
    destino = "app" if destino == "app" else "site"
    if not google.configurado():
        return _falha(request, destino, "O login com Google ainda não está ativo.")
    state, nonce = google.novo_estado()
    request.session["google"] = {"state": state, "nonce": nonce, "destino": destino}
    return RedirectResponse(google.url_autorizacao(_redirect_uri(request), state, nonce), status_code=303)


@app.get("/auth/google/retorno")
def google_retorno(request: Request, s: Sessao, usuario: Opcional, code: str = "", state: str = "", error: str = ""):
    guardado = request.session.pop("google", None) or {}
    destino = guardado.get("destino", "site")
    if error or not code or not guardado or state != guardado.get("state"):
        return _falha(request, destino, "Login com Google cancelado ou expirado. Tente de novo.")
    try:
        u = google.entrar_ou_criar(s, google.trocar_codigo(code, _redirect_uri(request), guardado["nonce"]))
    except ErroNegocio as e:
        return _falha(request, destino, str(e))
    request.session["usuario_id"] = u.id
    if destino == "app":
        return RedirectResponse(f"/app/#/google/{seguranca.gerar_token(u.id)}", status_code=303)
    return RedirectResponse("/", status_code=303)  # o portão leva a escolher o @ e aceitar os termos, se faltar
