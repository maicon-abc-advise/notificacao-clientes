"""Textos literais dos templates (alinhado a analise-inicial/PLANO_TEMPLATES.md)."""

from app.templates.modelo import CodigoTipoTemplate

IDS_POR_TIPO: dict[CodigoTipoTemplate, str] = {
    CodigoTipoTemplate.APARECEU_BUSCA: "a1b2c3d4-e5f6-4789-a012-345678abcdef",
    CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO: "e5f6a7b8-c9d0-4123-e456-789abcdef012",
    CodigoTipoTemplate.CREDITOS_NO_FIM: "b2c3d4e5-f6a7-4890-b123-456789abcdef",
    CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS: "c3d4e5f6-a7b8-4901-c234-56789abcdef0",
    CodigoTipoTemplate.CONSULTADO_SEM_EMAIL: "d4e5f6a7-b8c9-4012-d345-6789abcdef01",
    CodigoTipoTemplate.APRESENTACAO: "f1a2b3c4-d5e6-4789-a012-345678abcdef",
    CodigoTipoTemplate.BUSCA_COMPRADOR: "a7b8c9d0-e1f2-4345-a678-901234567890",
}

SMS_BUSCA_COMPRADOR = (
    "BuscaFornecedor: Veja o resultado da sua busca: {{ url }}"
)

SMS_APARECEU_BUSCA = (
    "Clientes em {{ uf }} buscaram fornecedores de {{ segmento }}. "
    "Sua empresa apareceu! Veja agora em: {{ url_login }}."
)

SMS_APARECEU_BUSCA_SEM_REGISTRO = (
    "Clientes em {{ uf }} buscaram fornecedores de {{ segmento }}. "
    "Sua empresa apareceu! Veja agora em: {{ url_login }}."
)

SMS_CREDITOS_NO_FIM = (
    "BuscaFornecedor: Seus créditos estão acabando! Garanta que sua empresa continue no topo "
    "das buscas hoje. Renove agora em: buscafornecedor.com.br"
)

SMS_LEMBRETE_CREDITOS = (
    "Atenção: Sua visibilidade na BuscaFornecedor foi interrompida por falta de créditos. "
    "Regularize e não perca vendas: buscafornecedor.com.br"
)

SMS_CONSULTADO_SEM_EMAIL = (
    "Clientes em {{ uf }} buscaram fornecedores de {{ segmento }}, mas você está sem e-mail de contato. "
    "Não perca vendas, resolva em: {{ url_login }}."
)

SMS_APRESENTACAO = "BuscaFornecedor: conheça a plataforma em {{ url_plataforma }}."

EMAIL_APARECEU_BUSCA = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Oportunidade em {{ uf }} identificada</title>
  <style>
    body { margin: 0; padding: 0; background-color: #f9fafb; font-family: "Inter", Arial, sans-serif; color: #0f172a; }
    .container { max-width: 600px; margin: 40px auto; background: #ffffff; border-radius: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); overflow: hidden; }
    .header { background: linear-gradient(90deg, #0f172a, #00c38a); color: #fff; text-align: center; padding: 24px; font-size: 22px; font-weight: 600; }
    .content { padding: 32px 24px; line-height: 1.6; }
    .content h1 { font-size: 20px; color: #0f172a; margin-bottom: 16px; text-align: left; }
    .content p { font-size: 15px; color: #475569; margin-bottom: 20px; }
    .highlight { background: #f8fafc; padding: 20px; border-radius: 10px; border: 1px solid #e2e8f0; border-left: 4px solid #00c38a; margin-bottom: 28px; font-size: 15px; color: #334155; }
    .button { display: inline-block; background: #00c38a; color: #fff !important; text-decoration: none; padding: 14px 30px; border-radius: 8px; font-weight: 700; text-transform: uppercase; font-size: 14px; }
    .footer { text-align: center; font-size: 13px; color: #94a3b8; padding: 32px 24px; border-top: 1px solid #f1f5f9; background-color: #f9fafb; }
    @media (max-width: 600px) { .content { padding: 24px 16px; } }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">BuscaFornecedor</div>
    <div class="content">
      <h1>Detectamos buscas por Fornecedores de {{ segmento }} em {{ uf }}!</h1>
      <div class="highlight">
        Olá, {{ saudacao_nome }}. <br><br>
        Temos ótimas notícias: sua empresa acaba de ser encontrada por compradores que buscam fornecedores exatamente no seu setor em <strong>{{ uf }}</strong>.
      </div>
      <p>
        O mercado de <strong>{{ segmento }}</strong> está em alta na sua região. O fato de você ter aparecido nessa busca prova que sua empresa está no radar de quem tem poder de compra agora.
      </p>
      <p>
        Não deixe essa visibilidade passar em branco. Acesse sua área exclusiva para ver os detalhes dessa atividade e garantir que seu perfil se destaque da concorrência.
      </p>
      <p style="text-align:center;">
        <a href="{{ url_login }}" class="button" target="_blank">Aproveitar Oportunidade</a>
      </p>
      <p style="font-size: 14px; color: #64748b; margin-top: 30px; border-top: 1px solid #f1f5f9; padding-top: 15px;">
        <strong>Dica:</strong> Manter seus dados 100% atualizados aumenta drasticamente as chances de converter essas buscas em novos contratos reais.
      </p>
    </div>
    <div class="footer">
      © BuscaFornecedor — Todos os direitos reservados.<br/>
      <a href="{{ url_plataforma }}" style="color:#00c38a; text-decoration:none;">buscafornecedor.com.br</a>
    </div>
  </div>
</body>
</html>"""

EMAIL_APARECEU_BUSCA_SEM_REGISTRO = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Empresas em {{ uf }} buscam seu setor</title>
  <style>
    body { margin: 0; padding: 0; background-color: #f9fafb; font-family: "Inter", Arial, sans-serif; color: #0f172a; }
    .container { max-width: 600px; margin: 40px auto; background: #ffffff; border-radius: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); overflow: hidden; }
    .header { background: linear-gradient(90deg, #0f172a, #00c38a); color: #fff; text-align: center; padding: 24px; font-size: 22px; font-weight: 600; }
    .content { padding: 32px 24px; line-height: 1.6; }
    .content h1 { font-size: 20px; color: #0f172a; margin-bottom: 16px; text-align: left; }
    .content p { font-size: 15px; color: #475569; margin-bottom: 20px; }
    .highlight { background: #f8fafc; padding: 20px; border-radius: 10px; border: 1px solid #e2e8f0; border-left: 4px solid #00c38a; margin-bottom: 28px; font-size: 15px; color: #334155; }
    .button { display: inline-block; background: #00c38a; color: #fff !important; text-decoration: none; padding: 14px 30px; border-radius: 8px; font-weight: 700; text-transform: uppercase; font-size: 14px; }
    .footer { text-align: center; font-size: 13px; color: #94a3b8; padding: 32px 24px; border-top: 1px solid #f1f5f9; background-color: #f9fafb; }
    @media (max-width: 600px) { .content { padding: 24px 16px; } }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">BuscaFornecedor</div>
    <div class="content">
      <h1>Detectamos demanda para fornecedores de {{ segmento }} em {{ uf }} e você foi listado!</h1>
      <div class="highlight">
        Olá, {{ saudacao_nome }}. <br><br>
        Identificamos que compradores em <strong>{{ uf }}</strong> realizaram buscas por fornecedores de <strong>{{ segmento }}</strong> e sua empresa foi listada.
      </div>
      <p>
        Sua empresa já está no radar do mercado, mas você ainda não assumiu o controle do seu perfil. Sem um cadastro completo, potenciais clientes perdem o contato direto e acabam fechando com quem já está verificado na plataforma.
      </p>
      <p>
        <strong>Não deixe essa oportunidade na mesa:</strong> finalize seu cadastro agora para ser encontrado com prioridade e receber propostas diretas.
      </p>
      <p style="text-align:center;">
        <a href="{{ url_login }}" class="button" target="_blank">Reivindicar meu Perfil</a>
      </p>
      <p style="font-size: 14px; color: #64748b; margin-top: 30px; border-top: 1px solid #f1f5f9; padding-top: 15px;">
        * Fornecedores com cadastro completo aparecem até 5x mais nos resultados de busca do que perfis básicos.
      </p>
    </div>
    <div class="footer">
      © BuscaFornecedor — Todos os direitos reservados.<br/>
      <a href="{{ url_plataforma }}" style="color:#00c38a; text-decoration:none;">buscafornecedor.com.br</a>
    </div>
  </div>
</body>
</html>"""

EMAIL_CREDITOS_NO_FIM = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Aviso de Visibilidade: Créditos no fim</title>
  <style>
    body { margin: 0; padding: 0; background-color: #f9fafb; font-family: "Inter", Arial, sans-serif; color: #0f172a; }
    .container { max-width: 600px; margin: 40px auto; background: #ffffff; border-radius: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); overflow: hidden; }
    .header { background: linear-gradient(90deg, #0f172a, #00c38a); color: #fff; text-align: center; padding: 24px; font-size: 22px; font-weight: 600; }
    .content { padding: 32px 24px; line-height: 1.6; }
    .content h1 { font-size: 22px; color: #0f172a; margin-bottom: 16px; text-align: left; letter-spacing: -0.5px; }
    .content p { font-size: 15px; color: #475569; margin-bottom: 20px; }
    .highlight { background: #fef2f2; padding: 20px; border-radius: 10px; border: 1px solid #fee2e2; border-left: 4px solid #ef4444; margin-bottom: 28px; font-size: 15px; color: #991b1b; }
    .button { display: inline-block; background: #00c38a; color: #fff !important; text-decoration: none; padding: 14px 30px; border-radius: 8px; font-weight: 700; text-transform: uppercase; font-size: 14px; }
    .footer { text-align: center; font-size: 13px; color: #94a3b8; padding: 32px 24px; border-top: 1px solid #f1f5f9; background-color: #f9fafb; }
    @media (max-width: 600px) { .content { padding: 24px 16px; } }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">BuscaFornecedor</div>
    <div class="content">
      <h1>Não deixe sua empresa sumir das buscas!</h1>
      <div class="highlight">
        Olá, {{ saudacao_nome }}. <br><br>
        Identificamos que seus créditos de visibilidade estão quase esgotados. Para evitar que sua empresa pare de aparecer para compradores, recomendamos a renovação imediata.
      </div>
      <p>
        Estar ativo na <strong>BuscaFornecedor</strong> garante que você seja encontrado no momento exato em que o cliente decide comprar. Quando seus créditos acabam, sua empresa perde o lugar no topo para a concorrência.
      </p>
      <p>
        Acesse sua área de gestão para garantir a continuidade da sua visibilidade:
      </p>
      <p style="text-align:center;">
        <a href="{{ url_login }}" class="button" target="_blank">Renovar meus créditos</a>
      </p>
    </div>
    <div class="footer">
      © BuscaFornecedor — Todos os direitos reservados.<br/>
      <a href="{{ url_plataforma }}" style="color:#00c38a; text-decoration:none;">buscafornecedor.com.br</a>
    </div>
  </div>
</body>
</html>"""

EMAIL_LEMBRETE_CREDITOS = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Sua visibilidade foi interrompida</title>
  <style>
    body { margin: 0; padding: 0; background-color: #f9fafb; font-family: "Inter", Arial, sans-serif; color: #0f172a; }
    .container { max-width: 600px; margin: 40px auto; background: #ffffff; border-radius: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); overflow: hidden; }
    .header { background: linear-gradient(90deg, #0f172a, #00c38a); color: #fff; text-align: center; padding: 24px; font-size: 22px; font-weight: 600; }
    .content { padding: 32px 24px; line-height: 1.6; }
    .content h1 { font-size: 22px; color: #0f172a; margin-bottom: 16px; text-align: left; letter-spacing: -0.5px; }
    .content p { font-size: 15px; color: #475569; margin-bottom: 20px; }
    .highlight { background: #fef2f2; padding: 20px; border-radius: 10px; border: 1px solid #fee2e2; border-left: 4px solid #ef4444; margin-bottom: 28px; font-size: 15px; color: #991b1b; }
    .button { display: inline-block; background: #00c38a; color: #fff !important; text-decoration: none; padding: 14px 30px; border-radius: 8px; font-weight: 700; text-transform: uppercase; font-size: 14px; }
    .footer { text-align: center; font-size: 13px; color: #94a3b8; padding: 32px 24px; border-top: 1px solid #f1f5f9; background-color: #f9fafb; }
    @media (max-width: 600px) { .content { padding: 24px 16px; } }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">BuscaFornecedor</div>
    <div class="content">
      <h1>Sua empresa parou de aparecer nas buscas!</h1>
      <div class="highlight">
        Olá, {{ saudacao_nome }}. <br><br>
        Seus créditos mensais esgotaram completamente. Neste momento, <strong>seu perfil não está mais visível</strong> para novos compradores que buscam por seus serviços na plataforma.
      </div>
      <p>
        Cada dia com o perfil offline é uma oportunidade de negócio que vai direto para a concorrência. Não deixe sua presença de mercado ser interrompida.
      </p>
      <p>
        Regularize seus créditos agora e volte a aparecer no topo dos resultados de busca imediatamente.
      </p>
      <p style="text-align:center;">
        <a href="{{ url_login }}" class="button" target="_blank">Reativar minha visibilidade</a>
      </p>
    </div>
    <div class="footer">
      © BuscaFornecedor — Todos os direitos reservados.<br/>
      <a href="{{ url_plataforma }}" style="color:#00c38a; text-decoration:none;">buscafornecedor.com.br</a>
    </div>
  </div>
</body>
</html>"""


EMAIL_APRESENTACAO = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Conheça o BuscaFornecedor</title>
  <style>
    body { margin: 0; padding: 0; background-color: #f9fafb; font-family: "Inter", Arial, sans-serif; color: #0f172a; }
    .container { max-width: 500px; margin: 40px auto; background: #ffffff; border-radius: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); overflow: hidden; }
    .header { background: linear-gradient(90deg, #0f172a, #00c38a); color: #fff; text-align: center; padding: 24px; font-size: 22px; font-weight: 600; }
    .content { padding: 32px 24px; line-height: 1.6; }
    .content h1 { font-size: 22px; color: #0f172a; margin-bottom: 20px; text-align: left; letter-spacing: -0.5px; font-weight: 700; }
    .content p { font-size: 15px; color: #475569; margin-bottom: 16px; }
    .highlight { background: #f0fdf4; padding: 20px; border-radius: 10px; border-left: 4px solid #00c38a; margin-bottom: 24px; font-size: 15px; color: #1e293b; }
    .button { display: inline-block; background: #00c38a; color: #fff !important; text-decoration: none; padding: 14px 30px; border-radius: 8px; font-weight: 700; text-transform: uppercase; font-size: 14px; }
    .footer { text-align: center; font-size: 13px; color: #94a3b8; padding: 32px 24px; border-top: 1px solid #f1f5f9; background-color: #f9fafb; }
    @media (max-width: 600px) { .content { padding: 24px 16px; } }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">BuscaFornecedor</div>
    <div class="content">
      <h1>Já ouviu falar do BuscaFornecedor?</h1>
      <div class="highlight">
        Olá, {{ saudacao_nome }}!<br><br>
        Nós somos o <strong>BuscaFornecedor</strong>, uma plataforma prática onde compradores de várias empresas buscam ativamente novos parceiros para cotar produtos e serviços.
      </div>
      <p>
        Estar cadastrado aqui significa colocar o seu negócio direto no radar de quem decide as compras, aparecendo no momento exato em que eles precisam exatamente do que você vende.
      </p>
      <p>
        Como resultado, você passa a receber mais pedidos de orçamento na sua mesa, cria conexões reais com o mercado B2B e aumenta o seu faturamento sem complicação.
      </p>
      <p style="text-align:center; margin-top: 28px;">
        <a href="{{ link_plataforma }}" class="button" target="_blank">Acessar a Plataforma</a>
      </p>
    </div>
    <div class="footer">
      © BuscaFornecedor — Todos os direitos reservados.<br/>
      <a href="{{ url_plataforma }}" style="color:#00c38a; text-decoration:none;">buscafornecedor.com.br</a>
    </div>
  </div>
</body>
</html>"""


def linhas_seed() -> list[tuple[str, str, str | None, str]]:
    """Tuplas (id, tipo, email, sms) na ordem de inserção."""
    return [
        (
            IDS_POR_TIPO[CodigoTipoTemplate.APARECEU_BUSCA],
            CodigoTipoTemplate.APARECEU_BUSCA.value,
            EMAIL_APARECEU_BUSCA,
            SMS_APARECEU_BUSCA,
        ),
        (
            IDS_POR_TIPO[CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO],
            CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO.value,
            EMAIL_APARECEU_BUSCA_SEM_REGISTRO,
            SMS_APARECEU_BUSCA_SEM_REGISTRO,
        ),
        (
            IDS_POR_TIPO[CodigoTipoTemplate.CREDITOS_NO_FIM],
            CodigoTipoTemplate.CREDITOS_NO_FIM.value,
            EMAIL_CREDITOS_NO_FIM,
            SMS_CREDITOS_NO_FIM,
        ),
        (
            IDS_POR_TIPO[CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS],
            CodigoTipoTemplate.LEMBRETE_CREDITOS_ESGOTADOS.value,
            EMAIL_LEMBRETE_CREDITOS,
            SMS_LEMBRETE_CREDITOS,
        ),
        (
            IDS_POR_TIPO[CodigoTipoTemplate.CONSULTADO_SEM_EMAIL],
            CodigoTipoTemplate.CONSULTADO_SEM_EMAIL.value,
            None,
            SMS_CONSULTADO_SEM_EMAIL,
        ),
        (
            IDS_POR_TIPO[CodigoTipoTemplate.APRESENTACAO],
            CodigoTipoTemplate.APRESENTACAO.value,
            EMAIL_APRESENTACAO,
            SMS_APRESENTACAO,
        ),
        (
            IDS_POR_TIPO[CodigoTipoTemplate.BUSCA_COMPRADOR],
            CodigoTipoTemplate.BUSCA_COMPRADOR.value,
            None,
            SMS_BUSCA_COMPRADOR,
        ),
    ]
