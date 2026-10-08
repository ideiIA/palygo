"""Sorteio, chaves, classificação e jogo ao vivo dos campeonatos."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from playgo import campeonatos, chaves
from playgo.campeonatos import NovoCampeonato
from playgo.db import Session, agora
from playgo.erros import ErroNegocio, SemPermissao
from playgo.models import Jogo, Notificacao, Usuario

PERTO = (-20.4535, -54.6201)


@pytest.fixture(autouse=True)
def _ja_existe_um_admin(banco):
    with Session() as s:
        if not s.scalar(select(Usuario.id).where(Usuario.admin).limit(1)):
            from playgo import contas

            contas.cadastrar(s, "Primeiro", f"{uuid.uuid4().hex[:8]}@t.local", "senha-de-teste-1", f"pri{uuid.uuid4().hex[:10]}", True, False)


def _torneio(s, fabrica, n_equipes, confirmar=True):
    org = fabrica.atleta("Organizador")
    hoje = agora().date()
    c = campeonatos.criar(
        s, org,
        NovoCampeonato(modalidade_id=fabrica.mod("futsal").id, nome="Copa", data_inicio=hoje + timedelta(days=20), inscricao_ate=hoje + timedelta(days=10), max_equipes=32, local_nome="G", latitude=PERTO[0], longitude=PERTO[1]),
    )
    donos = []
    for i in range(n_equipes):
        cap = fabrica.atleta(f"Capitao{i}")
        e = campeonatos.inscrever_equipe(s, c.id, cap, f"Equipe {i + 1}")
        if confirmar:
            campeonatos.decidir_equipe(s, e.id, org, True)
        donos.append(cap)
    return c, org, donos


def _jogos(s, c):
    return list(s.scalars(select(Jogo).where(Jogo.campeonato_id == c.id).order_by(Jogo.rodada, Jogo.posicao)))


def _disputar(s, c, org, j, a, b, vencedor_id=None):
    chaves.iniciar(s, c.id, j.id, org)
    chaves.definir_placar(s, c.id, j.id, org, a, b)
    return chaves.encerrar(s, c.id, j.id, org, vencedor_id)


def test_sorteio_so_da_organizacao_e_so_com_equipes_confirmadas(s, fabrica):
    c, org, donos = _torneio(s, fabrica, 1)
    with pytest.raises(ErroNegocio, match="pelo menos 2"):
        chaves.sortear(s, c.id, org, "eliminatoria")
    with pytest.raises(SemPermissao):
        chaves.sortear(s, c.id, donos[0], "eliminatoria")
    e2 = campeonatos.inscrever_equipe(s, c.id, fabrica.atleta("Outro"), "Pendente")
    with pytest.raises(ErroNegocio, match="pelo menos 2"):
        chaves.sortear(s, c.id, org, "eliminatoria")  # pendente não entra no sorteio
    campeonatos.decidir_equipe(s, e2.id, org, True)
    with pytest.raises(ErroNegocio, match="formato"):
        chaves.sortear(s, c.id, org, "xadrez")
    r = chaves.sortear(s, c.id, org, "eliminatoria")
    assert r["equipes"] == 2 and r["semente"]


def test_eliminatoria_com_folgas_avanca_o_vencedor_ate_o_campeao(s, fabrica):
    c, org, _ = _torneio(s, fabrica, 6)
    chaves.sortear(s, c.id, org, "eliminatoria")
    jogos = _jogos(s, c)
    assert [(j.rodada_nome, sum(1 for x in jogos if x.rodada == j.rodada)) for j in jogos if j.posicao == 0] == [("Quartas de final", 4), ("Semifinal", 2), ("Final", 1)]
    folgas = [j for j in jogos if j.folga]
    assert len(folgas) == 2 and all(j.status == "encerrado" and j.vencedor_id for j in folgas)
    assert {j.vencedor_id for j in folgas} <= {j.equipe_a_id or j.equipe_b_id for j in jogos if j.rodada == 2 for _ in (0,)} | {x for j in jogos if j.rodada == 2 for x in (j.equipe_a_id, j.equipe_b_id)}  # já estão nas semifinais
    assert s.get(type(org), org.id)  # sanidade
    equipes_r1 = [e for j in jogos if j.rodada == 1 for e in (j.equipe_a_id, j.equipe_b_id) if e]
    assert len(equipes_r1) == len(set(equipes_r1)) == 6  # todas as equipes, cada uma uma vez

    # joga a chave inteira dando a vitória ao lado A
    for rodada in (1, 2, 3):
        for j in [x for x in _jogos(s, c) if x.rodada == rodada and x.status == "agendado"]:
            _disputar(s, c, org, j, 2, 1)
    final = _jogos(s, c)[-1]
    assert final.status == "encerrado" and final.vencedor_id == final.equipe_a_id
    s.refresh(c)
    assert c.status == "encerrado"
    d = chaves.chaveamento(s, c, org)
    assert d["campeao"]["id"] == final.vencedor_id and d["formato"] == "eliminatoria" and len(d["rodadas"]) == 3


def test_empate_no_mata_mata_exige_desempate_e_pontos_corridos_aceita_empate(s, fabrica):
    c, org, _ = _torneio(s, fabrica, 2)
    chaves.sortear(s, c.id, org, "eliminatoria")
    j = _jogos(s, c)[0]
    chaves.iniciar(s, c.id, j.id, org)
    chaves.marcar(s, c.id, j.id, org, "a", 1)
    chaves.marcar(s, c.id, j.id, org, "b", 1)
    with pytest.raises(ErroNegocio, match="desempate"):
        chaves.encerrar(s, c.id, j.id, org)
    with pytest.raises(ErroNegocio, match="desempate"):
        chaves.encerrar(s, c.id, j.id, org, vencedor_id=987654)
    j = chaves.encerrar(s, c.id, j.id, org, vencedor_id=j.equipe_b_id)
    assert j.vencedor_id == j.equipe_b_id and j.desempate is True

    c2, org2, _ = _torneio(s, fabrica, 2)
    chaves.sortear(s, c2.id, org2, "pontos_corridos")
    j2 = _disputar(s, c2, org2, _jogos(s, c2)[0], 1, 1)
    assert j2.vencedor_id is None


def test_pontos_corridos_todos_contra_todos_e_classificacao(s, fabrica):
    c, org, _ = _torneio(s, fabrica, 4)
    chaves.sortear(s, c.id, org, "pontos_corridos")
    jogos = _jogos(s, c)
    assert len(jogos) == 6 and {j.rodada for j in jogos} == {1, 2, 3}
    pares = {frozenset((j.equipe_a_id, j.equipe_b_id)) for j in jogos}
    assert len(pares) == 6  # cada par uma vez
    for j in jogos:
        _disputar(s, c, org, j, 3, 0)  # o lado A sempre vence por 3 a 0
    s.refresh(c)
    assert c.status == "encerrado"
    tab = chaves.chaveamento(s, c, org)["classificacao"]
    assert [l["posicao"] for l in tab] == [1, 2, 3, 4]
    assert sum(l["pontos"] for l in tab) == 6 * 3 and sum(l["jogos"] for l in tab) == 12
    assert tab[0]["pontos"] >= tab[1]["pontos"] >= tab[2]["pontos"] >= tab[3]["pontos"]
    assert chaves.chaveamento(s, c, org)["campeao"]["id"] == tab[0]["equipe"]["id"]


def test_numero_impar_em_pontos_corridos_tem_folga_por_rodada(s, fabrica):
    c, org, _ = _torneio(s, fabrica, 5)
    chaves.sortear(s, c.id, org, "pontos_corridos")
    assert len(_jogos(s, c)) == 10  # 5 equipes: 10 jogos


def test_so_mesario_ou_organizacao_conduz_e_o_placar_nao_fica_negativo(s, fabrica):
    c, org, donos = _torneio(s, fabrica, 2)
    chaves.sortear(s, c.id, org, "eliminatoria")
    j = _jogos(s, c)[0]
    intruso, mesario = fabrica.atleta("Intruso"), fabrica.atleta("Mesario")
    for acao in (lambda: chaves.iniciar(s, c.id, j.id, intruso), lambda: chaves.adicionar_mesario(s, c.id, mesario, mesario.id)):
        with pytest.raises(SemPermissao):
            acao()
    assert chaves.adicionar_mesario(s, c.id, org, mesario.id)[0]["usuario_id"] == mesario.id
    chaves.iniciar(s, c.id, j.id, mesario)
    chaves.marcar(s, c.id, j.id, mesario, "a", -1)  # não desce de zero
    assert (j.placar_a, j.placar_b) == (0, 0)
    chaves.marcar(s, c.id, j.id, mesario, "a", 1)
    chaves.lance(s, c.id, j.id, mesario, "Cartão amarelo")
    with pytest.raises(ErroNegocio, match="já começou"):
        chaves.iniciar(s, c.id, j.id, mesario)
    with pytest.raises(SemPermissao):
        chaves.reabrir(s, c.id, j.id, mesario)  # reabrir é da organização
    chaves.encerrar(s, c.id, j.id, mesario)
    with pytest.raises(ErroNegocio, match="ao vivo"):
        chaves.marcar(s, c.id, j.id, mesario, "b", 1)
    s.refresh(j)
    assert [e.tipo for e in j.eventos] == ["inicio", "placar", "lance", "fim"]
    # avisos: o capitão do outro time foi avisado do início e do fim, sem duplicar
    assert s.query(Notificacao).filter(Notificacao.usuario_id.in_([d.id for d in donos]), Notificacao.titulo.like("%Ao vivo%")).count() >= 1


def test_reabrir_desfaz_o_avanco_se_a_proxima_rodada_nao_comecou(s, fabrica):
    c, org, _ = _torneio(s, fabrica, 4)
    chaves.sortear(s, c.id, org, "eliminatoria")
    j1 = _jogos(s, c)[0]
    _disputar(s, c, org, j1, 5, 2)
    final = [x for x in _jogos(s, c) if x.rodada == 2][0]
    campeao_provisorio = j1.vencedor_id
    assert campeao_provisorio in (final.equipe_a_id, final.equipe_b_id)
    chaves.reabrir(s, c.id, j1.id, org)
    s.refresh(final)
    assert j1.status == "ao_vivo" and j1.vencedor_id is None and campeao_provisorio not in (final.equipe_a_id, final.equipe_b_id)
    # com a final já em andamento, o jogo de origem não reabre
    _disputar_de_novo = chaves.encerrar(s, c.id, j1.id, org)
    j2 = _jogos(s, c)[1]
    _disputar(s, c, org, j2, 1, 0)
    chaves.iniciar(s, c.id, final.id, org)
    with pytest.raises(ErroNegocio, match="já começou"):
        chaves.reabrir(s, c.id, j1.id, org)
    assert _disputar_de_novo.status == "encerrado"


def test_nao_sorteia_de_novo_depois_que_um_jogo_comecou(s, fabrica):
    c, org, _ = _torneio(s, fabrica, 4)
    chaves.sortear(s, c.id, org, "eliminatoria")
    chaves.sortear(s, c.id, org, "pontos_corridos")  # ainda dá: nada começou
    assert {j.rodada_nome[:6] for j in _jogos(s, c)} == {"Rodada"}
    chaves.iniciar(s, c.id, _jogos(s, c)[0].id, org)
    with pytest.raises(ErroNegocio, match="Já há jogos"):
        chaves.sortear(s, c.id, org, "eliminatoria")


def test_api_todos_acompanham_e_so_a_organizacao_conduz(banco):
    """Só pela API/site (sem a sessão de teste aberta): o startup do app altera tabelas e travaria com ela."""
    from playgo.web.app import app

    with TestClient(app) as cli:
        def conta(nome):
            email = f"{uuid.uuid4().hex[:10]}@teste.local"
            r = cli.post("/api/v1/auth/cadastro", json={"nome": nome, "email": email, "senha": "senha-de-teste-1", "usuario": f"u{uuid.uuid4().hex[:12]}", "aceito_termos": True})
            return {"Authorization": "Bearer " + r.json()["token"]}, r.json()["usuario"]["id"], email

        h_org, org_id, org_email = conta("Organizadora")
        h_x, _, x_email = conta("Espectador")
        mods = {m["codigo"]: m["id"] for m in cli.get("/api/v1/modalidades", headers=h_org).json()}
        hoje = agora().date()
        camp = cli.post("/api/v1/campeonatos", headers=h_org, json={"modalidade_id": mods["futsal"], "nome": "Copa", "data_inicio": str(hoje + timedelta(days=20)), "inscricao_ate": str(hoje + timedelta(days=10)), "max_equipes": 8, "local_nome": "G", "latitude": PERTO[0], "longitude": PERTO[1]})
        assert camp.status_code == 201, camp.text
        cid = camp.json()["id"]
        for i in range(4):
            h_cap, _, _ = conta(f"Capitao{i}")
            cli.post(f"/api/v1/campeonatos/{cid}/equipes", headers=h_cap, json={"nome": f"Equipe {i + 1}"})
        for e in cli.get(f"/api/v1/campeonatos/{cid}", headers=h_org).json()["equipes_lista"]:
            assert cli.post(f"/api/v1/equipes/{e['id']}/decidir", headers=h_org, json={"confirmar": True}).status_code == 200

        assert cli.get(f"/api/v1/campeonatos/{cid}/chaves", headers=h_x).json()["rodadas"] == []
        assert cli.post(f"/api/v1/campeonatos/{cid}/sorteio", headers=h_x, json={"formato": "eliminatoria"}).status_code == 403
        d = cli.post(f"/api/v1/campeonatos/{cid}/sorteio", headers=h_org, json={"formato": "eliminatoria"}).json()
        assert len(d["rodadas"]) == 2 and d["pode_gerir"] is True
        d_x = cli.get(f"/api/v1/campeonatos/{cid}/chaves", headers=h_x).json()  # qualquer pessoa logada acompanha
        assert len(d_x["rodadas"]) == 2 and d_x["pode_gerir"] is False and d_x["pode_pontuar"] is False and d_x["mesarios"] == []
        jid = d_x["rodadas"][0]["jogos"][0]["id"]
        assert cli.post(f"/api/v1/campeonatos/{cid}/jogos/{jid}/iniciar", headers=h_x).status_code == 403
        assert cli.post(f"/api/v1/campeonatos/{cid}/jogos/{jid}/iniciar", headers=h_org).json()["status"] == "ao_vivo"
        v = cli.post(f"/api/v1/campeonatos/{cid}/jogos/{jid}/marcar", headers=h_org, json={"lado": "a", "delta": 1}).json()
        assert v["placar_a"] == 1 and v["eventos"][-1]["tipo"] == "placar" and v["pode_pontuar"] is True
        ao_vivo = cli.get(f"/api/v1/campeonatos/{cid}/jogos/{jid}", headers=h_x).json()
        assert ao_vivo["placar_a"] == 1 and ao_vivo["status"] == "ao_vivo" and ao_vivo["pode_pontuar"] is False
        assert cli.get(f"/api/v1/campeonatos/{cid}/chaves", headers=h_x).json()["ao_vivo"][0]["id"] == jid
        assert cli.post(f"/api/v1/campeonatos/{cid}/jogos/{jid}/encerrar", headers=h_org, json={}).json()["status"] == "encerrado"

        # páginas do site: logada acessa todas; o sorteio é só da organização
        assert cli.get(f"/campeonatos/{cid}/chaves", follow_redirects=False).status_code == 303  # sem login
        site = TestClient(app)
        assert site.post("/entrar", data={"email": x_email, "senha": "senha-de-teste-1"}, follow_redirects=False).status_code == 303
        for caminho in ("chaves", "ao-vivo", f"jogos/{jid}"):
            r = site.get(f"/campeonatos/{cid}/{caminho}")
            assert r.status_code == 200 and "chaves.js" in r.text, caminho
        assert site.get(f"/campeonatos/{cid}/sorteio", follow_redirects=False).headers["location"] == f"/campeonatos/{cid}/chaves"
        org_site = TestClient(app)
        org_site.post("/entrar", data={"email": org_email, "senha": "senha-de-teste-1"}, follow_redirects=False)
        assert org_site.get(f"/campeonatos/{cid}/sorteio").status_code == 200 and "Sorteio" in org_site.get(f"/campeonatos/{cid}").text
