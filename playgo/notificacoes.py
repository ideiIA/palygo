"""Caixa de entrada do atleta (seção 10 do projeto). O envio externo (push) é fase futura; hoje a
notificação vive no banco e o site e o app a leem."""

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as SessaoORM

from .models import Notificacao, Usuario


def avisar(
    s: SessaoORM,
    usuario_id: int,
    tipo: str,
    titulo: str,
    corpo: str = "",
    link: str | None = None,
    atividade_id: int | None = None,
    chave: str | None = None,
) -> Notificacao | None:
    """Grava o aviso. Com `chave`, o mesmo aviso não é gravado duas vezes para a mesma pessoa."""
    n = Notificacao(usuario_id=usuario_id, tipo=tipo, titulo=titulo, corpo=corpo, link=link, atividade_id=atividade_id, chave=chave)
    try:
        with s.begin_nested():
            s.add(n)
            s.flush()
    except IntegrityError:
        return None
    return n


def listar(s: SessaoORM, usuario: Usuario, limite: int = 50) -> list[Notificacao]:
    return list(s.scalars(select(Notificacao).where(Notificacao.usuario_id == usuario.id).order_by(Notificacao.id.desc()).limit(limite)))


def nao_lidas(s: SessaoORM, usuario: Usuario) -> int:
    return s.scalar(select(func.count()).select_from(Notificacao).where(Notificacao.usuario_id == usuario.id, ~Notificacao.lida)) or 0


def marcar_lidas(s: SessaoORM, usuario: Usuario, ids: list[int] | None = None) -> None:
    q = update(Notificacao).where(Notificacao.usuario_id == usuario.id, ~Notificacao.lida)
    if ids:
        q = q.where(Notificacao.id.in_(ids))
    s.execute(q.values(lida=True))
    s.commit()
