# PlayGo

**Encontre onde jogar. Encontre com quem jogar.**

Plataforma que conecta atletas, organizadores de jogos e gestores de arenas: descoberta por geolocalização,
vagas em tempo real, "Falta gente", grupos, campeonatos e gestão B2B de quadras. Projeto de origem em
`PlayGO.docx`; protótipo visual em `prototipo_playgo_atualizado.html`.

Duas visões sobre o mesmo backend:

| Visão | Onde | Como é feita |
|---|---|---|
| **Web** | `http://localhost:8010/` | FastAPI + Jinja (renderização no servidor), menu lateral do protótipo |
| **Aplicativo** | `http://localhost:8010/app/` | PWA mobile-first (instalável, abas Início · Explorar · Criar · Grupos · Perfil), consome a API |
| **API** | `http://localhost:8010/api/v1` (docs em `/docs`) | JSON, token Bearer; serve o PWA e qualquer app nativo futuro |

## Rodar

```powershell
.\scripts\dev_db.ps1 start              # Postgres de desenvolvimento (porta 5434, pasta .pgdata)
.venv\Scripts\python -m playgo demo     # cria tabelas, modalidades e dados de demonstração (Campo Grande)
.venv\Scripts\python -m playgo web      # site, app e API em http://localhost:8010
```

Primeira vez: `python -m venv .venv` e `.venv\Scripts\pip install -r requirements-dev.txt`.
Publicar (GitHub + Supabase + Vercel): [docs/deploy.md](docs/deploy.md).
O login de demonstração (`carlos@playgo.local`) e a senha estão em `playgo/demo.py`.

Outros comandos: `init-db` (só tabelas + modalidades), `demo --refazer` (**apaga tudo** e recria — só desenvolvimento),
`ciclo` (roda uma vez as rotinas do agendador) e `agendador` (fica rodando sem a interface).
Testes: `.venv\Scripts\python -m pytest tests` (banco próprio `playgo_teste`; pula se o Postgres da 5434 estiver fora).
Para outro Postgres ou chave de sessão, copie `.env.example` para `.env`.

> O app (PWA) pede a localização do aparelho só quando a pessoa toca em 📍. Geolocalização e instalação como app
> exigem **HTTPS** fora do `localhost`: em produção ponha o servidor atrás de um proxy com TLS.

## Como funciona

Tudo é um serviço Python puro em `playgo/`; o site (`web/app.py`) e a API (`api/v1.py`) só chamam os mesmos serviços.

- **Descoberta** (`descoberta.py`, `geo.py`): atividades, campeonatos, arenas, grupos e horários de quadra ao redor do atleta.
  Sem PostGIS: latitude/longitude em colunas comuns, caixa delimitadora (índice) + haversine em SQL. Filtros: esporte,
  distância (2/5/10/20 km/cidade toda), hoje/amanhã/fim de semana, período, nível, gratuito/pago, com vagas, busca livre.
- **Vagas** (`vagas.py`): `Atividade.confirmados` é mantido sob trava de linha (`SELECT … FOR UPDATE`) junto de `Participacao`:
  duas pessoas na última vaga não passam as duas. "Eu vou" → *confirmado*, *pendente* (exige aprovação) ou *espera* (lotado).
  Desistência chama a lista de espera por ordem de chegada e avisa quem subiu. O organizador ocupa a primeira vaga.
- **Falta gente e urgência** (`atividades.py`, `urgencia.py`): o destaque liga o aviso aos atletas compatíveis. A nota de urgência
  (0–100) combina tempo até o início (35%), proximidade (30%), vagas restantes (20%) e o selo (15%); ordena a vitrine e o feed.
- **Match** (`match.py`): compatível = pratica o esporte + nível (exato ou um degrau) + dentro do raio dele + disponibilidade +
  categoria. Avisa quem aceita (`notif_vagas`) e está dentro do `notif_raio_km`; cada aviso tem `chave` única, então não repete.
- **Arenas** (`arenas.py`): quadras, agenda horário × quadra, reservas sem sobreposição (trava na quadra), **divulgação de horário
  ocioso** (vira oportunidade pública e avisa atletas próximos) e painel (reservas, ocupação, ociosos, atletas alcançados,
  recorrência, modalidades e dias de maior demanda). Atleta só usa uma quadra no horário que a arena divulgou; o gestor, em qualquer um.
- **Campeonatos** (`campeonatos.py`): cadastro, inscrição pelo capitão, convites aos jogadores, confirmação pelo organizador.
  Tabelas, confrontos e classificação ficam para a fase seguinte (RF-009 "posteriormente").
- **Grupos** (`grupos.py`): administradores, agenda, histórico, avisos fixados e chat (o app atualiza por polling a cada 5 s).
- **Notificações** (`notificacoes.py`, `agendador.py`): caixa de entrada no banco; lembrete "seu jogo começa em 2 horas" e reforço
  de "falta gente" na última hora pelo agendador. Push no aparelho não existe ainda — o app mostra o contador no sino.
- **Acesso** (`seguranca.py`, `deps.py`): senha com scrypt; site por cookie de sessão assinado, app por token Bearer assinado
  (30 dias). A API aceita os dois. O primeiro cadastro vira administrador.

## Mural, comunidades e LGPD

- **Mural** (`publicacoes.py`): publicações e comentários em quatro lugares — feed geral, atividade, campeonato e comunidade —
  sempre com o **local marcado**. No mural de atividade/campeonato o local é o do evento e só participantes leem e postam; o autor
  escolhe, post a post, se também vai ao feed geral (só atividade pública, campeonato ou comunidade pública).
- **Moderação**: tudo entra "em análise" e passa por regras locais + IA (Claude ou Gemini, `moderacao.py`). Suspeito, falha ou
  mídia sem IA → fica visível só para o autor ("em análise") e cai na fila do admin (`/moderacao`). O organizador (e quem ele indicar)
  cuida do mural da atividade; donos/moderadores, das comunidades; admin, de tudo. **Ninguém edita post alheio**; edição do autor
  aparece como "Editado em dd/mm às HH:MM". Exclusão só na 1ª hora; depois, só ocultar. Ocultar vale em todos os lugares.
- **Perfis de acesso** (`administracao.py`, tela `/administracao`): **administrador** (tudo, inclusive promover/rebaixar; nunca fica sem um),
  **moderador geral** (vê e decide a fila e oculta em qualquer mural, sem gerir usuários nem desfazer o que um admin ocultou) e usuário comum.
  Toda mudança de perfil é auditada e a pessoa é avisada. Organizadores e donos de comunidade continuam moderando só o que é deles.
- **Planos** (`planos.py`, `cobranca.py`, tela **Meu plano**): Usuário grátis (vê, publica no feed e participa); **Pro** (organiza atividades, com limites); **Organizador** (campeonatos e atividades sem limite) e **Arena** (tudo isso + arenas, quadras,
  agenda e horários divulgados) são pagos. Teste de 30 dias automático + 7 de tolerância; vencido, não cria nem divulga nada novo, mas o que existe continua.
  Participar é sempre grátis. Preços e limites o administrador edita; cobrança recorrente pelo Asaas (Pix, boleto, cartão) com webhook. Ver docs/deploy.md.
- **Atividade**: pública, só autorizados (você aprova ou convida pelo `@usuario`) ou só por link (não aparece em lugar nenhum).
- **Comunidades** de relacionamento: públicas, só autorizadas ou só por link, com mural, moderadores e convites.
- **LGPD**: `@usuario` obrigatório, Termos de Uso e Política de Privacidade versionados com aceite registrado (site e app),
  consentimento de localização revogável, fotos sem EXIF/GPS, trilha de interações **somente de inserção** (gatilho no Postgres),
  `/privacidade` (baixar dados, revogar localização, excluir conta) e `python -m playgo purgar` (prazo de guarda).
  Detalhes, decisões e pendências para o jurídico em [docs/lgpd.md](docs/lgpd.md).

IA de moderação (opcional): `PLAYGO_ANTHROPIC_API_KEY` ou `PLAYGO_GEMINI_API_KEY` (e `PLAYGO_IA_PROVEDOR`). Sem chave, só valem as regras
locais e foto/vídeo vão para a fila do admin.

## Telas

Menu do protótipo: **Início** (hero, "oportunidades agora", 🔥 precisam de jogadores, esportes, perto de você, quadras livres,
campeonatos, seus grupos, recomendados, arenas) · **Explorar** (filtros + mapa Leaflet/OpenStreetMap) · **Criar atividade** ·
**Feed** · **Meus grupos** · **Comunidades** · **Campeonatos** · **Moderação** (admin) · **Minha Arena** (painel, agenda do dia, divulgar horário, nova quadra) · Perfil · Notificações.
O app tem as mesmas funções em abas, mais Criar jogo / atividade / grupo / campeonato.

## Limitações conhecidas

- Chat de grupo e textos descritivos (atividade, grupo, arena) ainda não passam pela moderação.
- Sem pagamento, reserva paga, ranking e reputação/avaliações (fases 2 e 3 do projeto; o modelo já separa `Reserva`
  de `Atividade` para a reserva entrar sem mexer no resto).
- O local de uma atividade é marcado no mapa (clique ou GPS) ou vem da arena; não há busca de endereço (geocodificação).
- Tabelas criadas por `create_all`; colunas novas entram por `ALTER TABLE … IF NOT EXISTS` em `playgo/db.py` (sem Alembic,
  como no Licitações).
- Login simples: sem recuperação de senha por e-mail nem bloqueio por tentativas.
- O mapa carrega Leaflet e os blocos do OpenStreetMap pela internet; offline a lista continua funcionando.
- Fotos de perfil, arena e grupo guardam só uma URL; upload existe só nas publicações do mural.
