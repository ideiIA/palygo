# LGPD, guarda legal e moderação — o que foi feito e o que falta

Documento técnico para o time e para o jurídico. **Não é parecer jurídico.** Os textos de `playgo/termos.py` são uma
minuta de partida (LGPD, Marco Civil, CDC) e **precisam de revisão por advogado antes de ir para produção** —
principalmente os prazos, a base legal de cada tratamento, a cláusula de responsabilidade e o texto sobre IA.

## Mapa: pedido → implementação

| Pedido | Como está |
|---|---|
| Nome de usuário nas postagens e para convites | `Usuario.usuario` (único, minúsculo, 3–20, `a-z0-9_.`, reservados bloqueados). Obrigatório no cadastro; contas antigas são barradas até escolher (portão). Buscas expõem só `@usuario` e iniciais — nunca nome real nem e-mail. |
| Termo de uso/responsabilidade ao entrar | `playgo/termos.py` (Termos de Uso + Política de Privacidade, versionados). Aceite obrigatório no cadastro e a cada nova `VERSAO` (portão no site e na API). Cada aceite grava `AceiteTermos` com versão, data, IP e aparelho. |
| Maior de idade | Declaração obrigatória de 18+. **Menores não são suportados**; ver "Pendências". |
| Consentimento de localização | `consent_localizacao` (específico, opcional, revogável). Sem ele a API recusa guardar lat/lng no perfil. Revogar apaga a localização. |
| Guardar todas as interações para resguardo em lei | Tabela `registros` (somente inserção, com **gatilho no Postgres** que recusa UPDATE/DELETE): usuário, ação, objeto, IP, porta, aparelho, data/hora, detalhes. Cobre cadastro, login (e falha), aceite, consentimento, atividades, participações, publicações, comentários, edições, exclusões, ocultações, análises, denúncias, convites, moderadores, comunidades, exportação e exclusão de conta. |
| Excluir só na 1ª hora; depois só o admin esconde | `publicacoes.excluir` (janela `PLAYGO_JANELA_EXCLUSAO_MIN`, padrão 60). Depois: `ocultar` por moderador/admin. Excluído e oculto continuam **guardados** (ocultos do app). Vale para comentários também. |
| Edição "igual WhatsApp" | `editado_em` + texto "Editado em dd/mm às HH:MM"; versão anterior em `publicacao_versoes`/`comentario_versoes`. Reedição passa de novo pela análise. |
| Admin não edita publicação alheia | `publicacoes.editar` só aceita o autor. Admin e moderadores só **ocultam**, aprovam ou rejeitam. |
| Admin bloqueia → some de todos os lugares | Uma publicação é uma linha só (mural + replicação no geral): `status='oculta'` vale em todos. Só admin restaura o que admin ocultou. |
| Fotos e vídeos | `midia.py`: tipo pelos bytes (JPEG/PNG/WebP; MP4/MOV/WebM), limites de tamanho/quantidade, fotos reencodadas **sem EXIF/GPS**, miniatura, arquivos fora de `/static`, entrega só por URL assinada (1 h) ou sessão. |
| Pré-análise por IA, "em análise" para o autor, fila do admin | `moderacao.py`: regras locais + IA (Claude ou Gemini). Suspeito/falha/sem IA → `em_analise`: só o autor vê (com o aviso), vai para `/moderacao`. Admin aprova (libera para todos) ou rejeita. **Falha da IA nunca libera.** |
| Local sempre marcado | `Publicacao.latitude/longitude/local_nome` obrigatórios; no mural de atividade/campeonato o local é sempre o do evento (não dá para trocar). |
| Mural por evento + feed geral + replicar | `escopo` = geral/atividade/campeonato/comunidade; `replicar_geral` por publicação, só em atividade pública, campeonato ou comunidade pública. |
| Organizador ou quem ele definir cuida do mural | `Moderador` (delegação pelo organizador/gestor); dono/moderadores nas comunidades; admin no geral e em tudo. |
| Atividade pública / só autorizados / por link | `Atividade.visibilidade` (+ `convite_token`). Link não aparece na busca, no mapa, nem gera aviso; entra quem tem o link ou convite. Convite pelo `@usuario` dispensa aprovação. |
| Comunidades de relacionamento | `comunidades.py`: pública / só autorizados / só por link, dono, moderadores, banimento, mural, convites. |
| Foto de perfil | `contas.definir_foto`: só imagem, recortada em quadrado 400x400, JPEG sem EXIF/GPS, arquivo em `uploads/perfil/<32 hex>.jpg`. A URL (`/foto/<hex>.jpg`) é pública para quem a recebe e não adivinhável; trocar/remover/excluir conta apaga o arquivo. A foto não passa pela moderação por IA (pendência). |
| Direitos do titular (art. 18) | `/privacidade`: baixar cópia dos dados (`privacidade.exportar`), revogar localização, excluir conta (anonimiza), contato do encarregado. |

## Decisões que o time deve confirmar

0. **Perfis**: o moderador geral tem acesso de leitura a todos os murais (necessário para moderar) e vê e-mail e nome real? **Não** — só o administrador vê e-mail e nome real, na tela de administração; a consulta de usuários não é auditada (só as mudanças de perfil).

1. **Ocultar por moderador de escopo vale em todos os lugares** (inclusive no feed geral, se replicada). Foi a leitura mais
   simples de "admin bloqueia → todos os lugares"; se o organizador deve ocultar só no mural dele, é uma coluna a mais.
2. **Quem lê o mural**: atividade = confirmados/lista de espera + organização; campeonato = inscritos + organização;
   comunidade pública = qualquer logado lê, só membro posta; fechada = só membros. Admin lê tudo (necessário para moderar) — a Política diz isso.
3. **Prazo de guarda**: `PLAYGO_RETENCAO_REGISTROS_DIAS=365`. O Marco Civil exige no mínimo 6 meses de registros de acesso
   (provedor de aplicação); o prazo para conteúdo moderado/denunciado é decisão jurídica. A purga é **manual** (`python -m playgo purgar`).
4. **Exclusão de conta** anonimiza dados pessoais, tira conteúdo do ar e mantém texto/registros até o fim do prazo. Confirmar com o jurídico se o texto das publicações deve ser apagado antes.
5. **IA de moderação** envia texto e imagens (sem nome/e-mail) a Anthropic ou Google — dito na Política (transferência internacional, art. 33). Confirmar contrato/DPA com o provedor escolhido.

## Pendências e limites honestos

- **A IA não foi testada contra as APIs reais** (sem chaves nesta máquina): o formato dos pedidos e a leitura das respostas foram
  testados com transporte simulado (`tests/test_mural.py`). Antes de produção: configurar `PLAYGO_ANTHROPIC_API_KEY` ou `PLAYGO_GEMINI_API_KEY`,
  testar com conteúdo real e ajustar o prompt (`moderacao.SISTEMA`) e a lista de regras locais (`moderacao.REGRAS`, deliberadamente curta).
- **Vídeo**: só o Gemini analisa (até ~18 MB); com Claude ou sem IA, todo vídeo vai para revisão humana (`PLAYGO_MODERACAO_MIDIA_SEM_IA=revisar`).
  Metadados de vídeo (inclusive GPS) **não** são removidos — exigiria `ffmpeg`.
- **Sem IA configurada**, texto limpo é liberado pelas regras locais; foto/vídeo vão sempre para a fila do admin.
- **Chat de grupo** (`grupo_mensagens`) ainda não passa pela moderação nem pela IA; segue sem janela de exclusão. O mesmo vale para o "descrição" de atividades/grupos/arenas (texto do organizador).
- **Registros**: gravam as ações principais; **não** são um log de acesso de todas as requisições. Para atender o art. 15 do Marco Civil por completo,
  mantenha também o log de acesso do proxy reverso por 6 meses. Atrás de proxy, ligue `PLAYGO_CONFIAR_PROXY=true` para registrar o IP real.
- **Menores**: não suportados (declaração de 18+). Aceitar adolescentes exige desenho próprio (ECA Digital, consentimento dos responsáveis).
- **Comunicação de incidente à ANPD**, DPO formal, RIPD e registro de operações de tratamento são processos da empresa, não do código.
- O contato do encarregado (`PLAYGO_CONTATO_PRIVACIDADE`) e o nome do controlador (`PLAYGO_CONTROLADOR_NOME`) vêm com valor provisório: preencher.
- Nomes reais ainda aparecem para participantes em listas antigas de grupos de esporte (mural, comunidades, atividades e campeonatos já usam `@usuario`).
