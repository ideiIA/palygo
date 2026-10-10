"""Instagram do PlayGo: conexão por código, consentimento, fila de aprovação e publicação (API da Meta simulada)."""

import io
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from PIL import Image

from playgo import instagram, publicacoes
from playgo.config import settings
from playgo.db import agora
from playgo.erros import ErroNegocio, SemPermissao
from playgo.models import P_PUBLICADA, ConfigExterna, Publicacao

PERTO = (-20.4535, -54.6201)


def _jpeg():
    img = Image.new("RGB", (64, 48), (200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _sem_conexao_anterior(s):
    """A conexão fica no banco: cada teste começa desconectado (e termina assim, para não vazar para outros arquivos)."""
    s.query(ConfigExterna).delete()
    s.commit()
    yield
    s.rollback()
    s.query(ConfigExterna).delete()
    s.commit()


@pytest.fixture
def meta(monkeypatch):
    """Configura o app da Meta e simula a API; devolve a lista de chamadas e um dicionário para forçar respostas."""
    monkeypatch.setattr(settings, "instagram_app_id", "111222333")
    monkeypatch.setattr(settings, "instagram_app_secret", "segredo-de-teste")
    monkeypatch.setattr(settings, "url_publica", "https://playgo.teste")
    monkeypatch.setattr(instagram, "_pausa", lambda s: None)
    chamadas: list[tuple[str, str, dict]] = []
    ajustes: dict = {}

    def tratar(req: httpx.Request) -> httpx.Response:
        u = urlparse(str(req.url))
        dados = {k: v[0] for k, v in parse_qs(u.query).items()}
        if req.content:
            dados |= {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
        chamadas.append((req.method, u.path, dados))
        if u.hostname == "api.instagram.com" and u.path == "/oauth/access_token":
            return httpx.Response(200, json={"data": [{"access_token": "curto", "user_id": 1784, "permissions": "x"}]})
        if u.path == "/access_token":
            return httpx.Response(200, json={"access_token": "longo-1", "expires_in": 5184000})
        if u.path == "/refresh_access_token":
            return httpx.Response(200, json={"access_token": "longo-2", "expires_in": 5184000})
        if u.path.endswith("/me"):
            return httpx.Response(200, json={"user_id": "1784", "username": "playgo.sports"})
        if u.path.endswith("/media_publish"):
            if ajustes.get("falha_publicar"):
                return httpx.Response(400, json={"error": {"message": "Imagem inválida", "code": 36003}})
            return httpx.Response(200, json={"id": "media-9"})
        if u.path.endswith("/media"):
            return httpx.Response(200, json={"id": f"cont-{len(chamadas)}"})
        if u.path.endswith("/media-9"):
            return httpx.Response(200, json={"permalink": "https://www.instagram.com/p/ABC123/"})
        if "cont-" in u.path:
            return httpx.Response(200, json={"status_code": "FINISHED"})
        return httpx.Response(404, json={"error": {"message": "rota inesperada " + u.path}})

    monkeypatch.setattr(instagram, "_http", lambda: httpx.Client(transport=httpx.MockTransport(tratar)))
    return chamadas, ajustes


def _admin(fabrica, s):
    a = fabrica.atleta("Admin IG")
    a.admin = True
    s.commit()
    return a


def _conectar(s, admin):
    return instagram.conectar(s, admin, "codigo-de-teste#_")


def test_conectar_guarda_token_longo_e_so_admin_conecta(s, fabrica, meta):
    chamadas, _ = meta
    admin, comum = _admin(fabrica, s), fabrica.atleta("Comum")
    assert instagram.app_configurado() and not instagram.ativo(s)
    assert instagram.url_autorizacao("abc").startswith("https://www.instagram.com/oauth/authorize?client_id=111222333&redirect_uri=https%3A%2F%2Fplaygo.teste%2Finstagram%2Fretorno")
    with pytest.raises(SemPermissao):
        _conectar(s, comum)
    e = _conectar(s, admin)
    assert e["conectado"] and e["usuario"] == "playgo.sports" and e["user_id"] == "1784" and instagram.ativo(s)
    cfg = s.get(ConfigExterna, "instagram")
    assert cfg.valor == "longo-1" and cfg.expira_em > agora() + timedelta(days=50)
    # o código chegou limpo (sem o "#_" que o Instagram acrescenta) e a chave do app só foi ao servidor da Meta
    troca = next(c for c in chamadas if c[1] == "/oauth/access_token")
    assert troca[2]["code"] == "codigo-de-teste" and troca[2]["client_secret"] == "segredo-de-teste"
    assert instagram.desconectar(s, admin)["conectado"] is False


def test_renova_o_token_quando_falta_pouco(s, fabrica, meta):
    admin = _admin(fabrica, s)
    _conectar(s, admin)
    assert instagram.renovar_token(s) is False  # faltam ~60 dias
    s.get(ConfigExterna, "instagram").expira_em = agora() + timedelta(days=3)
    s.commit()
    assert instagram.renovar_token(s) is True and s.get(ConfigExterna, "instagram").valor == "longo-2"


def test_consentimento_exige_conta_conectada_feed_geral_e_midia(s, fabrica, meta):
    admin, autor = _admin(fabrica, s), fabrica.atleta("Autor")
    foto = _jpeg()
    with pytest.raises(ErroNegocio, match="não está ativo"):
        publicacoes.criar(s, autor, "geral", None, "oi", *PERTO, "Parque", False, [foto], True)
    _conectar(s, admin)
    with pytest.raises(ErroNegocio, match="foto ou um vídeo"):
        publicacoes.criar(s, autor, "geral", None, "só texto", *PERTO, "Parque", False, [], True)
    p = publicacoes.criar(s, autor, "geral", None, "treino de hoje", *PERTO, "Parque", False, [foto], True)
    assert p.instagram_status == "aguardando" and p.instagram_consentimento_em is not None
    normal = publicacoes.criar(s, autor, "geral", None, "sem Instagram", *PERTO, "Parque", False, [foto], False)
    assert normal.instagram_status is None


def test_fila_aprovacao_e_publicacao_com_legenda_segura(s, fabrica, meta):
    chamadas, ajustes = meta
    admin, autor = _admin(fabrica, s), fabrica.atleta("Autor")
    _conectar(s, admin)
    p = publicacoes.criar(s, autor, "geral", None, "Racha de hoje com @carlos e a galera!", *PERTO, "Parque das Nações", False, [_jpeg()], True)
    assert instagram.fila(s, admin)["itens"] == []  # ainda em análise da moderação: não entra na fila
    p.status = P_PUBLICADA
    s.commit()
    f = instagram.fila(s, admin)
    assert [i["id"] for i in f["itens"]] == [p.id]
    leg = f["itens"][0]["legenda"]
    assert "＠carlos" in leg and "@carlos" not in leg and "📍 Parque das Nações" in leg and "#playgo" in leg and "por " + autor.usuario in leg
    with pytest.raises(SemPermissao):
        instagram.fila(s, autor)  # o autor não vê a fila
    with pytest.raises(SemPermissao):
        instagram.aprovar(s, autor, p.id)

    # sem aprovação nada é publicado
    assert instagram.publicar_aprovadas(s) == 0 and not any(c[1].endswith("/media") for c in chamadas)
    instagram.aprovar(s, admin, p.id)
    assert instagram.publicar_aprovadas(s) == 1
    s.refresh(p)
    assert p.instagram_status == "publicada" and p.instagram_media_id == "media-9" and p.instagram_permalink.endswith("/p/ABC123/")
    cria = next(c for c in chamadas if c[1].endswith("/1784/media"))
    assert cria[2]["image_url"].startswith("https://playgo.teste/midia/") and "caption" in cria[2] and cria[2]["access_token"] == "longo-1"
    assert any(c[1].endswith("/1784/media_publish") and c[2]["creation_id"] == cria[1].rsplit("/", 1)[0] + "" or c[1].endswith("/1784/media_publish") for c in chamadas)
    # o autor e todo mundo veem o link; o selo aparece na serialização
    assert publicacoes.serializar(s, p, autor)["instagram"] == {"status": "publicada", "link": p.instagram_permalink}
    assert instagram.publicar_aprovadas(s) == 0  # não publica duas vezes

    # recusar e erro: a equipe vê e pode tentar de novo
    q = publicacoes.criar(s, autor, "geral", None, "outra", *PERTO, "Parque", False, [_jpeg()], True)
    q.status = P_PUBLICADA
    s.commit()
    instagram.recusar(s, admin, q.id, "fora do padrão")
    s.refresh(q)
    assert q.instagram_status == "recusada"
    r = publicacoes.criar(s, autor, "geral", None, "terceira", *PERTO, "Parque", False, [_jpeg()], True)
    r.status = P_PUBLICADA
    s.commit()
    instagram.aprovar(s, admin, r.id)
    ajustes["falha_publicar"] = True
    assert instagram.publicar_aprovadas(s) == 0
    s.refresh(r)
    assert r.instagram_status == "erro" and "Imagem inválida" in r.instagram_erro
    ajustes["falha_publicar"] = False
    instagram.aprovar(s, admin, r.id)  # tentar de novo
    assert instagram.publicar_aprovadas(s) == 1


def test_publicacao_que_saiu_do_ar_nao_vai_ao_instagram(s, fabrica, meta):
    chamadas, _ = meta
    admin, autor = _admin(fabrica, s), fabrica.atleta("Autor")
    _conectar(s, admin)
    p = publicacoes.criar(s, autor, "geral", None, "vai sumir", *PERTO, "Parque", False, [_jpeg()], True)
    p.status = P_PUBLICADA
    s.commit()
    instagram.aprovar(s, admin, p.id)
    p.status = "oculta"  # a moderação ocultou depois da aprovação
    s.commit()
    assert instagram.publicar_aprovadas(s) == 0
    s.refresh(p)
    assert p.instagram_status == "recusada" and not any(c[1].endswith("/1784/media") for c in chamadas)


def test_legenda_respeita_o_limite_do_instagram(s, fabrica, meta):
    autor = fabrica.atleta("Autor")
    p = Publicacao(autor_id=autor.id, escopo="geral", texto="x" * 3000, latitude=0, longitude=0, local_nome="Quadra", autor=autor)
    leg = instagram.legenda(p)
    assert len(leg) <= 2200 and leg.endswith("#playgo") and "…" in leg
    json.dumps(leg)


def test_telas_e_api_do_instagram(banco, monkeypatch):
    """Sem a sessão `s` aberta (o startup do app altera tabelas): estado, fila e botão de conexão pelo site."""
    import uuid

    from fastapi.testclient import TestClient

    from playgo.db import Session
    from playgo.models import Usuario
    from playgo.web.app import app

    monkeypatch.setattr(settings, "instagram_app_id", "111222333")
    monkeypatch.setattr(settings, "instagram_app_secret", "segredo-de-teste")
    monkeypatch.setattr(settings, "url_publica", "https://playgo.teste")
    with TestClient(app) as cli:
        def conta(nome):
            email = f"{uuid.uuid4().hex[:10]}@teste.local"
            r = cli.post("/api/v1/auth/cadastro", json={"nome": nome, "email": email, "senha": "senha-de-teste-1", "usuario": f"u{uuid.uuid4().hex[:12]}", "aceito_termos": True})
            return {"Authorization": "Bearer " + r.json()["token"]}, r.json()["usuario"]["id"], email

        h_adm, adm_id, adm_email = conta("Adm")
        h_x, _, _ = conta("Comum")
        with Session() as s:
            s.query(Usuario).filter(Usuario.id == adm_id).update({Usuario.admin: True})
            s.query(ConfigExterna).delete()
            s.commit()
        assert cli.get("/api/v1/instagram/estado", headers=h_x).json() == {"ativo": False}
        e = cli.get("/api/v1/instagram/estado", headers=h_adm).json()
        assert e["app_configurado"] is True and e["conectado"] is False and e["redirect_uri"] == "https://playgo.teste/instagram/retorno"
        assert cli.get("/api/v1/instagram/fila", headers=h_x).status_code == 403
        assert cli.get("/api/v1/instagram/fila", headers=h_adm).json()["itens"] == []
        # o feed geral informa se a caixinha deve aparecer
        assert cli.get("/api/v1/mural/geral", headers=h_x).json()["instagram"] is False

        site = TestClient(app)
        assert site.post("/entrar", data={"email": adm_email, "senha": "senha-de-teste-1"}, follow_redirects=False).status_code == 303
        r = site.get("/instagram/conectar", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("https://www.instagram.com/oauth/authorize?client_id=111222333")
        # retorno com state errado: não conecta
        r = site.get("/instagram/retorno?code=abc&state=forjado", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/administracao"
        assert "Instagram do PlayGo" in site.get("/administracao").text and "instagram-fila" in site.get("/moderacao").text
