"""Sub-páginas de cada campeonato: chaves, ao vivo, jogo e sorteio (a organização). A tela em si é o `chaves.js`."""

from fastapi import Request
from fastapi.responses import RedirectResponse

from .. import campeonatos, detalhes
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


@app.get("/campeonatos/{campeonato_id}/sorteio")
def tela_sorteio(campeonato_id: int, request: Request, s: Sessao, usuario: Atual):
    c = campeonatos.obter(s, campeonato_id)
    if not campeonatos.pode_gerir(c, usuario):
        request.session["erro"] = "O sorteio é feito pela organização do campeonato."
        return RedirectResponse(f"/campeonatos/{campeonato_id}/chaves", status_code=303)
    return _sub(request, s, usuario, campeonato_id, "sorteio")
