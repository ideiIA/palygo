# Instagram do PlayGo (@playgo.sports)

Publicações do feed geral **que o autor marcou** com "📸 Compartilhar no Instagram do PlayGo" vão para o perfil do PlayGo, depois de
aprovadas pela moderação **e** pela equipe, pela API oficial da Meta (Instagram API com login do Instagram).

```
autor marca a caixinha ─► moderação aprova a publicação ─► fila do Instagram (Moderação)
        ─► equipe aprova ─► agendador publica (foto, vídeo/reel ou carrossel) ─► link guardado e autor avisado
```

Nada vai sozinho: sempre há o **consentimento do autor** (registrado com data) e a **aprovação da equipe**.

## Configuração (uma vez)

### 1. Instagram e Facebook
- O @playgo.sports precisa ser **conta profissional** (Empresa ou Criador) — feito.
- Página do Facebook "PlayGo" vinculada à conta (recomendado, e já feita).

### 2. App da Meta (developers.facebook.com)
1. **Meus apps → Criar app** → caso de uso de **conteúdo e mensagens do Instagram**.
2. No app: **Instagram → Configuração da API com login do Instagram**.
3. Em **Configurar o login empresarial do Instagram** (Business login settings):
   - **URIs de redirecionamento OAuth válidas:** `https://SEU-DOMINIO/instagram/retorno`
     (ex.: `https://playgo.ideiiaapp.com.br/instagram/retorno`). Tem de ser **exatamente** igual, com `https`.
   - **URL de retorno de cancelamento de autorização** e **URL de solicitação de exclusão de dados**: pode usar
     `https://SEU-DOMINIO/politica-de-privacidade` enquanto não houver endpoint próprio.
4. **Configurações do app → Básico**: preencha **URL da Política de Privacidade** (`https://SEU-DOMINIO/politica-de-privacidade`) e a
   **categoria**. Anote o **ID do app** e a **Chave secreta do app**.
5. **Funções do app (App roles)**: a conta do Instagram precisa ter papel no app (administrador/testador). Enquanto o app estiver em
   **modo de desenvolvimento** e você só publicar na própria conta, **não precisa de revisão da Meta**.

### 3. Variáveis do servidor
```
PLAYGO_URL_PUBLICA=https://SEU-DOMINIO
PLAYGO_INSTAGRAM_APP_ID=<ID do app>
PLAYGO_INSTAGRAM_APP_SECRET=<chave secreta do app>
```
No servidor próprio vai no `deploy/.env`; no Vercel, em *Environment Variables* (e **Redeploy**). A chave secreta nunca vai para o git
nem para o navegador. Se ela foi colada em algum chat ou e-mail, **gere outra** em Configurações do app → Básico → *Redefinir*.

### 4. Conectar a conta
Entre como administrador → **Administração → 📸 Instagram do PlayGo → Conectar Instagram** → entre com o @playgo.sports e autorize.
O PlayGo troca o código por um token de longa duração (60 dias), guarda no banco e o **renova sozinho** (o agendador renova quando
faltam 15 dias). Para trocar de conta, clique em **Reconectar**.

## Uso
- **Autor:** ao publicar no feed geral (ou em mural replicado no geral) com foto/vídeo, marca "📸 Compartilhar no Instagram do PlayGo".
  Vê o estado na própria publicação (aguardando, aprovada, publicada com link, recusada).
- **Equipe de moderação:** em **Moderação → Instagram do PlayGo**, vê as publicações aprovadas pela moderação com a **legenda
  exata**, as mídias e a data do consentimento; **Aprovar e publicar** ou **Não enviar**. Erros aparecem em "Últimas", com **Tentar
  de novo**.
- **Legenda:** texto do autor (os `@` viram `＠` para não marcar contas erradas do Instagram) + `📍 local` + `por <usuário> no PlayGo`
  + `#playgo`, no máximo 2.200 caracteres.

## Limites e cuidados
- **A API não exclui posts.** Se a publicação for apagada ou ocultada no PlayGo depois de ir ao Instagram, o post continua lá até
  alguém removê-lo **pelo próprio Instagram**. Por isso há consentimento e aprovação, e a caixinha avisa isso.
- **Só vai o que é público** (feed geral); nada de atividade fechada, comunidade restrita ou por link.
- **Menores e fotos de terceiros:** a fila existe para a equipe recusar o que expõe quem não deveria.
- **Vídeos:** o Meta baixa o arquivo por uma URL pública do PlayGo (URL assinada de 1 h). No Vercel o upload é limitado a 4 MB; para
  vídeos maiores use o servidor próprio. O vídeo precisa ser MP4 (H.264); senão a publicação fica em "erro".
- **Cota:** a Meta limita a ~100 publicações por API a cada 24 h (confira a documentação atual).
- **Termos de Uso:** o consentimento por publicação está claro na tela. Se o jurídico preferir, acrescente às cláusulas de conteúdo a
  licença para as redes sociais do PlayGo (isso muda `termos.VERSAO` e pede novo aceite).
