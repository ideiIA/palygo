"""Perfis de acesso: usuário, moderador geral e administrador."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from playgo import administracao, moderacao, publicacoes
from playgo.db import Session
from playgo.erros import ErroNegocio, SemPermissao
from playgo.models import Notificacao, Registro, Usuario


@pytest.fixture()
def so_um_admin(s, fabrica):
    """Zera os perfis do banco de teste e devolve um único administrador."""
    s.execute(update(Usuario).values(admin=False, moderador=False))
    a = fabrica.atleta("Admin")
    a.admin = True
    s.commit()
    return a


def _post(s, autor, texto="oi"):
    p = publicacoes.criar(s, autor, "geral", None, texto, latitude=1.0, longitude=1.0)
    moderacao.processar_publicacao(p.id)
    s.refresh(p)
    return p


def test_so_admin_gerencia_perfis(s, fabrica, so_um_admin):
    comum, alvo = fabrica.atleta("Comum"), fabrica.atleta("Alvo")
    with pytest.raises(SemPermissao):
        administracao.definir_perfil(s, comum, alvo.id, "admin")
    with pytest.raises(SemPermissao):
        administracao.listar(s, comum)
    r = administracao.definir_perfil(s, so_um_admin, alvo.id, "admin")
    assert r["perfil"] == "admin" and alvo.admin and not alvo.moderador
    assert s.scalar(select(Registro.detalhes).where(Registro.acao == "perfil_alterar", Registro.objeto_id == alvo.id)) == {"de": "usuario", "para": "admin", "alvo": alvo.usuario}
    assert s.query(Notificacao).filter(Notificacao.usuario_id == alvo.id, Notificacao.titulo.like("%Administrador%")).count() == 1
    # o novo administrador também promove
    outro = fabrica.atleta("Outro")
    assert administracao.definir_perfil(s, alvo, outro.id, "moderador")["perfil"] == "moderador"
    with pytest.raises(ErroNegocio):
        administracao.definir_perfil(s, so_um_admin, outro.id, "super")


def test_nunca_fica_sem_administrador(s, fabrica, so_um_admin):
    with pytest.raises(ErroNegocio, match="único administrador"):
        administracao.definir_perfil(s, so_um_admin, so_um_admin.id, "usuario")
    outro = fabrica.atleta("Outro")
    administracao.definir_perfil(s, so_um_admin, outro.id, "admin")
    administracao.definir_perfil(s, so_um_admin, so_um_admin.id, "moderador")  # agora pode se rebaixar
    assert not so_um_admin.admin and so_um_admin.moderador
    assert administracao.resumo(s, outro) == {"administradores": 1, "moderadores": 1, "usuarios": s.query(Usuario).filter(Usuario.ativo).count()}


def test_listar_filtra_por_busca_e_perfil(s, fabrica, so_um_admin):
    mod = fabrica.atleta("Moderadora Ana")
    administracao.definir_perfil(s, so_um_admin, mod.id, "moderador")
    achados = administracao.listar(s, so_um_admin, f"@{mod.usuario[:6]}")
    assert [i["id"] for i in achados] == [mod.id] and set(achados[0]) >= {"arroba", "nome", "email", "perfil"}
    assert [i["id"] for i in administracao.listar(s, so_um_admin, "", "moderador")] == [mod.id]
    assert so_um_admin.id in [i["id"] for i in administracao.listar(s, so_um_admin, "", "admin")]
    assert mod.id not in [i["id"] for i in administracao.listar(s, so_um_admin, "", "usuario")]


def test_moderador_geral_modera_mas_nao_gerencia(s, fabrica, so_um_admin):
    mod, autor, comum = fabrica.atleta("Mod"), fabrica.atleta("Autor"), fabrica.atleta("Comum")
    administracao.definir_perfil(s, so_um_admin, mod.id, "moderador")
    # a fila: o conteúdo suspeito chega ao moderador geral, que aprova
    p = _post(s, autor, "vou te matar")
    assert p.status == "em_analise"
    assert s.query(Notificacao).filter(Notificacao.usuario_id == mod.id, Notificacao.tipo == "moderacao", Notificacao.titulo.like("%aguardando%")).count() == 1
    assert p.id in [i["id"] for i in publicacoes.fila(s, mod)["itens"]]
    publicacoes.decidir_analise(s, "publicacao", p.id, mod, False)
    with pytest.raises(SemPermissao):
        publicacoes.fila(s, comum)
    # oculta em qualquer mural; o autor é avisado
    q = _post(s, autor, "post comum")
    assert publicacoes.ocultar(s, q.id, mod, "fora das regras").oculta_por_papel == "moderacao"
    # um administrador ocultou? o moderador geral não desfaz; o inverso vale
    r = _post(s, autor, "outro post")
    publicacoes.ocultar(s, r.id, so_um_admin, "decisão da administração")
    with pytest.raises(SemPermissao):
        publicacoes.restaurar(s, r.id, mod)
    assert publicacoes.restaurar(s, q.id, so_um_admin).status == "publicada"  # admin desfaz o do moderador geral
    # sem acesso à administração de usuários
    with pytest.raises(SemPermissao):
        administracao.definir_perfil(s, mod, comum.id, "admin")


def test_perfil_pela_api_e_pelo_site(banco):
    from playgo.web.app import app

    def cadastrar(c, nome):
        r = c.post("/api/v1/auth/cadastro", json={"nome": nome, "email": f"{uuid.uuid4().hex[:10]}@teste.local", "senha": "senha-de-teste-1", "usuario": f"p{uuid.uuid4().hex[:12]}", "aceito_termos": True, "maior_de_idade": True})
        return {"Authorization": "Bearer " + r.json()["token"]}, r.json()["usuario"]

    with TestClient(app) as c:
        with Session() as s:
            s.execute(update(Usuario).values(admin=False, moderador=False))
            s.commit()
        adm, au = cadastrar(c, "Adm")
        with Session() as s:
            s.query(Usuario).filter(Usuario.id == au["id"]).update({Usuario.admin: True})
            s.commit()
        comum, cu = cadastrar(c, "Comum")
        assert c.get("/api/v1/admin/usuarios", headers=comum).status_code == 403
        assert c.post(f"/api/v1/admin/usuarios/{cu['id']}/perfil", headers=comum, json={"perfil": "admin"}).status_code == 403
        r = c.post(f"/api/v1/admin/usuarios/{cu['id']}/perfil", headers=adm, json={"perfil": "moderador"})
        assert r.status_code == 200 and r.json()["perfil"] == "moderador"
        me = c.get("/api/v1/me", headers=comum).json()
        assert (me["perfil_acesso"], me["equipe_moderacao"], me["admin"]) == ("moderador", True, False)
        assert c.get("/api/v1/moderacao/fila", headers=comum).status_code == 200 and c.get("/api/v1/moderacao/contagem", headers=comum).json()["total"] >= 0
        lista = c.get(f"/api/v1/admin/usuarios?q={cu['usuario']}", headers=adm).json()
        assert [i["perfil"] for i in lista["itens"]] == ["moderador"] and lista["resumo"]["administradores"] == 1
        assert c.post(f"/api/v1/admin/usuarios/{au['id']}/perfil", headers=adm, json={"perfil": "usuario"}).status_code == 400  # único admin

        # site: só o admin vê a página; o moderador vê a moderação
        site_adm, site_mod = TestClient(app), TestClient(app)
        for cli, usuario in ((site_adm, au), (site_mod, cu)):
            assert usuario["email"]
            assert cli.post("/entrar", data={"email": usuario["email"], "senha": "senha-de-teste-1"}, follow_redirects=False).status_code == 303
        assert site_adm.get("/administracao").status_code == 200 and "Administração" in site_adm.get("/mural").text
        assert site_mod.get("/administracao", follow_redirects=False).status_code == 303
        assert site_mod.get("/moderacao").status_code == 200
