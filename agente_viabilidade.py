"""
agente_viabilidade.py - Agente de Viabilidade de Produto
=========================================================
Responde a pergunta: "Vale a pena vender esse produto no ML?"

A conta da viabilidade:
  - sold_quantity = vendas acumuladas do anúncio
  - Para estimar vendas/mês: sold_quantity / meses_no_ar (se souber)
  - Taxa de conversão média ML: ~1-3%
  - Visitas estimadas = sold_quantity / conversao
  - Demanda diária = sold_quantity_top10 / 30 dias

Cruzando com margem:
  - Lucro mensal estimado = demanda_diaria × margem_reais × 30

Score de viabilidade:
  🟢 ALTA    → demanda > 10/mês E margem >= 20%
  🟡 MÉDIA   → demanda 3-10/mês OU margem 10-20%
  🔴 BAIXA   → demanda < 3/mês OU margem < 10%
  ⚫ INVIÁVEL → preço mínimo acima de todos os concorrentes

Autor: Claude para QUBO
Data: 2026-04
"""

import re
import logging
import requests

logger = logging.getLogger(__name__)

# Conversão média estimada no ML para produtos físicos
CONVERSAO_ESTIMADA = 0.02  # 2%


def _limpar_termo(descricao: str) -> str:
    t = descricao.upper()
    t = re.sub(r'\d+[.,]?\d*\s*(MM|CM|M|KG|G|ML|L|UN|PCS|PC|UND|V|W|HP|HZ)\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\b\d+\s*[Xx×]\s*\d+\b', '', t)
    t = re.sub(r'\b\d{2,}\b', '', t)
    t = re.sub(r'\b(COM|PARA|POR|SEM|DOS|DAS|DE|DA|DO|E|A|O|TIPO|REF|COD)\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'[+\-*/()[\]{}#@&%$!;:=\'"]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    palavras = [p for p in t.split() if len(p) >= 3]
    return ' '.join(palavras[:5])


def _calcular_frete(preco, peso_kg):
    if not preco or preco < 79.90 or not peso_kg:
        return 0.0
    tabela = [
        (79, 99.99, 0, 0.299, 11.97), (79, 99.99, 0.3, 0.499, 12.87),
        (79, 99.99, 0.5, 0.999, 13.47), (79, 99.99, 1, 1.999, 14.07),
        (79, 99.99, 2, 2.999, 14.97), (79, 99.99, 3, 3.999, 16.17),
        (100, 119.99, 0, 0.299, 13.97), (100, 119.99, 0.3, 0.499, 15.02),
        (100, 119.99, 0.5, 0.999, 15.72), (100, 119.99, 1, 1.999, 16.42),
        (120, 149.99, 0, 0.299, 15.96), (120, 149.99, 0.5, 0.999, 17.96),
        (120, 149.99, 1, 1.999, 18.76), (120, 149.99, 2, 2.999, 19.96),
        (150, 199.99, 0, 0.299, 17.96), (150, 199.99, 0.5, 0.999, 20.21),
        (150, 199.99, 1, 1.999, 21.11), (150, 199.99, 2, 2.999, 22.46),
        (200, 999999, 0, 0.299, 19.95), (200, 999999, 0.5, 0.999, 22.45),
        (200, 999999, 1, 1.999, 23.45), (200, 999999, 2, 2.999, 24.95),
    ]
    for pm, px, wm, wx, fr in tabela:
        if pm <= preco <= px and wm <= peso_kg <= wx:
            return fr
    return 0.0


def _margem_real(custo, preco, taxa_pct, peso_kg=0, embalagem=0, imposto_pct=0):
    if not preco or preco <= 0 or not custo:
        return None
    taxa = taxa_pct / 100
    imp = imposto_pct / 100
    taxa_fixa = 6.25 if preco < 79 else 0
    frete = _calcular_frete(preco, peso_kg)
    total_custos = custo + preco * taxa + taxa_fixa + preco * imp + embalagem + frete
    return round((preco - total_custos) / preco * 100, 1)


def analisar_viabilidade(
    termo_ou_id: str,
    token_ml: str,
    custo: float = 0,
    peso_kg: float = 0,
    embalagem: float = 0,
    imposto_pct: float = 0,
    margem_minima: float = 20.0,
    produto_id: int = None
) -> dict:
    """
    Analisa viabilidade completa de um produto no ML.

    Parâmetros:
        termo_ou_id: nome do produto para buscar OU item_id do ML (MLBxxxxx)
        token_ml: access token OAuth
        custo: preço de custo do produto
        peso_kg: peso para cálculo de frete
        embalagem: custo de embalagem
        imposto_pct: alíquota de imposto (%)
        margem_minima: margem mínima desejada (%)
        produto_id: id no banco QUBO (opcional)
    """
    # Token é opcional: busca pública funciona sem ele (fallback para anúncios sem auth)
    headers = {"Authorization": f"Bearer {token_ml}"} if token_ml else {}

    # ── 1. Busca produtos no ML ───────────────────────────────────────
    eh_item_id = (termo_ou_id or "").upper().startswith("MLB")

    if eh_item_id:
        # Busca direta pelo ID
        r = requests.get(
            f"https://api.mercadolibre.com/items/{termo_ou_id}",
            headers=headers, timeout=15
        )
        if r.status_code in (401, 403) and headers:
            # tenta sem token (endpoint público)
            r = requests.get(f"https://api.mercadolibre.com/items/{termo_ou_id}", timeout=15)
        if r.status_code != 200:
            return {"ok": False, "erro": f"Item {termo_ou_id} não encontrado"}
        item = r.json()
        resultados = [item]
        termo_busca = item.get("title", termo_ou_id)
    else:
        termo_busca = _limpar_termo(termo_ou_id)
        if not termo_busca:
            return {"ok": False, "erro": "Termo de busca inválido"}

        r = requests.get(
            "https://api.mercadolibre.com/sites/MLB/search",
            headers=headers,
            params={"q": termo_busca, "limit": 20, "sort": "relevance"},
            timeout=15
        )
        if r.status_code in (401, 403) and headers:
            # Token inválido — tenta sem autenticação (search ML é público)
            headers = {}
            r = requests.get(
                "https://api.mercadolibre.com/sites/MLB/search",
                params={"q": termo_busca, "limit": 20, "sort": "relevance"},
                timeout=15
            )
        if r.status_code != 200:
            return {"ok": False, "erro": f"Erro API ML: {r.status_code}"}

        resultados = r.json().get("results", [])

    if not resultados:
        return {"ok": False, "erro": f'Nenhum resultado para "{termo_busca}"'}

    # ── 2. Analisa demanda (sold_quantity) ────────────────────────────
    vendas_acumuladas = [item.get("sold_quantity", 0) for item in resultados]
    total_vendas_top = sum(vendas_acumuladas)
    media_vendas_por_anuncio = total_vendas_top / len(resultados) if resultados else 0

    # Estimativa de vendas mensais:
    # Pega os top 5 por sold_quantity, divide por meses estimados no ar
    top5_por_vendas = sorted(resultados, key=lambda x: x.get("sold_quantity", 0), reverse=True)[:5]

    # Estima demanda mensal do mercado inteiro (top 20 anúncios)
    # Usando heurística: sold_quantity médio / 6 meses (estimativa conservadora)
    demanda_mensal_estimada = round(media_vendas_por_anuncio / 6, 1)

    # Demanda total do mercado (soma top 20 / 6 meses)
    demanda_mercado_mensal = round(total_vendas_top / 6, 0)

    # ── 3. Preços ─────────────────────────────────────────────────────
    precos = sorted([r.get("price", 0) for r in resultados if r.get("price", 0) > 0])
    if not precos:
        return {"ok": False, "erro": "Sem preços encontrados"}

    preco_min = precos[0]
    preco_mediano = precos[len(precos) // 2]
    preco_medio = round(sum(precos) / len(precos), 2)
    preco_max = precos[-1]

    # ── 4. Taxa ML real ───────────────────────────────────────────────
    categoria = resultados[0].get("category_id", "")
    taxa_pct = 16.5

    if categoria:
        try:
            r2 = requests.get(
                "https://api.mercadolibre.com/sites/MLB/listing_prices",
                headers=headers,
                params={"price": preco_mediano, "category_id": categoria, "currency_id": "BRL"},
                timeout=10
            )
            if r2.status_code == 200:
                for listing in r2.json():
                    if listing.get("listing_type_id") in ("gold_special", "gold_pro"):
                        for comp in listing.get("sale_fee_components", []):
                            if comp.get("type") == "fee":
                                taxa_pct = round(comp.get("ratio", 0.165) * 100, 1)
                                break
                        break
        except Exception:
            pass

    # ── 5. Análise de margem nos cenários ─────────────────────────────
    margem_no_min = _margem_real(custo, preco_min, taxa_pct, peso_kg, embalagem, imposto_pct) if custo > 0 else None
    margem_no_mediano = _margem_real(custo, preco_mediano, taxa_pct, peso_kg, embalagem, imposto_pct) if custo > 0 else None
    margem_competitivo = _margem_real(custo, preco_mediano * 0.95, taxa_pct, peso_kg, embalagem, imposto_pct) if custo > 0 else None

    # ── 6. Score de Viabilidade ───────────────────────────────────────
    # Leva em conta: demanda E margem
    score, classificacao, cor = _calcular_score(
        demanda_mensal_estimada, margem_no_mediano, margem_competitivo,
        margem_minima, preco_min, preco_mediano, custo, taxa_pct, peso_kg, embalagem
    )

    # ── 7. Lucro potencial mensal ─────────────────────────────────────
    lucro_mensal = None
    if custo > 0 and margem_no_mediano is not None:
        # Estimativa conservadora: 5% da demanda mensal do mercado
        vendas_mes_estimadas = max(1, demanda_mercado_mensal * 0.05)
        margem_reais = preco_mediano * (margem_no_mediano / 100)
        lucro_mensal = round(vendas_mes_estimadas * margem_reais, 2)

    # ── 8. Insights ───────────────────────────────────────────────────
    insights = _gerar_insights(
        demanda_mensal_estimada, demanda_mercado_mensal, margem_no_mediano,
        margem_competitivo, margem_minima, preco_min, preco_mediano,
        len(resultados), top5_por_vendas, custo
    )

    return {
        "ok": True,
        "produto_id": produto_id,
        "termo_buscado": termo_busca,
        "categoria_id": categoria,
        "total_anuncios": len(resultados),

        # Demanda
        "total_vendas_top20_acumulado": total_vendas_top,
        "media_vendas_por_anuncio": round(media_vendas_por_anuncio, 0),
        "demanda_mensal_estimada": demanda_mensal_estimada,
        "demanda_mercado_mensal": demanda_mercado_mensal,

        # Preços
        "preco_min": preco_min,
        "preco_mediano": preco_mediano,
        "preco_medio": preco_medio,
        "preco_max": preco_max,
        "taxa_percentual": taxa_pct,

        # Margem
        "custo": custo,
        "margem_no_min": margem_no_min,
        "margem_no_mediano": margem_no_mediano,
        "margem_competitivo": margem_competitivo,
        "lucro_mensal_estimado": lucro_mensal,

        # Score
        "score": score,
        "classificacao": classificacao,
        "cor": cor,

        # Insights e top anúncios
        "insights": insights,
        "top_anuncios": [{
            "titulo": a.get("title", "")[:60],
            "preco": a.get("price", 0),
            "vendas_acumuladas": a.get("sold_quantity", 0),
            "vendedor": a.get("seller", {}).get("nickname", ""),
            "link": a.get("permalink", "")
        } for a in top5_por_vendas]
    }


def _calcular_score(demanda, margem_mediano, margem_competitivo, margem_minima,
                     preco_min, preco_mediano, custo, taxa_pct, peso_kg, embalagem):
    """Calcula score 0-100 e classificação."""

    # Sem custo: avalia só demanda
    if not custo or custo <= 0:
        if demanda >= 10:
            return 70, "Alta demanda (sem custo cadastrado)", "🟡"
        elif demanda >= 3:
            return 45, "Demanda média (sem custo cadastrado)", "🟡"
        else:
            return 20, "Demanda baixa (sem custo cadastrado)", "🔴"

    # Com custo: avalia demanda + margem
    pts_demanda = 0
    if demanda >= 30: pts_demanda = 40
    elif demanda >= 10: pts_demanda = 30
    elif demanda >= 3: pts_demanda = 15
    else: pts_demanda = 5

    margem_ref = margem_competitivo or margem_mediano or 0
    pts_margem = 0
    if margem_ref >= 30: pts_margem = 40
    elif margem_ref >= 20: pts_margem = 30
    elif margem_ref >= 10: pts_margem = 15
    elif margem_ref >= 0: pts_margem = 5
    else: pts_margem = 0

    # Bonus: preco mínimo viável abaixo do preço mínimo do mercado
    taxa = taxa_pct / 100
    pct = taxa + margem_minima / 100
    preco_minimo_viavel = custo / (1 - pct) if pct < 1 else 999999
    bonus = 20 if preco_minimo_viavel < preco_min else 0

    score = min(100, pts_demanda + pts_margem + bonus)

    if score >= 70:
        return score, "Alta Viabilidade", "🟢"
    elif score >= 45:
        return score, "Viabilidade Média", "🟡"
    elif score >= 20:
        return score, "Baixa Viabilidade", "🔴"
    else:
        return score, "Inviável", "⚫"


def _gerar_insights(demanda_por_anuncio, demanda_mercado, margem_mediano,
                     margem_competitivo, margem_minima, preco_min, preco_mediano,
                     total_anuncios, top5, custo):
    insights = []

    # Demanda
    if demanda_mercado >= 50:
        insights.append({"tipo": "positivo", "msg": f"Mercado aquecido: ~{int(demanda_mercado)} vendas/mês estimadas nos top 20 anúncios."})
    elif demanda_mercado >= 10:
        insights.append({"tipo": "neutro", "msg": f"Demanda moderada: ~{int(demanda_mercado)} vendas/mês estimadas."})
    else:
        insights.append({"tipo": "negativo", "msg": f"Demanda baixa: apenas ~{int(demanda_mercado)} vendas/mês estimadas. Nicho pequeno."})

    # Concorrência
    if total_anuncios >= 15:
        insights.append({"tipo": "neutro", "msg": f"{total_anuncios} anúncios ativos — mercado competitivo. Diferenciação importante."})
    else:
        insights.append({"tipo": "positivo", "msg": f"Apenas {total_anuncios} concorrentes — boa oportunidade de entrada."})

    # Margem
    if custo > 0:
        if margem_competitivo and margem_competitivo >= margem_minima:
            insights.append({"tipo": "positivo", "msg": f"Margem de {margem_competitivo}% possível entrando 5% abaixo do mediano."})
        elif margem_mediano and margem_mediano >= margem_minima:
            insights.append({"tipo": "neutro", "msg": f"Margem de {margem_mediano}% no preço mediano — sem folga para competir no preço."})
        elif margem_mediano and margem_mediano > 0:
            insights.append({"tipo": "negativo", "msg": f"Margem de apenas {margem_mediano}% no preço mediano. Abaixo do mínimo de {margem_minima}%."})
        else:
            insights.append({"tipo": "negativo", "msg": f"Custo acima do preço de mercado. Produto inviável com a margem de {margem_minima}%."})

    # Top vendedor
    if top5:
        top = top5[0]
        insights.append({"tipo": "info", "msg": f"Líder de vendas: '{top['titulo'][:40]}' com {int(top['vendas_acumuladas'])} vendas acumuladas."})

    return insights
