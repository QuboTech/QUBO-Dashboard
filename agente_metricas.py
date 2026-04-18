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

# Benchmark do usuário: 1000 visitas devem gerar R$ 10.000 em vendas
# => R$ 10,00 de receita por visita
BENCHMARK_RS_VISITA = 10.0


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
            preco = float(d.get('price', 0) or 0)
            conversao = round((vendas / v) * 100, 2) if v > 0 else 0

            # Benchmark R$/visita (meta = BENCHMARK_RS_VISITA)
            receita_est = round(preco * vendas, 2)
            rs_por_visita = round(receita_est / v, 2) if v > 0 else 0
            atinge_benchmark = rs_por_visita >= BENCHMARK_RS_VISITA

            anuncios.append({
                'id': iid,
                'titulo': (d.get('title', '') or iid)[:70],
                'preco': preco,
                'visitas': v,
                'vendas_total': vendas,
                'conversao_pct': conversao,
                'receita_est': receita_est,
                'rs_por_visita': rs_por_visita,
                'atinge_benchmark': atinge_benchmark,
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
        total_receita_est = round(sum(a['receita_est'] for a in anuncios), 2)
        conv_geral = round((total_vendas / total_visitas_itens) * 100, 2) if total_visitas_itens else 0

        # Benchmark geral: R$ por visita médio
        rs_visita_geral = round(total_receita_est / total_visitas_itens, 2) if total_visitas_itens else 0
        atinge_benchmark_geral = rs_visita_geral >= BENCHMARK_RS_VISITA
        # % de quanto falta/sobra frente ao benchmark
        pct_benchmark = round((rs_visita_geral / BENCHMARK_RS_VISITA) * 100, 1) if BENCHMARK_RS_VISITA else 0

        return {
            'ok': True,
            'periodo_dias': dias,
            'total_visitas_vendedor': agreg.get('total_visitas', total_visitas_itens),
            'media_diaria': agreg.get('media_diaria', round(total_visitas_itens / dias, 1)),
            'total_anuncios_analisados': len(anuncios),
            'total_vendas_periodo': total_vendas,
            'conversao_media_pct': conv_geral,
            'receita_estimada': total_receita_est,
            'rs_por_visita': rs_visita_geral,
            'benchmark_rs_visita': BENCHMARK_RS_VISITA,
            'atinge_benchmark_geral': atinge_benchmark_geral,
            'pct_benchmark': pct_benchmark,
            'top_anuncios': top,
            'sem_visitas': sem_visitas,
            'baixa_conversao': baixa_conv,
            'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        }

    except Exception as e:
        logger.error(f"❌ Erro em analise_completa: {e}")
        return {'ok': False, 'erro': str(e)}
