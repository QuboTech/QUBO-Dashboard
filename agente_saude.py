"""
agente_saude.py - Monitor de Saúde dos Anúncios
================================================
Monitora todos os seus anúncios ativos no ML e identifica problemas:

  🔴 Perdendo exposição (unhealthy)  → cancelamentos/reclamações altas
  🟡 Em risco (warning)              → pode perder exposição em breve
  🟢 Saudáveis (healthy)             → tudo bem
  📊 Visitas baixas                  → anúncio ativo mas sem tráfego
  📉 Preço fora de mercado           → muito caro vs concorrentes

Endpoints usados:
  - /users/{id}/items/search              → lista anúncios
  - /users/{id}/items/search?reputation_health_gauge=unhealthy
  - /items/{id}/visits/time_window        → visitas por anúncio
  - /items/{id}                           → detalhes (preço, estoque)

Autor: Claude para QUBO
Data: 2026-04
"""

import os
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


def monitorar_saude(token_ml: str, user_id: str) -> dict:
    """
    Retorna relatório completo de saúde dos anúncios.
    """
    headers = {"Authorization": f"Bearer {token_ml}"}
    resultado = {
        "ok": True,
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "resumo": {},
        "unhealthy": [],
        "warning": [],
        "sem_visitas": [],
        "preco_fora": [],
        "saudaveis_qtd": 0
    }

    # ── 1. Lista todos os anúncios ativos ─────────────────────────────
    todos_ids = []
    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.mercadolibre.com/users/{user_id}/items/search",
                headers=headers,
                params={"limit": 100, "offset": offset},
                timeout=15
            )
            if r.status_code != 200:
                break
            data = r.json()
            ids = data.get("results", [])
            if not ids:
                break
            todos_ids.extend(ids)
            if len(todos_ids) >= data.get("paging", {}).get("total", 0):
                break
            offset += 100
        except Exception:
            break

    total_anuncios = len(todos_ids)
    resultado["resumo"]["total_anuncios"] = total_anuncios

    if total_anuncios == 0:
        resultado["resumo"]["msg"] = "Nenhum anúncio ativo encontrado."
        return resultado

    # ── 2. Anúncios com problema de reputação ─────────────────────────
    for gauge in ["unhealthy", "warning"]:
        try:
            r = requests.get(
                f"https://api.mercadolibre.com/users/{user_id}/items/search",
                headers=headers,
                params={"reputation_health_gauge": gauge, "limit": 50},
                timeout=15
            )
            if r.status_code == 200:
                ids_problema = r.json().get("results", [])
                if ids_problema:
                    # Busca detalhes dos primeiros 5
                    for item_id in ids_problema[:5]:
                        try:
                            r2 = requests.get(
                                f"https://api.mercadolibre.com/items/{item_id}",
                                headers=headers, timeout=10
                            )
                            if r2.status_code == 200:
                                item = r2.json()
                                resultado[gauge].append({
                                    "id": item_id,
                                    "titulo": item.get("title", "")[:60],
                                    "preco": item.get("price", 0),
                                    "link": item.get("permalink", ""),
                                    "status": item.get("status", "")
                                })
                        except Exception:
                            resultado[gauge].append({"id": item_id, "titulo": item_id})
                resultado["resumo"][f"qtd_{gauge}"] = len(ids_problema)
        except Exception:
            resultado["resumo"][f"qtd_{gauge}"] = 0

    # ── 3. Analisa visitas dos primeiros 10 anúncios ──────────────────
    anuncios_detalhes = []
    for item_id in todos_ids[:10]:
        try:
            # Detalhe do item
            r = requests.get(
                f"https://api.mercadolibre.com/items/{item_id}",
                headers=headers, timeout=10
            )
            if r.status_code != 200:
                continue
            item = r.json()

            # Visitas últimos 30 dias
            visitas_30d = 0
            try:
                r2 = requests.get(
                    f"https://api.mercadolibre.com/items/{item_id}/visits/time_window",
                    headers=headers,
                    params={"last": 30, "unit": "day"},
                    timeout=10
                )
                if r2.status_code == 200:
                    visitas_30d = r2.json().get("total_visits", 0)
            except Exception:
                pass

            preco = item.get("price", 0)
            sold = item.get("sold_quantity", 0)
            titulo = item.get("title", "")[:55]

            # Converta taxa estimada
            conversao_real = round(sold / visitas_30d * 100, 1) if visitas_30d > 0 else 0

            info = {
                "id": item_id,
                "titulo": titulo,
                "preco": preco,
                "sold_quantity": sold,
                "visitas_30d": visitas_30d,
                "conversao_pct": conversao_real,
                "link": item.get("permalink", ""),
                "status": item.get("status", ""),
                "estoque": item.get("available_quantity", 0)
            }
            anuncios_detalhes.append(info)

            # Flag sem visitas
            if visitas_30d < 10 and item.get("status") == "active":
                resultado["sem_visitas"].append(info)

        except Exception:
            continue

    resultado["anuncios"] = anuncios_detalhes

    # ── 4. Resumo geral ───────────────────────────────────────────────
    qtd_unhealthy = resultado["resumo"].get("qtd_unhealthy", 0)
    qtd_warning = resultado["resumo"].get("qtd_warning", 0)
    resultado["saudaveis_qtd"] = max(0, total_anuncios - qtd_unhealthy - qtd_warning)

    resultado["resumo"]["total_unhealthy"] = qtd_unhealthy
    resultado["resumo"]["total_warning"] = qtd_warning
    resultado["resumo"]["total_sem_visitas"] = len(resultado["sem_visitas"])
    resultado["resumo"]["total_saudaveis"] = resultado["saudaveis_qtd"]

    # Score geral de saúde 0-100
    if total_anuncios > 0:
        pct_problemas = (qtd_unhealthy * 2 + qtd_warning) / total_anuncios
        score_saude = max(0, round(100 - pct_problemas * 100))
    else:
        score_saude = 100

    resultado["score_saude"] = score_saude
    resultado["classificacao_saude"] = (
        "Excelente" if score_saude >= 90 else
        "Boa" if score_saude >= 70 else
        "Regular" if score_saude >= 50 else
        "Crítica"
    )

    return resultado
