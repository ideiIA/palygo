class ErroNegocio(Exception):
    """Regra de negócio violada. A mensagem já está em português e vai direto para a tela."""


class NaoEncontrado(ErroNegocio):
    pass


class SemPermissao(ErroNegocio):
    pass
