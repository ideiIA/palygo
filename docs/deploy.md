# Publicar o PlayGo: GitHub + Supabase + Vercel

Conta responsável: **ideiia@ideiia.com.br**. Repositório: https://github.com/ideiIA/palygo

```
GitHub (código) ──► Vercel (site + app + API, Python serverless)
                         │  PLAYGO_DATABASE_URL (pooler, porta 6543)
                         ├──► Supabase Postgres  (tabelas com RLS ligado)
                         └──► Supabase Storage   (bucket privado + URL assinada de 5 min)
```

## 1. GitHub

No terminal, na pasta do projeto (o Git abre o navegador: entre como **ideiIA**):

```powershell
git push -u origin main
```

O repositório é **público**. Ficam de fora (`.gitignore`): `PlayGO.docx`, o protótipo HTML, `.env`, `.chave_sessao`, `uploads/`.

## 2. Supabase (na conta da ideiia)

1. Em https://supabase.com/dashboard crie um projeto (nome sugerido: `playgo`, região **South America (São Paulo)**). Anote a senha do banco.
2. **Settings → Data API**: copie a *Project URL* (`https://<ref>.supabase.co`).
3. **Settings → API Keys**: copie a chave **service_role** (secreta; nunca vai para o navegador nem para o git).
4. **Connect → Transaction pooler**: copie a string de conexão e ajuste o início para `postgresql+psycopg://`.
5. Crie o arquivo `.env` (gitignored) na raiz:

```
PLAYGO_DATABASE_URL=postgresql+psycopg://postgres.<ref>:<SENHA>@aws-0-sa-east-1.pooler.supabase.com:6543/postgres
PLAYGO_SUPABASE_URL=https://<ref>.supabase.co
PLAYGO_SUPABASE_SERVICE_KEY=<service_role>
```

6. Prepare o banco e o Storage (uma vez; repita ao atualizar o esquema):

```powershell
.venv\Scripts\python -m playgo supabase
```

Isso cria as tabelas, o gatilho da trilha de auditoria, as modalidades, **liga o RLS em todas as tabelas sem política** (a API pública do
Supabase não enxerga nada; só o nosso servidor) e cria o bucket **privado** `playgo-midia`.

> Os dados de demonstração (`python -m playgo demo`) **não** devem ir para produção.
> O primeiro usuário que se cadastrar vira administrador; faça isso você mesmo antes de divulgar o endereço.

## 3. Vercel

1. https://vercel.com/new → entre com a conta da ideiia → **Import** `ideiIA/palygo` (o Vercel precisa ter acesso ao repositório pelo app GitHub dele).
2. Framework Preset: **Other**. Não precisa de Build Command. A entrada é `api/index.py` e o roteamento está em `vercel.json`.
3. Gere as variáveis de produção e cole em **Settings → Environment Variables → Import .env**:

```powershell
.venv\Scripts\python scripts\gerar_env_vercel.py
```

   Copie o conteúdo de `.env.vercel` (o arquivo é ignorado pelo git). Ele inclui `PLAYGO_SERVERLESS=true`, uma `PLAYGO_CHAVE_SESSAO` nova e o `CRON_SECRET`.
   Acrescente, quando for o caso: `PLAYGO_ANTHROPIC_API_KEY` ou `PLAYGO_GEMINI_API_KEY` (moderação por IA), `PLAYGO_CONTROLADOR_NOME`, `PLAYGO_CONTATO_PRIVACIDADE`.
4. **Deploy**. Abra a URL, cadastre-se (vira administrador) e teste: publicar com foto, foto de perfil, moderação.

## Como o PlayGo se comporta no Vercel

| Ponto | Como foi resolvido |
|---|---|
| Sem disco persistente | Fotos, vídeos e fotos de perfil vão para o **Supabase Storage** (bucket privado). O servidor confere a permissão e redireciona para uma URL assinada de 5 min. |
| Sem thread em segundo plano | A análise de moderação roda **dentro da requisição**. O agendador virou `GET /api/v1/cron/ciclo`, protegido por `CRON_SECRET`. |
| Tabelas | Não são criadas a cada partida (`PLAYGO_AUTO_MIGRAR` desligado no serverless). Rode `python -m playgo supabase` ao mudar o esquema. |
| Conexões | `NullPool` + pooler do Supabase (porta 6543, sem prepared statements). |
| Limite de 4,5 MB por requisição | Fotos são reduzidas no navegador antes de enviar (2048 px). **Vídeos ficam limitados a 4 MB** por enquanto. |
| Chave de sessão | Obrigatória por variável de ambiente (não há disco para guardá-la). |

### Rotinas periódicas (lembretes, "falta gente", encerramento)

`vercel.json` agenda o cron **uma vez por dia (09:00 UTC)**, o máximo do plano Hobby. Lembretes "seu jogo começa em 2 horas" precisam de frequência maior:

- **Vercel Pro**: troque `"0 9 * * *"` por `"*/10 * * * *"` em `vercel.json`.
- **Plano grátis**: use o `pg_cron` do Supabase para chamar o endereço a cada 10 minutos (SQL Editor):

```sql
create extension if not exists pg_cron;
create extension if not exists pg_net;
select cron.schedule('playgo-ciclo', '*/10 * * * *', $$
  select net.http_get(
    url := 'https://SEU-APP.vercel.app/api/v1/cron/ciclo',
    headers := jsonb_build_object('Authorization', 'Bearer SEU_CRON_SECRET'));
$$);
```

## Pendências conhecidas

- **Vídeos acima de 4 MB**: exigem upload direto do navegador para o Storage (URL assinada de envio). É a próxima etapa técnica.
- **Domínio próprio**, e-mail transacional e push no aparelho: não configurados.
- Os textos jurídicos continuam sendo minuta (ver `docs/lgpd.md`); como o repositório é público, o código da moderação e as listas de regras também ficam visíveis.
- Se o Vercel recusar o `includeFiles` ou o tamanho do pacote, o primeiro log de build indica o ajuste (as dependências somam bem menos que o limite de 250 MB).
