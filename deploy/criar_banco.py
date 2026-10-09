"""Cria o usuário e o banco do PlayGo em QUALQUER Postgres que você administre (VPS próprio, RDS, Neon, DigitalOcean, Railway…),
com credenciais novas, e imprime a URL pronta para `PLAYGO_DATABASE_URL`.

Uso (precisa de `pip install "psycopg[binary]"`, que o próprio PlayGo já usa):
    python deploy/criar_banco.py --admin-url "postgresql://postgres:SENHA@HOST:5432/postgres" [--nome playgo] [--usuario playgo]

- Gera uma senha forte para o usuário da aplicação (ou use --senha).
- Cria o usuário e o banco (idempotente: se já existirem, só atualiza a senha).
- Não cria tabelas: o PlayGo cria tabelas, gatilhos de auditoria e esportes iniciais sozinho na primeira subida
  (`python -m playgo init-db`, ou ao subir o site com PLAYGO_AUTO_MIGRAR=true).
- Se o provedor exigir TLS, acrescente ?sslmode=require na URL impressa."""

import argparse
import secrets
import sys
from urllib.parse import quote, urlsplit

import psycopg
from psycopg import sql


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--admin-url", required=True, help="URL de um usuário administrador do Postgres (postgresql://usuario:senha@host:5432/postgres)")
    ap.add_argument("--nome", default="playgo", help="nome do banco a criar")
    ap.add_argument("--usuario", default="playgo", help="usuário da aplicação a criar")
    ap.add_argument("--senha", default="", help="senha do usuário da aplicação (em branco = gera uma forte)")
    ap.add_argument("--host-app", default="", help="host/porta que a APLICAÇÃO usa para chegar ao banco, se diferente do admin (ex.: db:5432)")
    args = ap.parse_args()

    senha = args.senha or secrets.token_urlsafe(32)
    partes = urlsplit(args.admin_url.replace("postgresql+psycopg://", "postgresql://"))
    with psycopg.connect(args.admin_url.replace("postgresql+psycopg://", "postgresql://"), autocommit=True) as c:
        existe = c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (args.usuario,)).fetchone()
        if existe:
            c.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(sql.Identifier(args.usuario), sql.Literal(senha)))
            print(f"Usuário {args.usuario!r} já existia: senha atualizada.", file=sys.stderr)
        else:
            c.execute(sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(sql.Identifier(args.usuario), sql.Literal(senha)))
            print(f"Usuário {args.usuario!r} criado.", file=sys.stderr)
        if c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (args.nome,)).fetchone():
            print(f"Banco {args.nome!r} já existia: mantido.", file=sys.stderr)
        else:
            c.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(sql.Identifier(args.nome), sql.Identifier(args.usuario)))
            print(f"Banco {args.nome!r} criado.", file=sys.stderr)
        c.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(args.nome)))
        c.execute(sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(sql.Identifier(args.nome), sql.Identifier(args.usuario)))

    host = args.host_app or f"{partes.hostname}:{partes.port or 5432}"
    url = f"postgresql+psycopg://{quote(args.usuario, safe='')}:{quote(senha, safe='')}@{host}/{args.nome}"
    print("\nColoque no ambiente da aplicação (e guarde a senha em local seguro):\n")
    print(f"PLAYGO_DATABASE_URL={url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
