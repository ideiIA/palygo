"""Murais por escopo: geral (todo o app), atividade, campeonato e comunidade.
Aqui ficam as perguntas de permissão — quem lê, quem posta, quem modera — e o contexto (nome, local) de cada escopo."""

from sqlalchemy import select
from sqlalchemy.orm import Session as SessaoORM

from . import campeonatos as srv_campeonatos
from . import notificacoes
from .erros import ErroNegocio, NaoEncontrado, SemPermissao
from .models import (
    CONFIRMADO,
    ESCOPOS,
    ESPERA,
    M_CONFIRMADO,
    Atividade,
    Campeonato,
    Comunidade,
    ComunidadeMembro,
    Equipe,
    EquipeMembro,
    Moderador,
    Participacao,
    Usuario,
)

PAPEIS_MODERACAO_COMUNIDADE = ("dono", "moderador")


def validar(escopo: str, escopo_id: int | None) -> None:
    if escopo not in ESCOPOS or (escopo == "geral") != (escopo_id is None):
        raise ErroNegocio("Mural inválido.")


def carregar(s: SessaoORM, escopo: str, escopo_id: int | None):
    validar(escopo, escopo_id)
    if escopo == "geral":
        return None
    modelo = {"atividade": Atividade, "campeonato": Campeonato, "comunidade": Comunidade}[escopo]
    obj = s.get(modelo, escopo_id)
    if obj is None or (escopo == "comunidade" and not obj.ativa):
        raise NaoEncontrado("Mural não encontrado.")
    return obj


def contexto(s: SessaoORM, escopo: str, escopo_id: int | None) -> dict:
    """Título, link e local do escopo. Atividade e campeonato têm local próprio — o da publicação é sempre o do evento."""
    obj = carregar(s, escopo, escopo_id)
    if escopo == "geral":
        return {"titulo": "Feed geral", "link": "/mural", "latitude": None, "longitude": None, "local_nome": None}
    if escopo == "atividade":
        return {"titulo": obj.nome, "link": f"/atividades/{obj.id}", "latitude": obj.latitude, "longitude": obj.longitude, "local_nome": obj.local_nome}
    if escopo == "campeonato":
        return {"titulo": obj.nome, "link": f"/campeonatos/{obj.id}", "latitude": obj.latitude, "longitude": obj.longitude, "local_nome": obj.local_nome}
    return {"titulo": obj.nome, "link": f"/comunidades/{obj.id}", "latitude": None, "longitude": None, "local_nome": None}


def _membro_comunidade(s: SessaoORM, comunidade_id: int, usuario: Usuario) -> ComunidadeMembro | None:
    return s.get(ComunidadeMembro, (comunidade_id, usuario.id))


def eh_moderador(s: SessaoORM, usuario: Usuario, escopo: str, escopo_id: int | None) -> bool:
    """Admin modera tudo; no mais, quem o escopo define: organizador/gestor, delegados, dono/moderadores da comunidade."""
    if usuario.equipe_moderacao:
        return True
    if escopo == "geral":
        return False
    obj = carregar(s, escopo, escopo_id)
    if escopo == "comunidade":
        m = _membro_comunidade(s, obj.id, usuario)
        return bool(m and m.status == "ativo" and m.papel in PAPEIS_MODERACAO_COMUNIDADE)
    if escopo == "atividade" and obj.organizador_id == usuario.id:
        return True
    if escopo == "campeonato" and srv_campeonatos.pode_gerir(obj, usuario):
        return True
    return bool(s.get(Moderador, (escopo, escopo_id, usuario.id)))


def pode_ler(s: SessaoORM, usuario: Usuario, escopo: str, escopo_id: int | None) -> bool:
    if escopo == "geral" or usuario.equipe_moderacao:
        return True
    obj = carregar(s, escopo, escopo_id)
    if eh_moderador(s, usuario, escopo, escopo_id):
        return True
    if escopo == "atividade":
        return bool(s.scalar(select(Participacao.id).where(Participacao.atividade_id == obj.id, Participacao.usuario_id == usuario.id, Participacao.status.in_((CONFIRMADO, ESPERA)))))
    if escopo == "campeonato":
        return bool(
            s.scalar(
                select(EquipeMembro.usuario_id)
                .join(Equipe, Equipe.id == EquipeMembro.equipe_id)
                .where(Equipe.campeonato_id == obj.id, Equipe.status.in_(("pendente", "confirmada")), EquipeMembro.usuario_id == usuario.id, EquipeMembro.status == M_CONFIRMADO)
            )
        )
    m = _membro_comunidade(s, obj.id, usuario)
    if m is not None:
        return m.status == "ativo"
    return obj.visibilidade == "publica"  # comunidade pública: qualquer um lê (não banido)


def pode_postar(s: SessaoORM, usuario: Usuario, escopo: str, escopo_id: int | None) -> bool:
    if escopo == "geral":
        return True
    if escopo == "comunidade":
        m = _membro_comunidade(s, escopo_id, usuario)
        return bool(m and m.status == "ativo") or usuario.admin
    return pode_ler(s, usuario, escopo, escopo_id)


def pode_replicar(s: SessaoORM, escopo: str, escopo_id: int | None) -> bool:
    """Só vai para o feed geral quem é público: atividade pública, campeonato, comunidade pública.
    Atividade 'só autorizados' ou 'por link' e comunidade fechada nunca vazam para o geral."""
    if escopo == "geral":
        return False
    obj = carregar(s, escopo, escopo_id)
    if escopo == "atividade":
        return obj.visibilidade == "publica"
    if escopo == "comunidade":
        return obj.visibilidade == "publica"
    return True


def moderadores(s: SessaoORM, escopo: str, escopo_id: int) -> list[Usuario]:
    if escopo == "comunidade":
        return [m.usuario for m in s.scalars(select(ComunidadeMembro).where(ComunidadeMembro.comunidade_id == escopo_id, ComunidadeMembro.papel.in_(PAPEIS_MODERACAO_COMUNIDADE)))]
    return [m.usuario for m in s.scalars(select(Moderador).where(Moderador.escopo == escopo, Moderador.escopo_id == escopo_id))]


def definir_moderador(s: SessaoORM, escopo: str, escopo_id: int, por: Usuario, alvo: Usuario, ligado: bool) -> None:
    """O organizador (ou quem gere o campeonato) delega o cuidado do mural a outra pessoa."""
    from . import auditoria

    if escopo not in ("atividade", "campeonato"):
        raise ErroNegocio("Moderadores da comunidade são definidos pelos papéis dela.")
    obj = carregar(s, escopo, escopo_id)
    dono = obj.organizador_id == por.id if escopo == "atividade" else srv_campeonatos.pode_gerir(obj, por)
    if not dono and not por.admin:
        raise SemPermissao("Só quem organiza pode escolher quem cuida do mural.")
    existente = s.get(Moderador, (escopo, escopo_id, alvo.id))
    if ligado and existente is None:
        s.add(Moderador(escopo=escopo, escopo_id=escopo_id, usuario_id=alvo.id, concedido_por=por.id))
        notificacoes.avisar(s, alvo.id, "moderacao", f"Você agora cuida do mural de {obj.nome}", f"{por.arroba} indicou você como moderador.", contexto(s, escopo, escopo_id)["link"], None, f"mod:{escopo}:{escopo_id}:{alvo.id}")
    elif not ligado and existente is not None:
        s.delete(existente)
    else:
        return
    auditoria.registrar(s, por.id, "moderador_definir", escopo, escopo_id, alvo=alvo.id, ligado=ligado)
    s.commit()
