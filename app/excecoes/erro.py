class ErroEnvioZenvia(Exception):
    
    def __init__(self, mensagem: str, status_code: int | None = None, corpo: str | None = None) -> None:
        super().__init__(mensagem)
        self.status_code = status_code
        self.corpo = corpo
