"""
agente_reputacao.py - Reputação e Métricas do Vendedor ML
=========================================================
Dados completos de reputação: nível, termômetro, transações,
cancelamentos, atrasos, reclamações e capacidade de listagem.

Autor: Claude para QUBO
Data: 2026-04
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

NIVEL_LABEL = {
    '1_red':        ('🔴', 'Vermelho',      '#f87171'),
    '2_orange':     ('🟠', 'Laranja',       '#fb923c'),
    '3_yellow':     ('🟡', 'Amarelo',       '#fbbf24'),
    '4_light_green':('🟢', 'Verde Claro',   '#86efac'),
    '5_green':      ('💚', 'Verde',         '#4ade80'),
    'not_yet_rated':('⚪', 'Sem Histórico', '#8b92a5'),
    'newbie':       ('🆕', 'Iniciante',     '#8b92a5'),
}

POWER_SELLER = {
    'silver': ('🥈', 'MercadoLíder Silver'),
    'gold':   ('🥇', 'MercadoLíder Gold'),
    'platinum':('💎', 'MercadoLíder Platinum'),
    None:     ('', ''),
}


def obter_reputacao(token_ml: str, user_id: str) -> dict:
    """
    Obtém reputação completa do vendedor.
    Combina /users/{id}, /users/{id}/seller_reputation e /marketplace/users/cap
    """
    if not token_ml or not user_id:
        return {'ok': False, 'erro': 'ML não conectado'}

    headers = {'Authorization': f'Bearer {token_ml}', 'Accept': 'application/json'}

    try:
        # ── 1. Dados gerais do usuário + reputação ────────────────────
        resp_user = requests.get(
            f'https://api.mercadolibre.com/users/{user_id}',
            headers=headers, timeout=15
        )
        if resp_user.status_code == 401:
            return {'ok': False, 'erro': 'Token expirado. Reconecte.'}
        if resp_user.status_code != 200:
            return {'ok': False, 'erro': f'Erro API ML: {resp_user.status_code}'}

        user = resp_user.json()
        rep = user.get('seller_reputation', {})

        nivel_id = rep.get('level_id', 'not_yet_rated') or 'not_yet_rated'
        nivel_icone, nivel_label, nivel_cor = NIVEL_LABEL.get(nivel_id, ('❓', nivel_id, '#8b92a5'))

        power_id = rep.get('power_seller_status')
        ps_icone, ps_label = POWER_SELLER.get(power_id, ('', ''))

        # Métricas detalhadas
        metricas_period = rep.get('metrics', {})
        transacoes = rep.get('transactions', {})

        cancel   = metricas_period.get('cancellations', {})
        atrasos  = metricas_period.get('delayed_handling_time', {})
        claims   = metricas_period.get('claims', {})
        ratings  = metricas_period.get('ratings', {})

        total_trans = transacoes.get('total', 0)
        completas   = transacoes.get('completed', 0)
        canceladas  = transacoes.get('canceled', 0)

        # Rating positivo %
        rat_pos = ratings.get('positive', 0)
        rat_neg = ratings.get('negative', 0)
        rat_neu = ratings.get('neutral', 0)
        rat_total = rat_pos + rat_neg + rat_neu
        pct_positivo = round(rat_pos / rat_total * 100, 1) if rat_total > 0 else 0

        # Percentuais de problemas
        def pct_metrica(m):
            rate = m.get('rate', m.get('value', 0)) or 0
            return round(float(rate) * 100, 1) if float(rate) <= 1 else round(float(rate), 1)

        pct_cancel  = pct_metrica(cancel)
        pct_atraso  = pct_metrica(atrasos)
        pct_claims  = pct_metrica(claims)

        # ── 2. Capacidade de listagem ──────────────────────────────────
        cap = {}
        try:
            resp_cap = requests.get(
                'https://api.mercadolibre.com/marketplace/users/cap',
                headers=headers, timeout=10
            )
            if resp_cap.status_code == 200:
                cap = resp_cap.json()
        except Exception:
            pass

        quota = cap.get('quota', 0)
        total_items = cap.get('total_items_active', 0)
        slots_livres = max(0, quota - total_items) if quota else 0

        # ── 3. Monta saúde ─────────────────────────────────────────────
        alertas = []

        if pct_cancel >= 3:
            alertas.append({'tipo': 'critico', 'icone': '🚨', 'msg': f'Cancelamentos em {pct_cancel}% — acima do limite!', 'cor': '#f87171'})
        elif pct_cancel >= 2:
            alertas.append({'tipo': 'aviso', 'icone': '⚠️', 'msg': f'Cancelamentos em {pct_cancel}% — atenção', 'cor': '#fbbf24'})

        if pct_atraso >= 10:
            alertas.append({'tipo': 'critico', 'icone': '🚨', 'msg': f'Atrasos em {pct_atraso}% — impacta reputação!', 'cor': '#f87171'})
        elif pct_atraso >= 5:
            alertas.append({'tipo': 'aviso', 'icone': '⚠️', 'msg': f'Atrasos em {pct_atraso}% — monitore', 'cor': '#fbbf24'})

        if pct_claims >= 3:
            alertas.append({'tipo': 'critico', 'icone': '🚨', 'msg': f'Reclamações em {pct_claims}% — acima do limite!', 'cor': '#f87171'})
        elif pct_claims >= 1.5:
            alertas.append({'tipo': 'aviso', 'icone': '⚠️', 'msg': f'Reclamações em {pct_claims}%', 'cor': '#fbbf24'})

        if not alertas:
            alertas.append({'tipo': 'ok', 'icone': '✅', 'msg': 'Reputação saudável! Continue assim.', 'cor': '#4ade80'})

        return {
            'ok': True,
            'user_id': user_id,
            'apelido': user.get('nickname', ''),
            'nome': f"{user.get('first_name','')} {user.get('last_name','')}".strip(),

            # Nível
            'nivel_id': nivel_id,
            'nivel_icone': nivel_icone,
            'nivel_label': nivel_label,
            'nivel_cor': nivel_cor,

            # Power Seller
            'power_icone': ps_icone,
            'power_label': ps_label,

            # Transações
            'total_transacoes': total_trans,
            'transacoes_completas': completas,
            'transacoes_canceladas': canceladas,

            # Métricas %
            'pct_positivo': pct_positivo,
            'pct_cancelamentos': pct_cancel,
            'pct_atrasos': pct_atraso,
            'pct_reclamacoes': pct_claims,

            # Capacidade
            'quota_anuncios': quota,
            'anuncios_ativos': total_items,
            'slots_livres': slots_livres,

            # Alertas
            'alertas': alertas,

            'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        }

    except Exception as e:
        logger.error(f"❌ Erro em obter_reputacao: {e}")
        return {'ok': False, 'erro': str(e)}
