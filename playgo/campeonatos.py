"""Campeonatos e torneios (RF-007, RF-008, RF-021, RF-022): cadastro, inscrição de equipes e convites.
Tabelas, confrontos e classificação (RF-009) ficam para a fase seguinte, como no projeto."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session as SessaoORM

from . import notificacoes, planos
from .db import agora
from .erros import ErroNegocio, NaoEncontrado, SemPermissao
from .geo import distancia_sql, formatar_km
from .models import (
    C_ABERTO,
    C_CANCELADO,
    E_CANCELADA,
    E_CONFIRMADA,
    E_PENDENTE,
    E_RECUSADA,
    M_CONFIRMADO,
    M_CONVIDADO,
    M_RECUSADO,
    Arena,
    Campeonato,
    Equipe,
    EquipeMembro,
    Modalidade,
    Usuario,
    UsuarioModalidade,
)

ATIVAS_EQUIPE = (E_PENDENTE, E_CONFIRMADA)


@dataclass
class NovoCampeonato:
    modalidade_id: int
    nome: str
    data_inicio: date
    inscricao_ate: date
    max_equipes: int
    atletas_por_equipe: int = 5
    arena_id: int | None = None
    data_fim: date | None = None
    categoria: str | None = None
    local_nome: str = ""
    latitude: float | None = None
    longitude: float | None = None
    valor_inscricao: Decimal = Decimal(0)
    premiacao: str | None = None
    premiacao_valor: Decimal | None = None
    regulamento: str | None = None
    descricao: str | None = None


def obter(s: SessaoORM, campeonato_id: int) -> Campeonato:
    c = s.get(Campeonato, campeonato_id)
    if c is None:
        raise NaoEncontrado("Campeonato não encontrado.")
    return c


def pode_gerir(c: Campeonato, usuario: Usuario) -> bool:
    return usuario.admin or c.organizador_id == usuario.id or (c.arena is not None and usuario in c.arena.gestores)


def exigir_gestao(c: Campeonato, usuario: Usuario) -> None:
    if not pode_gerir(c, usuario):
        raise SemPermissao("Só quem organiza o campeonato pode fazer isso.")


def equipes_ativas(s: SessaoORM, c: Campeonato) -> int:
    """Consulta o banco: a coleção `c.equipes` pode estar desatualizada dentro da mesma sessão."""
    return s.scalar(select(func.count()).select_from(Equipe).where(Equipe.campeonato_id == c.id, Equipe.status.in_(ATIVAS_EQUIPE))) or 0


def criar(s: SessaoORM, usuario: Usuario, d: NovoCampeonato) -> Campeonato:
    if s.get(Modalidade, d.modalidade_id) is None:
        raise ErroNegocio("Escolha a modalidade.")
    if not d.nome.strip():
        raise ErroNegocio("Dê um nome ao campeonato.")
    if d.max_equipes < 2:
        raise ErroNegocio("Um campeonato precisa de pelo menos 2 equipes.")
    planos.exigir(s, usuario, "campeonato")
    if d.atletas_por_equipe < 1:
        raise ErroNegocio("Informe quantos atletas formam uma equipe.")
    if d.inscricao_ate > d.data_inicio:
        raise ErroNegocio("O prazo de inscrição precisa ser até o início do campeonato.")
    if d.data_fim and d.data_fim < d.data_inicio:
        raise ErroNegocio("A data final não pode ser anterior à inicial.")
    if d.valor_inscricao < 0:
        raise ErroNegocio("O valor da inscrição não pode ser negativo.")
    arena = s.get(Arena, d.arena_id) if d.arena_id else None
    if arena is not None and not usuario.admin and usuario not in arena.gestores:
        raise SemPermissao("Só gestores da arena criam campeonatos nela.")
    lat, lng = d.latitude, d.longitude
    local = d.local_nome.strip()
    if arena is not None:
        lat, lng, local = (lat if lat is not None else arena.latitude), (lng if lng is not None else arena.longitude), (local or arena.nome)
    if lat is None or lng is None or not local:
        raise ErroNegocio("Informe o local do campeonato (arena ou ponto no mapa).")
    c = Campeonato(
        organizador_id=usuario.id, arena_id=arena.id if arena else None, modalidade_id=d.modalidade_id,
        nome=d.nome.strip(), categoria=d.categoria, descricao=d.descricao, regulamento=d.regulamento,
        premiacao=d.premiacao, premiacao_valor=d.premiacao_valor, local_nome=local, latitude=lat, longitude=lng,
        data_inicio=d.data_inicio, data_fim=d.data_fim, inscricao_ate=d.inscricao_ate, max_equipes=d.max_equipes,
        atletas_por_equipe=d.atletas_por_equipe, valor_inscricao=d.valor_inscricao,
    )
    s.add(c)
    s.flush()
    _avisar_proximos(s, c)
    s.commit()
    return c


def _avisar_proximos(s: SessaoORM, c: Campeonato) -> None:
    """'🏆 Foram abertas inscrições para um campeonato de Beach Tennis próximo de você.'"""
    dist = distancia_sql(Usuario.latitude, Usuario.longitude, c.latitude, c.longitude)
    q = (
        select(Usuario, dist)
        .join(UsuarioModalidade, UsuarioModalidade.usuario_id == Usuario.id)
        .where(
            UsuarioModalidade.modalidade_id == c.modalidade_id,
            Usuario.ativo, Usuario.notif_campeonatos, Usuario.latitude.is_not(None),
            Usuario.id != c.organizador_id, dist <= Usuario.notif_raio_km,
        )
        .limit(500)
    )
    for u, km in s.execute(q).unique():
        notificacoes.avisar(
            s, u.id, "campeonato", f"🏆 Inscrições abertas: {c.nome}",
            f"Campeonato de {c.modalidade.nome} a {formatar_km(km)} de você, a partir de {c.data_inicio.strftime('%d/%m')}.",
            f"/campeonatos/{c.id}", None, f"camp:{c.id}",
        )


def definir_status(s: SessaoORM, campeonato_id: int, por: Usuario, status: str) -> Campeonato:
    c = obter(s, campeonato_id)
    exigir_gestao(c, por)
    if status not in ("aberto", "em_andamento", "encerrado", "cancelado"):
        raise ErroNegocio("Situação inválida.")
    c.status = status
    if status == C_CANCELADO:
        for e in c.equipes:
            if e.status in ATIVAS_EQUIPE:
                notificacoes.avisar(s, e.capitao_id, "campeonato", f"❌ {c.nome} foi cancelado", "", f"/campeonatos/{c.id}", None, f"campcanc:{c.id}:{e.id}")
    s.commit()
    return c


# ---------------------------------------------------------------- equipes


def _equipe_do_atleta(s: SessaoORM, c: Campeonato, usuario_id: int) -> Equipe | None:
    return s.scalar(
        select(Equipe)
        .join(EquipeMembro, EquipeMembro.equipe_id == Equipe.id)
        .where(Equipe.campeonato_id == c.id, Equipe.status.in_(ATIVAS_EQUIPE), EquipeMembro.usuario_id == usuario_id, EquipeMembro.status == M_CONFIRMADO)
        .limit(1)
    )


def inscrever_equipe(s: SessaoORM, campeonato_id: int, capitao: Usuario, nome: str, convidados: list[int] | None = None) -> Equipe:
    """O capitão cadastra a equipe (RF-008) e já convida os jogadores. A inscrição fica pendente até o organizador confirmar."""
    c = s.scalar(select(Campeonato).where(Campeonato.id == campeonato_id).with_for_update(of=Campeonato))
    if c is None:
        raise NaoEncontrado("Campeonato não encontrado.")
    if c.status != C_ABERTO or c.inscricao_ate < agora().date():
        raise ErroNegocio("As inscrições deste campeonato estão encerradas.")
    if equipes_ativas(s, c) >= c.max_equipes:
        raise ErroNegocio("Todas as vagas do campeonato foram preenchidas.")
    if not nome.strip():
        raise ErroNegocio("Dê um nome à equipe.")
    if _equipe_do_atleta(s, c, capitao.id):
        raise ErroNegocio("Você já está em uma equipe deste campeonato.")
    if s.scalar(select(Equipe.id).where(Equipe.campeonato_id == c.id, Equipe.status.in_(ATIVAS_EQUIPE), func.lower(Equipe.nome) == nome.strip().lower())):
        raise ErroNegocio("Já existe uma equipe com esse nome neste campeonato.")
    e = Equipe(campeonato_id=c.id, capitao_id=capitao.id, nome=nome.strip())
    e.membros.append(EquipeMembro(usuario_id=capitao.id, status=M_CONFIRMADO))
    s.add(e)
    s.flush()
    for uid in convidados or []:
        convidar(s, e.id, capitao, uid, _commit=False)
    notificacoes.avisar(s, c.organizador_id, "equipe", f"Nova equipe em {c.nome}: {e.nome}", f"Capitão: {capitao.nome}", f"/campeonatos/{c.id}", None, f"eq:{e.id}")
    s.commit()
    return e


def convidar(s: SessaoORM, equipe_id: int, por: Usuario, usuario_id: int, _commit: bool = True) -> EquipeMembro:
    e = s.get(Equipe, equipe_id)
    if e is None:
        raise NaoEncontrado("Equipe não encontrada.")
    if e.capitao_id != por.id:
        raise SemPermissao("Só o capitão convida jogadores.")
    if e.status not in ATIVAS_EQUIPE:
        raise ErroNegocio("Esta equipe não está mais inscrita.")
    alvo = s.get(Usuario, usuario_id)
    if alvo is None or not alvo.ativo:
        raise NaoEncontrado("Atleta não encontrado.")
    c = e.campeonato
    m = s.get(EquipeMembro, (e.id, alvo.id))
    if m is not None and m.status != M_RECUSADO:
        return m
    ocupados = s.scalar(select(func.count()).select_from(EquipeMembro).where(EquipeMembro.equipe_id == e.id, EquipeMembro.status != M_RECUSADO)) or 0
    if ocupados >= c.atletas_por_equipe:
        raise ErroNegocio(f"A equipe já tem os {c.atletas_por_equipe} atletas.")
    if _equipe_do_atleta(s, c, alvo.id):
        raise ErroNegocio(f"{alvo.nome} já está em uma equipe deste campeonato.")
    if m is None:
        m = EquipeMembro(equipe_id=e.id, usuario_id=alvo.id, status=M_CONVIDADO)
        s.add(m)
    else:
        m.status = M_CONVIDADO
    notificacoes.avisar(s, alvo.id, "equipe", f"🏆 {por.nome} convidou você para a equipe {e.nome}", f"Campeonato: {c.nome}", f"/campeonatos/{c.id}", None, f"conv:{e.id}:{alvo.id}:{agora().strftime('%d%H%M')}")
    if _commit:
        s.commit()
    return m


def responder_convite(s: SessaoORM, equipe_id: int, usuario: Usuario, aceitar: bool) -> EquipeMembro:
    m = s.get(EquipeMembro, (equipe_id, usuario.id))
    if m is None or m.status != M_CONVIDADO:
        raise NaoEncontrado("Convite não encontrado.")
    if aceitar and _equipe_do_atleta(s, m.equipe.campeonato, usuario.id):
        raise ErroNegocio("Você já está em uma equipe deste campeonato.")
    m.status = M_CONFIRMADO if aceitar else M_RECUSADO
    notificacoes.avisar(
        s, m.equipe.capitao_id, "equipe", f"{usuario.nome} {'aceitou' if aceitar else 'recusou'} o convite para {m.equipe.nome}", "", f"/campeonatos/{m.equipe.campeonato_id}", None, f"resp:{equipe_id}:{usuario.id}:{agora().strftime('%d%H%M%S')}"
    )
    s.commit()
    return m


def decidir_equipe(s: SessaoORM, equipe_id: int, por: Usuario, confirmar: bool) -> Equipe:
    e = s.get(Equipe, equipe_id)
    if e is None:
        raise NaoEncontrado("Equipe não encontrada.")
    exigir_gestao(e.campeonato, por)
    e.status = E_CONFIRMADA if confirmar else E_RECUSADA
    notificacoes.avisar(
        s, e.capitao_id, "equipe", f"{'✅ Inscrição confirmada' if confirmar else '❌ Inscrição recusada'}: {e.nome}", e.campeonato.nome, f"/campeonatos/{e.campeonato_id}", None, f"dec:{e.id}:{e.status}"
    )
    s.commit()
    return e


def cancelar_equipe(s: SessaoORM, equipe_id: int, por: Usuario) -> None:
    e = s.get(Equipe, equipe_id)
    if e is None:
        raise NaoEncontrado("Equipe não encontrada.")
    if e.capitao_id != por.id and not pode_gerir(e.campeonato, por):
        raise SemPermissao("Só o capitão cancela a inscrição.")
    e.status = E_CANCELADA
    s.commit()


def minha_situacao(s: SessaoORM, c: Campeonato, usuario: Usuario) -> dict:
    """Onde o atleta está neste campeonato: capitão, convidado ou fora."""
    e = _equipe_do_atleta(s, c, usuario.id)
    if e is None:
        convite = s.scalar(
            select(EquipeMembro).join(Equipe, Equipe.id == EquipeMembro.equipe_id)
            .where(Equipe.campeonato_id == c.id, Equipe.status.in_(ATIVAS_EQUIPE), EquipeMembro.usuario_id == usuario.id, EquipeMembro.status == M_CONVIDADO)
        )
        return {"estado": "convidado" if convite else "fora", "equipe_id": convite.equipe_id if convite else None}
    return {"estado": "capitao" if e.capitao_id == usuario.id else "jogador", "equipe_id": e.id}


def contar_pendentes(s: SessaoORM, c: Campeonato) -> int:
    return s.scalar(select(func.count()).select_from(Equipe).where(Equipe.campeonato_id == c.id, Equipe.status == E_PENDENTE)) or 0
