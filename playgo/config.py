from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=RAIZ / ".env", env_prefix="PLAYGO_", extra="ignore")

    database_url: str = "postgresql+psycopg://playgo@localhost:5434/playgo"

    # Sessão do site e token do app: chave que assina os dois (em branco = gerada em .chave_sessao)
    chave_sessao: str = ""
    dias_token_app: int = 30

    fuso: str = "America/Campo_Grande"
    # Onde o mapa abre para quem ainda não informou a localização (Campo Grande, MS)
    latitude_padrao: float = -20.4697
    longitude_padrao: float = -54.6201

    # Descoberta
    raio_padrao_km: int = 10
    limite_resultados: int = 60
    # "Falta gente" some da vitrine depois que o jogo começou há mais que isso
    tolerancia_inicio_min: int = 30

    # Publicações e mídia
    pasta_uploads: Path = RAIZ / "uploads"
    max_foto_mb: int = 10
    max_video_mb: int = 50
    max_midias_post: int = 4
    max_texto_post: int = 2000
    janela_exclusao_min: int = 60  # o autor só exclui na primeira hora; depois, só moderador/admin oculta
    limite_posts_10min: int = 10
    denuncias_para_analise: int = 3  # denúncias que mandam o conteúdo para a análise do admin

    # Moderação por IA. Provedor: "claude" ou "gemini"; em branco = o que tiver chave preenchida.
    ia_provedor: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    modelo_moderacao: str = ""  # em branco = modelo barato padrão do provedor
    # Foto/vídeo quando não há IA que consiga analisar: "revisar" (admin avalia) ou "liberar"
    moderacao_midia_sem_ia: str = "revisar"

    # LGPD / Marco Civil
    controlador_nome: str = "PlayGo (razão social a definir)"
    contato_privacidade: str = "privacidade@playgo.invalid"
    retencao_registros_dias: int = 365  # prazo de guarda dos registros de interação (confirmar com o jurídico)
    confiar_proxy: bool = False  # lê o IP de X-Forwarded-For (só atrás de proxy de confiança)

    # Agendador: lembretes e reposição. A interface também dispara.
    agendador_na_web: bool = True
    intervalo_agendador_s: int = 60
    lembrete_antecedencia_min: int = 120


    @property
    def provedor_ia(self) -> str:
        """'claude', 'gemini' ou '' (sem IA configurada)."""
        if self.ia_provedor in ("claude", "gemini"):
            return self.ia_provedor if (self.anthropic_api_key if self.ia_provedor == "claude" else self.gemini_api_key) else ""
        return "claude" if self.anthropic_api_key else "gemini" if self.gemini_api_key else ""


settings = Settings()
