"""
agente_price_win.py - Benchmarks e Price to Win
================================================
Sugestões oficiais de preço do Mercado Livre:
- "Price to Win" — preço competitivo recomendado pelo ML por item
- Benchmarks — análise comparativa de preço vs concorrentes
- Descontos sugeridos pelo próprio ML
- Comparativo: seu preço vs preço vencedor

Autor: Claude para QUBO
Data: 2026-04
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PRICE TO WIN — preço competitivo recomendado pelo ML
# ─────────────────────────────────────────────────────────────────────────────
def price_to_win(token_ml: str, item_id: str) -> dict:
    """
    Consulta o preço competitivo recomendado pelo ML para um item específico.
    Endpoint: /items/{item_id}/price_to_win
    """
    if not token_ml or not item_id:
        return {'ok': False, 'erro': 'Parâmetros inválidos'}

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}

    try:
        resp = requests.get(
            f'https://api.mercadolibre.com/items/{item_id}/price_to_win',
            headers=headers, timeout=15
        )
        if resp.status_code == 404:
            return {'ok': False, 'erro': 'Item sem recomendação de preço disponível'}
        if resp.status_code == 401:
            return {'ok': False, 'erro': 'Token expirado. Reconecte.'}
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro {resp.status_code}'}

        data = resp.json()
        current = float(data.get('current_price', 0) or 0)
        win_price = float(data.get('price_to_win', data.get('suggested_price', 0)) or 0)

        # Descobre competitividade
        status = data.get('status', '')
        diff_pct = 0
        if win_price and current:
            diff_pct = round(((current - win_price) / win_price) * 100, 1)

        return {
            'ok': True,
            'item_id': item_id,
            'current_price': current,
            'price_to_win': win_price,
            'diff_pct': diff_pct,
            'acima_do_preco': diff_pct > 0,
            'abaixo_do_preco': diff_pct < 0,
            'status': status,
            'raw': data,
        }
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# DESCONTOS SUGERIDOS — ML calcula desconto ótimo por item
# ─────────────────────────────────────────────────────────────────────────────
def descontos_sugeridos(token_ml: str, user_id: str, limite: int = 50) -> dict:
    """
    Lista descontos sugeridos pelo ML para o vendedor.
    Endpoint: /seller-promotions/users/{user_id}
    """
    if not token_ml or not user_id:
        return {'ok': False, 'erro': 'ML não conectado'}

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}

    try:
        resp = requests.get(
            f'https://api.mercadolibre.com/seller-promotions/users/{user_id}',
            headers=headers,
            params={'app_version': 'v2', 'limit': limite},
            timeout=15
        )
        if resp.status_code == 401:
            return {'ok': False, 'erro': 'Token expirado. Reconecte.'}
        if resp.status_code == 403:
            return {'ok': False, 'erro': 'Sem permissão para promoções.'}
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro {resp.status_code}'}

        data = resp.json()
        promos = data.get('results', []) if isinstance(data, dict) else (data or [])

        return {
            'ok': True,
            'total': len(promos),
            'promocoes': promos[:limite],
        }
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# BENCHMARK COMPLETO — análise de TODOS os seus anúncios vs concorrência
# ─────────────────────────────────────────────────────────────────────────────
def benchmark_vendedor(token_ml: str, user_id: str, limite: int = 30) -> dict:
    """
    Para cada anúncio ativo:
    - Busca price_to_win
    - Compara com preço atual
    - Classifica em: CARO (acima do win), OK (no preço), BARATO (abaixo)

    Retorna ranking de itens que precisam de ajuste de preço.
    """
    if not token_ml or not user_id:
        return {'ok': False, 'erro': 'ML não conectado'}

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}

    try:
        # ── 1. Lista anúncios ativos ─────────────────────────────────────
        resp = requests.get(
            f'https://api.mercadolibre.com/users/{user_id}/items/search',
            headers=headers,
            params={'status': 'active', 'limit': min(limite, 50)},
            timeout=15
        )
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro: {resp.status_code}'}

        item_ids = resp.json().get('results', [])
        if not item_ids:
            return {'ok': True, 'total': 0, 'analise': []}

        # ── 2. Pega detalhes dos items ─────────────────────────────────
        detalhes = {}
        for i in range(0, len(item_ids), 20):
            batch = item_ids[i:i+20]
            r2 = requests.get(
                'https://api.mercadolibre.com/items',
                headers=headers,
                params={'ids': ','.join(batch), 'attributes': 'id,title,price,sold_quantity,permalink'},
                timeout=20
            )
            if r2.status_code == 200:
                for entry in r2.json():
                    if entry.get('code') == 200:
                        b = entry.get('body', {})
                        detalhes[b.get('id')] = b

        # ── 3. Para cada item, busca price_to_win ──────────────────────
        analise = []
        for iid in item_ids[:limite]:
            d = detalhes.get(iid, {})
            ptw = price_to_win(token_ml, iid)
            current = d.get('price', 0)

            if not ptw.get('ok'):
                continue

            win = ptw.get('price_to_win', 0)
            if not win:
                continue

            diff_pct = ptw.get('diff_pct', 0)
            if diff_pct > 5:
                classe = 'caro'
                cor = '#f87171'
                icone = '🔴'
                acao = f'Reduza {abs(diff_pct):.1f}% para ganhar Buy Box'
            elif diff_pct < -5:
                classe = 'barato'
                cor = '#fbbf24'
                icone = '🟡'
                acao = f'Pode subir {abs(diff_pct):.1f}% sem perder vendas'
            else:
                classe = 'ok'
                cor = '#4ade80'
                icone = '✅'
                acao = 'Preço competitivo'

            analise.append({
                'id': iid,
                'titulo': (d.get('title', '') or iid)[:60],
                'preco_atual': current,
                'preco_sugerido': win,
                'diff_pct': diff_pct,
                'classe': classe,
                'cor': cor,
                'icone': icone,
                'acao': acao,
                'link': d.get('permalink', ''),
                'vendas': d.get('sold_quantity', 0),
            })

        # Ordena: problemas primeiro (caros, depois baratos, depois ok)
        ordem = {'caro': 0, 'barato': 1, 'ok': 2}
        analise.sort(key=lambda x: (ordem[x['classe']], -abs(x['diff_pct'])))

        contador = {'caro': 0, 'barato': 0, 'ok': 0}
        for a in analise:
            contador[a['classe']] += 1

        return {
            'ok': True,
            'total_analisados': len(analise),
            'caros': contador['caro'],
            'baratos': contador['barato'],
            'competitivos': contador['ok'],
            'analise': analise,
            'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        }

    except Exception as e:
        logger.error(f"❌ Erro em benchmark_vendedor: {e}")
        return {'ok': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# HIGHLIGHTS POR CATEGORIA — produtos em alta numa categoria
# ─────────────────────────────────────────────────────────────────────────────
def highlights_categoria(token_ml: str, category_id: str, limite: int = 20) -> dict:
    """Produtos em destaque numa categoria (mais vendidos no período)."""
    if not category_id:
        return {'ok': False, 'erro': 'category_id obrigatório'}

    headers = {'Accept': 'application/json'}
    if token_ml:
        headers['Authorization'] = f'Bearer {token_ml}'

    try:
        resp = requests.get(
            f'https://api.mercadolibre.com/highlights/MLB/category/{category_id}',
            headers=headers, timeout=15
        )
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro {resp.status_code}'}

        data = resp.json()
        content = data.get('content', [])[:limite]

        return {
            'ok': True,
            'category_id': category_id,
            'total': len(content),
            'destaques': content,
        }
    except Exception as e:
        return {'ok': False, 'erro': str(e)}
