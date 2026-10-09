"""Sorteio do chaveamento, acompanhamento dos jogos pelas chaves e jogo ao vivo com placar (RF-009).

Formatos: `eliminatoria` (mata-mata com folgas, o vencedor avança sozinho) e `pontos_corridos` (todos contra todos, com
classificação). Quem gere o campeonato (organizador, gestor da arena, admin) sorteia e conduz; os **mesários** que ele indica
também iniciam, marcam o placar e encerram. Qualquer pessoa logada acompanha.

Regras de corrida: o placar muda sob trava de linha (dois mesários clicando juntos não perdem ponto) e todo jogo guarda
uma linha do tempo (`JogoEvento`). No Vercel não há conexão aberta: quem acompanha consulta de poucos em poucos segundos."""

import math
import random
import secrets
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as SessaoORM

from . import auditoria, campeonatos, notificacoes
from .db import agora
from .erros import ErroNegocio, NaoEncontrado, SemPermissao
from .models import (
    C_ANDAMENTO,
    C_CANCELADO,
    C_ENCERRADO,
    E_CONFIRMADA,
    J_AGENDADO,
    J_AO_VIVO,
    J_ENCERRADO,
    M_CONFIRMADO,
    Campeonato,
    CampeonatoMesario,
    Equipe,
    EquipeMembro,
    ChaveEquipe,
    Jogo,
    JogoEvento,
    Usuario,
)

FORMATOS = {
    "eliminatoria": "Eliminatória (mata-mata)",
    "pontos_corridos": "Pontos corridos (todos contra todos)",
    "grupos": "Fase de grupos + mata-mata",
}
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
PONTOS = {"vitoria": 3, "empate": 1, "derrota": 0}
MAX_PLACAR = 999


# ---------------------------------------------------------------- permissões


def eh_mesario(s: SessaoORM, c: Campeonato, u: Usuario) -> bool:
    return s.get(CampeonatoMesario, (c.id, u.id)) is not None


def pode_pontuar(s: SessaoORM, c: Campeonato, u: Usuario) -> bool:
    return campeonatos.pode_gerir(c, u) or eh_mesario(s, c, u)


def _exigir_pontuar(s: SessaoORM, c: Campeonato, u: Usuario) -> None:
    if not pode_pontuar(s, c, u):
        raise SemPermissao("Só a organização e os mesários indicados conduzem os jogos.")


def mesarios(s: SessaoORM, c: Campeonato) -> list[dict]:
    linhas = s.scalars(select(CampeonatoMesario).where(CampeonatoMesario.campeonato_id == c.id).order_by(CampeonatoMesario.criado_em)).unique()
    return [{"usuario_id": m.usuario_id, "arroba": m.usuario.arroba} for m in linhas]


def adicionar_mesario(s: SessaoORM, campeonato_id: int, por: Usuario, usuario_id: int) -> list[dict]:
    c = campeonatos.obter(s, campeonato_id)
    campeonatos.exigir_gestao(c, por)
    alvo = s.get(Usuario, usuario_id)
    if alvo is None or not alvo.ativo or not alvo.usuario:
        raise NaoEncontrado("Pessoa não encontrada.")
    if s.get(CampeonatoMesario, (c.id, alvo.id)) is None:
        s.add(CampeonatoMesario(campeonato_id=c.id, usuario_id=alvo.id))
        auditoria.registrar(s, por.id, "mesario_adicionar", "campeonato", c.id, mesario=alvo.id)
        notificacoes.avisar(s, alvo.id, "campeonato", f"📋 Você é mesário de {c.nome}", "Você pode iniciar jogos e marcar o placar ao vivo.", f"/campeonatos/{c.id}/ao-vivo", None, f"mesario:{c.id}:{alvo.id}")
        s.commit()
    return mesarios(s, c)


def remover_mesario(s: SessaoORM, campeonato_id: int, por: Usuario, usuario_id: int) -> list[dict]:
    c = campeonatos.obter(s, campeonato_id)
    campeonatos.exigir_gestao(c, por)
    m = s.get(CampeonatoMesario, (c.id, usuario_id))
    if m is not None:
        s.delete(m)
        auditoria.registrar(s, por.id, "mesario_remover", "campeonato", c.id, mesario=usuario_id)
        s.commit()
    return mesarios(s, c)


# ---------------------------------------------------------------- sorteio


def _semeadura(tamanho: int) -> list[int]:
    """Ordem padrão de chave (1×8, 4×5, 2×7, 3×6…): os melhores cabeças só se cruzam o mais tarde possível."""
    ordem = [1]
    while len(ordem) < tamanho:
        n = len(ordem) * 2
        ordem = [x for s_ in ordem for x in (s_, n + 1 - s_)]
    return ordem


def _nome_rodada(restantes: int, rodada: int) -> str:
    return {2: "Final", 4: "Semifinal", 8: "Quartas de final", 16: "Oitavas de final"}.get(restantes, f"Fase {rodada}")


def _pessoas(s: SessaoORM, equipe_id: int) -> set[int]:
    e = s.get(Equipe, equipe_id)
    if e is None:
        return set()
    ids = set(s.scalars(select(EquipeMembro.usuario_id).where(EquipeMembro.equipe_id == equipe_id, EquipeMembro.status == M_CONFIRMADO)))
    return ids | {e.capitao_id}


def _avisar_equipes(s: SessaoORM, c: Campeonato, equipes: list[int | None], titulo: str, corpo: str, chave: str, excluir: int | None = None) -> None:
    link = f"/campeonatos/{c.id}/chaves"
    for eid in {e for e in equipes if e}:
        for uid in _pessoas(s, eid):
            if uid != excluir:
                notificacoes.avisar(s, uid, "campeonato", titulo, corpo, link, None, f"{chave}:{uid}")


def sortear(
    s: SessaoORM, campeonato_id: int, por: Usuario, formato: str, grupos: int | None = None, classificam: int | None = None, cabecas: list[int] | None = None
) -> dict:
    """`cabecas` = ids das equipes cabeças de chave, em ordem (o primeiro é o nº 1). Na eliminatória ocupam as melhores posições da chave
    (e as folgas); na fase de grupos cada grupo recebe no máximo um. As demais equipes são sorteadas."""
    c = campeonatos.obter(s, campeonato_id)
    campeonatos.exigir_gestao(c, por)
    if formato not in FORMATOS:
        raise ErroNegocio("Escolha o formato: eliminatória, pontos corridos ou fase de grupos.")
    if c.status == C_CANCELADO:
        raise ErroNegocio("Este campeonato foi cancelado.")
    equipes = list(s.scalars(select(Equipe).where(Equipe.campeonato_id == c.id, Equipe.status == E_CONFIRMADA).order_by(Equipe.id)))
    if len(equipes) < 2:
        raise ErroNegocio("Confirme pelo menos 2 equipes para sortear o chaveamento.")
    cabecas = list(cabecas or [])
    por_id = {e.id: e for e in equipes}
    if len(set(cabecas)) != len(cabecas) or any(i not in por_id for i in cabecas):
        raise ErroNegocio("Os cabeças de chave precisam ser equipes confirmadas, sem repetir.")
    q = None
    if formato == "grupos":
        n = len(equipes)
        if n < 4:
            raise ErroNegocio("A fase de grupos precisa de pelo menos 4 equipes confirmadas.")
        if not grupos or not 2 <= grupos <= n // 2:
            raise ErroNegocio(f"Escolha de 2 a {n // 2} grupos (cada grupo precisa de pelo menos 2 equipes).")
        if len(cabecas) > grupos:
            raise ErroNegocio("Há mais cabeças de chave do que grupos: cada grupo recebe no máximo um.")
        q = classificam or 2
        if not 1 <= q <= n // grupos:
            raise ErroNegocio(f"Classificam de 1 a {n // grupos} equipes por grupo.")
        if grupos * q < 2:
            raise ErroNegocio("O mata-mata precisa de pelo menos 2 classificados.")
    elif formato == "pontos_corridos":
        cabecas = []  # todos jogam contra todos: a posição na tabela não depende do sorteio
    _limpar_chaves(s, c)

    semente = secrets.randbits(62)
    rnd = random.Random(semente)
    resto = [e for e in equipes if e.id not in cabecas]
    rnd.shuffle(resto)
    if formato == "eliminatoria":
        _montar_eliminatoria(s, c, [por_id[i] for i in cabecas] + resto)  # a ordem é a de cabeça de chave
        s.add_all(ChaveEquipe(campeonato_id=c.id, equipe_id=i, cabeca=n_ + 1) for n_, i in enumerate(cabecas))
    elif formato == "grupos":
        for g, lista in enumerate(_distribuir(por_id, cabecas, resto, grupos)):
            _montar_pontos_corridos(s, c, lista, grupo=LETRAS[g], fase="grupos")
            for e in lista:
                s.add(ChaveEquipe(campeonato_id=c.id, equipe_id=e.id, grupo=LETRAS[g], cabeca=cabecas.index(e.id) + 1 if e.id in cabecas else None))
    else:
        _montar_pontos_corridos(s, c, resto)
    c.grupos_qtd, c.classificam = (grupos, q) if formato == "grupos" else (None, None)
    c.formato, c.sorteado_em, c.sorteio_semente = formato, agora(), semente
    if c.status != C_ENCERRADO:
        c.status = C_ANDAMENTO
    auditoria.registrar(s, por.id, "campeonato_sorteio", "campeonato", c.id, formato=formato, equipes=len(equipes), semente=semente, grupos=grupos, cabecas=cabecas)
    s.flush()
    _avisar_equipes(s, c, [e.id for e in equipes], f"🎲 Sorteio feito: {c.nome}", "Veja seus jogos nas chaves do campeonato.", f"sorteio:{c.id}:{semente}", excluir=por.id)
    s.commit()
    return {"formato": formato, "equipes": len(equipes), "semente": semente}


def _limpar_chaves(s: SessaoORM, c: Campeonato) -> None:
    """Apaga o sorteio anterior, se nada começou (folgas da eliminatória já nascem encerradas e não contam)."""
    antigos = list(s.scalars(select(Jogo).where(Jogo.campeonato_id == c.id)))
    if any(j.status != J_AGENDADO and not j.folga for j in antigos):
        raise ErroNegocio("Já há jogos começados ou encerrados. Não dá para sortear de novo sem perder o placar.")
    for j in antigos:
        j.proximo_id = None
    s.flush()
    for j in antigos:
        s.delete(j)
    for k in s.scalars(select(ChaveEquipe).where(ChaveEquipe.campeonato_id == c.id)):
        s.delete(k)
    s.flush()


def _distribuir(por_id: dict[int, Equipe], cabecas: list[int], resto: list[Equipe], grupos: int) -> list[list[Equipe]]:
    """Cabeça nº k vai para o grupo k; as outras equipes (já embaralhadas) vão sempre para o grupo com menos equipes."""
    n = len(por_id)
    tamanhos = [n // grupos + (1 if g < n % grupos else 0) for g in range(grupos)]
    lista: list[list[Equipe]] = [[] for _ in range(grupos)]
    for g, i in enumerate(cabecas):
        lista[g].append(por_id[i])
    for e in resto:
        g = min((g for g in range(grupos) if len(lista[g]) < tamanhos[g]), key=lambda g: (len(lista[g]), g))
        lista[g].append(e)
    return lista


def _montar_eliminatoria(s: SessaoORM, c: Campeonato, equipes: list[Equipe], fase: str | None = None) -> None:
    """`equipes` já vem na ordem de cabeça de chave (a 1ª é a nº 1); quem sobra de vaga (folga) são os melhores colocados."""
    n = len(equipes)
    tamanho = 1 << math.ceil(math.log2(n))
    rodadas = int(math.log2(tamanho))
    por_rodada: list[list[Jogo]] = []
    for r in range(1, rodadas + 1):
        restantes = tamanho >> (r - 1)
        jogos = [Jogo(campeonato_id=c.id, rodada=r, posicao=p, rodada_nome=_nome_rodada(restantes, r), fase=fase) for p in range(restantes // 2)]
        s.add_all(jogos)
        por_rodada.append(jogos)
    ordem = _semeadura(tamanho)
    for p, j in enumerate(por_rodada[0]):
        a, b = ordem[2 * p], ordem[2 * p + 1]
        j.equipe_a_id = equipes[a - 1].id if a <= n else None
        j.equipe_b_id = equipes[b - 1].id if b <= n else None
    s.flush()
    for r, jogos in enumerate(por_rodada[:-1]):
        for p, j in enumerate(jogos):
            prox = por_rodada[r + 1][p // 2]
            j.proximo_id, j.proximo_lado = prox.id, "a" if p % 2 == 0 else "b"
    s.flush()
    for j in por_rodada[0]:  # folga: quem não tem adversário já passa para a rodada seguinte
        if (j.equipe_a_id is None) != (j.equipe_b_id is None):
            j.folga, j.status = True, J_ENCERRADO
            j.vencedor_id = j.equipe_a_id or j.equipe_b_id
            j.encerrado_em = agora()
            _avancar(s, j)


def _montar_pontos_corridos(s: SessaoORM, c: Campeonato, equipes: list[Equipe], grupo: str | None = None, fase: str | None = None) -> None:
    lista: list[Equipe | None] = list(equipes)
    if len(lista) % 2:
        lista.append(None)
    n = len(lista)
    for r in range(n - 1):
        pos = 0
        for i in range(n // 2):
            a, b = lista[i], lista[n - 1 - i]
            if a is None or b is None:
                continue
            if r % 2 and i == 0:
                a, b = b, a
            nome = f"Grupo {grupo} · Rodada {r + 1}" if grupo else f"Rodada {r + 1}"
            s.add(Jogo(campeonato_id=c.id, rodada=r + 1, posicao=pos, rodada_nome=nome, equipe_a_id=a.id, equipe_b_id=b.id, grupo=grupo, fase=fase))
            pos += 1
        lista = [lista[0], lista[-1], *lista[1:-1]]


def _avancar(s: SessaoORM, j: Jogo) -> None:
    if j.proximo_id is None or j.vencedor_id is None:
        return
    prox = s.get(Jogo, j.proximo_id)
    vencedor = s.get(Equipe, j.vencedor_id)  # a relação também: a sessão não expira ao salvar e `prox.equipe_a` ficaria velha
    if j.proximo_lado == "a":
        prox.equipe_a = vencedor
    else:
        prox.equipe_b = vencedor


# ---------------------------------------------------------------- jogo ao vivo


def _travar(s: SessaoORM, campeonato_id: int, jogo_id: int) -> tuple[Campeonato, Jogo]:
    c = campeonatos.obter(s, campeonato_id)
    j = s.scalar(select(Jogo).where(Jogo.id == jogo_id, Jogo.campeonato_id == c.id).with_for_update(of=Jogo).execution_options(populate_existing=True))
    if j is None:
        raise NaoEncontrado("Jogo não encontrado.")
    return c, j


def _evento(s: SessaoORM, j: Jogo, tipo: str, por: Usuario, texto: str | None = None, equipe_id: int | None = None) -> None:
    s.add(JogoEvento(jogo_id=j.id, tipo=tipo, texto=texto, equipe_id=equipe_id, placar_a=j.placar_a, placar_b=j.placar_b, autor_id=por.id))


def _nome(e: Equipe | None) -> str:
    return e.nome if e else "a definir"


def agendar(s: SessaoORM, campeonato_id: int, jogo_id: int, por: Usuario, inicio: datetime | None, local: str | None) -> Jogo:
    c, j = _travar(s, campeonato_id, jogo_id)
    _exigir_pontuar(s, c, por)
    if j.status != J_AGENDADO:
        raise ErroNegocio("Só dá para marcar horário de um jogo que ainda não começou.")
    j.inicio_previsto = inicio
    j.local = (local or "").strip()[:120] or None
    auditoria.registrar(s, por.id, "jogo_agendar", "jogo", j.id, inicio=inicio, local=j.local)
    s.commit()
    return j


def agendar_lote(
    s: SessaoORM, campeonato_id: int, por: Usuario, escopo: str, inicio: datetime, duracao_min: int, intervalo_min: int = 0,
    locais: list[str] | None = None, ate: time | None = None, sobrescrever: bool = True,
) -> dict:
    """Define os horários de vários jogos de uma vez, um depois do outro: o 1º começa em `inicio` e cada jogo seguinte entra depois de
    `duracao_min` + `intervalo_min`. Com várias quadras (`locais`) os jogos de uma mesma rodada acontecem juntos, uma quadra cada.
    Cada rodada começa num horário novo (a equipe não joga duas vezes ao mesmo tempo e o mata-mata espera a rodada anterior).
    `ate`: horário-limite do dia; o que não couber continua no dia seguinte, na hora de `inicio`.
    `escopo`: "todos", "grupos", "mata_mata" ou "rodada:N". Só jogos ainda não começados."""
    c = campeonatos.obter(s, campeonato_id)
    campeonatos.exigir_gestao(c, por)
    if not 5 <= duracao_min <= 600:
        raise ErroNegocio("A duração de cada jogo vai de 5 a 600 minutos.")
    if not 0 <= intervalo_min <= 240:
        raise ErroNegocio("O intervalo entre jogos vai de 0 a 240 minutos.")
    passo = timedelta(minutes=duracao_min + intervalo_min)
    if ate is not None and (datetime.combine(inicio.date(), ate) - inicio) < timedelta(minutes=duracao_min):
        raise ErroNegocio("O horário-limite do dia precisa deixar espaço para pelo menos um jogo depois do início.")
    quadras = [q.strip()[:120] for q in (locais or []) if q and q.strip()]
    jogos = [j for j in s.scalars(select(Jogo).where(Jogo.campeonato_id == c.id, Jogo.status == J_AGENDADO)) if not j.folga]
    if escopo == "grupos":
        jogos = [j for j in jogos if j.fase == "grupos"]
    elif escopo == "mata_mata":
        jogos = [j for j in jogos if j.fase == "mata_mata"]
    elif escopo.startswith("rodada:"):
        try:
            n = int(escopo.split(":", 1)[1])
        except ValueError:
            raise ErroNegocio("Escolha o que agendar.") from None
        jogos = [j for j in jogos if j.rodada == n and j.fase != "grupos"]
    elif escopo != "todos":
        raise ErroNegocio("Escolha o que agendar.")
    if not sobrescrever:
        jogos = [j for j in jogos if j.inicio_previsto is None]
    if not jogos:
        raise ErroNegocio("Não há jogos para agendar nessa seleção (eles podem já ter começado ou ter horário).")
    jogos.sort(key=lambda j: (1 if j.fase == "mata_mata" else 0, j.rodada, j.grupo or "", j.posicao))

    cursor, ultimo_fim, total = inicio, inicio, 0
    por_rodada: dict[tuple, list[Jogo]] = {}
    for j in jogos:
        por_rodada.setdefault((j.fase or "", j.rodada), []).append(j)
    paralelo = max(1, len(quadras))
    for lista in por_rodada.values():
        for i in range(0, len(lista), paralelo):
            fim = cursor + timedelta(minutes=duracao_min)
            if ate is not None and (fim.date() > cursor.date() or fim.time() > ate):
                cursor = datetime.combine(cursor.date() + timedelta(days=1), inicio.time())  # não cabe hoje: recomeça amanhã
                fim = cursor + timedelta(minutes=duracao_min)
            for k, j in enumerate(lista[i:i + paralelo]):
                j.inicio_previsto = cursor
                if quadras:
                    j.local = quadras[k]
                total += 1
            ultimo_fim = fim
            cursor += passo
    c.duracao_jogo_min = duracao_min
    auditoria.registrar(s, por.id, "campeonato_agenda_lote", "campeonato", c.id, escopo=escopo, inicio=inicio, duracao=duracao_min, intervalo=intervalo_min, jogos=total)
    equipes = {e for j in jogos for e in (j.equipe_a_id, j.equipe_b_id) if e}
    _avisar_equipes(s, c, list(equipes), f"📅 Horários de {c.nome}", "A organização definiu os horários dos jogos. Veja nas chaves.", f"agenda:{c.id}:{agora().strftime('%d%H%M')}", excluir=por.id)
    s.commit()
    return {"agendados": total, "primeiro": _dt(inicio), "ultimo_fim": _dt(ultimo_fim)}


def iniciar(s: SessaoORM, campeonato_id: int, jogo_id: int, por: Usuario) -> Jogo:
    c, j = _travar(s, campeonato_id, jogo_id)
    _exigir_pontuar(s, c, por)
    if j.status != J_AGENDADO:
        raise ErroNegocio("Este jogo já começou ou terminou.")
    if j.equipe_a_id is None or j.equipe_b_id is None:
        raise ErroNegocio("Este jogo ainda não tem as duas equipes definidas.")
    j.status, j.iniciado_em = J_AO_VIVO, agora()
    _evento(s, j, "inicio", por, "Bola rolando!")
    auditoria.registrar(s, por.id, "jogo_iniciar", "jogo", j.id)
    _avisar_equipes(s, c, [j.equipe_a_id, j.equipe_b_id], f"🔴 Ao vivo: {_nome(j.equipe_a)} x {_nome(j.equipe_b)}", f"{c.nome} — acompanhe o placar.", f"jogo-vivo:{j.id}")
    s.commit()
    return j


def _exigir_ao_vivo(j: Jogo) -> None:
    if j.status != J_AO_VIVO:
        raise ErroNegocio("O jogo precisa estar ao vivo para mexer no placar.")


def marcar(s: SessaoORM, campeonato_id: int, jogo_id: int, por: Usuario, lado: str, delta: int) -> Jogo:
    c, j = _travar(s, campeonato_id, jogo_id)
    _exigir_pontuar(s, c, por)
    _exigir_ao_vivo(j)
    if lado not in ("a", "b") or delta not in (1, -1):
        raise ErroNegocio("Marcação inválida.")
    atual = j.placar_a if lado == "a" else j.placar_b
    novo = max(0, min(MAX_PLACAR, atual + delta))
    if novo == atual:
        return j
    if lado == "a":
        j.placar_a = novo
    else:
        j.placar_b = novo
    equipe = j.equipe_a if lado == "a" else j.equipe_b
    _evento(s, j, "placar", por, f"+1 {_nome(equipe)}" if delta > 0 else f"Correção: -1 {_nome(equipe)}", equipe.id if equipe else None)
    auditoria.registrar(s, por.id, "jogo_placar", "jogo", j.id, placar=f"{j.placar_a}x{j.placar_b}")
    s.commit()
    return j


def definir_placar(s: SessaoORM, campeonato_id: int, jogo_id: int, por: Usuario, a: int, b: int) -> Jogo:
    c, j = _travar(s, campeonato_id, jogo_id)
    _exigir_pontuar(s, c, por)
    _exigir_ao_vivo(j)
    if not (0 <= a <= MAX_PLACAR and 0 <= b <= MAX_PLACAR):
        raise ErroNegocio(f"O placar vai de 0 a {MAX_PLACAR}.")
    if (a, b) != (j.placar_a, j.placar_b):
        j.placar_a, j.placar_b = a, b
        _evento(s, j, "placar", por, "Placar ajustado pela mesa")
        auditoria.registrar(s, por.id, "jogo_placar", "jogo", j.id, placar=f"{a}x{b}")
        s.commit()
    return j


def lance(s: SessaoORM, campeonato_id: int, jogo_id: int, por: Usuario, texto: str, equipe_id: int | None = None) -> Jogo:
    c, j = _travar(s, campeonato_id, jogo_id)
    _exigir_pontuar(s, c, por)
    _exigir_ao_vivo(j)
    texto = (texto or "").strip()
    if not texto:
        raise ErroNegocio("Escreva o lance.")
    if len(texto) > 200:
        raise ErroNegocio("O lance passa de 200 caracteres.")
    if equipe_id not in (None, j.equipe_a_id, j.equipe_b_id):
        raise ErroNegocio("A equipe do lance não joga esta partida.")
    _evento(s, j, "lance", por, texto, equipe_id)
    s.commit()
    return j


def encerrar(s: SessaoORM, campeonato_id: int, jogo_id: int, por: Usuario, vencedor_id: int | None = None) -> Jogo:
    c, j = _travar(s, campeonato_id, jogo_id)
    _exigir_pontuar(s, c, por)
    _exigir_ao_vivo(j)
    eliminatoria = c.formato == "eliminatoria" or j.fase == "mata_mata"
    if j.placar_a != j.placar_b:
        j.vencedor_id = j.equipe_a_id if j.placar_a > j.placar_b else j.equipe_b_id
        j.desempate = False
    elif eliminatoria:
        if vencedor_id not in (j.equipe_a_id, j.equipe_b_id) or vencedor_id is None:
            raise ErroNegocio("Empate no mata-mata: informe quem venceu no desempate.")
        j.vencedor_id, j.desempate = vencedor_id, True
    else:
        j.vencedor_id, j.desempate = None, False
    j.status, j.encerrado_em = J_ENCERRADO, agora()
    vencedor = j.equipe_a if j.vencedor_id == j.equipe_a_id else j.equipe_b if j.vencedor_id == j.equipe_b_id else None
    texto = f"Fim de jogo: {j.placar_a} x {j.placar_b}" + (f" — {_nome(vencedor)} vence no desempate" if j.desempate else "")
    _evento(s, j, "fim", por, texto)
    auditoria.registrar(s, por.id, "jogo_encerrar", "jogo", j.id, placar=f"{j.placar_a}x{j.placar_b}", vencedor=j.vencedor_id)
    _avancar(s, j)
    s.flush()
    _gerar_mata_mata_se_pronto(s, c)
    _fechar_campeonato_se_acabou(s, c)
    _avisar_equipes(s, c, [j.equipe_a_id, j.equipe_b_id], f"🏁 Fim de jogo: {_nome(j.equipe_a)} {j.placar_a} x {j.placar_b} {_nome(j.equipe_b)}", c.nome, f"jogo-fim:{j.id}")
    s.commit()
    return j


def _classificados(s: SessaoORM, c: Campeonato, jogos: list[Jogo]) -> list[Equipe]:
    """Os `classificam` primeiros de cada grupo, na ordem de cabeça de chave do mata-mata: todos os 1º (A, B, C…), depois os 2º…
    Com 1º×último no cruzamento padrão, grupos diferentes se enfrentam já na primeira rodada."""
    membros = list(s.scalars(select(ChaveEquipe).where(ChaveEquipe.campeonato_id == c.id, ChaveEquipe.grupo.is_not(None))))
    por_grupo: dict[str, list[Equipe]] = {}
    for m in membros:
        por_grupo.setdefault(m.grupo, []).append(s.get(Equipe, m.equipe_id))
    tabelas = {g: classificacao([j for j in jogos if j.grupo == g], eqs) for g, eqs in sorted(por_grupo.items())}
    ordem: list[Equipe] = []
    nivel: list[int] = []  # colocação no grupo de cada equipe de `ordem` (0 = 1º)
    grupo_de: dict[int, str] = {}
    for pos in range(c.classificam or 2):
        for g in sorted(tabelas):
            e = s.get(Equipe, tabelas[g][pos]["equipe"]["id"])
            ordem.append(e)
            nivel.append(pos)
            grupo_de[e.id] = g
    _evitar_revanche(ordem, nivel, grupo_de)
    return ordem


def _evitar_revanche(ordem: list[Equipe], nivel: list[int], grupo_de: dict[int, str]) -> None:
    """Troca equipes da mesma colocação entre confrontos para que, na 1ª rodada do mata-mata, ninguém reencontre o próprio grupo."""
    n = len(ordem)
    tam = 1 << math.ceil(math.log2(n))
    semeadura = _semeadura(tam)
    pares = [(semeadura[2 * p] - 1, semeadura[2 * p + 1] - 1) for p in range(tam // 2)]

    def conflitos() -> int:
        return sum(1 for a, b in pares if a < n and b < n and grupo_de[ordem[a].id] == grupo_de[ordem[b].id])

    atual = conflitos()
    melhorou = True
    while atual and melhorou:
        melhorou = False
        for a in range(n):
            for b in range(a + 1, n):
                if nivel[a] != nivel[b]:
                    continue
                ordem[a], ordem[b] = ordem[b], ordem[a]
                novo = conflitos()
                if novo < atual:
                    atual, melhorou = novo, True
                else:
                    ordem[a], ordem[b] = ordem[b], ordem[a]


def _gerar_mata_mata_se_pronto(s: SessaoORM, c: Campeonato) -> None:
    """Quando o último jogo da fase de grupos termina, monta o mata-mata com os classificados."""
    if c.formato != "grupos":
        return
    jogos = list(s.scalars(select(Jogo).where(Jogo.campeonato_id == c.id)))
    grupos = [j for j in jogos if j.fase == "grupos"]
    if not grupos or any(j.fase == "mata_mata" for j in jogos) or any(j.status != J_ENCERRADO for j in grupos):
        return
    classificados = _classificados(s, c, grupos)
    _montar_eliminatoria(s, c, classificados, "mata_mata")
    _avisar_equipes(s, c, [e.id for e in classificados], f"➡️ Mata-mata de {c.nome} definido", "Sua equipe se classificou. Veja o cruzamento nas chaves.", f"mata:{c.id}")


def _fechar_campeonato_se_acabou(s: SessaoORM, c: Campeonato) -> None:
    jogos = list(s.scalars(select(Jogo).where(Jogo.campeonato_id == c.id)))
    if c.formato == "grupos" and not any(j.fase == "mata_mata" for j in jogos):
        return  # ainda falta o mata-mata
    if jogos and all(j.status == J_ENCERRADO for j in jogos) and c.status != C_CANCELADO:
        c.status = C_ENCERRADO
        if c.formato in ("eliminatoria", "grupos"):
            final = max((j for j in jogos if j.fase != "grupos"), key=lambda j: j.rodada)
            campeao = final.equipe_a if final.vencedor_id == final.equipe_a_id else final.equipe_b
            if campeao is not None:
                _avisar_equipes(s, c, [campeao.id], f"🏆 Campeões de {c.nome}!", f"{campeao.nome} venceu o campeonato.", f"campeao:{c.id}")


def reabrir(s: SessaoORM, campeonato_id: int, jogo_id: int, por: Usuario) -> Jogo:
    """Corrige um encerramento errado. Só a organização, e só se a rodada seguinte ainda não começou."""
    c, j = _travar(s, campeonato_id, jogo_id)
    campeonatos.exigir_gestao(c, por)
    if j.status != J_ENCERRADO or j.folga:
        raise ErroNegocio("Só dá para reabrir um jogo encerrado.")
    if j.fase == "grupos":  # o mata-mata saiu desta classificação: só dá para refazê-lo se ainda não começou
        mata = list(s.scalars(select(Jogo).where(Jogo.campeonato_id == c.id, Jogo.fase == "mata_mata")))
        if any(x.status != J_AGENDADO and not x.folga for x in mata):
            raise ErroNegocio("O mata-mata já começou; não dá mais para reabrir jogos da fase de grupos.")
        for x in mata:
            x.proximo_id = None
        s.flush()
        for x in mata:
            s.delete(x)
        s.flush()
    if j.proximo_id:
        prox = s.get(Jogo, j.proximo_id)
        if prox.status != J_AGENDADO:
            raise ErroNegocio("O próximo jogo já começou; não dá mais para reabrir este.")
        if j.proximo_lado == "a":
            prox.equipe_a = None
        else:
            prox.equipe_b = None
    j.status, j.vencedor_id, j.desempate, j.encerrado_em = J_AO_VIVO, None, False, None
    if c.status == C_ENCERRADO:
        c.status = C_ANDAMENTO
    _evento(s, j, "reaberto", por, "Jogo reaberto pela organização")
    auditoria.registrar(s, por.id, "jogo_reabrir", "jogo", j.id)
    s.commit()
    return j


# ---------------------------------------------------------------- leitura (chaves, classificação, jogo)


def _eq(e: Equipe | None) -> dict | None:
    return {"id": e.id, "nome": e.nome} if e else None


def _dt(d: datetime | None) -> str | None:
    return d.isoformat(timespec="seconds") if d else None


def jogo_dict(j: Jogo) -> dict:
    return {
        "id": j.id, "rodada": j.rodada, "rodada_nome": j.rodada_nome, "fase": j.fase, "grupo": j.grupo, "posicao": j.posicao, "a": _eq(j.equipe_a), "b": _eq(j.equipe_b),
        "placar_a": j.placar_a, "placar_b": j.placar_b, "status": j.status, "vencedor_id": j.vencedor_id, "desempate": j.desempate, "folga": j.folga,
        "inicio_previsto": _dt(j.inicio_previsto), "local": j.local, "iniciado_em": _dt(j.iniciado_em),
    }


def classificacao(jogos: list[Jogo], equipes: list[Equipe]) -> list[dict]:
    linhas = {e.id: {"equipe": {"id": e.id, "nome": e.nome}, "pontos": 0, "jogos": 0, "vitorias": 0, "empates": 0, "derrotas": 0, "pro": 0, "contra": 0} for e in equipes}
    for j in jogos:
        if j.status != J_ENCERRADO or j.folga or j.equipe_a_id not in linhas or j.equipe_b_id not in linhas:
            continue
        for eid, pro, contra in ((j.equipe_a_id, j.placar_a, j.placar_b), (j.equipe_b_id, j.placar_b, j.placar_a)):
            L = linhas[eid]
            L["jogos"] += 1
            L["pro"] += pro
            L["contra"] += contra
            if pro > contra:
                L["vitorias"] += 1
                L["pontos"] += PONTOS["vitoria"]
            elif pro == contra:
                L["empates"] += 1
                L["pontos"] += PONTOS["empate"]
            else:
                L["derrotas"] += 1
    out = list(linhas.values())
    for L in out:
        L["saldo"] = L["pro"] - L["contra"]
    out.sort(key=lambda L: (-L["pontos"], -L["saldo"], -L["pro"], L["equipe"]["nome"].lower()))
    for i, L in enumerate(out, 1):
        L["posicao"] = i
    return out


def chaveamento(s: SessaoORM, c: Campeonato, u: Usuario) -> dict:
    jogos = list(s.scalars(select(Jogo).where(Jogo.campeonato_id == c.id).order_by(Jogo.rodada, Jogo.posicao).execution_options(populate_existing=True)))
    de_grupo = [j for j in jogos if j.fase == "grupos"]
    chave = [j for j in jogos if j.fase != "grupos"]  # eliminatória, pontos corridos ou o mata-mata depois dos grupos
    rodadas: list[dict] = []
    for j in chave:
        if not rodadas or rodadas[-1]["rodada"] != j.rodada:
            rodadas.append({"rodada": j.rodada, "nome": j.rodada_nome, "jogos": []})
        rodadas[-1]["jogos"].append(jogo_dict(j))
    confirmadas = list(s.scalars(select(Equipe).where(Equipe.campeonato_id == c.id, Equipe.status == E_CONFIRMADA).order_by(Equipe.id)))
    marcas = {k.equipe_id: k for k in s.scalars(select(ChaveEquipe).where(ChaveEquipe.campeonato_id == c.id))}
    grupos_out: list[dict] = []
    for letra in sorted({k.grupo for k in marcas.values() if k.grupo}):
        eqs = [e for e in confirmadas if e.id in marcas and marcas[e.id].grupo == letra]
        js = [j for j in de_grupo if j.grupo == letra]
        rod: list[dict] = []
        for j in js:
            if not rod or rod[-1]["rodada"] != j.rodada:
                rod.append({"rodada": j.rodada, "nome": f"Rodada {j.rodada}", "jogos": []})
            rod[-1]["jogos"].append(jogo_dict(j))
        tabela = classificacao(js, eqs)
        for L in tabela:
            L["classifica"] = L["posicao"] <= (c.classificam or 0)
            L["cabeca"] = marcas[L["equipe"]["id"]].cabeca
        grupos_out.append({"grupo": letra, "classificacao": tabela, "rodadas": rod})
    cabecas = sorted(({"ordem": k.cabeca, "equipe": _eq(next((e for e in confirmadas if e.id == k.equipe_id), None))} for k in marcas.values() if k.cabeca), key=lambda x: x["ordem"])
    campeao = None
    if c.formato in ("eliminatoria", "grupos") and chave:
        final = max(chave, key=lambda j: j.rodada)
        if final.status == J_ENCERRADO and final.vencedor_id:
            campeao = _eq(final.equipe_a if final.vencedor_id == final.equipe_a_id else final.equipe_b)
    elif c.formato == "pontos_corridos" and chave and all(j.status == J_ENCERRADO for j in chave):
        campeao = classificacao(jogos, confirmadas)[0]["equipe"]
    pendentes = campeonatos.contar_pendentes(s, c)
    return {
        "campeonato": {"id": c.id, "nome": c.nome, "status": c.status, "modalidade": c.modalidade.nome, "icone": c.modalidade.icone},
        "formato": c.formato, "formato_nome": FORMATOS.get(c.formato or ""), "sorteado_em": _dt(c.sorteado_em), "semente": str(c.sorteio_semente) if c.sorteio_semente else None,  # texto: passa de 2^53 e o JavaScript perderia dígitos
        "rodadas": rodadas, "ao_vivo": [jogo_dict(j) for j in jogos if j.status == J_AO_VIVO],
        "classificacao": classificacao(chave, confirmadas) if c.formato == "pontos_corridos" else [], "campeao": campeao,
        "grupos": grupos_out, "classificam": c.classificam, "cabecas": cabecas, "duracao_jogo_min": c.duracao_jogo_min,
        "jogos_grupos_restantes": sum(1 for j in de_grupo if j.status != J_ENCERRADO) if c.formato == "grupos" and not chave else 0,
        "equipes": [_eq(e) for e in confirmadas],
        "equipes_confirmadas": len(confirmadas), "equipes_pendentes": pendentes,
        "pode_gerir": campeonatos.pode_gerir(c, u), "pode_pontuar": pode_pontuar(s, c, u),
        "pode_sortear_de_novo": all(j.status == J_AGENDADO or j.folga for j in jogos),
        "mesarios": mesarios(s, c) if campeonatos.pode_gerir(c, u) else [],
    }


def detalhe_jogo(s: SessaoORM, c: Campeonato, jogo_id: int, u: Usuario) -> dict:
    j = s.scalar(select(Jogo).where(Jogo.id == jogo_id, Jogo.campeonato_id == c.id).execution_options(populate_existing=True))
    if j is None:
        raise NaoEncontrado("Jogo não encontrado.")
    eventos = [
        {"id": e.id, "tipo": e.tipo, "texto": e.texto, "equipe_id": e.equipe_id, "placar_a": e.placar_a, "placar_b": e.placar_b, "em": _dt(e.criado_em)}
        for e in j.eventos
    ]
    return jogo_dict(j) | {
        "campeonato": {"id": c.id, "nome": c.nome, "formato": c.formato, "status": c.status},
        "eventos": eventos, "pode_pontuar": pode_pontuar(s, c, u), "pode_gerir": campeonatos.pode_gerir(c, u),
        "mata_mata": c.formato == "eliminatoria" or j.fase == "mata_mata", "agora": _dt(agora()),
    }
