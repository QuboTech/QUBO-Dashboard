"""
agente_metricas.py - Métricas de Visitas e Conversão
======================================================
- Visitas totais do vendedor (últimos N dias)
- Visitas por anúncio (top + bottom performers)
- Taxa de conversão (vendas / visitas)
- Identifica anúncios com visitas mas sem venda (problema de preço/ficha)
- Identifica anúncios sem visitas (problema de SEO/categoria)

Autor: Claude para QUBO
Data: 2026-04
"""

import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def visitas_vendedor(token_ml: str, user_id: str, dias: int = 30) -> dict:
    """Visitas agregadas a todos os anúncios do vendedor no período."""
    if not token_ml or not user_id:
        return {'ok': False, 'erro': 'ML não conectado'}

    date_to = datetime.utcnow().strftime('%Y-%m-%d')
    date_from = (datetime.utcnow() - timedelta(days=dias)).strftime('%Y-%m-%d')

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}

    try:
        resp = requests.get(
            f'https://api.mercadolibre.com/users/{user_id}/items_visits',
            headers=headers,
            params={'date_from': date_from, 'date_to': date_to},
            timeout=20
        )
        if resp.status_code == 401:
            return {'ok': False, 'erro': 'Token expirado. Reconecte.'}
        if resp.status_code == 403:
            return {'ok': False, 'erro': 'Sem permissão para ler métricas.'}
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro {resp.status_code}'}

        data = resp.json()
        total = data.get('total_visits', 0)
        # Série temporal (se vier)
        serie = []
        for v in (data.get('visits_detail') or []):
            serie.append({
                'data': v.get('date', '')[:10],
                'visitas': v.get('total', 0),
            })

        return {
            'ok': True,
            'total_visitas': total,
            'periodo_dias': dias,
            'date_from': date_from,
            'date_to': date_to,
            'serie': serie,
            'media_diaria': round(total / max(dias, 1), 1),
        }
    except Exception as e:
        logger.error(f"❌ Erro em visitas_vendedor: {e}")
        return {'ok': False, 'erro': str(e)}


def visitas_por_item(token_ml: str, item_ids: list, dias: int = 30) -> dict:
    """
    Visitas de uma lista de item_ids (máx 20 por chamada).
    """
    if not token_ml or not item_ids:
        return {'ok': False, 'erro': 'Parâmetros inválidos'}

    date_to = datetime.utcnow().strftime('%Y-%m-%d')
    date_from = (datetime.utcnow() - timedelta(days=dias)).strftime('%Y-%m-%d')

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}

    resultados = {}
    try:
        for i in range(0, len(item_ids), 20):
            batch = item_ids[i:i+20]
            resp = requests.get(
                'https://api.mercadolibre.com/visits/items',
                headers=headers,
                params={'ids': ','.join(batch), 'date_from': date_from, 'date_to': date_to},
                timeout=20
            )
            if resp.status_code != 200:
                continue
            data = resp.json() or {}
            if isinstance(data, dict):
                resultados.update(data)

        return {'ok': True, 'visitas': resultados, 'periodo_dias': dias}
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


def analise_completa(token_ml: str, user_id: str, dias: int = 30,
                     limite_anuncios: int = 30) -> dict:
    """
    Análise completa de performance:
      - Total de visitas do vendedor
      - Top 10 anúncios mais visitados
      - Bottom 10 (sem visitas)
      - Anúncios com visitas mas sem venda (problema de conversão)
    """
    if not token_ml or not user_id:
        return {'ok': False, 'erro': 'ML não conectado'}

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}

    try:
        # ── 1. Visitas agregadas ──────────────────────────────────────
        agreg = visitas_vendedor(token_ml, user_id, dias)

        # ── 2. Lista IDs dos anúncios ativos ──────────────────────────
        resp = requests.get(
            f'https://api.mercadolibre.com/users/{user_id}/items/search',
            headers=headers,
            params={'status': 'active', 'limit': min(limite_anuncios, 50)},
            timeout=15
        )
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro ao listar anúncios: {resp.status_code}'}

        item_ids = resp.json().get('results', [])
        if not item_ids:
            return {'ok': True, 'total_visitas': agreg.get('total_visitas', 0),
                    'top_anuncios': [], 'sem_visitas': [], 'baixa_conversao': []}

        # ── 3. Busca detalhes (title, price, sold_quantity) ─────────────
        detalhes = {}
        for i in range(0, len(item_ids), 20):
            batch = item_ids[i:i+20]
            r2 = requests.get(
                'https://api.mercadolibre.com/items',
                headers=headers,
                params={'ids': ','.join(batch), 'attributes': 'id,title,price,sold_quantity,permalink,thumbnail'},
                timeout=20
            )
            if r2.status_code == 200:
                for entry in r2.json():
                    if entry.get('code') == 200:
                        b = entry.get('body', {})
                        detalhes[b.get('id')] = b

        # ── 4. Busca visitas em lote ───────────────────────────────────
        vis_resp = visitas_por_item(token_ml, item_ids, dias)
        visitas_map = vis_resp.get('visitas', {})

        # ── 5. Monta lista ─────────────────────────────────────────────
        anuncios = []
        for iid in item_ids:
            d = detalhes.get(iid, {})
            v = int(visitas_map.get(iid, 0))
            vendas = int(d.get('sold_quantity', 0))
            conversao = round((vendas / v) * 100, 2) if v > 0 else 0

            anuncios.append({
                'id': iid,
                'titulo': (d.get('title', '') or iid)[:70],
                'preco': d.get('price', 0),
                'visitas': v,
                'vendas_total': vendas,
                'conversao_pct': conversao,
                'link': d.get('permalink', ''),
                'thumbnail': d.get('thumbnail', ''),
            })

        # ── 6. Rankings ────────────────────────────────────────────────
        ordenado_por_vis = sorted(anuncios, key=lambda x: -x['visitas'])
        top = ordenado_por_vis[:10]
        sem_visitas = [a for a in anuncios if a['visitas'] == 0][:10]
        # Baixa conversão: >20 visitas mas <1% conversão
        baixa_conv = sorted(
            [a for a in anuncios if a['visitas'] >= 20 and a['conversao_pct'] < 1],
            key=lambda x: -x['visitas']
        )[:10]

        total_visitas_itens = sum(a['visitas'] for a in anuncios)
        total_vendas = sum(a['vendas_total'] for a in anuncios)
        conv_geral = round((total_vendas / total_visitas_itens) * 100, 2) if total_visitas_itens else 0

        return {
            'ok': True,
            'periodo_dias': dias,
            'total_visitas_vendedor': agreg.get('total_visitas', total_visitas_itens),
            'media_diaria': agreg.get('media_diaria', round(total_visitas_itens / dias, 1)),
            'total_anuncios_analisados': len(anuncios),
            'total_vendas_periodo': total_vendas,
            'conversao_media_pct': conv_geral,
            'top_anuncios': top,
            'sem_visitas': sem_visitas,
            'baixa_conversao': baixa_conv,
            'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        }

    except Exception as e:
        logger.error(f"❌ Erro em analise_completa: {e}")
        return {'ok': False, 'erro': str(e)}
