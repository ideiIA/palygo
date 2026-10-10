"""Conexão da conta do Instagram do PlayGo (um administrador autoriza uma vez; o token fica no banco e se renova sozinho)."""

from fastapi import Request
from fastapi.responses import RedirectResponse

from .. import instagram
from ..deps import Atual, Sessao
from ..erros import ErroNegocio
from .app import app


@app.get("/instagram/conectar")
def instagram_conectar(request: Request, usuario: Atual):
    if not usuario.admin:
        request.session["erro"] = "Só administradores conectam o Instagram."
        return RedirectResponse("/", status_code=303)
    try:
        estado = instagram.novo_estado()
        request.session["ig_state"] = estado
        return RedirectResponse(instagram.url_autorizacao(estado), status_code=303)
    except ErroNegocio as e:
        request.session["erro"] = str(e)
        return RedirectResponse("/administracao", status_code=303)


@app.get("/instagram/retorno")
def instagram_retorno(request: Request, s: Sessao, usuario: Atual, code: str = "", state: str = "", error: str = "", error_description: str = ""):
    esperado = request.session.pop("ig_state", None)
    if not usuario.admin:
        return RedirectResponse("/", status_code=303)
    if error or not code or not esperado or state != esperado:
        request.session["erro"] = "A conexão com o Instagram foi cancelada ou expirou. Tente de novo." + (f" ({error_description})" if error_description else "")
        return RedirectResponse("/administracao", status_code=303)
    try:
        e = instagram.conectar(s, usuario, code)
        request.session["ok"] = f"Instagram conectado: @{e['usuario']}."
    except ErroNegocio as ex:
        request.session["erro"] = str(ex)
    return RedirectResponse("/administracao", status_code=303)
