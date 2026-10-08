"""Foto de perfil: recorte quadrado, sem EXIF/GPS, troca, remoção, exibição e exclusão de conta."""

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from playgo import contas, midia, privacidade, publicacoes
from playgo.erros import ErroNegocio


def _imagem(tamanho=(800, 500), exif=False, formato="JPEG"):
    img = Image.new("RGB", tamanho, (30, 140, 90))
    buf = io.BytesIO()
    if exif:
        e = Image.Exif()
        e[0x010F] = "CameraDoLuiz"
        gps = e.get_ifd(0x8825)
        gps[1], gps[2], gps[3], gps[4] = "S", (20.0, 28.0, 10.0), "W", (54.0, 37.0, 12.0)
        img.save(buf, formato, exif=e)
    else:
        img.save(buf, formato)
    return buf.getvalue()


def test_avatar_quadrado_sem_metadados():
    jpeg = midia.processar_avatar(_imagem((1200, 600), exif=True))
    img = Image.open(io.BytesIO(jpeg))
    assert img.size == (400, 400) and len(img.getexif()) == 0 and b"CameraDoLuiz" not in jpeg
    assert Image.open(io.BytesIO(midia.processar_avatar(_imagem(formato="PNG")))).size == (400, 400)


def test_avatar_recusa_o_que_nao_e_foto():
    for lixo in (b"", b"<svg onload=alert(1)>", b"\x00\x00\x00\x18ftypmp42" + b"\0" * 80, b"\xff\xd8\xff corpo invalido"):
        with pytest.raises(ErroNegocio):
            midia.processar_avatar(lixo)


def test_trocar_e_remover_foto_apaga_o_arquivo_antigo(s, fabrica):
    u = fabrica.atleta("Com Foto")
    contas.definir_foto(s, u, _imagem())
    assert u.foto_url.startswith("/foto/") and len(u.foto_url) == len("/foto/") + 36
    primeira = midia.caminho("perfil/" + u.foto_url[6:])
    assert primeira.exists()
    contas.definir_foto(s, u, _imagem((300, 300)))
    assert not primeira.exists() and midia.caminho("perfil/" + u.foto_url[6:]).exists()
    atual = midia.caminho("perfil/" + u.foto_url[6:])
    contas.remover_foto(s, u)
    assert u.foto_url is None and not atual.exists()


def test_excluir_conta_apaga_a_foto(s, fabrica):
    u = fabrica.atleta("Quem Sai")
    contas.definir_foto(s, u, _imagem())
    arquivo = midia.caminho("perfil/" + u.foto_url[6:])
    admin = fabrica.atleta("Admin")
    admin.admin = True
    s.commit()
    privacidade.excluir_conta(s, u, "senha-de-teste-1")
    assert not arquivo.exists() and u.foto_url is None


def test_foto_aparece_no_mural(s, fabrica):
    u = fabrica.atleta("Postador")
    contas.definir_foto(s, u, _imagem())
    p = publicacoes.criar(s, u, "geral", None, "oi", latitude=1.0, longitude=1.0)
    assert publicacoes.serializar(s, p, u)["autor"]["foto_url"] == u.foto_url


def test_foto_pela_api_e_pelo_site(banco):
    from playgo.web.app import app

    with TestClient(app) as c:
        email = f"{uuid.uuid4().hex[:10]}@teste.local"
        r = c.post("/api/v1/auth/cadastro", json={"nome": "Foto Api", "email": email, "senha": "senha-de-teste-1", "usuario": f"f{uuid.uuid4().hex[:12]}", "aceito_termos": True, "maior_de_idade": True})
        h = {"Authorization": "Bearer " + r.json()["token"]}
        assert c.post("/api/v1/me/foto", headers=h, files={"arquivo": ("x.txt", b"nao sou foto", "text/plain")}).status_code == 400
        assert c.post("/api/v1/me/foto", headers={}, files={"arquivo": ("f.jpg", _imagem(), "image/jpeg")}).status_code == 401
        me = c.post("/api/v1/me/foto", headers=h, files={"arquivo": ("f.jpg", _imagem(exif=True), "image/jpeg")}).json()
        foto = me["foto_url"]
        resp = c.get(foto)
        assert resp.status_code == 200 and resp.headers["content-type"] == "image/jpeg" and Image.open(io.BytesIO(resp.content)).size == (400, 400)
        assert c.get("/foto/nao-existe.jpg").status_code == 404 and c.get("/foto/" + "0" * 32 + ".jpg").status_code == 404
        assert c.get("/foto/..%2F..%2Fconfig.jpg").status_code == 404
        assert c.delete("/api/v1/me/foto", headers=h).json()["foto_url"] is None
        assert c.get(foto).status_code == 404
