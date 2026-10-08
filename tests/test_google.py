"""Login com Google: fluxo OAuth simulado (sem falar com o Google de verdade)."""

import base64
import json
import time
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from playgo import google
from playgo.config import settings
from playgo.db import Session
from playgo.models import Usuario


def _jwt(**claims) -> str:
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{b({'alg': 'RS256'})}.{b(claims)}.assinatura"


@pytest.fixture
def conta_google(monkeypatch):
    """Configura o Google e devolve uma função que define o que o 'Google' responde na troca do código."""
    monkeypatch.setattr(settings, "google_client_id", "cliente-teste.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "segredo-teste")
    resposta: dict = {}

    def tratar(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "oauth2.googleapis.com" and b"segredo-teste" in req.content
        return httpx.Response(200, json={"id_token": _jwt(**resposta["claims"](_nonce(req)))}) if resposta.get("ok", True) else httpx.Response(400, json={})

    nonce_atual = {}
    _nonce = lambda req: nonce_atual["n"]  # noqa: E731
    monkeypatch.setattr(google, "_http", lambda: httpx.Client(transport=httpx.MockTransport(tratar)))

    def definir(email, sub=None, nonce_errado=False, verificado=True, **extra):
        sub = sub or uuid.uuid4().hex[:20]
        resposta["claims"] = lambda n: {
            "iss": "https://accounts.google.com", "aud": settings.google_client_id, "exp": int(time.time()) + 600, "sub": sub, "email": email,
            "email_verified": verificado, "name": "Maria Google", "nonce": "outro" if nonce_errado else n, **extra,
        }
        return sub

    definir.nonce = nonce_atual
    return definir


def _fazer_login(c: TestClient, nonce_atual: dict, **kw):
    r = c.get("/auth/google/iniciar" + ("?destino=app" if kw.get("app") else ""), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("https://accounts.google.com/")
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["client_id"] == [settings.google_client_id] and q["redirect_uri"][0].endswith("/auth/google/retorno") and q["scope"] == ["openid email profile"]
    nonce_atual["n"] = q["nonce"][0]
    return c.get("/auth/google/retorno", params={"code": "abc", "state": kw.get("state", q["state"][0])}, follow_redirects=False)


def test_botao_so_aparece_com_google_configurado(banco, monkeypatch):
    from playgo.web.app import app

    c = TestClient(app)
    monkeypatch.setattr(settings, "google_client_id", "")
    assert "Continuar com Google" not in c.get("/entrar").text and c.get("/api/v1/auth/provedores").json() == {"google": False}
    assert c.get("/auth/google/iniciar", follow_redirects=False).headers["location"] == "/entrar"
    monkeypatch.setattr(settings, "google_client_id", "x")
    monkeypatch.setattr(settings, "google_client_secret", "y")
    assert "Continuar com Google" in c.get("/entrar").text and "Continuar com Google" in c.get("/cadastro").text
    assert c.get("/api/v1/auth/provedores").json() == {"google": True}


def test_conta_nova_entra_pendente_de_usuario_e_termos(banco, conta_google):
    from playgo.web.app import app

    email = f"{uuid.uuid4().hex[:10]}@gmail.com"
    sub = conta_google(email)
    c = TestClient(app)
    r = _fazer_login(c, conta_google.nonce)
    assert r.status_code == 303 and r.headers["location"] == "/"
    with Session() as s:
        u = s.query(Usuario).filter_by(email=email).one()
        assert u.google_sub == sub and u.usuario is None and u.termos_versao is None and u.foto_url is None
    # o portão leva a escolher o @ antes de qualquer coisa
    assert c.get("/", follow_redirects=False).headers["location"] == "/cadastro/completar"
    assert c.post("/cadastro/completar", data={"nome_usuario": "g" + uuid.uuid4().hex[:8]}, follow_redirects=False).headers["location"] == "/termos/aceitar"
    assert c.post("/termos/aceitar", data={"aceito_termos": "1"}, follow_redirects=False).status_code == 303
    assert c.get("/mural").status_code == 200
    # e a mesma conta Google volta para o mesmo usuário
    c2 = TestClient(app)
    assert _fazer_login(c2, conta_google.nonce).headers["location"] == "/"
    with Session() as s:
        assert s.query(Usuario).filter_by(email=email).count() == 1


def test_vincula_conta_existente_pelo_email_verificado(banco, conta_google):
    from playgo.web.app import app

    email = f"{uuid.uuid4().hex[:10]}@gmail.com"
    c = TestClient(app)
    assert c.post("/cadastro", data={"nome": "Já Existia", "email": email, "senha": "senha-de-teste-1", "usuario": "j" + uuid.uuid4().hex[:9], "aceito_termos": "1", "maior_de_idade": "1"}, follow_redirects=False).status_code == 303
    sub = conta_google(email)
    c2 = TestClient(app)
    assert _fazer_login(c2, conta_google.nonce).headers["location"] == "/"
    assert c2.get("/mural").status_code == 200  # já tinha @ e termos: entra direto
    with Session() as s:
        assert s.query(Usuario).filter_by(email=email).one().google_sub == sub


def test_recusa_login_inseguro(banco, conta_google):
    from playgo.web.app import app

    c = TestClient(app)
    conta_google(f"{uuid.uuid4().hex[:10]}@gmail.com", nonce_errado=True)
    assert _fazer_login(c, conta_google.nonce).headers["location"] == "/entrar"  # nonce não confere
    conta_google(f"{uuid.uuid4().hex[:10]}@gmail.com", verificado=False)
    assert _fazer_login(c, conta_google.nonce).headers["location"] == "/entrar"  # e-mail não verificado
    assert c.get("/mural", follow_redirects=False).headers["location"] == "/entrar"  # nada de sessão
    conta_google(f"{uuid.uuid4().hex[:10]}@gmail.com")
    assert _fazer_login(c, conta_google.nonce, state="forjado").headers["location"] == "/entrar"  # state não confere
    assert c.get("/auth/google/retorno?code=x&state=y", follow_redirects=False).headers["location"] == "/entrar"  # sem passar pelo início
    assert c.get("/auth/google/retorno?error=access_denied", follow_redirects=False).headers["location"] == "/entrar"


def test_app_recebe_o_token_no_fragmento(banco, conta_google):
    from playgo.web.app import app

    conta_google(f"{uuid.uuid4().hex[:10]}@gmail.com")
    c = TestClient(app)
    destino = _fazer_login(c, conta_google.nonce, app=True).headers["location"]
    assert destino.startswith("/app/#/google/")
    token = destino.rsplit("/", 1)[1]
    assert c.get("/api/v1/me", headers={"Authorization": "Bearer " + token}).json()["pendencia"] == "usuario"
