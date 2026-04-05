"""
agente_precificacao.py - Agente de Precificação Inteligente
===========================================================
Analisa concorrentes no ML e sugere preço ideal com:
- Margem mínima configurável
- Taxa ML real da categoria
- Frete calculado pelo peso
- Comparativo com top concorrentes
- Sugestão de preço competitivo

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


TABELA_FRETE = [
    {"pm":79,"px":99.99,"wm":0,"wx":0.299,"fr":11.97},
    {"pm":79,"px":99.99,"wm":0.3,"wx":0.499,"fr":12.87},
    {"pm":79,"px":99.99,"wm":0.5,"wx":0.999,"fr":13.47},
    {"pm":79,"px":99.99,"wm":1,"wx":1.999,"fr":14.07},
    {"pm":79,"px":99.99,"wm":2,"wx":2.999,"fr":14.97},
    {"pm":79,"px":99.99,"wm":3,"wx":3.999,"fr":16.17},
    {"pm":79,"px":99.99,"wm":4,"wx":4.999,"fr":17.07},
    {"pm":79,"px":99.99,"wm":5,"wx":8.999,"fr":26.67},
    {"pm":100,"px":119.99,"wm":0,"wx":0.299,"fr":13.97},
    {"pm":100,"px":119.99,"wm":0.3,"wx":0.499,"fr":15.02},
    {"pm":100,"px":119.99,"wm":0.5,"wx":0.999,"fr":15.72},
    {"pm":100,"px":119.99,"wm":1,"wx":1.999,"fr":16.42},
    {"pm":100,"px":119.99,"wm":2,"wx":2.999,"fr":17.47},
    {"pm":100,"px":119.99,"wm":3,"wx":3.999,"fr":18.87},
    {"pm":100,"px":119.99,"wm":4,"wx":4.999,"fr":19.92},
    {"pm":100,"px":119.99,"wm":5,"wx":8.999,"fr":31.12},
    {"pm":120,"px":149.99,"wm":0,"wx":0.299,"fr":15.96},
    {"pm":120,"px":149.99,"wm":0.3,"wx":0.499,"fr":17.16},
    {"pm":120,"px":149.99,"wm":0.5,"wx":0.999,"fr":17.96},
    {"pm":120,"px":149.99,"wm":1,"wx":1.999,"fr":18.76},
    {"pm":120,"px":149.99,"wm":2,"wx":2.999,"fr":19.96},
    {"pm":120,"px":149.99,"wm":3,"wx":3.999,"fr":21.56},
    {"pm":120,"px":149.99,"wm":4,"wx":4.999,"fr":22.76},
    {"pm":120,"px":149.99,"wm":5,"wx":8.999,"fr":35.56},
    {"pm":150,"px":199.99,"wm":0,"wx":0.299,"fr":17.96},
    {"pm":150,"px":199.99,"wm":0.3,"wx":0.499,"fr":19.31},
    {"pm":150,"px":199.99,"wm":0.5,"wx":0.999,"fr":20.21},
    {"pm":150,"px":199.99,"wm":1,"wx":1.999,"fr":21.11},
    {"pm":150,"px":199.99,"wm":2,"wx":2.999,"fr":22.46},
    {"pm":150,"px":199.99,"wm":3,"wx":3.999,"fr":24.26},
    {"pm":150,"px":199.99,"wm":4,"wx":4.999,"fr":25.61},
    {"pm":150,"px":199.99,"wm":5,"wx":8.999,"fr":40.01},
    {"pm":200,"px":999999,"wm":0,"wx":0.299,"fr":19.95},
    {"pm":200,"px":999999,"wm":0.3,"wx":0.499,"fr":21.45},
    {"pm":200,"px":999999,"wm":0.5,"wx":0.999,"fr":22.45},
    {"pm":200,"px":999999,"wm":1,"wx":1.999,"fr":23.45},
    {"pm":200,"px":999999,"wm":2,"wx":2.999,"fr":24.95},
    {"pm":200,"px":999999,"wm":3,"wx":3.999,"fr":26.95},
    {"pm":200,"px":999999,"wm":4,"wx":4.999,"fr":28.45},
    {"pm":200,"px":999999,"wm":5,"wx":8.999,"fr":44.45},
]


def calcular_frete(preco, peso_kg):
    if not preco or not peso_kg or preco < 79.90:
        return 0.0
    for e in TABELA_FRETE:
        if e["pm"] <= preco <= e["px"] and e["wm"] <= peso_kg <= e["wx"]:
            return e["fr"]
    return 0.0


def calcular_preco_minimo(custo, taxa_pct, peso_kg=0, embalagem=0,
                           imposto_pct=0, ads=0, margem_minima=20):
    """
    Calcula o preço mínimo para atingir a margem desejada.
    Fórmula iterativa para convergir com o frete (que depende do preço).
    """
    taxa = taxa_pct / 100
    imp = imposto_pct / 100
    margem = margem_minima / 100

    # Estimativa inicial sem frete
    pct_total = taxa + imp + margem
    if pct_total >= 1:
        return 0

    fixos = embalagem + ads
    preco_est = (custo + fixos) / (1 - pct_total)

    # 2 iterações para convergir com o frete
    for _ in range(2):
        taxa_fixa = 6.25 if preco_est < 79 else 0
        frete = calcular_frete(preco_est, peso_kg)
        preco_est = (custo + fixos + frete + taxa_fixa) / (1 - pct_total)

    return round(preco_est, 2)


def calcular_margem(custo, preco, taxa_pct, peso_kg=0, embalagem=0,
                     imposto_pct=0, ads=0):
    """Calcula margem real para um preço dado."""
    if not preco or preco <= 0:
        return 0
    taxa = taxa_pct / 100
    imp = imposto_pct / 100
    taxa_fixa = 6.25 if preco < 79 else 0
    frete = calcular_frete(preco, peso_kg)
    custos = custo + preco * taxa + taxa_fixa + preco * imp + embalagem + frete + ads
    margem = (preco - custos) / preco * 100
    return round(margem, 1)


def precificar_produto(produto_id: int, token_ml: str,
                        margem_minima: float = 20.0,
                        imposto_pct: float = 0.0) -> dict:
    """
    Agente de Precificação Inteligente.

    Dado um produto selecionado:
    1. Busca concorrentes no ML
    2. Calcula preço mínimo para margem desejada
    3. Sugere preço competitivo (abaixo do mediano, acima do mínimo)
    4. Classifica cenários: agressivo / competitivo / premium
    """
    import requests

    try:
        conn, is_pg = get_conn()
        if is_pg:
            cur = conn.cursor()
            cur.execute("SELECT * FROM produtos WHERE id = %s", (produto_id,))
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            produto = dict(zip(cols, row)) if row else {}
        else:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,))
            row = cur.fetchone()
            produto = dict(row) if row else {}
        conn.close()

        if not produto:
            return {"ok": False, "erro": "Produto não encontrado"}

        custo = float(produto.get("custo") or 0)
        peso_kg = float(produto.get("peso_kg") or 0)
        embalagem = float(produto.get("custo_embalagem") or 0)
        ads = float(produto.get("custo_ads") or 0)
        descricao = produto.get("descricao", "")

        # Limpa termo para busca
        termo = _limpar_termo(descricao)
        if not termo:
            return {"ok": False, "erro": "Não foi possível gerar termo de busca"}

        headers = {"Authorization": f"Bearer {token_ml}"}

        # ── Busca ML ─────────────────────────────────────────────────
        resp = requests.get(
            "https://api.mercadolibre.com/sites/MLB/search",
            headers=headers,
            params={"q": termo, "limit": 20},
            timeout=15
        )

        if resp.status_code == 401:
            return {"ok": False, "erro": "Token ML expirado. Reconecte em ML Auth."}
        if resp.status_code == 403:
            return {"ok": False, "erro": "Acesso negado à API ML."}
        if resp.status_code != 200:
            return {"ok": False, "erro": f"Erro API ML: {resp.status_code}"}

        resultados = resp.json().get("results", [])
        if not resultados:
            return {"ok": False, "erro": f'Nenhum resultado para "{termo}"'}

        precos = sorted([r["price"] for r in resultados if r.get("price", 0) > 0])
        if not precos:
            return {"ok": False, "erro": "Sem preços encontrados"}

        preco_min_ml = precos[0]
        preco_mediano = precos[len(precos) // 2]
        preco_medio = round(sum(precos) / len(precos), 2)
        preco_max_ml = precos[-1]

        # ── Taxa ML real ──────────────────────────────────────────────
        categoria = resultados[0].get("category_id", "")
        taxa_pct = 16.5  # default

        if categoria:
            try:
                r2 = requests.get(
                    "https://api.mercadolibre.com/sites/MLB/listing_prices",
                    headers=headers,
                    params={"price": preco_mediano, "category_id": categoria,
                            "currency_id": "BRL"},
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

        # ── Cálculo de cenários ───────────────────────────────────────
        preco_minimo_viavel = calcular_preco_minimo(
            custo, taxa_pct, peso_kg, embalagem, imposto_pct, ads, margem_minima
        ) if custo > 0 else None

        # Cenário Agressivo: 5% abaixo do menor concorrente (se viável)
        preco_agressivo = round(preco_min_ml * 0.95, 2)
        margem_agressivo = calcular_margem(custo, preco_agressivo, taxa_pct,
                                            peso_kg, embalagem, imposto_pct, ads) if custo > 0 else None

        # Cenário Competitivo: 5% abaixo do mediano
        preco_competitivo = round(preco_mediano * 0.95, 2)
        margem_competitivo = calcular_margem(custo, preco_competitivo, taxa_pct,
                                              peso_kg, embalagem, imposto_pct, ads) if custo > 0 else None

        # Cenário Premium: 5% acima do mediano
        preco_premium = round(preco_mediano * 1.05, 2)
        margem_premium = calcular_margem(custo, preco_premium, taxa_pct,
                                          peso_kg, embalagem, imposto_pct, ads) if custo > 0 else None

        # Recomendação inteligente
        recomendacao = _recomendar(
            preco_minimo_viavel, preco_agressivo, preco_competitivo,
            preco_premium, margem_agressivo, margem_competitivo,
            margem_premium, margem_minima
        )

        # Top 5 concorrentes
        top5 = [{
            "titulo": r.get("title", "")[:60],
            "preco": r.get("price", 0),
            "vendas": r.get("sold_quantity", 0),
            "vendedor": r.get("seller", {}).get("nickname", ""),
            "link": r.get("permalink", "")
        } for r in sorted(resultados, key=lambda x: x.get("sold_quantity", 0), reverse=True)[:5]]

        return {
            "ok": True,
            "produto_id": produto_id,
            "produto_nome": descricao,
            "custo": custo,
            "termo_buscado": termo,
            "total_concorrentes": len(resultados),

            # Mercado
            "preco_min_ml": round(preco_min_ml, 2),
            "preco_mediano": round(preco_mediano, 2),
            "preco_medio": preco_medio,
            "preco_max_ml": round(preco_max_ml, 2),
            "taxa_percentual": taxa_pct,
            "categoria_id": categoria,

            # Viabilidade
            "preco_minimo_viavel": preco_minimo_viavel,
            "margem_minima_alvo": margem_minima,

            # Cenários
            "cenarios": {
                "agressivo": {
                    "preco": preco_agressivo,
                    "margem": margem_agressivo,
                    "descricao": "5% abaixo do menor concorrente",
                    "viavel": (margem_agressivo or 0) >= margem_minima
                },
                "competitivo": {
                    "preco": preco_competitivo,
                    "margem": margem_competitivo,
                    "descricao": "5% abaixo do preço mediano",
                    "viavel": (margem_competitivo or 0) >= margem_minima
                },
                "premium": {
                    "preco": preco_premium,
                    "margem": margem_premium,
                    "descricao": "5% acima do preço mediano",
                    "viavel": (margem_premium or 0) >= margem_minima
                }
            },

            # Recomendação
            "recomendacao": recomendacao,

            # Top concorrentes
            "top_concorrentes": top5
        }

    except Exception as e:
        logger.error(f"❌ Erro na precificação: {e}")
        return {"ok": False, "erro": str(e)}


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


def _recomendar(preco_min_viavel, preco_agressivo, preco_competitivo,
                preco_premium, margem_agressivo, margem_competitivo,
                margem_premium, margem_minima):
    """Escolhe o melhor cenário e explica o raciocínio."""

    if preco_min_viavel is None:
        return {
            "cenario": "competitivo",
            "preco": preco_competitivo,
            "motivo": "Sem custo cadastrado. Use o preço competitivo como referência."
        }

    # Se agressivo é viável, recomenda para ganhar Buy Box
    if margem_agressivo and margem_agressivo >= margem_minima:
        return {
            "cenario": "agressivo",
            "preco": preco_agressivo,
            "motivo": f"Margem de {margem_agressivo}% acima do mínimo de {margem_minima}%. "
                      f"Preço mais baixo que o concorrente mais barato — alta chance de Buy Box."
        }

    # Se competitivo é viável
    if margem_competitivo and margem_competitivo >= margem_minima:
        return {
            "cenario": "competitivo",
            "preco": preco_competitivo,
            "motivo": f"Margem de {margem_competitivo}% atingida. "
                      f"Preço 5% abaixo do mediano — bom equilíbrio entre volume e margem."
        }

    # Se só premium é viável
    if margem_premium and margem_premium >= margem_minima:
        return {
            "cenario": "premium",
            "preco": preco_premium,
            "motivo": f"Apenas o cenário premium atinge {margem_minima}% de margem. "
                      f"Considere reduzir custos ou revisar a margem mínima."
        }

    # Nenhum cenário viável
    return {
        "cenario": "inviavel",
        "preco": preco_min_viavel,
        "motivo": f"Preço mínimo viável (R$ {preco_min_viavel}) está acima de todos os concorrentes. "
                  f"Produto difícil de competir com a margem de {margem_minima}%. "
                  f"Considere reduzir a margem mínima ou negociar melhor com o fornecedor."
    }
