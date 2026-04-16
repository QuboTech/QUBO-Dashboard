"""
agente_alerta.py - Agente de Alerta Diário
==========================================
Resumo matinal da operação no ML:
- Vendas do dia/semana
- Perguntas não respondidas
- Estoque baixo
- Mudança de preço de rivais nos seus produtos
- Reputação do vendedor

Disponível em: GET /api/alerta-diario

Autor: Claude para QUBO
Data: 2026-04
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timedelta

from db import get_conn as _db_get_conn, USAR_POSTGRES as _PG

logger = logging.getLogger(__name__)


def get_conn():
    """Retorna (conn, is_pg) usando a conexão central de db.py (suporta REST/psycopg2/SQLite)."""
    return _db_get_conn(), _PG


def gerar_alerta_diario(token_ml: str, user_id: str) -> dict:
    """
    Gera resumo completo da operação.
    Retorna dict com todos os alertas e dados do dia.
    """
    import requests

    headers = {"Authorization": f"Bearer {token_ml}"}
    alertas = []
    hoje = datetime.now()
    ontem = (hoje - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00.000-03:00")
    semana = (hoje - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00.000-03:00")

    resultado = {
        "ok": True,
        "gerado_em": hoje.strftime("%d/%m/%Y %H:%M"),
        "alertas": [],
        "vendas": {},
        "perguntas": {},
        "reputacao": {},
        "estoque": [],
        "variacao_precos": []
    }

    # ── 1. Vendas do dia ──────────────────────────────────────────────
    try:
        r = requests.get(
            f"https://api.mercadolibre.com/orders/search",
            headers=headers,
            params={
                "seller": user_id,
                "order.status": "paid",
                "order.date_created.from": ontem,
                "limit": 50
            },
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            pedidos_hoje = data.get("results", [])
            total_hoje = sum(p.get("total_amount", 0) for p in pedidos_hoje)
            qtd_hoje = len(pedidos_hoje)

            # Vendas da semana
            r2 = requests.get(
                f"https://api.mercadolibre.com/orders/search",
                headers=headers,
                params={
                    "seller": user_id,
                    "order.status": "paid",
                    "order.date_created.from": semana,
                    "limit": 200
                },
                timeout=15
            )
            pedidos_semana = r2.json().get("results", []) if r2.status_code == 200 else []
            total_semana = sum(p.get("total_amount", 0) for p in pedidos_semana)

            resultado["vendas"] = {
                "hoje_qtd": qtd_hoje,
                "hoje_valor": round(total_hoje, 2),
                "semana_qtd": len(pedidos_semana),
                "semana_valor": round(total_semana, 2)
            }

            if qtd_hoje == 0:
                alertas.append({
                    "tipo": "aviso",
                    "icone": "📭",
                    "msg": "Nenhuma venda hoje ainda."
                })
            else:
                alertas.append({
                    "tipo": "info",
                    "icone": "💰",
                    "msg": f"{qtd_hoje} venda(s) hoje — R$ {total_hoje:,.2f}"
                })
        elif r.status_code == 403:
            resultado["vendas"] = {"erro": "Sem permissão para acessar pedidos"}
    except Exception as e:
        resultado["vendas"] = {"erro": str(e)}

    # ── 2. Perguntas não respondidas ──────────────────────────────────
    try:
        r = requests.get(
            f"https://api.mercadolibre.com/my/received_questions/search",
            headers=headers,
            params={"status": "UNANSWERED", "limit": 50},
            timeout=15
        )
        if r.status_code == 200:
            perguntas = r.json().get("questions", [])
            qtd = len(perguntas)
            resultado["perguntas"] = {
                "nao_respondidas": qtd,
                "lista": [{
                    "item_id": p.get("item_id", ""),
                    "texto": p.get("text", "")[:100],
                    "data": p.get("date_created", "")[:10]
                } for p in perguntas[:5]]
            }
            if qtd > 0:
                alertas.append({
                    "tipo": "urgente" if qtd > 3 else "aviso",
                    "icone": "❓",
                    "msg": f"{qtd} pergunta(s) sem resposta! Responda rápido para não perder vendas."
                })
    except Exception as e:
        resultado["perguntas"] = {"erro": str(e)}

    # ── 3. Reputação do vendedor ──────────────────────────────────────
    try:
        r = requests.get(
            f"https://api.mercadolibre.com/users/{user_id}",
            headers=headers,
            timeout=15
        )
        if r.status_code == 200:
            user_data = r.json()
            rep = user_data.get("seller_reputation", {})
            nivel = rep.get("level_id", "")
            status = rep.get("power_seller_status", "")
            metricas = rep.get("metrics", {})

            resultado["reputacao"] = {
                "nivel": nivel,
                "status": status,
                "cancelamentos": metricas.get("cancellations", {}).get("rate", 0),
                "reclamacoes": metricas.get("claims", {}).get("rate", 0),
                "atrasos": metricas.get("delayed_handling_time", {}).get("rate", 0)
            }

            # Alerta se reputação caindo
            cancelamentos = metricas.get("cancellations", {}).get("rate", 0)
            reclamacoes = metricas.get("claims", {}).get("rate", 0)

            if cancelamentos > 0.02:
                alertas.append({
                    "tipo": "urgente",
                    "icone": "🚨",
                    "msg": f"Taxa de cancelamento alta: {cancelamentos*100:.1f}%! Pode afetar sua reputação."
                })
            if reclamacoes > 0.01:
                alertas.append({
                    "tipo": "urgente",
                    "icone": "⚠️",
                    "msg": f"Taxa de reclamações alta: {reclamacoes*100:.1f}%! Verifique seus pedidos."
                })
            if not alertas or all(a["tipo"] == "info" for a in alertas):
                nivel_fmt = nivel.replace("_", " ").title() if nivel else "N/A"
                alertas.append({
                    "tipo": "ok",
                    "icone": "⭐",
                    "msg": f"Reputação: {nivel_fmt} — tudo bem!"
                })
    except Exception as e:
        resultado["reputacao"] = {"erro": str(e)}

    # ── 4. Estoque baixo (produtos com preco_ml > 0 sem estoque) ─────
    try:
        conn, is_pg = get_conn()
        cur = conn.cursor()
        ph = "%s" if is_pg else "?"
        cur.execute(
            f"SELECT id, descricao, fornecedor FROM produtos WHERE preco_ml > 0 AND escolhido = 1 ORDER BY id LIMIT 20"
        )
        rows = cur.fetchall()
        conn.close()

        # Para cada produto escolhido, verifica estoque no ML se tiver link
        estoque_baixo = []
        for row in rows:
            if is_pg:
                pid, desc, forn = row[0], row[1], row[2]
            else:
                pid, desc, forn = row["id"], row["descricao"], row["fornecedor"]
            estoque_baixo.append({"id": pid, "descricao": desc[:50], "fornecedor": forn})

        resultado["estoque"] = estoque_baixo[:10]

    except Exception as e:
        resultado["estoque"] = []

    # ── 5. Variação de preço de concorrentes (top produtos escolhidos) ─
    try:
        conn, is_pg = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, descricao, preco_ml FROM produtos WHERE escolhido = 1 AND preco_ml > 0 ORDER BY preco_ml DESC LIMIT 5"
        )
        rows = cur.fetchall()
        conn.close()

        variacoes = []
        for row in rows:
            if is_pg:
                pid, desc, preco_ref = row[0], row[1], row[2]
            else:
                pid, desc, preco_ref = row["id"], row["descricao"], row["preco_ml"]

            if not preco_ref:
                continue

            try:
                from agente_pesquisa import limpar_termo_busca
                termo = limpar_termo_busca(desc)
                r = requests.get(
                    "https://api.mercadolibre.com/sites/MLB/search",
                    headers=headers,
                    params={"q": termo, "limit": 5},
                    timeout=10
                )
                if r.status_code == 200:
                    res = r.json().get("results", [])
                    if res:
                        preco_atual_ml = min(r2.get("price", 9999) for r2 in res)
                        variacao = round((preco_atual_ml - preco_ref) / preco_ref * 100, 1)
                        variacoes.append({
                            "produto": desc[:40],
                            "seu_preco": preco_ref,
                            "menor_concorrente": round(preco_atual_ml, 2),
                            "variacao_pct": variacao,
                            "status": "✅ Competitivo" if preco_ref <= preco_atual_ml * 1.05
                                      else "⚠️ Concorrente mais barato"
                        })
            except Exception:
                continue

        resultado["variacao_precos"] = variacoes

        # Alertas de variação
        for v in variacoes:
            if v["variacao_pct"] < -10:
                alertas.append({
                    "tipo": "aviso",
                    "icone": "📉",
                    "msg": f'"{v["produto"][:30]}": concorrente {abs(v["variacao_pct"])}% mais barato!'
                })

    except Exception as e:
        resultado["variacao_precos"] = []

    resultado["alertas"] = alertas
    return resultado
