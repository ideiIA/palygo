"""Esportes iniciais (RF-012). Acrescentar um esporte é inserir uma linha em `modalidades`."""

from sqlalchemy import select
from sqlalchemy.orm import Session as SessaoORM

from .models import Modalidade

# codigo, nome, ícone, cor, usa_quadra, vagas_padrao
INICIAIS = (
    ("futebol", "Futebol", "⚽", "roxo", True, 14),
    ("futsal", "Futsal", "⚽", "roxo", True, 10),
    ("volei", "Vôlei", "🏐", "verde", True, 12),
    ("volei_de_areia", "Vôlei de areia", "🏐", "verde", True, 8),
    ("beach_tennis", "Beach Tennis", "🎾", "laranja", True, 4),
    ("tenis", "Tênis", "🎾", "laranja", True, 4),
    ("padel", "Padel", "🎾", "laranja", True, 4),
    ("corrida", "Corrida", "🏃", "laranja", False, 30),
    ("basquete", "Basquete", "🏀", "roxo", True, 10),
    ("ciclismo", "Ciclismo", "🚴", "verde", False, 20),
    ("caminhada", "Caminhada", "🚶", "verde", False, 30),
    ("futevolei", "Futevôlei", "🏐", "verde", True, 4),
    ("funcional", "Funcional", "💪", "laranja", False, 20),
    ("trilha", "Trilha", "🥾", "verde", False, 15),
)


def semear(s: SessaoORM) -> int:
    """Cria as modalidades que ainda não existem; devolve quantas entraram."""
    existentes = set(s.scalars(select(Modalidade.codigo)))
    novas = 0
    for ordem, (codigo, nome, icone, cor, usa_quadra, vagas) in enumerate(INICIAIS, start=1):
        if codigo in existentes:
            continue
        s.add(Modalidade(codigo=codigo, nome=nome, icone=icone, cor=cor, usa_quadra=usa_quadra, vagas_padrao=vagas, ordem=ordem))
        novas += 1
    s.commit()
    return novas


def ativas(s: SessaoORM) -> list[Modalidade]:
    return list(s.scalars(select(Modalidade).where(Modalidade.ativo).order_by(Modalidade.ordem, Modalidade.nome)))
