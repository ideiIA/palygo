# Rastreabilidade: requisitos do projeto → código

Fonte: `PlayGO.docx`. Situação: ✅ feito · 🟡 parcial · ⏭ fase posterior (como o próprio projeto prevê).

| Requisito | Situação | Onde |
|---|---|---|
| Perfis Atleta / Organizador / Gestor | ✅ | `models.Usuario` (`gestor`), qualquer atleta organiza; `arenas.criar` concede gestão |
| Perfil do atleta (esportes+nível, disponibilidade, raio, localização) | ✅ | `contas.py`, `models.UsuarioModalidade`, tela Perfil (site e app) |
| Histórico de jogos e grupos | ✅ | `/perfil`, `/api/v1/minhas-atividades` |
| RF-001 Criar atividade | ✅ | `atividades.criar`, `/atividades/nova`, app Criar |
| RF-002 Participar (automática ou com aprovação) | ✅ | `vagas.entrar/aprovar/recusar` |
| RF-003 Encontrar atividades próximas (2/5/10/20 km/cidade) | ✅ | `descoberta.buscar_atividades`, `geo.py` |
| RF-004 / RF-020 Grupos (admins, chat, agenda, avisos, histórico) | ✅ | `grupos.py`, `/grupos` |
| RF-005 Cadastro de arenas e quadras | ✅ | `arenas.criar/criar_quadra` (fotos: só URL — upload pendente) |
| RF-006 Agenda das quadras | ✅ | `arenas.agenda_do_dia` (grade igual ao protótipo) |
| RF-007 / RF-021 Criar campeonato | ✅ | `campeonatos.criar` |
| RF-008 Inscrição de equipes, capitão convida | ✅ | `campeonatos.inscrever_equipe/convidar/responder_convite` |
| RF-009 Tabelas, confrontos, classificação, campeão | ✅ | `chaves.py`: sorteio (eliminatória ou pontos corridos), chaves, classificação, campeão, jogo ao vivo com placar e mesários; sub-páginas do campeonato (site e app) |
| RF-010 Descoberta geográfica de atividades, grupos, campeonatos, arenas | ✅ | `descoberta.explorar` |
| RF-011 Mapa esportivo com filtros | ✅ | Explorar (site e app), Leaflet/OSM |
| RF-012 Múltiplas modalidades sem mudar a aplicação | ✅ | tabela `modalidades` |
| RF-013 Vagas em tempo real | ✅ | `Atividade.confirmados` sob trava; cards atualizam ao confirmar |
| RF-014 Falta gente | ✅ | `atividades.definir_falta_gente`, selo "AO VIVO" |
| RF-015 Busca automática de atletas | ✅ | `match.candidatos/compatibilidade` |
| RF-016 Notificação de vagas próximas + preferências | ✅ | `match.avisar_compativeis`, `agendador.reforcar_urgentes`; push no aparelho ⏭ |
| RF-017 Entrada rápida "Eu vou" | ✅ | botão EU VOU (fetch no site, ação no app) |
| RF-018 Lista de espera e reposição automática | ✅ | `vagas.repor` |
| RF-019 Atividades sem quadra (ponto de encontro, percurso) | ✅ | `Modalidade.usa_quadra`, `Atividade.percurso` |
| RF-022 Descoberta de campeonatos | ✅ | `descoberta.buscar_campeonatos` |
| RF-023 Gestão B2B da arena | ✅ | `/gestao`, `arenas.py` |
| RF-024 Divulgação de horários disponíveis | ✅ | `arenas.divulgar/divulgar_ociosos`; reserva e pagamento pelo app ⏭ |
| RF-025 Feed personalizado (6 seções) | ✅ | `feed.montar` |
| RF-026 Prioridade por urgência e proximidade | ✅ | `urgencia.nota` |
| RF-027 Painel gerencial | 🟡 | `arenas.indicadores`; **receita de reservas e taxa de cancelamento** dependem de pagamento ⏭ |
| §10 Notificações inteligentes (lembrete, desistência, campeonato, grupo) | ✅ | `agendador.lembretes`, `vagas.repor`, `campeonatos._avisar_proximos`, `atividades.criar` |
| §11 Avaliação e reputação | ⏭ | fase 3 |
| §14 Modelo de negócio (planos, taxas, destaque patrocinado) | ⏭ | fase 3 |
| Visão web + visão aplicativo | ✅ | site `/`, PWA `/app/`, API `/api/v1` |

## Mural, comunidades e LGPD (pedido de 08/10/2026)

| Pedido | Situação | Onde |
|---|---|---|
| Feed geral e mural por evento, com comentários | ✅ | `publicacoes.py`, `escopos.py`, `mural.js`; `/mural`, mural em atividade/campeonato/comunidade |
| Local sempre marcado | ✅ | `Publicacao.latitude/longitude/local_nome` (no evento, o local do evento) |
| Organizador (ou quem ele definir) modera o mural | ✅ | `escopos.definir_moderador`, `Moderador` |
| Replicar do mural para o feed geral (escolha do autor) | ✅ | `Publicacao.replicar_geral` (só atividade pública, campeonato, comunidade pública) |
| Admin bloqueia → some de todos os lugares; admin não edita post alheio | ✅ | `publicacoes.ocultar/restaurar/editar` |
| Edição marcada ("editado em") | ✅ | `editado_em`, `*_versoes` |
| Exclusão só na 1ª hora; depois só ocultar | ✅ | `publicacoes.excluir`, `PLAYGO_JANELA_EXCLUSAO_MIN` |
| Atividade pública / só autorizados / por link | ✅ | `Atividade.visibilidade`, `convites.py` |
| Fotos e vídeos nas publicações | ✅ | `midia.py` (sem EXIF/GPS nas fotos; vídeo: metadados não removidos) |
| Pré-análise por IA → "em análise" → admin | ✅ (IA simulada em teste) | `moderacao.py`, `/moderacao` — **testar com chave real** |
| `@usuario` no cadastro, busca para convites | ✅ | `contas.py`, `/api/v1/atletas` |
| Comunidades de relacionamento | ✅ | `comunidades.py`, `/comunidades` |
| Guardar interações para resguardo legal | ✅ (ações principais) | `auditoria.py`, tabela `registros` somente-inserção |
| Termo de uso/privacidade, aceite versionado | ✅ (minuta; revisar com jurídico) | `termos.py`, portão em `deps.py` |
| LGPD: consentimento de localização, cópia dos dados, exclusão de conta, purga por prazo | ✅ | `contas.py`, `privacidade.py`, `/privacidade` |
| Perfis: administrador promove outros administradores e moderadores gerais | ✅ | `administracao.py`, `/administracao`, `#/admin` no app |
| Mensalidades por perfil (atleta grátis; organizador e arena pagos), teste 30 dias + 7 de tolerância, Asaas | ✅ (Asaas só simulado em teste) | `planos.py`, `cobranca.py`, `/planos`, Administração → Planos |
| Chat de grupo e textos de organizador moderados por IA | ⏭ | ainda não passam pela moderação |
