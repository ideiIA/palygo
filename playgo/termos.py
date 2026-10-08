"""Termos de Uso e Política de Privacidade (versionados). Trocar `VERSAO` obriga todo mundo a aceitar de novo.

Texto de partida redigido a partir da LGPD (Lei 13.709/2018), do Marco Civil da Internet (Lei 12.965/2014) e do
CDC; **precisa de revisão jurídica antes de ir para produção** (ver docs/lgpd.md)."""

from .config import settings

VERSAO = "2026-10-08"

DECLARACOES = {
    "termos": "Li e aceito os Termos de Uso e a Política de Privacidade, inclusive as regras de publicação e de moderação.",
    "maior_idade": "Declaro ter 18 anos ou mais.",
    "localizacao": "Autorizo o PlayGo a guardar a localização do meu perfil para mostrar atividades perto de mim (opcional; posso revogar a qualquer momento).",
}


def termos_de_uso() -> list[dict]:
    return [
        {"titulo": "1. Quem pode usar", "paragrafos": [
            "O PlayGo conecta atletas, organizadores e arenas. Para criar conta, você declara ter 18 anos ou mais e informar dados verdadeiros.",
            "Você é responsável por manter sua senha em sigilo e por tudo o que for feito na sua conta.",
        ]},
        {"titulo": "2. Nome de usuário", "paragrafos": [
            "Você escolhe um nome de usuário (@), único, que aparece nas suas publicações e comentários e permite que outras pessoas o encontrem para enviar convites. Não use nome de terceiros, marcas ou termos ofensivos; podemos alterá-lo quando violar estes termos.",
        ]},
        {"titulo": "3. Atividades, eventos e riscos esportivos", "paragrafos": [
            "O PlayGo é uma plataforma de conexão: não organiza as atividades, os campeonatos nem os espaços divulgados. Organizadores e gestores respondem pelo que anunciam.",
            "A prática esportiva envolve riscos. Participe conforme sua condição de saúde e por sua conta e risco. Pagamentos combinados entre usuários ocorrem fora do PlayGo, que não é parte deles.",
        ]},
        {"titulo": "4. Publicações, fotos, vídeos e comentários", "paragrafos": [
            "Você é o único responsável pelo que publica e comenta. O PlayGo não endossa o conteúdo dos usuários.",
            "É proibido publicar: ofensa, discriminação, discurso de ódio, ameaça, assédio ou incitação à violência; nudez ou conteúdo sexual; conteúdo que exponha crianças e adolescentes; dados pessoais de terceiros (como CPF, documentos, endereço residencial ou telefone) sem autorização; golpes, spam e propaganda não autorizada; conteúdo que viole direitos autorais, de imagem ou de privacidade; e qualquer conteúdo ilegal.",
            "Só publique fotos e vídeos de outras pessoas com autorização delas. Imagens de crianças e adolescentes exigem autorização de seus responsáveis.",
            "Você mantém seus direitos sobre o que publica e nos autoriza, de forma não exclusiva e gratuita, a exibi-lo no PlayGo conforme o alcance que você escolheu (mural da atividade, do campeonato, da comunidade ou feed geral).",
            "Toda publicação mostra o local marcado. Ao publicar, você concorda com a exibição desse local.",
        ]},
        {"titulo": "5. Moderação, edição e exclusão", "paragrafos": [
            "Antes de aparecer para os outros, textos e mídias passam por uma análise automática, que pode usar inteligência artificial de provedores contratados. Se algo suspeito for detectado, a publicação fica “em análise”, visível só para você, até que um administrador a avalie. Decisões nunca dependem só da máquina: você pode pedir revisão humana pelo contato indicado na Política de Privacidade.",
            "Organizadores (e quem eles indicarem) cuidam do mural da sua atividade ou campeonato; donos e moderadores cuidam das comunidades; administradores cuidam do feed geral e de toda a plataforma. Todos podem ocultar conteúdo que viole estes termos. Conteúdo ocultado por administrador some de todos os lugares.",
            "Você pode editar suas publicações e comentários. Toda edição fica sinalizada com “editado em” e a data e hora, e as versões anteriores são guardadas.",
            "Você pode excluir uma publicação ou comentário somente na primeira hora após postar. Depois disso, ela só pode ser ocultada por um moderador ou administrador. Mesmo excluído ou ocultado, o conteúdo é mantido de forma restrita pelo prazo legal descrito na Política de Privacidade.",
            "Administradores não editam publicações de outras pessoas; apenas ocultam, aprovam ou rejeitam.",
        ]},
        {"titulo": "6. Registros e guarda de dados", "paragrafos": [
            "Para cumprir a lei e permitir a defesa de direitos, guardamos registros das suas interações (data e hora, endereço IP e porta de origem, ações realizadas, publicações, edições, ocultações e exclusões). Esses registros podem ser fornecidos a autoridades mediante ordem judicial ou requisição legal.",
        ]},
        {"titulo": "7. Suspensão e encerramento", "paragrafos": [
            "Podemos suspender ou encerrar contas que violem estes termos ou a lei. Você pode encerrar sua conta a qualquer momento em Privacidade > Excluir conta.",
        ]},
        {"titulo": "8. Responsabilidade do PlayGo", "paragrafos": [
            "Empregamos esforços razoáveis de segurança e moderação, mas não garantimos disponibilidade ininterrupta nem a ausência de conteúdo indevido. Nos termos do Marco Civil da Internet, só respondemos por conteúdo de terceiros se, após ordem judicial específica, não tomarmos as providências cabíveis, sem prejuízo das hipóteses legais de remoção independente de ordem.",
        ]},
        {"titulo": "9. Mudanças nestes termos", "paragrafos": [
            f"Estes termos têm versão ({VERSAO}). Quando mudarem de forma relevante, pediremos um novo aceite para continuar usando o app.",
        ]},
        {"titulo": "10. Lei aplicável", "paragrafos": ["Aplica-se a legislação brasileira. Dúvidas ou reclamações: " + settings.contato_privacidade + "."]},
    ]


def politica_de_privacidade() -> list[dict]:
    return [
        {"titulo": "1. Quem é o controlador", "paragrafos": [
            f"O controlador dos seus dados é {settings.controlador_nome}. Encarregado (DPO) e canal para exercer seus direitos: {settings.contato_privacidade}.",
        ]},
        {"titulo": "2. Quais dados coletamos", "paragrafos": [
            "Cadastro: nome, e-mail, nome de usuário, senha (guardada de forma criptográfica, nunca em texto) e, opcionalmente, sexo, data de nascimento e foto.",
            "Perfil esportivo: esportes, níveis, disponibilidade, distância máxima e preferências de notificação.",
            "Localização: só se você autorizar, de forma específica, a guarda da localização do perfil; você pode revogar a qualquer momento. A localização de uma publicação é marcada por você (ou vem do evento) e fica visível a quem vê a publicação.",
            "Conteúdo: publicações, fotos, vídeos, comentários, mensagens de grupo, participações e inscrições.",
            "Registros: data e hora, endereço IP, porta de origem, aparelho/navegador e ações realizadas, além do histórico de aceite dos termos.",
        ]},
        {"titulo": "3. Para que usamos e em quais bases legais", "paragrafos": [
            "Executar o serviço que você contratou (conta, atividades, grupos, campeonatos, notificações): execução de contrato (LGPD, art. 7º, V).",
            "Mostrar atividades próximas a você: seu consentimento (art. 7º, I), revogável.",
            "Moderar conteúdo e prevenir fraude e abuso: legítimo interesse (art. 7º, IX) e proteção do crédito e da plataforma, com análise automática e revisão humana.",
            "Guardar registros de interação: cumprimento de obrigação legal (art. 7º, II; Marco Civil, arts. 13 e 15) e exercício regular de direitos em processos (art. 7º, VI).",
        ]},
        {"titulo": "4. Com quem compartilhamos", "paragrafos": [
            "Provedores de inteligência artificial contratados para moderação (Anthropic e/ou Google, conforme configuração): recebem o texto e as imagens/vídeos enviados em publicações e comentários apenas para análise de conteúdo ofensivo, sem seu nome ou e-mail. Isso pode envolver transferência internacional de dados (LGPD, art. 33).",
            "Provedores de hospedagem e infraestrutura, e autoridades públicas mediante ordem judicial ou obrigação legal.",
            "Não vendemos seus dados.",
        ]},
        {"titulo": "5. Por quanto tempo guardamos", "paragrafos": [
            f"Dados da conta: enquanto ela existir. Ao excluir a conta, anonimizamos seus dados pessoais. Registros de interação e conteúdo excluído ou ocultado ficam guardados de forma restrita por {settings.retencao_registros_dias} dias (prazo mínimo legal de seis meses para registros de acesso), sendo depois eliminados, salvo obrigação legal ou ordem de autoridade que exija mais tempo.",
        ]},
        {"titulo": "6. Seus direitos (LGPD, art. 18)", "paragrafos": [
            "Você pode confirmar a existência de tratamento, acessar, corrigir, anonimizar, bloquear ou eliminar dados, pedir portabilidade, saber com quem compartilhamos, revogar consentimentos e pedir a revisão de decisões automatizadas.",
            "No app, em Privacidade, você baixa uma cópia dos seus dados, revoga a localização e exclui a conta. Para os demais pedidos, escreva para " + settings.contato_privacidade + ".",
        ]},
        {"titulo": "7. Cookies", "paragrafos": ["Usamos apenas um cookie essencial de sessão, necessário para você permanecer conectado. Não usamos cookies de publicidade."]},
        {"titulo": "8. Segurança", "paragrafos": ["Senhas criptografadas, tráfego protegido, acesso restrito a mídias e trilha de auditoria somente de inserção. Se houver incidente relevante, comunicaremos você e a ANPD conforme a lei."]},
        {"titulo": "9. Crianças e adolescentes", "paragrafos": ["O PlayGo é destinado a maiores de 18 anos."]},
        {"titulo": "10. Mudanças", "paragrafos": [f"Esta política tem versão ({VERSAO}); mudanças relevantes exigem novo aceite."]},
    ]
