"""Direitos do titular (LGPD, art. 18): cópia dos dados, exclusão da conta (anonimização) e purga por prazo.

Equilíbrio entre apagar e guardar: ao excluir a conta, os dados pessoais somem (nome, e-mail, @, foto, local…),
mas os registros de interação e o conteúdo ocultado/excluído ficam, de forma restrita, pelo prazo legal
(`retencao_registros_dias`) — Marco Civil e defesa em processos — e depois são eliminados por `purgar`."""

from datetime import timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session as SessaoORM

from . import auditoria, midia, seguranca
from .config import settings
from .db import agora
from .erros import ErroNegocio
from .models import (
    ATIVAS,
    P_EXCLUIDA,
    AceiteTermos,
    Atividade,
    Comentario,
    ComunidadeMembro,
    GrupoMembro,
    GrupoMensagem,
    Notificacao,
    Participacao,
    Publicacao,
    PublicacaoVersao,
    Registro,
    Usuario,
)


def exportar(s: SessaoORM, u: Usuario) -> dict:
    """Cópia legível dos dados da pessoa (portabilidade e acesso)."""
    from . import contas

    perfil = contas.dados_publicos(u)
    perfil.pop("pendencia", None)
    publicacoes = list(s.scalars(select(Publicacao).where(Publicacao.autor_id == u.id).order_by(Publicacao.id)).unique())
    auditoria.registrar(s, u.id, "dados_exportados", "usuario", u.id)
    s.commit()
    return {
        "gerado_em": agora().isoformat(timespec="seconds"),
        "perfil": perfil,
        "aceites_termos": [{"versao": a.versao, "em": a.aceito_em.isoformat(timespec="seconds"), "ip": a.ip} for a in s.scalars(select(AceiteTermos).where(AceiteTermos.usuario_id == u.id))],
        "participacoes": [{"atividade_id": p.atividade_id, "status": p.status, "em": p.criado_em.isoformat(timespec="seconds")} for p in s.scalars(select(Participacao).where(Participacao.usuario_id == u.id))],
        "grupos": [m.grupo_id for m in s.scalars(select(GrupoMembro).where(GrupoMembro.usuario_id == u.id))],
        "comunidades": [{"comunidade_id": m.comunidade_id, "papel": m.papel, "status": m.status} for m in s.scalars(select(ComunidadeMembro).where(ComunidadeMembro.usuario_id == u.id))],
        "publicacoes": [
            {
                "id": p.id, "escopo": p.escopo, "escopo_id": p.escopo_id, "texto": p.texto, "local": p.local_nome, "latitude": p.latitude, "longitude": p.longitude,
                "status": p.status, "criada_em": p.criado_em.isoformat(timespec="seconds"), "editada_em": p.editado_em.isoformat(timespec="seconds") if p.editado_em else None,
                "midias": [{"tipo": m.tipo, "sha256": m.sha256} for m in p.midias],
                "versoes_anteriores": [v.texto for v in s.scalars(select(PublicacaoVersao).where(PublicacaoVersao.publicacao_id == p.id).order_by(PublicacaoVersao.id))],
            }
            for p in publicacoes
        ],
        "comentarios": [{"id": c.id, "publicacao_id": c.publicacao_id, "texto": c.texto, "status": c.status, "em": c.criado_em.isoformat(timespec="seconds")} for c in s.scalars(select(Comentario).where(Comentario.autor_id == u.id).order_by(Comentario.id)).unique()],
        "mensagens_de_grupo": [{"grupo_id": m.grupo_id, "texto": m.texto, "em": m.criado_em.isoformat(timespec="seconds")} for m in s.scalars(select(GrupoMensagem).where(GrupoMensagem.usuario_id == u.id)).unique()],
        "registros_de_acesso_e_interacao": [
            {"em": r.em.isoformat(timespec="seconds"), "acao": r.acao, "objeto": f"{r.objeto_tipo}:{r.objeto_id}" if r.objeto_tipo else None, "ip": r.ip}
            for r in s.scalars(select(Registro).where(Registro.usuario_id == u.id).order_by(Registro.id.desc()).limit(2000))
        ],
    }


def excluir_conta(s: SessaoORM, u: Usuario, senha: str) -> None:
    """Anonimiza a conta. Exige a senha. Libera as vagas, cancela o que a pessoa organizava e some do app."""
    from . import atividades, vagas

    if not seguranca.conferir(senha, u.senha_hash):
        raise ErroNegocio("Senha incorreta.")
    if u.admin and not s.scalar(select(Usuario.id).where(Usuario.admin, Usuario.ativo, Usuario.id != u.id).limit(1)):
        raise ErroNegocio("Você é o único administrador. Torne outra pessoa administradora antes de excluir a conta.")
    n = agora()
    # O que a pessoa organizava e ainda vai acontecer é cancelado; as participações futuras liberam a vaga.
    for a in s.scalars(select(Atividade).where(Atividade.organizador_id == u.id, Atividade.status == "aberta", Atividade.inicio >= n)).unique().all():
        atividades.cancelar(s, a.id, u)
    for p in s.scalars(select(Participacao).where(Participacao.usuario_id == u.id, Participacao.status.in_(ATIVAS))).all():
        try:
            vagas.sair(s, p.atividade_id, u)
        except ErroNegocio:
            pass  # organizadora de atividade passada: nada a liberar
    # Conteúdo some do app; o texto fica guardado, restrito, até o fim do prazo legal
    for p in s.scalars(select(Publicacao).where(Publicacao.autor_id == u.id, Publicacao.status != P_EXCLUIDA)).unique():
        p.status, p.excluido_em = P_EXCLUIDA, n
    for c in s.scalars(select(Comentario).where(Comentario.autor_id == u.id, Comentario.status != P_EXCLUIDA)).unique():
        c.status, c.excluido_em = P_EXCLUIDA, n
    s.execute(delete(GrupoMembro).where(GrupoMembro.usuario_id == u.id))
    s.execute(delete(ComunidadeMembro).where(ComunidadeMembro.usuario_id == u.id))
    s.execute(delete(Notificacao).where(Notificacao.usuario_id == u.id))
    u.esportes.clear()
    from . import contas

    midia.remover_arquivos(contas._arquivo_da_foto(u))
    u.nome, u.email, u.usuario = "Usuário removido", f"removido+{u.id}@playgo.invalid", f"removido{u.id}"
    u.senha_hash = seguranca.gerar_hash(seguranca.chave_sessao() + str(u.id) + str(n))  # impossível de adivinhar
    u.foto_url = u.cidade = u.sexo = u.nascimento = u.latitude = u.longitude = None
    u.disponibilidade, u.consent_localizacao, u.consent_localizacao_em = [], False, n
    u.ativo, u.admin, u.moderador, u.gestor, u.anonimizado_em = False, False, False, False, n
    u.notif_vagas = u.notif_lembretes = u.notif_campeonatos = u.notif_grupos = False
    auditoria.registrar(s, u.id, "conta_excluida", "usuario", u.id)
    s.commit()


def purgar(s: SessaoORM) -> dict:
    """Elimina o que passou do prazo de guarda: registros de interação e publicações excluídas (com os arquivos).
    Roda sob demanda (`python -m playgo purgar`); é a única operação que o gatilho de somente-inserção libera."""
    limite = agora() - timedelta(days=settings.retencao_registros_dias)
    antigas = list(s.scalars(select(Publicacao).where(Publicacao.status == P_EXCLUIDA, Publicacao.excluido_em < limite)).unique())
    arquivos = [(m.arquivo, m.miniatura) for p in antigas for m in p.midias]
    for p in antigas:
        s.delete(p)
    s.flush()
    for arq, mini in arquivos:
        midia.remover_arquivos(arq, mini)
    s.execute(text("SET LOCAL playgo.purga = 'on'"))
    removidos = s.execute(delete(Registro).where(Registro.em < limite)).rowcount
    s.commit()
    return {"registros": removidos, "publicacoes": len(antigas), "arquivos": len(arquivos)}
