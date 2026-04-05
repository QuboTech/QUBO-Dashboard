"""
agente_tendencias.py - Painel de Tendências do Mercado Livre
=============================================================
Busca o que está em alta no ML agora e cruza com o catálogo QUBO.

Endpoints usados:
  - /trends/MLB                    → top produtos em alta agora
  - /sites/MLB/search?q={termo}    → detalhes de cada tendência
  - banco QUBO                     → verifica se já tem o produto

Retorna:
  - Lista de produtos em alta com preço, vendas e margem estimada
  - Flag "já tenho" se o produto está no catálogo QUBO
  - Score de oportunidade por produto

Autor: Claude para QUBO
Data: 2026-04
"""

import os
import re
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)
DB_PATH = Path("data/viabilidade.db")
DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_conn():
    if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        return conn, True
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn, False


def buscar_tendencias(token_ml: str, limite: int = 20) -> dict:
    """
    Busca tendências do ML e enriquece com dados de mercado.
    Cruza com catálogo QUBO para identificar oportunidades.
    """
    import requests
    headers = {"Authorization": f"Bearer {token_ml}"}

    # ── 1. Busca tendências ───────────────────────────────────────────
    r = requests.get(
        "https://api.mercadolibre.com/trends/MLB",
        headers=headers, timeout=15
    )
    if r.status_code == 401:
        return {"ok": False, "erro": "Token ML expirado. Reconecte em ML Auth."}
    if r.status_code != 200:
        return {"ok": False, "erro": f"Erro API ML: {r.status_code}"}

    tendencias_raw = r.json()[:limite]

    # ── 2. Busca produtos do QUBO para cruzar ─────────────────────────
    descricoes_qubo = set()
    try:
        conn, is_pg = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT descricao FROM produtos")
        rows = cur.fetchall()
        conn.close()
        for row in rows:
            desc = row[0] if is_pg else row["descricao"]
            if desc:
                descricoes_qubo.add(desc.upper())
    except Exception:
        pass

    # ── 3. Enriquece cada tendência ───────────────────────────────────
    resultado = []
    for item in tendencias_raw:
        keyword = item.get("keyword", "")
        url = item.get("url", "")

        if not keyword:
            continue

        # Busca top anúncio para pegar preço e vendas
        preco_min = None
        preco_medio = None
        vendas_top = None
        taxa_pct = 16.5
        categoria = ""

        try:
            r2 = requests.get(
                "https://api.mercadolibre.com/sites/MLB/search",
                headers=headers,
                params={"q": keyword, "limit": 5},
                timeout=10
            )
            if r2.status_code == 200:
                res = r2.json().get("results", [])
                if res:
                    precos = [x.get("price", 0) for x in res if x.get("price", 0) > 0]
                    vendas = [x.get("sold_quantity", 0) for x in res]
                    preco_min = round(min(precos), 2) if precos else None
                    preco_medio = round(sum(precos) / len(precos), 2) if precos else None
                    vendas_top = sum(vendas)
                    categoria = res[0].get("category_id", "")
        except Exception:
            pass

        # Verifica se já tem no catálogo QUBO
        keyword_upper = keyword.upper()
        ja_tenho = any(
            keyword_upper in desc or
            all(p in desc for p in keyword_upper.split()[:2] if len(p) > 3)
            for desc in descricoes_qubo
        )

        # Score de oportunidade simples
        score_oportunidade = _score_oportunidade(preco_medio, vendas_top, ja_tenho)

        resultado.append({
            "keyword": keyword,
            "url_ml": url,
            "preco_min": preco_min,
            "preco_medio": preco_medio,
            "vendas_acum_top5": vendas_top,
            "categoria": categoria,
            "ja_tenho_no_catalogo": ja_tenho,
            "score": score_oportunidade,
            "oportunidade": _classificar_oportunidade(score_oportunidade, ja_tenho)
        })

    # Ordena por score
    resultado.sort(key=lambda x: x["score"], reverse=True)

    return {
        "ok": True,
        "total": len(resultado),
        "tendencias": resultado
    }


def _score_oportunidade(preco_medio, vendas_top, ja_tenho):
    score = 0
    if preco_medio:
        if preco_medio >= 200: score += 30
        elif preco_medio >= 100: score += 20
        elif preco_medio >= 50: score += 10
    if vendas_top:
        if vendas_top >= 500: score += 40
        elif vendas_top >= 100: score += 25
        elif vendas_top >= 20: score += 10
    if ja_tenho:
        score += 20  # bonus: já tem o produto
    return score


def _classificar_oportunidade(score, ja_tenho):
    if ja_tenho and score >= 40:
        return {"label": "Você tem! Alto potencial", "cor": "#4ade80", "icone": "⭐"}
    elif ja_tenho:
        return {"label": "Você tem no catálogo", "cor": "#4ade80", "icone": "✅"}
    elif score >= 50:
        return {"label": "Alta oportunidade", "cor": "#fbbf24", "icone": "🔥"}
    elif score >= 25:
        return {"label": "Oportunidade média", "cor": "#f59e0b", "icone": "💡"}
    else:
        return {"label": "Baixo potencial", "cor": "#8b92a5", "icone": "📉"}
