"""API da edição do campeonato e do elenco das equipes (nome, RG, técnico, capitão)."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel

from .. import campeonatos, detalhes, elenco
from ..deps import AtualApi, Sessao

router = APIRouter(prefix="/api/v1")


class CampeonatoEdicaoIn(BaseModel):
    """Só o que for enviado muda."""

    nome: str | None = None
    categoria: str | None = None
    descricao: str | None = None
    regulamento: str | None = None
    premiacao: str | None = None
    premiacao_valor: Decimal | None = None
    local_nome: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    inscricao_ate: date | None = None
    max_equipes: int | None = None
    atletas_por_equipe: int | None = None
    valor_inscricao: Decimal | None = None
    cadastro_elenco: bool | None = None


class ComponenteIn(BaseModel):
    nome: str
    rg: str
    funcao: str = "atleta"
    capitao: bool = False


@router.put("/campeonatos/{campeonato_id}")
def editar_campeonato(campeonato_id: int, corpo: CampeonatoEdicaoIn, u: AtualApi, s: Sessao):
    campos = corpo.model_dump(exclude_unset=True)
    # nulos explícitos limpam campos de texto; datas e números nulos são ignorados (não dá para apagar)
    obrigatorios = ("nome", "data_inicio", "inscricao_ate", "max_equipes", "atletas_por_equipe", "valor_inscricao", "cadastro_elenco", "local_nome")
    campos = {k: v for k, v in campos.items() if v is not None or k not in obrigatorios}
    c = campeonatos.editar(s, campeonato_id, u, **campos)
    return detalhes.campeonato(s, c, u)


@router.get("/equipes/{equipe_id}/componentes")
def listar_componentes(equipe_id: int, u: AtualApi, s: Sessao):
    return elenco.listar(s, equipe_id, u)


@router.post("/equipes/{equipe_id}/componentes", status_code=201)
def adicionar_componente(equipe_id: int, corpo: ComponenteIn, u: AtualApi, s: Sessao):
    return elenco.adicionar(s, equipe_id, u, corpo.nome, corpo.rg, corpo.funcao, corpo.capitao)


@router.put("/equipes/{equipe_id}/componentes/{componente_id}")
def atualizar_componente(equipe_id: int, componente_id: int, corpo: ComponenteIn, u: AtualApi, s: Sessao):
    return elenco.atualizar(s, equipe_id, componente_id, u, corpo.nome, corpo.rg, corpo.funcao, corpo.capitao)


@router.post("/equipes/{equipe_id}/componentes/{componente_id}/capitao")
def marcar_capitao(equipe_id: int, componente_id: int, u: AtualApi, s: Sessao):
    return elenco.definir_capitao(s, equipe_id, componente_id, u)


@router.delete("/equipes/{equipe_id}/componentes/{componente_id}")
def remover_componente(equipe_id: int, componente_id: int, u: AtualApi, s: Sessao):
    return elenco.remover(s, equipe_id, componente_id, u)
