"""Grupos esportivos locais (RF-004, RF-020): comunidade permanente com administradores, chat,
agenda, avisos e histórico."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session as SessaoORM

from .db import agora
from .erros import ErroNegocio, NaoEncontrado, SemPermissao
from .models import ABERTA, Atividade, Grupo, GrupoMembro, GrupoMensagem, Modalidade, Usuario


def obter(s: SessaoORM, grupo_id: int) -> Grupo:
    g = s.get(Grupo, grupo_id)
    if g is None or not g.ativo:
        raise NaoEncontrado("Grupo não encontrado.")
    return g


def membro(s: SessaoORM, grupo_id: int, usuario: Usuario) -> GrupoMembro | None:
    return s.get(GrupoMembro, (grupo_id, usuario.id))


def criar(
    s: SessaoORM,
    usuario: Usuario,
    nome: str,
    modalidade_id: int,
    descricao: str | None = None,
    cidade: str | None = None,
    local_habitual: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> Grupo:
    if not nome.strip():
        raise ErroNegocio("Dê um nome ao grupo.")
    if s.get(Modalidade, modalidade_id) is None:
        raise ErroNegocio("Escolha a modalidade do grupo.")
    g = Grupo(
        nome=nome.strip(), modalidade_id=modalidade_id, descricao=descricao, cidade=cidade or usuario.cidade,
        local_habitual=local_habitual, latitude=latitude if latitude is not None else usuario.latitude,
        longitude=longitude if longitude is not None else usuario.longitude,
    )
    g.membros.append(GrupoMembro(usuario_id=usuario.id, papel="admin"))
    s.add(g)
    s.commit()
    return g


def entrar(s: SessaoORM, grupo_id: int, usuario: Usuario) -> GrupoMembro:
    g = obter(s, grupo_id)
    m = membro(s, g.id, usuario)
    if m is None:
        m = GrupoMembro(grupo_id=g.id, usuario_id=usuario.id, papel="membro")
        s.add(m)
        s.commit()
    return m


def sair(s: SessaoORM, grupo_id: int, usuario: Usuario) -> None:
    m = membro(s, grupo_id, usuario)
    if m is None:
        return
    if m.papel == "admin":
        outros_admins = s.scalar(select(func.count()).select_from(GrupoMembro).where(GrupoMembro.grupo_id == grupo_id, GrupoMembro.papel == "admin", GrupoMembro.usuario_id != usuario.id))
        if not outros_admins:
            raise ErroNegocio("Você é o único administrador. Promova outro membro antes de sair.")
    s.delete(m)
    s.commit()


def promover(s: SessaoORM, grupo_id: int, alvo_id: int, por: Usuario) -> None:
    quem = membro(s, grupo_id, por)
    if (quem is None or quem.papel != "admin") and not por.admin:
        raise SemPermissao("Só administradores do grupo podem promover membros.")
    m = s.get(GrupoMembro, (grupo_id, alvo_id))
    if m is None:
        raise NaoEncontrado("Essa pessoa não é do grupo.")
    m.papel = "admin"
    s.commit()


def meus(s: SessaoORM, usuario: Usuario) -> list[Grupo]:
    return list(s.scalars(select(Grupo).join(GrupoMembro, GrupoMembro.grupo_id == Grupo.id).where(GrupoMembro.usuario_id == usuario.id, Grupo.ativo).order_by(Grupo.nome)))


def agenda(s: SessaoORM, grupo_id: int) -> list[Atividade]:
    return list(s.scalars(select(Atividade).where(Atividade.grupo_id == grupo_id, Atividade.status == ABERTA, Atividade.inicio >= agora()).order_by(Atividade.inicio)))


def historico(s: SessaoORM, grupo_id: int, limite: int = 20) -> list[Atividade]:
    return list(s.scalars(select(Atividade).where(Atividade.grupo_id == grupo_id, Atividade.inicio < agora()).order_by(Atividade.inicio.desc()).limit(limite)))


def postar(s: SessaoORM, grupo_id: int, usuario: Usuario, texto: str, aviso: bool = False) -> GrupoMensagem:
    m = membro(s, grupo_id, usuario)
    if m is None:
        raise SemPermissao("Entre no grupo para participar da conversa.")
    texto = texto.strip()
    if not texto:
        raise ErroNegocio("Escreva uma mensagem.")
    if aviso and m.papel != "admin":
        raise SemPermissao("Só administradores publicam avisos.")
    msg = GrupoMensagem(grupo_id=grupo_id, usuario_id=usuario.id, texto=texto[:2000], aviso=aviso)
    s.add(msg)
    s.commit()
    return msg


def mensagens(s: SessaoORM, grupo_id: int, depois_de: int = 0, limite: int = 80) -> list[GrupoMensagem]:
    """Mais recentes primeiro na consulta, devolvidas em ordem cronológica. `depois_de` serve ao polling do app."""
    q = select(GrupoMensagem).where(GrupoMensagem.grupo_id == grupo_id, GrupoMensagem.id > depois_de).order_by(GrupoMensagem.id.desc()).limit(limite)
    return list(reversed(list(s.scalars(q))))


def avisos(s: SessaoORM, grupo_id: int, limite: int = 3) -> list[GrupoMensagem]:
    return list(s.scalars(select(GrupoMensagem).where(GrupoMensagem.grupo_id == grupo_id, GrupoMensagem.aviso).order_by(GrupoMensagem.id.desc()).limit(limite)))
