"""Vagas em tempo real, aprovação e lista de espera (RF-002, RF-013, RF-017, RF-018)."""

from datetime import timedelta

import pytest

from playgo import atividades, notificacoes, vagas
from playgo.atividades import NovaAtividade
from playgo.db import agora
from playgo.erros import ErroNegocio, SemPermissao
from playgo.models import Notificacao


def _atividade(s, fabrica, org, max_p=3, **kw):
    return atividades.criar(
        s, org,
        NovaAtividade(modalidade_id=fabrica.mod("futebol").id, nome="Racha", inicio=agora() + timedelta(hours=3), max_participantes=max_p, local_nome="Quadra", latitude=-20.47, longitude=-54.62, **kw),
    )


def test_organizador_ocupa_a_primeira_vaga(s, fabrica):
    a = _atividade(s, fabrica, fabrica.atleta("Org"))
    assert (a.confirmados, a.vagas) == (1, 2)


def test_lotou_vai_para_espera_e_desistencia_repoe(s, fabrica):
    org, b, c, d = (fabrica.atleta(n) for n in ("Org", "B", "C", "D"))
    a = _atividade(s, fabrica, org, max_p=3)
    assert vagas.entrar(s, a.id, b).status == "confirmado"
    assert vagas.entrar(s, a.id, c).status == "confirmado"
    assert vagas.entrar(s, a.id, d).status == "espera"
    s.refresh(a)
    assert (a.confirmados, a.vagas) == (3, 0)

    vagas.sair(s, a.id, b)  # desistência: D entra automaticamente
    s.refresh(a)
    assert a.confirmados == 3
    assert vagas.participacao_de(s, a.id, d.id).status == "confirmado"
    aviso = s.query(Notificacao).filter_by(usuario_id=d.id, tipo="reposicao").one()
    assert "Alguém desistiu" in aviso.titulo


def test_fila_de_espera_respeita_a_ordem(s, fabrica):
    org, b, c, d = (fabrica.atleta(n) for n in ("Org", "B", "C", "D"))
    a = _atividade(s, fabrica, org, max_p=2)
    vagas.entrar(s, a.id, b)
    vagas.entrar(s, a.id, c)  # primeiro da fila
    vagas.entrar(s, a.id, d)  # segundo da fila
    vagas.sair(s, a.id, b)
    assert vagas.participacao_de(s, a.id, c.id).status == "confirmado"
    assert vagas.participacao_de(s, a.id, d.id).status == "espera"


def test_entrar_duas_vezes_nao_duplica(s, fabrica):
    org, b = fabrica.atleta("Org"), fabrica.atleta("B")
    a = _atividade(s, fabrica, org)
    vagas.entrar(s, a.id, b)
    vagas.entrar(s, a.id, b)
    s.refresh(a)
    assert a.confirmados == 2


def test_aprovacao_do_organizador(s, fabrica):
    org, b, intruso = fabrica.atleta("Org"), fabrica.atleta("B"), fabrica.atleta("X")
    a = _atividade(s, fabrica, org, exige_aprovacao=True)
    p = vagas.entrar(s, a.id, b)
    assert p.status == "pendente"
    s.refresh(a)
    assert a.confirmados == 1  # pendente não ocupa vaga
    with pytest.raises(SemPermissao):
        vagas.aprovar(s, a.id, p.id, intruso)
    vagas.aprovar(s, a.id, p.id, org)
    s.refresh(a)
    assert (vagas.participacao_de(s, a.id, b.id).status, a.confirmados) == ("confirmado", 2)


def test_recusado_nao_pode_voltar(s, fabrica):
    org, b = fabrica.atleta("Org"), fabrica.atleta("B")
    a = _atividade(s, fabrica, org, exige_aprovacao=True)
    p = vagas.entrar(s, a.id, b)
    vagas.recusar(s, a.id, p.id, org)
    with pytest.raises(ErroNegocio):
        vagas.entrar(s, a.id, b)


def test_organizador_nao_sai_da_propria_atividade(s, fabrica):
    org = fabrica.atleta("Org")
    a = _atividade(s, fabrica, org)
    with pytest.raises(ErroNegocio):
        vagas.sair(s, a.id, org)


def test_categoria_exige_sexo_do_perfil(s, fabrica):
    org = fabrica.atleta("Org")
    a = _atividade(s, fabrica, org, categoria="feminino")
    sem_sexo = fabrica.atleta("Sem")
    with pytest.raises(ErroNegocio):
        vagas.entrar(s, a.id, sem_sexo)
    mulher = fabrica.atleta("Mulher", sexo="F")
    assert vagas.entrar(s, a.id, mulher).status == "confirmado"
    homem = fabrica.atleta("Homem", sexo="M")
    with pytest.raises(ErroNegocio):
        vagas.entrar(s, a.id, homem)


def test_aumentar_capacidade_chama_a_espera(s, fabrica):
    org, b, c = fabrica.atleta("Org"), fabrica.atleta("B"), fabrica.atleta("C")
    a = _atividade(s, fabrica, org, max_p=2)
    vagas.entrar(s, a.id, b)
    assert vagas.entrar(s, a.id, c).status == "espera"
    atividades.alterar_capacidade(s, a.id, org, 3)
    assert vagas.participacao_de(s, a.id, c.id).status == "confirmado"
    with pytest.raises(ErroNegocio):
        atividades.alterar_capacidade(s, a.id, org, 1)  # abaixo dos confirmados


def test_cancelar_avisa_participantes(s, fabrica):
    org, b = fabrica.atleta("Org"), fabrica.atleta("B")
    a = _atividade(s, fabrica, org)
    vagas.entrar(s, a.id, b)
    atividades.cancelar(s, a.id, org)
    assert notificacoes.nao_lidas(s, b) >= 1
    with pytest.raises(ErroNegocio):
        vagas.entrar(s, a.id, fabrica.atleta("Z"))
