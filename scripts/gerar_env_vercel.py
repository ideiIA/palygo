"""Gera `.env.vercel` (ignorado pelo git) para colar em Vercel > Settings > Environment Variables ("Import .env").
Lê o `.env` local, acrescenta o que o ambiente de produção exige e cria chaves aleatórias novas.
Uso: python scripts/gerar_env_vercel.py"""

import secrets
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
OBRIGATORIAS = ("PLAYGO_DATABASE_URL", "PLAYGO_SUPABASE_URL", "PLAYGO_SUPABASE_SERVICE_KEY")


def ler_env(arq: Path) -> dict[str, str]:
    saida: dict[str, str] = {}
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                if v.strip():
                    saida[k.strip()] = v.strip()
    return saida


def main() -> None:
    env = ler_env(RAIZ / ".env")
    faltam = [k for k in OBRIGATORIAS if k not in env]
    if faltam:
        raise SystemExit("Faltam no .env: " + ", ".join(faltam) + "\n(veja docs/deploy.md, passo 2)")
    url = env["PLAYGO_DATABASE_URL"]
    if "pooler.supabase.com" not in url and ":6543/" not in url:
        print("AVISO: no Vercel use a string do POOLER do Supabase (porta 6543), não a conexão direta.")
    env.setdefault("PLAYGO_CHAVE_SESSAO", secrets.token_urlsafe(48))
    env.setdefault("CRON_SECRET", secrets.token_urlsafe(32))
    env["PLAYGO_SERVERLESS"] = "true"
    env.setdefault("PLAYGO_AGENDADOR_NA_WEB", "false")
    env.setdefault("PLAYGO_FUSO", "America/Campo_Grande")
    (RAIZ / ".env.vercel").write_text("\n".join(f"{k}={v}" for k, v in sorted(env.items())) + "\n", encoding="utf-8")
    print(f".env.vercel gerado com {len(env)} variáveis (arquivo ignorado pelo git; não compartilhe).")
    print("Guarde a PLAYGO_CHAVE_SESSAO: trocá-la desconecta todo mundo.")


if __name__ == "__main__":
    main()
