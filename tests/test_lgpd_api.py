"""LGPD e guarda legal (auditoria, exportação, exclusão, purga) e o mural pela API e pelo site."""

import io
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from playgo import contas, moderacao, privacidade, publicacoes, termos
from playgo.config import settings
from playgo.db import Session, agora, engine
from playgo.erros import ErroNegocio
from playgo.models import AceiteTermos, Registro, Usuario

PERTO = (-20.4535, -54.6201)


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (80, 60), (10, 120, 200)).save(buf, "JPEG")
    return buf.getvalue()


def _admin(fabrica, s):
    a = fabrica.atleta("Admin")
    a.admin = True
    s.commit()
    return a


# ---------------------------------------------------------------- trilha de auditoria


def test_acoes_ficam_registradas(s, fabrica):
    u = fabrica.atleta("A")
    p = publicacoes.criar(s, u, "geral", None, "oi", latitude=1.0, longitude=1.0)
    acoes = [r.acao for r in s.scalars(select(Registro).where(Registro.usuario_id == u.id).order_by(Registro.id))]
    assert acoes[:3] == ["aceite_termos", "consentimento_localizacao", "cadastro"] and "publicacao_criar" in acoes
    reg = s.scalar(select(Registro).where(Registro.acao == "publicacao_criar", Registro.objeto_id == p.id))
    assert reg.detalhes["escopo"] == "geral" and reg.em is not None
    assert s.scalar(select(AceiteTermos).where(AceiteTermos.usuario_id == u.id)).versao == termos.VERSAO


def test_login_e_falha_de_login_sao_registrados(s, fabrica):
    u = fabrica.atleta("A")
    email = u.email
    assert contas.autenticar(s, email, "errada-errada") is None
    assert contas.autenticar(s, email, "senha-de-teste-1") is not None
    assert contas.autenticar(s, "ninguem@teste.local", "x" * 10) is None
    acoes = [r.acao for r in s.scalars(select(Registro).where(Registro.acao.in_(("login", "login_falha")), Registro.usuario_id == u.id).order_by(Registro.id))]
    assert acoes == ["login_falha", "login"]


def test_trilha_so_aceita_insercao():
    with Session() as s:
        s.add(Registro(acao="teste_gatilho"))
        s.commit()
        rid = s.scalar(select(Registro.id).where(Registro.acao == "teste_gatilho").order_by(Registro.id.desc()))
    with engine.connect() as c:
        with pytest.raises(DBAPIError, match="somente de inserção"):
            c.execute(text("UPDATE registros SET acao = 'adulterado' WHERE id = :i"), {"i": rid})
        c.rollback()
        with pytest.raises(DBAPIError, match="somente de inserção"):
            c.execute(text("DELETE FROM registros WHERE id = :i"), {"i": rid})
        c.rollback()


def test_purga_so_elimina_o_que_passou_do_prazo(s, fabrica):
    u = fabrica.atleta("A")
    velho = Registro(acao="velho", usuario_id=u.id, em=agora() - timedelta(days=settings.retencao_registros_dias + 5))
    novo = Registro(acao="novo", usuario_id=u.id)
    s.add_all([velho, novo])
    s.commit()
    antigo = publicacoes.criar(s, u, "geral", None, "vai ser purgada", latitude=1.0, longitude=1.0, arquivos=[_jpeg()])
    arquivo = antigo.midias[0].arquivo
    publicacoes.excluir(s, antigo.id, u)
    antigo.excluido_em = agora() - timedelta(days=settings.retencao_registros_dias + 1)
    s.commit()
    from playgo import midia

    assert midia.caminho(arquivo).exists()
    r = privacidade.purgar(s)
    assert r["registros"] >= 1 and r["publicacoes"] >= 1 and r["arquivos"] >= 1
    assert not midia.caminho(arquivo).exists()
    assert s.scalar(select(Registro.id).where(Registro.id == velho.id)) is None
    assert s.scalar(select(Registro.id).where(Registro.id == novo.id)) == novo.id


# ---------------------------------------------------------------- direitos do titular


def test_exportar_dados(s, fabrica):
    u = fabrica.atleta("Titular")
    p = publicacoes.criar(s, u, "geral", None, "versão 1", latitude=1.0, longitude=1.0)
    moderacao.processar_publicacao(p.id)
    publicacoes.editar(s, p.id, u, "versão 2")
    d = privacidade.exportar(s, u)
    assert d["perfil"]["usuario"] == u.usuario and "senha_hash" not in str(d)
    assert d["publicacoes"][0]["versoes_anteriores"] == ["versão 1"] and d["publicacoes"][0]["texto"] == "versão 2"
    assert d["aceites_termos"][0]["versao"] == termos.VERSAO
    assert any(r["acao"] == "publicacao_criar" for r in d["registros_de_acesso_e_interacao"])
    assert s.scalar(select(Registro.id).where(Registro.acao == "dados_exportados", Registro.usuario_id == u.id))


def test_excluir_conta_anonimiza_e_preserva_a_trilha(s, fabrica):
    from playgo import atividades, vagas
    from playgo.atividades import NovaAtividade

    u, outro = fabrica.atleta("Quem Sai"), fabrica.atleta("Fica")
    email, usuario = u.email, u.usuario
    p = publicacoes.criar(s, u, "geral", None, "meu texto", latitude=1.0, longitude=1.0)
    moderacao.processar_publicacao(p.id)
    jogo = atividades.criar(s, u, NovaAtividade(modalidade_id=fabrica.mod("futebol").id, nome="Do Titular", inicio=agora() + timedelta(days=1), max_participantes=4, local_nome="Q", latitude=1.0, longitude=1.0))
    vagas.entrar(s, jogo.id, outro)
    with pytest.raises(ErroNegocio, match="Senha"):
        privacidade.excluir_conta(s, u, "senha-errada-xx")
    privacidade.excluir_conta(s, u, "senha-de-teste-1")

    s.refresh(u)
    assert (u.nome, u.ativo, u.latitude, u.cidade, u.nascimento) == ("Usuário removido", False, None, None, None)
    assert u.email != email and u.usuario != usuario and u.usuario.startswith("removido") and u.anonimizado_em
    assert contas.autenticar(s, email, "senha-de-teste-1") is None
    s.refresh(p)
    assert p.status == "excluida" and p.texto == "meu texto"  # some do app, fica guardado até o fim do prazo
    s.refresh(jogo)
    assert jogo.status == "cancelada"  # o que ele organizava foi cancelado
    assert s.scalar(select(Registro.id).where(Registro.acao == "conta_excluida", Registro.usuario_id == u.id))
    assert contas.por_usuario(s, usuario) is None  # o @ não é mais achado (e fica livre)


def test_unico_admin_nao_exclui_a_propria_conta(s, fabrica):
    s.query(Usuario).update({Usuario.admin: False})
    s.commit()
    admin = _admin(fabrica, s)
    with pytest.raises(ErroNegocio, match="único administrador"):
        privacidade.excluir_conta(s, admin, "senha-de-teste-1")
    _admin(fabrica, s)  # há outro admin: agora pode
    privacidade.excluir_conta(s, admin, "senha-de-teste-1")


# ---------------------------------------------------------------- API (multipart, portão, moderação)


@pytest.fixture(scope="module")
def cliente(banco):
    from playgo.web.app import app

    with TestClient(app) as c:
        yield c


def _cadastrar(cliente, nome="Teste", admin=False):
    email = f"{uuid.uuid4().hex[:10]}@teste.local"
    r = cliente.post("/api/v1/auth/cadastro", json={"nome": nome, "email": email, "senha": "senha-de-teste-1", "usuario": f"u{uuid.uuid4().hex[:12]}", "aceito_termos": True, "maior_de_idade": True, "consent_localizacao": True})
    assert r.status_code == 200, r.text
    if admin:
        with Session() as s:
            s.query(Usuario).filter(Usuario.email == email).update({Usuario.admin: True})
            s.commit()
    return {"Authorization": "Bearer " + r.json()["token"]}, r.json()["usuario"]


def test_portao_de_termos_e_usuario_na_api(cliente):
    h, u = _cadastrar(cliente)
    assert cliente.get("/api/v1/feed", headers=h).status_code == 200
    with Session() as s:
        s.query(Usuario).filter(Usuario.id == u["id"]).update({Usuario.termos_versao: "2020-01-01"})
        s.commit()
    r = cliente.get("/api/v1/feed", headers=h)
    assert r.status_code == 403 and r.json()["detail"]["pendencia"] == "termos"
    assert cliente.get("/api/v1/me", headers=h).json()["pendencia"] == "termos"  # /me segue livre para o app se orientar
    assert cliente.post("/api/v1/me/aceitar-termos", headers=h, json={"aceito_termos": False}).status_code == 400
    assert cliente.post("/api/v1/me/aceitar-termos", headers=h, json={"aceito_termos": True}).json()["pendencia"] is None
    assert cliente.get("/api/v1/feed", headers=h).status_code == 200
    with Session() as s:
        s.query(Usuario).filter(Usuario.id == u["id"]).update({Usuario.usuario: None})
        s.commit()
    assert cliente.get("/api/v1/feed", headers=h).json()["detail"]["pendencia"] == "usuario"
    assert cliente.put("/api/v1/me/usuario", headers=h, json={"usuario": "ab"}).status_code == 400
    assert cliente.put("/api/v1/me/usuario", headers=h, json={"usuario": f"novo{uuid.uuid4().hex[:8]}"}).json()["pendencia"] is None


def test_termos_publicos(cliente):
    r = cliente.get("/api/v1/termos").json()
    assert r["versao"] == termos.VERSAO and len(r["termos_de_uso"]) >= 8 and "primeira hora" in str(r["termos_de_uso"])
    assert "Anthropic" in str(r["politica_de_privacidade"]) and "LGPD" in str(r["politica_de_privacidade"])


def test_publicar_com_foto_pela_api_e_fluxo_de_moderacao(cliente):
    admin, _ = _cadastrar(cliente, "Admin", admin=True)
    autor, au = _cadastrar(cliente, "Autor")
    outro, _ = _cadastrar(cliente, "Outro")

    r = cliente.post("/api/v1/publicacoes", headers=autor, data={"escopo": "geral", "texto": "Foto do treino", "latitude": PERTO[0], "longitude": PERTO[1], "local_nome": "Parque"}, files=[("arquivos", ("treino.jpg", _jpeg(), "image/jpeg"))])
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "em_analise" or p["status"] == "publicada"  # a análise roda em segundo plano
    p = cliente.get(f"/api/v1/publicacoes/{p['id']}", headers=autor).json()
    assert p["status"] == "em_analise" and p["midias"][0]["tipo"] == "foto"  # sem IA para a foto: vai para revisão do admin
    assert p["autor"]["arroba"] == "@" + au["usuario"] and p["local"]["nome"] == "Parque"
    assert cliente.get("/api/v1/mural/geral", headers=outro).json()["itens"] == [] or p["id"] not in [i["id"] for i in cliente.get("/api/v1/mural/geral", headers=outro).json()["itens"]]
    assert cliente.get(f"/api/v1/publicacoes/{p['id']}", headers=outro).status_code == 403

    # só o admin enxerga a fila e decide
    assert cliente.get("/api/v1/moderacao/fila", headers=autor).status_code == 403
    fila = cliente.get("/api/v1/moderacao/fila", headers=admin).json()
    item = next(i for i in fila["itens"] if i["id"] == p["id"])
    assert "revisão humana" in item["motivo_analise"] and item["midias"][0]["miniatura"]
    assert cliente.get("/api/v1/moderacao/contagem", headers=admin).json()["total"] >= 1
    assert cliente.post(f"/api/v1/moderacao/publicacao/{p['id']}/decidir", headers=autor, json={"aprovar": True}).status_code == 403
    assert cliente.post(f"/api/v1/moderacao/publicacao/{p['id']}/decidir", headers=admin, json={"aprovar": True}).status_code == 200
    visivel = cliente.get("/api/v1/mural/geral", headers=outro).json()["itens"]
    assert p["id"] in [i["id"] for i in visivel]

    # a mídia é servida pela URL assinada e por nenhuma outra
    url = next(i for i in visivel if i["id"] == p["id"])["midias"][0]
    assert cliente.get(url["url"]).status_code == 200 and cliente.get(url["miniatura"]).headers["content-type"] == "image/jpeg"
    assert cliente.get(url["url"].split("?")[0]).status_code == 404  # sem token e sem sessão: nada
    assert cliente.get(url["url"].split("?")[0] + "?t=falso").status_code == 404

    # comentários
    c = cliente.post(f"/api/v1/publicacoes/{p['id']}/comentarios", headers=outro, json={"texto": "Bacana!"})
    assert c.status_code == 201
    lista = cliente.get(f"/api/v1/publicacoes/{p['id']}/comentarios", headers=autor).json()
    assert [x["texto"] for x in lista] == ["Bacana!"] and lista[0]["pode_denunciar"] and not lista[0]["pode_editar"]
    assert cliente.patch(f"/api/v1/comentarios/{lista[0]['id']}", headers=autor, json={"texto": "editado pelo dono do post"}).status_code == 403

    # só o autor edita; o admin não
    assert cliente.patch(f"/api/v1/publicacoes/{p['id']}", headers=admin, json={"texto": "admin editando"}).status_code == 403
    ed = cliente.patch(f"/api/v1/publicacoes/{p['id']}", headers=autor, json={"texto": "Foto do treino de hoje"}).json()
    assert ed["editado"].startswith("Editado em")
    assert cliente.delete(f"/api/v1/publicacoes/{p['id']}", headers=outro).status_code == 403
    assert cliente.delete(f"/api/v1/publicacoes/{p['id']}", headers=autor).status_code == 200  # dentro da 1ª hora


def test_ip_e_porta_entram_na_trilha(cliente):
    h, u = _cadastrar(cliente)
    cliente.post("/api/v1/publicacoes", headers=h, data={"escopo": "geral", "texto": "rastro", "latitude": 1, "longitude": 1})
    with Session() as s:
        r = s.scalar(select(Registro).where(Registro.usuario_id == u["id"], Registro.acao == "publicacao_criar"))
        assert r.ip == "testclient" and r.porta is not None and r.user_agent


def test_privacidade_pela_api(cliente):
    h, u = _cadastrar(cliente)
    assert cliente.get("/api/v1/privacidade/meus-dados", headers=h).json()["perfil"]["usuario"] == u["usuario"]
    cliente.patch("/api/v1/me", headers=h, json={"latitude": PERTO[0], "longitude": PERTO[1]})
    assert cliente.post("/api/v1/privacidade/revogar-localizacao", headers=h).json()["latitude"] is None
    assert cliente.patch("/api/v1/me", headers=h, json={"latitude": 1.0, "longitude": 1.0}).status_code == 400  # revogou: não guarda mais
    assert cliente.post("/api/v1/privacidade/excluir-conta", headers=h, json={"senha": "errada"}).status_code == 400
    assert cliente.post("/api/v1/privacidade/excluir-conta", headers=h, json={"senha": "senha-de-teste-1"}).status_code == 200
    assert cliente.get("/api/v1/me", headers=h).status_code == 401  # a conta deixou de existir para o app


# ---------------------------------------------------------------- site


def _site(cliente, **extra):
    c = TestClient(cliente.app)
    email = f"{uuid.uuid4().hex[:10]}@teste.local"
    dados = {"nome": "Carlos Almeida", "email": email, "senha": "senha-de-teste-1", "usuario": f"c{uuid.uuid4().hex[:12]}", "aceito_termos": "1"} | extra
    r = c.post("/cadastro", data=dados, follow_redirects=False)
    return c, r, dados


def test_cadastro_do_site_exige_aceites_e_usuario(cliente):
    c = TestClient(cliente.app)
    for faltando in ({"aceito_termos": ""}, {"usuario": "ab"}, {"usuario": "admin"}):
        _, r, _ = _site(cliente, **faltando)
        assert r.status_code == 400, faltando
    _, ok, dados = _site(cliente)
    assert ok.status_code == 303
    _, repetido, _ = _site(cliente, usuario=dados["usuario"].upper())
    assert repetido.status_code == 400 and "em uso" in repetido.text
    pagina = c.get("/cadastro")
    assert "Termos de Uso" in pagina.text and "18 anos" not in pagina.text and "maior_de_idade" not in pagina.text and 'name="usuario"' in pagina.text and 'name="consent_localizacao"' in pagina.text


def test_portao_do_site_e_telas_de_termos(cliente):
    anon = TestClient(cliente.app)
    assert "primeira hora" in anon.get("/termos").text and "LGPD" in anon.get("/politica-de-privacidade").text
    c, _, dados = _site(cliente)
    with Session() as s:
        s.query(Usuario).filter(Usuario.email == dados["email"]).update({Usuario.termos_versao: "2020-01-01"})
        s.commit()
    r = c.get("/mural", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/termos/aceitar"
    assert c.post("/termos/aceitar", data={}, follow_redirects=False).status_code == 303 and c.get("/mural", follow_redirects=False).status_code == 303  # sem marcar, segue barrado
    assert "18 anos" not in c.get("/termos/aceitar").text
    c.post("/termos/aceitar", data={"aceito_termos": "1"})
    assert c.get("/mural").status_code == 200
    with Session() as s:
        s.query(Usuario).filter(Usuario.email == dados["email"]).update({Usuario.usuario: None})
        s.commit()
    assert c.get("/mural", follow_redirects=False).headers["location"] == "/cadastro/completar"
    r = c.post("/cadastro/completar", data={"nome_usuario": "meu.novo.arroba"}, follow_redirects=False)
    assert r.status_code == 303 and c.get("/mural").status_code == 200


def test_paginas_novas_do_site_renderizam(cliente):
    c, _, _ = _site(cliente)
    for caminho in ("/mural", "/comunidades", "/comunidades/nova", "/convites", "/privacidade", "/perfil"):
        r = c.get(caminho)
        assert r.status_code == 200, f"{caminho}: {r.status_code}"
    assert c.get("/privacidade/meus-dados.json").headers["content-disposition"].startswith("attachment")
    assert c.get("/moderacao", follow_redirects=False).status_code == 303  # não-admin: volta para o início


def test_fluxo_de_comunidade_e_convite_pelo_site(cliente):
    dono, _, _ = _site(cliente)
    r = dono.post("/comunidades", data={"nome": "Corredores CG", "visibilidade": "link", "descricao": "gente que corre"}, follow_redirects=False)
    assert r.status_code == 303
    pagina = dono.get(r.headers["location"]).text
    assert "/convite/c" in pagina  # o dono vê o link para compartilhar
    token = pagina.split("/convite/")[1].split("<")[0].split('"')[0].split(" ")[0].strip()
    visitante = TestClient(cliente.app)
    ir = visitante.get(f"/convite/{token}", follow_redirects=False)
    assert ir.status_code == 303 and ir.headers["location"] == "/entrar"  # anônimo: entra primeiro
    novo, _, _ = _site(cliente)
    abrir = novo.get(f"/convite/{token}")
    assert abrir.status_code == 200 and "Corredores CG" in abrir.text
    entrou = novo.post(f"/convite/{token}/entrar", follow_redirects=True)
    assert entrou.status_code == 200 and "Você entrou" in entrou.text
