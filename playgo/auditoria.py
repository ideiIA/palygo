"""Trilha de interações guardada para resguardo legal (Marco Civil, art. 15; LGPD, arts. 7º e 16).
Cada ação relevante grava IP, porta, data/hora, usuário e o objeto. A tabela só aceita inserção."""

from contextvars import ContextVar
from typing import Any

from sqlalchemy.orm import Session as SessaoORM

from .config import settings
from .models import Registro

_contexto: ContextVar[dict | None] = ContextVar("playgo_requisicao", default=None)


def ip_do_cliente(request) -> tuple[str | None, int | None]:
    """IP e porta de origem. X-Forwarded-For só vale atrás de proxy de confiança (PLAYGO_CONFIAR_PROXY)."""
    ip = request.client.host if request.client else None
    porta = request.client.port if request.client else None
    if settings.confiar_proxy:
        encaminhado = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if encaminhado:
            ip = encaminhado
    return ip, porta


def definir_contexto(request):
    """Chamado pelo middleware: guarda de onde veio a requisição para todos os registros dela."""
    ip, porta = ip_do_cliente(request)
    return _contexto.set({"ip": ip, "porta": porta, "user_agent": (request.headers.get("user-agent") or "")[:300]})


def contexto() -> dict:
    return _contexto.get() or {}


def registrar(s: SessaoORM, usuario_id: int | None, acao: str, objeto_tipo: str | None = None, objeto_id: int | None = None, commit: bool = False, **detalhes: Any) -> Registro:
    """Acrescenta um registro. Sem `commit`, vai junto com a transação de quem chamou."""
    c = contexto()
    r = Registro(
        usuario_id=usuario_id, acao=acao, objeto_tipo=objeto_tipo, objeto_id=objeto_id,
        ip=c.get("ip"), porta=c.get("porta"), user_agent=c.get("user_agent"),
        detalhes={k: (str(v)[:500] if not isinstance(v, (int, float, bool, type(None))) else v) for k, v in detalhes.items()} or None,
    )
    s.add(r)
    if commit:
        s.commit()
    return r
