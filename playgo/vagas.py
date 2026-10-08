"""Vagas em tempo real, aprovação e lista de espera (RF-002, RF-013, RF-017, RF-018).

`Atividade.confirmados` é mantido junto de `Participacao`, sob trava de linha: duas pessoas clicando
em "Eu vou" na última vaga não passam as duas."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as SessaoORM

from . import auditoria, match, notificacoes
from .config import settings
from .db import agora
from .erros import ErroNegocio, NaoEncontrado, SemPermissao
from .models import (
    ABERTA,
    ATIVAS,
    CANCELADO,
    CONFIRMADO,
    ESPERA,
    PENDENTE,
    RECUSADO,
    Atividade,
    Convite,
    Participacao,
    Usuario,
)


def travar(s: SessaoORM, atividade_id: int) -> Atividade:
    """Lê a atividade com trava de linha. `of=` porque os joins eager da atividade são externos."""
    a = s.scalar(select(Atividade).where(Atividade.id == atividade_id).with_for_update(of=Atividade))
    if a is None:
        raise NaoEncontrado("Atividade não encontrada.")
    return a


def participacao_de(s: SessaoORM, atividade_id: int, usuario_id: int) -> Participacao | None:
    return s.scalar(select(Participacao).where(Participacao.atividade_id == atividade_id, Participacao.usuario_id == usuario_id))


def _idade(u: Usuario) -> int | None:
    if not u.nascimento:
        return None
    hoje = agora().date()
    return hoje.year - u.nascimento.year - ((hoje.month, hoje.day) < (u.nascimento.month, u.nascimento.day))


def _checar_elegibilidade(a: Atividade, u: Usuario) -> None:
    if a.categoria != "misto":
        if not u.sexo:
            raise ErroNegocio("Esta atividade é por categoria. Informe seu sexo no perfil para participar.")
        if (a.categoria == "masculino") != (u.sexo == "M"):
            raise ErroNegocio(f"Esta atividade é da categoria {a.categoria}.")
    if a.idade_min is not None or a.idade_max is not None:
        idade = _idade(u)
        if idade is None:
            raise ErroNegocio("Esta atividade tem faixa etária. Informe seu nascimento no perfil para participar.")
        if (a.idade_min is not None and idade < a.idade_min) or (a.idade_max is not None and idade > a.idade_max):
            raise ErroNegocio("Sua idade está fora da faixa desta atividade.")


def _avisar_organizador(s: SessaoORM, a: Atividade, quem: Usuario, texto: str, sufixo: str) -> None:
    if a.organizador_id != quem.id:
        notificacoes.avisar(
            s, a.organizador_id, "atividade", f"{quem.nome} {texto}", a.nome, f"/atividades/{a.id}", a.id, f"org:{a.id}:{quem.id}:{sufixo}"
        )


def _fechar_se_lotou(a: Atividade) -> None:
    if a.vagas == 0:
        a.falta_gente = False


def entrar(s: SessaoORM, atividade_id: int, usuario: Usuario, token: str | None = None) -> Participacao:
    """'Eu vou'. Resultado: confirmado, pendente (atividade só para autorizados) ou espera (lotado).
    Quem foi convidado pelo @usuario ou entra pelo link dispensa a aprovação."""
    from . import convites, planos

    planos.exigir(s, usuario, "basico")
    a = travar(s, atividade_id)
    convite = s.scalar(select(Convite).where(Convite.escopo == "atividade", Convite.escopo_id == a.id, Convite.convidado_id == usuario.id, Convite.status != "recusado"))
    if a.visibilidade == "link" and not convites.pode_acessar_atividade(s, usuario, a, token):
        raise ErroNegocio("Esta atividade é só por convite. Peça o link ao organizador.")
    if a.status != ABERTA:
        raise ErroNegocio("Esta atividade foi cancelada ou encerrada.")
    if agora() > a.inicio + timedelta(minutes=settings.tolerancia_inicio_min):
        raise ErroNegocio("Esta atividade já começou.")
    p = participacao_de(s, a.id, usuario.id)
    if p and p.status in ATIVAS:
        return p
    if p and p.status == RECUSADO:
        raise ErroNegocio("O organizador recusou sua solicitação para esta atividade.")
    _checar_elegibilidade(a, usuario)

    if p is None:
        p = Participacao(atividade_id=a.id, usuario_id=usuario.id, status=ESPERA)
        s.add(p)
    p.criado_em = agora()  # quem volta depois de desistir entra no fim da fila

    if a.visibilidade == "autorizados" and convite is None and usuario.id != a.organizador_id:
        p.status = PENDENTE
        _avisar_organizador(s, a, usuario, "pediu para participar", "pedido")
    elif a.vagas > 0:
        p.status = CONFIRMADO
        a.confirmados += 1
        _fechar_se_lotou(a)
        _avisar_organizador(s, a, usuario, "vai participar", "entrou")
    else:
        p.status = ESPERA
    auditoria.registrar(s, usuario.id, "participacao_entrar", "atividade", a.id, situacao=p.status)
    s.commit()
    return p


def _decidir(s: SessaoORM, atividade_id: int, participacao_id: int, por: Usuario) -> tuple[Atividade, Participacao]:
    a = travar(s, atividade_id)
    if por.id != a.organizador_id and not por.admin:
        raise SemPermissao("Só o organizador pode fazer isso.")
    p = s.get(Participacao, participacao_id)
    if p is None or p.atividade_id != a.id:
        raise NaoEncontrado("Participação não encontrada.")
    return a, p


def aprovar(s: SessaoORM, atividade_id: int, participacao_id: int, por: Usuario) -> Participacao:
    a, p = _decidir(s, atividade_id, participacao_id, por)
    if p.status != PENDENTE:
        return p
    if a.vagas > 0:
        p.status = CONFIRMADO
        a.confirmados += 1
        _fechar_se_lotou(a)
        titulo = f"Você está confirmado em {a.nome}!"
    else:
        p.status = ESPERA
        titulo = f"Você foi aprovado em {a.nome}, mas o jogo está lotado: entrou na lista de espera."
    notificacoes.avisar(s, p.usuario_id, "atividade", titulo, "", f"/atividades/{a.id}", a.id, f"aprov:{a.id}:{p.usuario_id}")
    s.commit()
    return p


def recusar(s: SessaoORM, atividade_id: int, participacao_id: int, por: Usuario) -> Participacao:
    a, p = _decidir(s, atividade_id, participacao_id, por)
    if p.status == PENDENTE:
        p.status = RECUSADO
        notificacoes.avisar(s, p.usuario_id, "atividade", f"Sua solicitação para {a.nome} não foi aprovada.", "", f"/atividades/{a.id}", a.id, f"recus:{a.id}:{p.usuario_id}")
        s.commit()
    return p


def sair(s: SessaoORM, atividade_id: int, usuario: Usuario) -> None:
    a = travar(s, atividade_id)
    if a.organizador_id == usuario.id:
        raise ErroNegocio("O organizador não pode sair da própria atividade; cancele-a se não for acontecer.")
    p = participacao_de(s, a.id, usuario.id)
    if p is None or p.status not in ATIVAS:
        return
    liberou = p.status == CONFIRMADO
    p.status = CANCELADO
    if liberou:
        a.confirmados -= 1
        repor(s, a)
    auditoria.registrar(s, usuario.id, "participacao_sair", "atividade", a.id)
    s.commit()


def remover(s: SessaoORM, atividade_id: int, participacao_id: int, por: Usuario) -> None:
    a, p = _decidir(s, atividade_id, participacao_id, por)
    if p.usuario_id == a.organizador_id:
        raise ErroNegocio("O organizador não pode ser removido.")
    if p.status not in ATIVAS:
        return
    liberou = p.status == CONFIRMADO
    p.status = CANCELADO
    notificacoes.avisar(s, p.usuario_id, "atividade", f"Você foi removido de {a.nome}.", "", f"/atividades/{a.id}", a.id, f"rem:{a.id}:{p.usuario_id}")
    if liberou:
        a.confirmados -= 1
        repor(s, a)
    s.commit()


def repor(s: SessaoORM, a: Atividade) -> int:
    """Há vaga livre: chama a lista de espera na ordem de chegada (RF-018). Quem sobrar de vaga
    pode virar aviso para atletas próximos (RF-016). Chamar com a atividade já travada."""
    chamados = 0
    if a.status == ABERTA:
        fila = s.scalars(
            select(Participacao)
            .where(Participacao.atividade_id == a.id, Participacao.status == ESPERA)
            .order_by(Participacao.criado_em, Participacao.id)
        )
        for p in fila:
            if a.vagas <= 0:
                break
            p.status = CONFIRMADO
            a.confirmados += 1
            chamados += 1
            notificacoes.avisar(
                s, p.usuario_id, "reposicao", "👤 Alguém desistiu. Você saiu da lista de espera e está confirmado.", a.nome, f"/atividades/{a.id}", a.id, f"repos:{a.id}:{p.usuario_id}:{a.confirmados}"
            )
        _fechar_se_lotou(a)
        minutos = (a.inicio - agora()).total_seconds() / 60
        if a.vagas > 0 and (a.falta_gente or 0 <= minutos <= 180):
            s.flush()
            match.avisar_compativeis(s, a, "vaga")
    return chamados


def lista(s: SessaoORM, atividade_id: int) -> dict[str, list[Participacao]]:
    """Participantes da atividade agrupados por situação."""
    saida: dict[str, list[Participacao]] = {CONFIRMADO: [], PENDENTE: [], ESPERA: []}
    for p in s.scalars(select(Participacao).where(Participacao.atividade_id == atividade_id).order_by(Participacao.criado_em, Participacao.id)):
        if p.status in saida:
            saida[p.status].append(p)
    return saida
