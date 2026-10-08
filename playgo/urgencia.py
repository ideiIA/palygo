"""Priorização por urgência e proximidade (RF-026). Função pura: recebe números, devolve a nota."""

from math import exp

PESO_TEMPO = 0.35
PESO_PROXIMIDADE = 0.30
PESO_VAGAS = 0.20
PESO_FALTA_GENTE = 0.15


def nota(minutos_para_inicio: float, distancia_km: float | None, vagas_restantes: int, falta_gente: bool) -> float:
    """0 a 100. Um jogo a 1 km, que começa em 40 min e precisa de 1 jogador, passa à frente do
    mesmo jogo marcado para a semana seguinte."""
    if vagas_restantes <= 0:
        return 0.0
    # Tempo: pleno na última hora, cai devagar até virar irrelevante em dias.
    folga = max(0.0, minutos_para_inicio - 60)
    tempo = exp(-folga / 480)
    # Proximidade: 1 colado, ~0,37 a 5 km. Sem localização do usuário, não pesa nada.
    proximidade = exp(-distancia_km / 5) if distancia_km is not None else 0.5
    # Vagas: faltar um só pesa mais que faltar seis.
    vagas = 1 / (1 + 0.25 * (vagas_restantes - 1))
    return round(100 * (PESO_TEMPO * tempo + PESO_PROXIMIDADE * proximidade + PESO_VAGAS * vagas + PESO_FALTA_GENTE * falta_gente), 1)


def contagem_regressiva(minutos: float) -> str:
    """'começa em 48 min', 'começa em 1h18', 'começou há 10 min'."""
    m = int(round(minutos))
    if m < 0:
        return f"começou há {-m} min"
    if m < 60:
        return f"começa em {m} min"
    if m < 24 * 60:
        h, r = divmod(m, 60)
        return f"começa em {h}h{r:02d}" if r else f"começa em {h}h"
    d = m // (24 * 60)
    return f"começa em {d} dia{'s' if d > 1 else ''}"
