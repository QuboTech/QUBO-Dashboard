"""
taxas_ml.py - Tabela de Taxas do Mercado Livre Brasil (2025-2026)
=================================================================
Fonte: https://developers.mercadolivre.com.br/pt_br/comissao-por-vender
       Koncili, Magis5, Ferax, Ecommerce na Prática (2025-2026)

Hierarquia de uso:
  1. API listing_prices (taxa real por categoria/preço) — quando tem token
  2. Tabela por category_id (quando category_id conhecido)
  3. Tabela por nome de categoria (busca por palavras-chave)
  4. Default conservador: 14%

Autor: Claude para QUBO
Data: 2026-04
"""

import logging
import re

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# TABELA OFICIAL DE TAXAS ML BRASIL (Clássico / Premium)
# Atualizado: Jan 2026
# ─────────────────────────────────────────────────────────────────────────────
TAXAS_POR_CATEGORIA = {
    # id_ml → (classico_pct, premium_pct, nome_display)
    "MLB1648":  (11.0, 16.0, "Informática"),
    "MLB1051":  (11.0, 16.0, "Celulares e Smartphones"),
    "MLB1246":  (11.0, 16.0, "Câmeras e Acessórios"),
    "MLB1574":  (11.0, 16.0, "Eletrodomésticos"),
    "MLB1000":  (13.0, 18.0, "Eletrônicos, Áudio e Vídeo"),
    "MLB1144":  (13.0, 18.0, "Games"),
    "MLB1953":  (11.5, 16.5, "Acessórios para Veículos"),
    "MLB1743":  (11.5, 16.5, "Agro"),
    "MLB5726":  (11.5, 16.5, "Antiguidades e Coleções"),
    "MLB1168":  (11.5, 16.5, "Arte, Papelaria e Armarinho"),
    "MLB1459":  (11.5, 16.5, "Brinquedos e Hobbies"),
    "MLB1574":  (11.5, 16.5, "Casa, Móveis e Decoração"),
    "MLB1459":  (11.5, 16.5, "Construção"),
    "MLB1276":  (11.5, 16.5, "Festas e Lembranças"),
    "MLB3937":  (11.5, 16.5, "Indústria e Comércio"),
    "MLB1207":  (11.5, 16.5, "Instrumentos Musicais"),
    "MLB1182":  (11.5, 16.5, "Joias e Relógios"),
    "MLB3025":  (12.0, 17.0, "Livros, Revistas e HQ"),
    "MLB1213":  (12.0, 17.0, "Música, Filmes e Séries"),
    "MLB1540":  (12.0, 17.0, "Saúde"),
    "MLB5547":  (14.0, 19.0, "Alimentos e Bebidas"),
    "MLB1392":  (14.0, 19.0, "Bebês"),
    "MLB1246":  (14.0, 19.0, "Beleza e Cuidado Pessoal"),
    "MLB1430":  (14.0, 19.0, "Esportes e Fitness"),
    "MLB1430":  (14.0, 19.0, "Calçados, Roupas e Bolsas"),
    "MLB4655":  (12.5, 17.5, "Pet Shop"),
}

# Mapeamento por palavras-chave no NOME da categoria (para fallback)
# Ordem importa: mais específico primeiro
TAXAS_POR_NOME = [
    # 11% Clássico
    (["celular", "smartphone", "iphone", "android"],            11.0, 16.0),
    (["notebook", "computador", "desktop", "pc gamer", "monitor", "teclado gamer", "mouse gamer", "memória", "processador", "placa de vídeo", "ssd", "hd externo"],  11.0, 16.0),
    (["câmera", "camera", "lente", "tripé", "flash"],           11.0, 16.0),
    (["geladeira", "fogão", "microondas", "máquina de lavar", "lavadora", "secadora", "lava louça", "ar condicionado", "ventilador", "purificador"],  11.0, 16.0),
    # 13% Clássico
    (["tv ", "televisão", "televisor", "som ", "caixa de som", "fone de ouvido", "headphone", "headset", "amplificador", "receiver", "projetor", "home theater"],  13.0, 18.0),
    (["game", "videogame", "playstation", "xbox", "nintendo", "controle de game", "jogo para"],  13.0, 18.0),
    # 11.5% Clássico
    (["pneu", "roda", "óleo motor", "filtro de ar", "bateria automotiva", "amortecedor", "acessório para carro", "acessório veicular"],  11.5, 16.5),
    (["brinquedo", "boneco", "boneca", "lego", "quebra-cabeça", "miniaturas"],  11.5, 16.5),
    (["móvel", "cadeira", "mesa ", "sofa", "sofá", "armário", "estante", "prateleira", "tapete", "cortina", "luminária", "abajur"],  11.5, 16.5),
    (["ferramenta", "parafuso", "tinta ", "cimento", "telha", "material de construção"],  11.5, 16.5),
    (["instrumento musical", "violão", "guitarra", "teclado musical", "bateria musical", "flauta"],  11.5, 16.5),
    (["joia", "joias", "relogio", "relógio", "anel ", "colar ", "pulseira", "brinco"],  12.5, 17.5),
    # 12% Clássico
    (["livro", "revista", "hq ", "comic", "mangá"],             12.0, 17.0),
    (["filme", "série", "dvd", "blu-ray", "cd de música"],      12.0, 17.0),
    (["saúde", "medicamento", "vitamina", "suplemento vitamínico", "termômetro", "oxímetro"],  12.0, 17.0),
    (["pet", "ração", "coleira", "brinquedo pet", "aquário"],   12.5, 17.5),
    # 14% Clássico
    (["roupa", "camiseta", "camisa ", "calça", "vestido", "blusa", "casaco", "jaqueta", "moda", "tênis", "sapato", "sandalia", "bota ", "calçado"],  14.0, 19.0),
    (["bolsa", "mochila", "carteira", "necessaire"],            14.0, 19.0),
    (["bebê", "bebe", "fraldas", "carrinho de bebê", "berço"],  14.0, 19.0),
    (["shampoo", "condicionador", "creme ", "perfume", "desodorante", "maquiagem", "batom", "base maquiagem", "beleza"],  14.0, 19.0),
    (["esporte", "fitness", "academia", "musculação", "bicicleta", "patins", "skate", "natação", "futebol", "basquete"],  14.0, 19.0),
    (["alimento", "bebida", "café ", "chá ", "suplemento alimentar", "proteína", "whey"],  14.0, 19.0),
]

# Default quando não consegue identificar categoria
TAXA_DEFAULT_CLASSICO = 13.0   # conservador: mediana das taxas
TAXA_DEFAULT_PREMIUM  = 18.0


# ─────────────────────────────────────────────────────────────────────────────
# TAXA FIXA PARA ITENS BARATOS (< R$79)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_taxa_fixa(preco: float, categoria: str = "") -> float:
    """
    Retorna a taxa fixa (R$) para itens abaixo de R$79.
    Livros têm tabela especial.
    """
    eh_livro = any(p in categoria.lower() for p in ["livro", "revista", "hq", "comic"])

    if preco >= 79:
        return 0.0

    if eh_livro:
        if preco < 6:    return preco * 0.50
        if preco < 29:   return 3.00
        if preco < 50:   return 3.50
        return 4.00
    else:
        if preco < 12.5:  return preco * 0.50
        if preco < 29:    return 6.25
        if preco < 50:    return 6.50
        return 6.75


# ─────────────────────────────────────────────────────────────────────────────
# BUSCA DE TAXA POR PALAVRAS-CHAVE
# ─────────────────────────────────────────────────────────────────────────────
def taxa_por_nome(nome_produto: str) -> tuple[float, float, str]:
    """
    Infere taxa ML (clássico, premium, fonte) pelo nome/descrição do produto.
    Retorna (taxa_classico, taxa_premium, metodo_usado).
    """
    txt = nome_produto.lower()
    for palavras, classico, premium in TAXAS_POR_NOME:
        for p in palavras:
            if p in txt:
                return classico, premium, f"nome:{p}"
    return TAXA_DEFAULT_CLASSICO, TAXA_DEFAULT_PREMIUM, "default"


def taxa_por_category_id(category_id: str) -> tuple[float, float] | None:
    """Retorna (classico, premium) se category_id for conhecido."""
    if category_id and category_id in TAXAS_POR_CATEGORIA:
        c, p, _ = TAXAS_POR_CATEGORIA[category_id]
        return c, p
    return None


# ─────────────────────────────────────────────────────────────────────────────
# BUSCA VIA API (com token)
# ─────────────────────────────────────────────────────────────────────────────
def taxa_via_api(preco: float, category_id: str, token_ml: str,
                 tipo: str = "gold_special") -> dict | None:
    """
    Consulta /sites/MLB/listing_prices para obter taxa real da categoria.
    Retorna dict com taxa_percentual, taxa_fixa, taxa_total ou None se falhar.
    """
    if not token_ml or not category_id:
        return None
    try:
        import requests
        resp = requests.get(
            "https://api.mercadolibre.com/sites/MLB/listing_prices",
            headers={"Authorization": f"Bearer {token_ml}"},
            params={
                "price": preco,
                "category_id": category_id,
                "currency_id": "BRL",
                "listing_type_id": tipo,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        items = data if isinstance(data, list) else [data]

        for item in items:
            lid = item.get("listing_type_id", "")
            if lid == tipo or not items:
                det = item.get("sale_fee_details", {})
                pct = det.get("meli_percentage_fee") or det.get("percentage_fee", 0)
                fixa = det.get("fixed_fee", 0) / 100 if det.get("fixed_fee", 0) > 10 else det.get("fixed_fee", 0)
                total_api = item.get("sale_fee_amount", 0)
                # Normaliza: às vezes vem em centavos
                if total_api > preco * 0.5 and preco > 0:
                    total_api /= 100
                return {
                    "taxa_percentual": round(float(pct), 2),
                    "taxa_fixa": round(float(fixa), 2),
                    "taxa_total_reais": round(float(total_api), 2),
                    "fonte": "api",
                    "listing_type": lid,
                }
    except Exception as e:
        logger.warning(f"⚠️ taxas_ml: erro na API listing_prices: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÃO PRINCIPAL: get_taxa_ml()
# ─────────────────────────────────────────────────────────────────────────────
def get_taxa_ml(
    preco: float,
    descricao: str = "",
    category_id: str = "",
    token_ml: str = "",
    tipo_anuncio: str = "classico",  # "classico" | "premium"
) -> dict:
    """
    Retorna a taxa ML mais precisa possível para um produto.

    Hierarquia:
      1. API listing_prices (real, por categoria/preço)
      2. Tabela por category_id
      3. Tabela por palavras-chave na descrição
      4. Default

    Retorna:
      {
        taxa_percentual: float,      # ex: 11.0
        taxa_fixa: float,            # ex: 6.25 (para itens < R$79)
        custo_ml_reais: float,       # custo total ML em R$
        margem_taxa_pct: float,      # % real do preço (taxa_pct + taxa_fixa/preco)
        fonte: str,                  # "api" | "category_id" | "nome:palavra" | "default"
        tipo: str,                   # "classico" | "premium"
      }
    """
    listing_type = "gold_pro" if tipo_anuncio == "premium" else "gold_special"

    # ── 1. Via API ────────────────────────────────────────────────────
    if token_ml and category_id and preco > 0:
        api_result = taxa_via_api(preco, category_id, token_ml, listing_type)
        if api_result and api_result["taxa_percentual"] > 0:
            taxa_pct = api_result["taxa_percentual"]
            taxa_fixa = api_result["taxa_fixa"] or calcular_taxa_fixa(preco, descricao)
            custo = preco * (taxa_pct / 100) + taxa_fixa
            return {
                "taxa_percentual": taxa_pct,
                "taxa_fixa": taxa_fixa,
                "custo_ml_reais": round(custo, 2),
                "margem_taxa_pct": round((custo / preco) * 100, 2) if preco else 0,
                "fonte": "api",
                "tipo": tipo_anuncio,
                "category_id": category_id,
            }

    # ── 2. Por category_id (tabela local) ────────────────────────────
    taxa_pct = None
    fonte = "default"

    if category_id:
        res = taxa_por_category_id(category_id)
        if res:
            taxa_pct = res[0] if tipo_anuncio == "classico" else res[1]
            fonte = f"category_id:{category_id}"

    # ── 3. Por palavras-chave na descrição ───────────────────────────
    if taxa_pct is None and descricao:
        c, p, f = taxa_por_nome(descricao)
        taxa_pct = c if tipo_anuncio == "classico" else p
        fonte = f

    # ── 4. Default ───────────────────────────────────────────────────
    if taxa_pct is None:
        taxa_pct = TAXA_DEFAULT_CLASSICO if tipo_anuncio == "classico" else TAXA_DEFAULT_PREMIUM
        fonte = "default"

    taxa_fixa = calcular_taxa_fixa(preco, descricao)
    custo = (preco * taxa_pct / 100) + taxa_fixa

    return {
        "taxa_percentual": round(taxa_pct, 2),
        "taxa_fixa": round(taxa_fixa, 2),
        "custo_ml_reais": round(custo, 2),
        "margem_taxa_pct": round((custo / preco) * 100, 2) if preco > 0 else 0,
        "fonte": fonte,
        "tipo": tipo_anuncio,
        "category_id": category_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROTA DE SUGESTÃO DE TAXA PARA O DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
def sugerir_taxa_produto(descricao: str, preco: float = 0,
                         category_id: str = "", token_ml: str = "") -> dict:
    """
    Sugere taxa ML para um produto baseado na descrição.
    Usado pelo endpoint /api/sugerir-taxa.
    """
    c, p, fonte = taxa_por_nome(descricao)

    # Tenta API se tiver token e category_id
    api_classico = None
    if token_ml and category_id and preco > 0:
        api_classico = taxa_via_api(preco, category_id, token_ml, "gold_special")

    resultado = {
        "ok": True,
        "descricao": descricao[:80],
        "category_id": category_id,
        "classico": api_classico["taxa_percentual"] if api_classico else c,
        "premium": api_classico["taxa_percentual"] + 5 if api_classico else p,
        "taxa_fixa_estimada": calcular_taxa_fixa(preco, descricao) if preco > 0 else 0,
        "fonte": "api" if api_classico else fonte,
        "nota": "Taxa via API ML (exata)" if api_classico else f"Taxa estimada por categoria ({fonte})",
    }
    return resultado
