"""Sub-páginas de cada campeonato: chaves, ao vivo, jogo e sorteio (a organização). A tela em si é o `chaves.js`."""

from fastapi import Request
from fastapi.responses import RedirectResponse

from .. import armazenamento, campeonatos, detalhes
from ..config import settings
from ..erros import NaoEncontrado
from ..models import Usuario
from ..deps import Atual, Sessao
from .app import app, pagina


def _sub(request: Request, s, usuario, campeonato_id: int, modo: str, **extra):
    c = campeonatos.obter(s, campeonato_id)
    return pagina(request, s, usuario, "campeonato_chaves.html", "campeonatos", k=detalhes.campeonato(s, c, usuario), modo=modo, **extra)


@app.get("/campeonatos/{campeonato_id}/chaves")
def tela_chaves(campeonato_id: int, request: Request, s: Sessao, usuario: Atual):
    return _sub(request, s, usuario, campeonato_id, "chaves")


@app.get("/campeonatos/{campeonato_id}/ao-vivo")
def tela_ao_vivo(campeonato_id: int, request: Request, s: Sessao, usuario: Atual):
    return _sub(request, s, usuario, campeonato_id, "ao_vivo")


@app.get("/campeonatos/{campeonato_id}/jogos/{jogo_id}")
def tela_jogo(campeonato_id: int, jogo_id: int, request: Request, s: Sessao, usuario: Atual):
    return _sub(request, s, usuario, campeonato_id, "jogo", jogo_id=jogo_id)


@app.get("/campeonatos/{campeonato_id}/regulamento.pdf")
def baixar_regulamento(campeonato_id: int, request: Request, s: Sessao, t: str = ""):
    uid = campeonatos.usuario_do_token_pdf(t, campeonato_id) if t else request.session.get("usuario_id")
    usuario = s.get(Usuario, uid) if uid else None
    c = campeonatos.obter(s, campeonato_id)
    if usuario is None or not usuario.ativo or not c.regulamento_arquivo:
        raise NaoEncontrado("Regulamento não encontrado.")
    return armazenamento.servir(c.regulamento_arquivo, "application/pdf", "private, max-age=300")


@app.get("/campeonatos/{campeonato_id}/editar")
def tela_editar(campeonato_id: int, request: Request, s: Sessao, usuario: Atual):
    c = campeonatos.obter(s, campeonato_id)
    if not campeonatos.pode_gerir(c, usuario):
        request.session["erro"] = "Só a organização do campeonato pode editá-lo."
        return RedirectResponse(f"/campeonatos/{campeonato_id}", status_code=303)
    return pagina(request, s, usuario, "campeonato_editar.html", "campeonatos", k=detalhes.campeonato(s, c, usuario), limite_pdf_mb=settings.limite_pdf_mb)


@app.get("/campeonatos/{campeonato_id}/sorteio")
def tela_sorteio(campeonato_id: int, request: Request, s: Sessao, usuario: Atual):
    c = campeonatos.obter(s, campeonato_id)
    if not campeonatos.pode_gerir(c, usuario):
        request.session["erro"] = "O sorteio é feito pela organização do campeonato."
        return RedirectResponse(f"/campeonatos/{campeonato_id}/chaves", status_code=303)
    return _sub(request, s, usuario, campeonato_id, "sorteio")
