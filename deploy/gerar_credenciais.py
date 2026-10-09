"""Gera o arquivo deploy/.env com credenciais NOVAS e fortes para a publicação própria do PlayGo.

Uso (na raiz do projeto, qualquer Python 3.9+, sem dependências):
    python deploy/gerar_credenciais.py --dominio playgo.seudominio.com.br --email voce@seudominio.com.br

Gera: senha do Postgres, chave de sessão, segredo do cron e token do webhook do Asaas. Não sobrescreve um .env existente
(use --forcar). O arquivo fica fora do git. Preencha à mão o que depende de terceiros (Google, Asaas, IA)."""

import argparse
import secrets
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dominio", required=True, help="endereço público, ex.: playgo.seudominio.com.br (sem https://)")
    ap.add_argument("--email", required=True, help="e-mail para os avisos do certificado HTTPS (Let's Encrypt)")
    ap.add_argument("--forcar", action="store_true", help="sobrescreve o .env existente (as credenciais antigas deixam de valer)")
    args = ap.parse_args()

    destino = PASTA / ".env"
    if destino.exists() and not args.forcar:
        print(f"Já existe {destino}. Use --forcar para gerar outro (as senhas mudam).", file=sys.stderr)
        return 1
    dominio = args.dominio.replace("https://", "").replace("http://", "").strip("/ ")

    modelo = (PASTA / ".env.exemplo").read_text(encoding="utf-8")
    valores = {
        "__DOMINIO__": dominio,
        "__EMAIL_ACME__": args.email.strip(),
        "__SENHA_BANCO__": secrets.token_urlsafe(32),
        "__CHAVE_SESSAO__": secrets.token_urlsafe(48),
        "__CRON_SECRET__": secrets.token_urlsafe(32),
        "__TOKEN_ASAAS__": secrets.token_urlsafe(32),
    }
    for chave, valor in valores.items():
        modelo = modelo.replace(chave, valor)
    destino.write_text(modelo, encoding="utf-8")
    try:
        destino.chmod(0o600)
    except OSError:
        pass
    print(f"Criado {destino}")
    print("Credenciais geradas: senha do banco, chave de sessão, segredo do cron e token do webhook do Asaas.")
    print("Falta preencher à mão (se for usar): PLAYGO_GOOGLE_*, PLAYGO_ASAAS_API_KEY, chaves de IA e os dados do controlador (LGPD).")
    print(f"Token do webhook do Asaas (cadastre o mesmo lá): {valores['__TOKEN_ASAAS__']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
