"""
agente_anuncios.py - Gestão de Anúncios do Mercado Livre
=========================================================
Lista anúncios ativos/pausados do vendedor.
Permite pausar e reativar anúncios diretamente pelo dashboard.
Mostra preço, estoque, tipo e link.

Autor: Claude para QUBO
Data: 2026-04
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

TIPO_PT = {
    'gold_pro':     ('👑', 'Premium'),
    'gold_special': ('⭐', 'Clássico'),
    'gold':         ('🥇', 'Ouro'),
    'silver':       ('🥈', 'Prata'),
    'bronze':       ('🥉', 'Bronze'),
    'free':         ('🆓', 'Grátis'),
}

STATUS_COR = {
    'active':  '#4ade80',
    'paused':  '#fbbf24',
    'closed':  '#f87171',
    'under_review': '#f87171',
    'inactive': '#8b92a5',
}


def listar_anuncios(token_ml: str, user_id: str,
                    status: str = "active",
                    limite: int = 50,
                    offset: int = 0) -> dict:
    """
    Lista anúncios do vendedor por status.

    status: "active" | "paused" | "closed" | "" (todos ativos+pausados)
    """
    if not token_ml or not user_id:
        return {'ok': False, 'erro': 'ML não conectado'}

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}

    try:
        # ── 1. Busca IDs dos itens ─────────────────────────────────────
        params = {
            'status': status if status else 'active,paused',
            'limit': min(limite, 50),
            'offset': offset,
        }

        resp = requests.get(
            f'https://api.mercadolibre.com/users/{user_id}/items/search',
            headers=headers,
            params=params,
            timeout=15
        )

        if resp.status_code == 401:
            return {'ok': False, 'erro': 'Token ML expirado. Reconecte.'}
        if resp.status_code == 403:
            return {'ok': False, 'erro': 'Sem permissão para listar anúncios.'}
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro API ML: {resp.status_code}'}

        data = resp.json()
        item_ids = data.get('results', [])
        total = data.get('paging', {}).get('total', 0)

        if not item_ids:
            return {
                'ok': True, 'total': 0, 'anuncios': [],
                'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
            }

        # ── 2. Busca detalhes em batch (até 20 por chamada) ─────────────
        anuncios = []
        for i in range(0, len(item_ids), 20):
            batch = item_ids[i:i+20]
            ids_str = ','.join(batch)

            resp2 = requests.get(
                f'https://api.mercadolibre.com/items',
                headers=headers,
                params={'ids': ids_str},
                timeout=20
            )
            if resp2.status_code != 200:
                continue

            for entry in resp2.json():
                if entry.get('code') != 200:
                    continue
                item = entry.get('body', {})

                tipo_id = item.get('listing_type_id', '')
                tipo_icone, tipo_label = TIPO_PT.get(tipo_id, ('📋', tipo_id))
                status_item = item.get('status', '')
                cor = STATUS_COR.get(status_item, '#8b92a5')

                # Variações (soma de estoques)
                variacoes = item.get('variations', [])
                estoque = item.get('available_quantity', 0)
                if variacoes:
                    estoque = sum(v.get('available_quantity', 0) for v in variacoes)

                anuncios.append({
                    'id': item.get('id'),
                    'titulo': (item.get('title', '') or '')[:70],
                    'preco': item.get('price', 0),
                    'estoque': estoque,
                    'status': status_item,
                    'status_cor': cor,
                    'tipo_id': tipo_id,
                    'tipo_icone': tipo_icone,
                    'tipo_label': tipo_label,
                    'categoria_id': item.get('category_id', ''),
                    'link': item.get('permalink', ''),
                    'thumbnail': item.get('thumbnail', ''),
                    'vendas': item.get('sold_quantity', 0),
                    'data_mod': (item.get('last_updated', '') or '')[:10],
                })

        # Ordena por estoque (0 em baixo) depois por vendas
        anuncios.sort(key=lambda x: (-x['vendas'], x['titulo']))

        return {
            'ok': True,
            'total': total,
            'retornados': len(anuncios),
            'anuncios': anuncios,
            'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        }

    except Exception as e:
        logger.error(f"❌ Erro em listar_anuncios: {e}")
        return {'ok': False, 'erro': str(e)}


def pausar_anuncio(token_ml: str, item_id: str) -> dict:
    """Pausa um anúncio ativo."""
    return _mudar_status(token_ml, item_id, 'paused')


def ativar_anuncio(token_ml: str, item_id: str) -> dict:
    """Reativa um anúncio pausado."""
    return _mudar_status(token_ml, item_id, 'active')


def atualizar_estoque(token_ml: str, item_id: str, quantidade: int) -> dict:
    """Atualiza o estoque disponível de um anúncio."""
    if not token_ml:
        return {'ok': False, 'erro': 'ML não conectado'}
    if quantidade < 0:
        return {'ok': False, 'erro': 'Quantidade inválida'}

    headers = {
        'Authorization': f'Bearer {token_ml}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    try:
        resp = requests.put(
            f'https://api.mercadolibre.com/items/{item_id}',
            headers=headers,
            json={'available_quantity': quantidade},
            timeout=15
        )
        if resp.status_code in (200, 204):
            return {'ok': True, 'msg': f'Estoque atualizado para {quantidade}'}
        elif resp.status_code == 401:
            return {'ok': False, 'erro': 'Token expirado. Reconecte.'}
        else:
            err = resp.json() if resp.text else {}
            return {'ok': False, 'erro': err.get('message', f'Erro {resp.status_code}')}
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


def _mudar_status(token_ml: str, item_id: str, novo_status: str) -> dict:
    if not token_ml:
        return {'ok': False, 'erro': 'ML não conectado'}

    headers = {
        'Authorization': f'Bearer {token_ml}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    try:
        resp = requests.put(
            f'https://api.mercadolibre.com/items/{item_id}',
            headers=headers,
            json={'status': novo_status},
            timeout=15
        )
        if resp.status_code in (200, 204):
            label = 'pausado' if novo_status == 'paused' else 'ativado'
            return {'ok': True, 'msg': f'Anúncio {label} com sucesso!'}
        elif resp.status_code == 401:
            return {'ok': False, 'erro': 'Token expirado. Reconecte.'}
        elif resp.status_code == 403:
            return {'ok': False, 'erro': 'Sem permissão para modificar este anúncio.'}
        else:
            err = resp.json() if resp.text else {}
            return {'ok': False, 'erro': err.get('message', f'Erro {resp.status_code}')}
    except Exception as e:
        return {'ok': False, 'erro': str(e)}
