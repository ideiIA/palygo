"""Prepara um banco/Storage do Supabase para o PlayGo: tabelas, trilha de auditoria, modalidades, RLS e bucket privado.
Uso: `python -m playgo supabase` (com PLAYGO_DATABASE_URL e, para o bucket, PLAYGO_SUPABASE_URL + PLAYGO_SUPABASE_SERVICE_KEY).

Por que o RLS: o Supabase expõe as tabelas do schema `public` por uma API REST aberta pela chave pública (anon).
Ligar o RLS **sem nenhuma política** fecha essa porta: só o nosso servidor, que conecta como dono do banco, enxerga os dados."""

import httpx
from sqlalchemy import text

from . import armazenamento, modalidades
from .db import Session, criar_tabelas, engine


def preparar() -> list[str]:
    avisos: list[str] = []
    criar_tabelas()
    with Session() as s:
        novas = modalidades.semear(s)
    avisos.append(f"Tabelas e trilha de auditoria prontas; {novas} modalidade(s) nova(s).")

    with engine.begin() as c:
        tabelas = [r[0] for r in c.execute(text("select tablename from pg_tables where schemaname = 'public' order by 1"))]
        for t in tabelas:
            c.execute(text(f'ALTER TABLE public."{t}" ENABLE ROW LEVEL SECURITY'))
        papeis = {r[0] for r in c.execute(text("select rolname from pg_roles where rolname in ('anon', 'authenticated')"))}
        for papel in sorted(papeis):  # defesa em profundidade: sem acesso direto às tabelas pela API pública
            c.execute(text(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{papel}"'))
            c.execute(text(f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM "{papel}"'))
    avisos.append(f"RLS ligado em {len(tabelas)} tabela(s), sem políticas; acesso público revogado ({', '.join(sorted(papeis)) or 'sem papéis anon/authenticated neste banco'}).")
    try:
        avisos.append(armazenamento.garantir_bucket())
    except httpx.HTTPError as e:
        avisos.append(f"ATENÇÃO: o bucket NÃO foi criado ({e.__class__.__name__}: confira PLAYGO_SUPABASE_URL e PLAYGO_SUPABASE_SERVICE_KEY). Rode de novo depois de corrigir.")
    return avisos
