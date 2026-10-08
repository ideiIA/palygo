from playgo import geo, urgencia


def test_haversine_conhecido():
    # Centro de Campo Grande → Parque das Nações Indígenas: poucos km
    km = geo.haversine(-20.4647, -54.6165, -20.4500, -54.5900)
    assert 2.5 < km < 3.5
    assert geo.haversine(-20.47, -54.62, -20.47, -54.62) == 0


def test_formatar_km():
    assert geo.formatar_km(1.7) == "1,7 km"
    assert geo.formatar_km(0.42) == "420 m"
    assert geo.formatar_km(None) == ""


def test_urgencia_prioriza_proximo_e_iminente():
    # RF-026: 1 km, começa em 40 min, falta 1 → à frente do mesmo jogo na semana seguinte
    agora = urgencia.nota(40, 1.0, 1, True)
    semana = urgencia.nota(7 * 24 * 60, 1.0, 1, True)
    assert agora > semana + 20


def test_urgencia_vagas_e_distancia():
    assert urgencia.nota(60, 1, 1, False) > urgencia.nota(60, 1, 5, False)
    assert urgencia.nota(60, 1, 2, False) > urgencia.nota(60, 9, 2, False)
    assert urgencia.nota(60, 1, 0, True) == 0  # lotado não é oportunidade


def test_contagem_regressiva():
    assert urgencia.contagem_regressiva(48) == "começa em 48 min"
    assert urgencia.contagem_regressiva(78) == "começa em 1h18"
    assert urgencia.contagem_regressiva(120) == "começa em 2h"
    assert urgencia.contagem_regressiva(-10) == "começou há 10 min"
    assert urgencia.contagem_regressiva(3 * 24 * 60) == "começa em 3 dias"
