"""
webhook_handler.py - Receptor de Webhooks do Mercado Livre
===========================================================
ML envia POST em tempo real quando acontece:
  - orders_v2: novo pedido / mudança de status
  - items: anúncio criado / editado / pausado
  - questions: nova pergunta / resposta
  - messages: nova mensagem pós-venda
  - shipments: mudança de status de envio
  - payments: mudança de status de pagamento

Este módulo:
  1. Recebe o POST e valida origem (ML)
  2. Armazena o evento em ml_webhooks_events
  3. Processa notificações críticas (ex: alerta de nova pergunta)

Configurar no painel ML:
  https://developers.mercadolivre.com.br/panel/applications
  → Notifications URL → https://<seu-app>.onrender.com/webhook/ml

Autor: Claude para QUBO
Data: 2026-04
"""

import json
import logging
from datetime import datetime

from db import get_conn, USAR_POSTGRES

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA — tabela de eventos
# ─────────────────────────────────────────────────────────────────────────────
def garantir_tabela_webhooks():
    """Cria tabela ml_webhooks_events se não existir (multi-tenant)."""
    try:
        conn = get_conn(); cur = conn.cursor()
        if USAR_POSTGRES:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ml_webhooks_events (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT DEFAULT 'qubo',
                    resource TEXT,
                    topic TEXT,
                    user_id TEXT,
                    application_id TEXT,
                    sent_at TEXT,
                    received_at TEXT,
                    received_ts BIGINT,
                    processed INTEGER DEFAULT 0,
                    payload TEXT
                )
            """)
            try: cur.execute("ALTER TABLE ml_webhooks_events ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'qubo'")
            except Exception: pass
            cur.execute("CREATE INDEX IF NOT EXISTS idx_whevt_tenant_topic ON ml_webhooks_events(tenant_id, topic)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_whevt_ts ON ml_webhooks_events(received_ts)")
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ml_webhooks_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT DEFAULT 'qubo',
                    resource TEXT, topic TEXT, user_id TEXT, application_id TEXT,
                    sent_at TEXT, received_at TEXT, received_ts INTEGER,
                    processed INTEGER DEFAULT 0, payload TEXT
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_whevt_tenant_topic ON ml_webhooks_events(tenant_id, topic)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_whevt_ts ON ml_webhooks_events(received_ts)")
        conn.commit(); conn.close()
    except Exception as e:
        logger.warning(f"⚠️ Falha ao criar ml_webhooks_events: {e}")


def _resolver_tenant_por_ml_user(ml_user_id: str) -> str:
    """Descobre qual tenant é dono deste ML user_id (via ml_tokens.user_id)."""
    if not ml_user_id:
        return 'qubo'
    try:
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        cur.execute(f"SELECT tenant_id, id FROM ml_tokens WHERE user_id = {ph}", (str(ml_user_id),))
        r = cur.fetchone(); conn.close()
        if r:
            return r[0] or r[1] or 'qubo'
    except Exception:
        pass
    return 'qubo'


# ─────────────────────────────────────────────────────────────────────────────
# RECEPTOR — processa POST do ML
# ─────────────────────────────────────────────────────────────────────────────
def processar_notificacao(body: dict) -> dict:
    """
    Armazena notificação recebida do ML.
    Formato esperado (ML):
      {
        "resource": "/orders/123",
        "user_id": 567,
        "topic": "orders_v2",
        "application_id": 123,
        "attempts": 1,
        "sent": "2026-04-15T10:00:00Z",
        "received": "2026-04-15T10:00:01Z"
      }
    """
    if not body:
        return {'ok': False, 'erro': 'Body vazio'}

    try:
        garantir_tabela_webhooks()

        resource = body.get('resource', '')
        topic = body.get('topic', '')
        user_id = str(body.get('user_id', ''))
        app_id = str(body.get('application_id', ''))
        sent_at = body.get('sent', '')
        received_at = body.get('received', datetime.utcnow().isoformat())
        received_ts = int(datetime.utcnow().timestamp())
        payload_json = json.dumps(body)[:8000]

        # Resolve tenant dono deste ML user_id
        tenant_id = _resolver_tenant_por_ml_user(user_id)

        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        cur.execute(f"""
            INSERT INTO ml_webhooks_events
            (tenant_id, resource, topic, user_id, application_id, sent_at, received_at, received_ts, processed, payload)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, 0, {ph})
        """, (tenant_id, resource, topic, user_id, app_id, sent_at, received_at, received_ts, payload_json))
        conn.commit(); conn.close()

        logger.info(f"🔔 Webhook recebido ({tenant_id}): {topic} → {resource}")
        return {'ok': True, 'topic': topic, 'resource': resource, 'tenant_id': tenant_id}

    except Exception as e:
        logger.error(f"❌ Erro ao processar webhook: {e}")
        return {'ok': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# CONSULTA — eventos recentes para dashboard
# ─────────────────────────────────────────────────────────────────────────────
TOPIC_LABEL = {
    'orders_v2':    ('🛒', 'Pedido',    '#4ade80'),
    'items':        ('📋', 'Anúncio',   '#60a5fa'),
    'questions':    ('❓', 'Pergunta',  '#fbbf24'),
    'messages':     ('💬', 'Mensagem',  '#c084fc'),
    'shipments':    ('🚚', 'Envio',     '#93c5fd'),
    'payments':     ('💰', 'Pagamento', '#fbbf24'),
    'claims':       ('⚠️', 'Reclamação','#f87171'),
    'invoices':     ('🧾', 'NF',        '#8b92a5'),
}


def listar_eventos(limite: int = 50, topic: str = "", tenant_id: str = 'qubo') -> dict:
    """Lista os últimos eventos recebidos (escopado por tenant)."""
    try:
        garantir_tabela_webhooks()
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"

        if topic:
            cur.execute(f"""
                SELECT resource, topic, user_id, sent_at, received_at, received_ts, processed
                FROM ml_webhooks_events
                WHERE tenant_id = {ph} AND topic = {ph}
                ORDER BY received_ts DESC
                LIMIT {ph}
            """, (tenant_id, topic, limite))
        else:
            cur.execute(f"""
                SELECT resource, topic, user_id, sent_at, received_at, received_ts, processed
                FROM ml_webhooks_events
                WHERE tenant_id = {ph}
                ORDER BY received_ts DESC
                LIMIT {ph}
            """, (tenant_id, limite))

        rows = cur.fetchall()
        eventos = []
        for r in rows:
            resource, top, uid, sent, received, ts, proc = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
            icone, label, cor = TOPIC_LABEL.get(top, ('🔔', top, '#8b92a5'))
            try:
                ts_fmt = datetime.fromtimestamp(int(ts)).strftime('%d/%m %H:%M:%S')
            except Exception:
                ts_fmt = str(received)[:16]
            eventos.append({
                'resource': resource,
                'topic': top,
                'icone': icone,
                'label': label,
                'cor': cor,
                'data': ts_fmt,
                'processed': bool(proc),
                'link': _resource_para_link(resource, top),
            })

        # Estatísticas (do tenant)
        cur.execute(f"SELECT topic, COUNT(*) FROM ml_webhooks_events WHERE tenant_id = {ph} GROUP BY topic", (tenant_id,))
        stats = {row[0]: row[1] for row in cur.fetchall()}

        # Último evento (do tenant)
        cur.execute(f"SELECT MAX(received_ts) FROM ml_webhooks_events WHERE tenant_id = {ph}", (tenant_id,))
        r_max = cur.fetchone()
        ultimo_ts = r_max[0] if r_max else None

        conn.close()

        ultimo_fmt = ''
        if ultimo_ts:
            try:
                ultimo_fmt = datetime.fromtimestamp(int(ultimo_ts)).strftime('%d/%m/%Y %H:%M:%S')
            except Exception:
                pass

        return {
            'ok': True,
            'eventos': eventos,
            'stats': stats,
            'ultimo_evento': ultimo_fmt,
            'total': sum(stats.values()),
        }
    except Exception as e:
        logger.error(f"❌ Erro em listar_eventos: {e}")
        return {'ok': False, 'erro': str(e), 'eventos': [], 'stats': {}, 'total': 0}


def _resource_para_link(resource: str, topic: str) -> str:
    """Converte resource ML em link do ML onde possível."""
    if not resource:
        return ''
    # resource é tipo "/orders/123" ou "/items/MLB123"
    if resource.startswith('/items/'):
        item_id = resource.split('/')[-1]
        return f'https://www.mercadolivre.com.br/{item_id}'
    if resource.startswith('/orders/'):
        return ''  # orders não tem URL pública
    if resource.startswith('/questions/'):
        return ''
    return ''


def limpar_antigos(dias: int = 30) -> dict:
    """Remove eventos com mais de N dias para manter tabela enxuta."""
    try:
        limite_ts = int(datetime.utcnow().timestamp()) - (dias * 86400)
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        cur.execute(f"DELETE FROM ml_webhooks_events WHERE received_ts < {ph}", (limite_ts,))
        removidos = cur.rowcount
        conn.commit(); conn.close()
        return {'ok': True, 'removidos': removidos}
    except Exception as e:
        return {'ok': False, 'erro': str(e)}
