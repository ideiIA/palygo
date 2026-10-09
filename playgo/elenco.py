"""Elenco da equipe: nome e RG dos componentes, o técnico e quem é o capitão (quando a organização libera o cadastro).

Regras: o cadastro só existe se `Campeonato.cadastro_elenco` estiver ligado; quem cadastra é o capitão da equipe (quem a inscreveu)
ou a organização. O capitão edita até a equipe ter um jogo começado; a organização sempre. Há no máximo `atletas_por_equipe` atletas,
um técnico e um capitão (que é um dos atletas). O RG não se repete na equipe e só aparece para a organização e para o capitão da
equipe: nunca em listas públicas, avisos ou na trilha de auditoria."""

import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as SessaoORM

from . import auditoria, campeonatos
from .erros import ErroNegocio, NaoEncontrado, SemPermissao
from .models import E_CANCELADA, E_RECUSADA, J_AGENDADO, Equipe, EquipeComponente, Jogo, Usuario

FUNCOES = {"atleta": "Atleta", "tecnico": "Técnico"}
_RG = re.compile(r"^[0-9A-Za-z.\-/ ]{5,20}$")


def _equipe(s: SessaoORM, equipe_id: int) -> Equipe:
    e = s.get(Equipe, equipe_id)
    if e is None:
        raise NaoEncontrado("Equipe não encontrada.")
    return e


def _gestor(e: Equipe, u: Usuario) -> bool:
    return campeonatos.pode_gerir(e.campeonato, u)


def _exigir_acesso(e: Equipe, u: Usuario) -> None:
    if e.capitao_id != u.id and not _gestor(e, u):
        raise SemPermissao("Só o capitão da equipe e a organização veem e editam o elenco.")


def _exigir_liberado(e: Equipe) -> None:
    if not e.campeonato.cadastro_elenco:
        raise ErroNegocio("A organização ainda não liberou o cadastro de componentes neste campeonato.")
    if e.status in (E_CANCELADA, E_RECUSADA):
        raise ErroNegocio("Esta equipe não está mais inscrita.")


def _jogo_comecou(s: SessaoORM, e: Equipe) -> bool:
    return s.scalar(
        select(func.count()).select_from(Jogo).where(or_(Jogo.equipe_a_id == e.id, Jogo.equipe_b_id == e.id), Jogo.status != J_AGENDADO, Jogo.folga.is_(False))
    ) > 0


def pode_editar(s: SessaoORM, e: Equipe, u: Usuario) -> bool:
    if not e.campeonato.cadastro_elenco or e.status in (E_CANCELADA, E_RECUSADA):
        return False
    if _gestor(e, u):
        return True
    return e.capitao_id == u.id and not _jogo_comecou(s, e)


def _exigir_edicao(s: SessaoORM, e: Equipe, u: Usuario) -> None:
    _exigir_acesso(e, u)
    _exigir_liberado(e)
    if not _gestor(e, u) and _jogo_comecou(s, e):
        raise ErroNegocio("A equipe já começou a jogar: só a organização altera o elenco agora.")


def _limpar(nome: str, rg: str, funcao: str) -> tuple[str, str, str]:
    nome = " ".join((nome or "").split())
    rg = (rg or "").strip()
    if len(nome) < 3:
        raise ErroNegocio("Informe o nome completo.")
    if len(nome) > 120:
        raise ErroNegocio("O nome passa de 120 caracteres.")
    if not _RG.match(rg):
        raise ErroNegocio("Informe o RG (de 5 a 20 caracteres, só letras, números, ponto e traço).")
    if funcao not in FUNCOES:
        raise ErroNegocio("Escolha atleta ou técnico.")
    return nome, rg, funcao


def _item(c: EquipeComponente) -> dict:
    return {"id": c.id, "nome": c.nome, "rg": c.rg, "funcao": c.funcao, "funcao_nome": FUNCOES[c.funcao], "capitao": c.capitao}


def _lista(s: SessaoORM, e: Equipe) -> list[EquipeComponente]:
    return list(s.scalars(select(EquipeComponente).where(EquipeComponente.equipe_id == e.id).order_by(EquipeComponente.funcao, EquipeComponente.id).execution_options(populate_existing=True)))


def listar(s: SessaoORM, equipe_id: int, u: Usuario) -> dict:
    e = _equipe(s, equipe_id)
    _exigir_acesso(e, u)
    itens = _lista(s, e)
    return {
        "equipe": {"id": e.id, "nome": e.nome}, "liberado": bool(e.campeonato.cadastro_elenco), "pode_editar": pode_editar(s, e, u),
        "limite_atletas": e.campeonato.atletas_por_equipe, "atletas": sum(1 for c in itens if c.funcao == "atleta"),
        "tem_tecnico": any(c.funcao == "tecnico" for c in itens), "componentes": [_item(c) for c in itens],
    }


def contagens(s: SessaoORM, equipe_ids: list[int]) -> dict[int, int]:
    """Quantos componentes cada equipe tem cadastrados (número público: sem nomes nem RG)."""
    if not equipe_ids:
        return {}
    linhas = s.execute(select(EquipeComponente.equipe_id, func.count()).where(EquipeComponente.equipe_id.in_(equipe_ids)).group_by(EquipeComponente.equipe_id)).all()
    return {i: n for i, n in linhas}


def _validar_limites(s: SessaoORM, e: Equipe, funcao: str, ignorar_id: int | None = None) -> None:
    itens = [c for c in _lista(s, e) if c.id != ignorar_id]
    if funcao == "atleta" and sum(1 for c in itens if c.funcao == "atleta") >= e.campeonato.atletas_por_equipe:
        raise ErroNegocio(f"A equipe já tem os {e.campeonato.atletas_por_equipe} atletas.")
    if funcao == "tecnico" and any(c.funcao == "tecnico" for c in itens):
        raise ErroNegocio("A equipe já tem um técnico cadastrado.")


def _rg_repetido(s: SessaoORM, e: Equipe, rg: str, ignorar_id: int | None = None) -> None:
    chave = re.sub(r"[^0-9A-Za-z]", "", rg).lower()
    for c in _lista(s, e):
        if c.id != ignorar_id and re.sub(r"[^0-9A-Za-z]", "", c.rg).lower() == chave:
            raise ErroNegocio("Já existe um componente com esse RG nesta equipe.")


def _unico_capitao(s: SessaoORM, e: Equipe, manter_id: int) -> None:
    for c in _lista(s, e):
        if c.id != manter_id and c.capitao:
            c.capitao = False


def adicionar(s: SessaoORM, equipe_id: int, por: Usuario, nome: str, rg: str, funcao: str = "atleta", capitao: bool = False) -> dict:
    e = _equipe(s, equipe_id)
    _exigir_edicao(s, e, por)
    nome, rg, funcao = _limpar(nome, rg, funcao)
    if capitao and funcao != "atleta":
        raise ErroNegocio("O capitão é um dos atletas; o técnico não pode ser o capitão.")
    _validar_limites(s, e, funcao)
    _rg_repetido(s, e, rg)
    c = EquipeComponente(equipe_id=e.id, nome=nome, rg=rg, funcao=funcao, capitao=bool(capitao))
    s.add(c)
    s.flush()
    if capitao:
        _unico_capitao(s, e, c.id)
    auditoria.registrar(s, por.id, "elenco_adicionar", "equipe", e.id, componente=c.id, funcao=funcao)
    s.commit()
    return listar(s, e.id, por)


def atualizar(s: SessaoORM, equipe_id: int, componente_id: int, por: Usuario, nome: str, rg: str, funcao: str, capitao: bool | None = None) -> dict:
    e = _equipe(s, equipe_id)
    _exigir_edicao(s, e, por)
    c = s.get(EquipeComponente, componente_id)
    if c is None or c.equipe_id != e.id:
        raise NaoEncontrado("Componente não encontrado.")
    nome, rg, funcao = _limpar(nome, rg, funcao)
    if funcao != c.funcao:
        _validar_limites(s, e, funcao, ignorar_id=c.id)
    _rg_repetido(s, e, rg, ignorar_id=c.id)
    c.nome, c.rg, c.funcao = nome, rg, funcao
    if funcao == "tecnico":
        c.capitao = False
    elif capitao is not None:
        c.capitao = bool(capitao)
        if capitao:
            _unico_capitao(s, e, c.id)
    auditoria.registrar(s, por.id, "elenco_editar", "equipe", e.id, componente=c.id)
    s.commit()
    return listar(s, e.id, por)


def definir_capitao(s: SessaoORM, equipe_id: int, componente_id: int, por: Usuario) -> dict:
    e = _equipe(s, equipe_id)
    _exigir_edicao(s, e, por)
    c = s.get(EquipeComponente, componente_id)
    if c is None or c.equipe_id != e.id:
        raise NaoEncontrado("Componente não encontrado.")
    if c.funcao != "atleta":
        raise ErroNegocio("O capitão é um dos atletas; o técnico não pode ser o capitão.")
    c.capitao = True
    _unico_capitao(s, e, c.id)
    auditoria.registrar(s, por.id, "elenco_capitao", "equipe", e.id, componente=c.id)
    s.commit()
    return listar(s, e.id, por)


def remover(s: SessaoORM, equipe_id: int, componente_id: int, por: Usuario) -> dict:
    e = _equipe(s, equipe_id)
    _exigir_edicao(s, e, por)
    c = s.get(EquipeComponente, componente_id)
    if c is None or c.equipe_id != e.id:
        raise NaoEncontrado("Componente não encontrado.")
    s.delete(c)
    auditoria.registrar(s, por.id, "elenco_remover", "equipe", e.id, componente=componente_id)
    s.commit()
    return listar(s, e.id, por)
