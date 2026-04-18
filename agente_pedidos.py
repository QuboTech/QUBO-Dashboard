"""
agente_pedidos.py - Pedidos e Vendas do Mercado Livre
======================================================
Lista pedidos recentes com status, comprador, envio e valor.
Agrupa por status e calcula resumo financeiro do período.

Autor: Claude para QUBO
Data: 2026-04
"""

import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

STATUS_PT = {
    'confirmed':      ('✅', 'Confirmado',   '#4ade80'),
    'payment_required':('💳','Aguard. Pgto', '#fbbf24'),
    'payment_in_process':('⏳','Pgto Process.','#fbbf24'),
    'partially_refunded':('↩️','Dev. Parcial', '#fbbf24'),
    'pending':        ('⏳', 'Pendente',     '#fbbf24'),
    'paid':           ('💰', 'Pago',         '#4ade80'),
    'shipped':        ('🚚', 'Enviado',      '#667eea'),
    'delivered':      ('📦', 'Entregue',     '#4ade80'),
    'cancelled':      ('❌', 'Cancelado',    '#f87171'),
    'invalid':        ('🚫', 'Inválido',     '#f87171'),
}

ENVIO_PT = {
    'pending':         ('⏳', 'Pendente'),
    'handling':        ('📋', 'Preparando'),
    'ready_to_ship':   ('📫', 'Pronto p/ Envio'),
    'shipped':         ('🚚', 'Enviado'),
    'delivered':       ('✅', 'Entregue'),
    'not_delivered':   ('❌', 'Não Entregue'),
    'cancelled':       ('🚫', 'Cancelado'),
    'returning':       ('↩️', 'Devolvendo'),
    'returned':        ('↩️', 'Devolvido'),
}


def listar_pedidos(token_ml: str, user_id: str, dias: int = 30,
                   status_filtro: str = "") -> dict:
    """
    Lista pedidos do vendedor nos últimos N dias.

    Parâmetros:
        token_ml: access token ML
        user_id: seller user_id (vem do token)
        dias: janela de tempo (default 30 dias)
        status_filtro: "paid" | "shipped" | "delivered" | "cancelled" | "" (todos)
    """
    if not token_ml or not user_id:
        return {'ok': False, 'erro': 'ML não conectado'}

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}

    try:
        # ── 1. Busca pedidos ──────────────────────────────────────────
        date_from = (datetime.utcnow() - timedelta(days=dias)).strftime('%Y-%m-%dT00:00:00.000Z')

        params = {
            'seller': user_id,
            'order.date_created.from': date_from,
            'sort': 'date_desc',
            'limit': 50,
        }
        if status_filtro:
            params['order.status'] = status_filtro

        resp = requests.get(
            'https://api.mercadolibre.com/orders/search',
            headers=headers,
            params=params,
            timeout=20
        )

        if resp.status_code == 401:
            return {'ok': False, 'erro': 'Token ML expirado. Reconecte.'}
        if resp.status_code == 403:
            return {'ok': False, 'erro': 'Sem permissão. Verifique escopos do app ML.'}
        if resp.status_code != 200:
            return {'ok': False, 'erro': f'Erro API ML: {resp.status_code}'}

        data = resp.json()
        orders_raw = data.get('results', [])
        total_ml = data.get('paging', {}).get('total', 0)

        # ── 2. Processa pedidos ───────────────────────────────────────
        pedidos = []
        total_valor = 0.0
        total_frete = 0.0
        contador_status = {}

        for o in orders_raw:
            status = o.get('status', '')
            icone_s, label_s, cor_s = STATUS_PT.get(status, ('❓', status, '#8b92a5'))

            comprador = o.get('buyer', {})
            itens = o.get('order_items', [])

            # Primeiro item do pedido (geralmente só tem 1)
            item = itens[0] if itens else {}
            titulo = item.get('item', {}).get('title', 'Sem título')[:60]
            qtd = item.get('quantity', 1)
            preco_unit = item.get('unit_price', 0)

            valor_total = o.get('total_amount', 0)
            valor_pago = o.get('paid_amount', 0)

            # Envio
            envio = o.get('shipping', {})
            envio_id = envio.get('id')

            data_criacao = o.get('date_created', '')
            if data_criacao:
                try:
                    dt = datetime.strptime(data_criacao[:19], '%Y-%m-%dT%H:%M:%S')
                    data_fmt = dt.strftime('%d/%m %H:%M')
                except Exception:
                    data_fmt = data_criacao[:10]
            else:
                data_fmt = ''

            total_valor += valor_pago or valor_total
            contador_status[label_s] = contador_status.get(label_s, 0) + 1

            pedidos.append({
                'id': o.get('id'),
                'status': status,
                'status_icone': icone_s,
                'status_label': label_s,
                'status_cor': cor_s,
                'data': data_fmt,
                'comprador': comprador.get('nickname', comprador.get('first_name', 'N/A')),
                'titulo': titulo,
                'qtd': qtd,
                'preco_unit': round(preco_unit, 2),
                'valor_total': round(valor_total, 2),
                'valor_pago': round(valor_pago or valor_total, 2),
                'envio_id': envio_id,
            })

        # ── 3. Resumo ─────────────────────────────────────────────────
        hoje = datetime.utcnow().date()
        ontem = hoje - timedelta(days=1)
        esta_semana = hoje - timedelta(days=7)

        qtd_hoje = sum(1 for p in pedidos if p['data'] and
                       p['data'].startswith(hoje.strftime('%d/%m')))
        val_semana = sum(p['valor_pago'] for p in pedidos if p['status'] not in ('cancelled', 'invalid'))

        return {
            'ok': True,
            'total_ml': total_ml,
            'periodo_dias': dias,
            'total_processados': len(pedidos),
            'total_valor': round(total_valor, 2),
            'qtd_hoje': qtd_hoje,
            'val_semana': round(val_semana, 2),
            'por_status': contador_status,
            'pedidos': pedidos,
            'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        }

    except Exception as e:
        logger.error(f"❌ Erro em listar_pedidos: {e}")
        return {'ok': False, 'erro': str(e)}
