class FalhaConfiguracaoProvedor(Exception):
    def __init__(self, detalhe: str, status_code: int = 503) -> None:
        self.detalhe = detalhe
        self.status_code = status_code
        super().__init__(detalhe)
