"""
db.py - Banco de dados multi-tenant
Cada tenant_id isola completamente os dados do usuário.

Modos de conexão:
  - SUPABASE_KEY definida  → REST API via _exec() (Render/produção, sem psycopg2)
  - DATABASE_URL postgresql → psycopg2 direto (dev local com IPv6)
  - Nenhum dos dois        → SQLite (dev local offline)
"""
import os
import re
import sqlite3
from pathlib import Path

DATABASE_URL  = os.getenv("DATABASE_URL", "")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY", "")

# Deriva SUPABASE_URL a partir da DATABASE_URL (formato pooler: postgres.PROJECT:PASS@...)
_m_project = re.match(r'postgresql://postgres\.([a-z0-9]+):', DATABASE_URL)
SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    f"https://{_m_project.group(1)}.supabase.co" if _m_project else ""
)

# Usa psycopg2 direto apenas quando SUPABASE_KEY não estiver disponível
USE_REST  = bool(SUPABASE_KEY and SUPABASE_URL)
USAR_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgresql")) or USE_REST
DB_PATH   = Path("data/viabilidade.db")


# ─────────────────────────────────────────────────────────────────────────────
# Fake cursor/conexão que roteia SQL → Supabase REST API (função _exec)
# ─────────────────────────────────────────────────────────────────────────────

def _to_pg_params(sql: str, params):
    """Converte placeholders %s → $1, $2, ... para a função _exec."""
    i = [0]
    def repl(_):
        i[0] += 1
        return f'${i[0]}'
    return re.sub(r'%s', repl, sql), list(params) if params else []


class _FakeCursor:
    """Cursor psycopg2-compatível que executa SQL via REST API (função _exec)."""

    def __init__(self, url: str, headers: dict):
        self._url     = url
        self._headers = headers
        self._rows    = []
        self.description = None
        self.rowcount    = 0

    def _call(self, sql: str, params):
        import json, urllib.request as _ur, urllib.error as _ue
        new_sql, plist = _to_pg_params(sql, params)

        # Converte para tipos JSON nativos
        json_params = []
        for v in plist:
            if v is None:
                json_params.append(None)
            elif isinstance(v, bool):
                json_params.append(v)
            elif isinstance(v, int):
                json_params.append(v)
            elif isinstance(v, float):
                json_params.append(v)
            else:
                json_params.append(str(v))

        body = json.dumps({'q': new_sql, 'p': json_params}).encode('utf-8')
        req  = _ur.Request(
            f"{self._url}/rest/v1/rpc/_exec",
            data=body,
            headers={**self._headers, 'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with _ur.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except _ue.HTTPError as e:
            body_err = e.read().decode('utf-8', errors='replace')
            raise RuntimeError(f"Supabase _exec HTTP {e.code}: {body_err}") from e

    def execute(self, sql: str, params=None):
        data     = self._call(sql, params)
        sql_up   = sql.strip().upper()
        is_sel   = sql_up.startswith('SELECT') or sql_up.startswith('WITH')
        has_ret  = 'RETURNING' in sql.upper()

        if is_sel or has_ret:
            self._rows = data if isinstance(data, list) else []
            if self._rows:
                self.description = [(k, None, None, None, None, None, None)
                                    for k in self._rows[0].keys()]
            else:
                self.description = []
            self.rowcount = len(self._rows)
        else:
            self._rows       = []
            self.description = []
            self.rowcount    = int(data) if isinstance(data, (int, float)) else 0

    def executemany(self, sql: str, params_list):
        for params in params_list:
            self.execute(sql, params)

    def fetchall(self):
        return [tuple(row.values()) for row in self._rows]

    def fetchone(self):
        return tuple(self._rows[0].values()) if self._rows else None


class _FakeConn:
    """Conexão fake psycopg2-compatível usando Supabase REST API."""

    def __init__(self, url: str, key: str):
        self._headers = {
            'apikey':        key,
            'Authorization': f'Bearer {key}',
        }
        self._url = url

    def cursor(self):
        return _FakeCursor(self._url, self._headers)

    def commit(self):
        pass   # REST API é auto-commit

    def close(self):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

def get_conn():
    if USE_REST:
        return _FakeConn(SUPABASE_URL, SUPABASE_KEY)
    if USAR_POSTGRES:
        import psycopg2
        from urllib.parse import urlparse, unquote
        p = urlparse(DATABASE_URL)
        return psycopg2.connect(
            host=p.hostname,
            port=p.port or 5432,
            dbname=(p.path or '/postgres').lstrip('/') or 'postgres',
            user=unquote(p.username or 'postgres'),
            password=unquote(p.password or ''),
            sslmode='require',
            connect_timeout=10,
        )
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def existe_banco():
    try:
        conn = get_conn()
        cur  = conn.cursor()
        if USAR_POSTGRES:
            cur.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables "
                "WHERE table_name='produtos')"
            )
            existe = cur.fetchone()[0]
        else:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='produtos'")
            existe = bool(cur.fetchone())
        conn.close()
        return existe
    except Exception:
        return False


def garantir_schema():
    conn = get_conn()
    cur  = conn.cursor()

    if USAR_POSTGRES:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT DEFAULT 'default',
                codigo TEXT DEFAULT '',
                fornecedor TEXT DEFAULT '',
                descricao TEXT DEFAULT '',
                custo REAL DEFAULT 0,
                preco_ml REAL DEFAULT 0,
                taxa_categoria REAL DEFAULT 0.165,
                custo_frete REAL DEFAULT 0,
                taxa_fixa_ml REAL DEFAULT 0,
                peso_kg REAL DEFAULT 0,
                custo_embalagem REAL DEFAULT 0,
                imposto_valor REAL DEFAULT 0,
                custo_total REAL DEFAULT 0,
                margem_percentual REAL DEFAULT 0,
                margem_reais REAL DEFAULT 0,
                viavel INTEGER DEFAULT 0,
                link_ml TEXT DEFAULT '',
                notas TEXT DEFAULT '',
                pagina_origem INTEGER DEFAULT 0,
                tipo_anuncio TEXT DEFAULT 'classico',
                escolhido INTEGER DEFAULT 0,
                custo_full REAL DEFAULT 0,
                custo_ads REAL DEFAULT 0,
                promo_percentual REAL DEFAULT 0,
                margem_alvo REAL DEFAULT 25,
                preco_ideal REAL DEFAULT 0,
                preco_final REAL DEFAULT 0,
                lucro_final REAL DEFAULT 0,
                margem_final REAL DEFAULT 0,
                data_analise TEXT DEFAULT '',
                arquivo_origem TEXT DEFAULT ''
            )
        """)
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='produtos'"
        )
        existentes = {row[0] for row in cur.fetchall()}
        novas_colunas = {
            'tenant_id':        "TEXT DEFAULT 'default'",
            'preco_ml':         'REAL DEFAULT 0',
            'taxa_categoria':   'REAL DEFAULT 0.165',
            'custo_frete':      'REAL DEFAULT 0',
            'taxa_fixa_ml':     'REAL DEFAULT 0',
            'peso_kg':          'REAL DEFAULT 0',
            'custo_embalagem':  'REAL DEFAULT 0',
            'imposto_valor':    'REAL DEFAULT 0',
            'custo_total':      'REAL DEFAULT 0',
            'margem_percentual':'REAL DEFAULT 0',
            'margem_reais':     'REAL DEFAULT 0',
            'viavel':           'INTEGER DEFAULT 0',
            'link_ml':          "TEXT DEFAULT ''",
            'notas':            "TEXT DEFAULT ''",
            'pagina_origem':    'INTEGER DEFAULT 0',
            'tipo_anuncio':     "TEXT DEFAULT 'classico'",
            'escolhido':        'INTEGER DEFAULT 0',
            'custo_full':       'REAL DEFAULT 0',
            'custo_ads':        'REAL DEFAULT 0',
            'promo_percentual': 'REAL DEFAULT 0',
            'margem_alvo':      'REAL DEFAULT 25',
            'preco_ideal':      'REAL DEFAULT 0',
            'preco_final':      'REAL DEFAULT 0',
            'lucro_final':      'REAL DEFAULT 0',
            'margem_final':     'REAL DEFAULT 0',
            'data_analise':     "TEXT DEFAULT ''",
            'arquivo_origem':   "TEXT DEFAULT ''",
        }
        for col, tipo in novas_colunas.items():
            if col not in existentes:
                try:
                    cur.execute(
                        f"ALTER TABLE produtos ADD COLUMN IF NOT EXISTS {col} {tipo}"
                    )
                except Exception:
                    pass
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_tenant ON produtos(tenant_id)"
        )
        # Tabela de tokens ML (persiste entre deploys) — 1 row por tenant
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ml_tokens (
                id TEXT PRIMARY KEY DEFAULT 'principal',
                access_token TEXT,
                refresh_token TEXT,
                user_id TEXT,
                expires_at TEXT,
                salvo_em TEXT,
                tenant_id TEXT DEFAULT 'qubo'
            )
        """)
        # Adiciona tenant_id se não existir (upgrade)
        try:
            cur.execute("ALTER TABLE ml_tokens ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'qubo'")
        except Exception: pass
        # Migração: row 'principal' legado vira 'qubo' (se ainda não existir 'qubo')
        try:
            cur.execute("UPDATE ml_tokens SET id='qubo', tenant_id='qubo' WHERE id='principal' AND NOT EXISTS (SELECT 1 FROM ml_tokens WHERE id='qubo')")
        except Exception: pass

        # ═══════════════════════════════════════════════════════════════
        # MULTI-TENANT: tabelas tenants + usuarios
        # ═══════════════════════════════════════════════════════════════
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id SERIAL PRIMARY KEY,
                slug TEXT UNIQUE NOT NULL,
                nome_empresa TEXT NOT NULL,
                email_admin TEXT,
                plano TEXT DEFAULT 'free',
                ativo INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                cor_primaria TEXT DEFAULT '#667eea'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                nome TEXT,
                role TEXT DEFAULT 'admin',
                ativo INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usuario_tenant ON usuarios(tenant_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usuario_email ON usuarios(email)")

        # Seed: Qubo como primeiro tenant (id=1)
        cur.execute("""
            INSERT INTO tenants (slug, nome_empresa, email_admin, plano)
            VALUES ('qubo', 'Qubo', 'gustavo@qubo.com.br', 'enterprise')
            ON CONFLICT (slug) DO NOTHING
        """)

        # Config — adiciona tenant_id
        try:
            cur.execute("ALTER TABLE config ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'qubo'")
        except Exception: pass
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT DEFAULT 'default',
                codigo TEXT, fornecedor TEXT, descricao TEXT, custo REAL,
                data_analise TEXT, arquivo_origem TEXT, pagina_origem INTEGER DEFAULT 0
            )
        """)
        cur.execute("PRAGMA table_info(produtos)")
        existentes = {row[1] for row in cur.fetchall()}
        novas = {
            'tenant_id': "TEXT DEFAULT 'default'",
            'preco_ml': 'REAL DEFAULT 0',
            'taxa_categoria': 'REAL DEFAULT 0.165',
            'custo_frete': 'REAL DEFAULT 0',
            'taxa_fixa_ml': 'REAL DEFAULT 0',
            'peso_kg': 'REAL DEFAULT 0',
            'custo_embalagem': 'REAL DEFAULT 0',
            'imposto_valor': 'REAL DEFAULT 0',
            'custo_total': 'REAL DEFAULT 0',
            'margem_percentual': 'REAL DEFAULT 0',
            'margem_reais': 'REAL DEFAULT 0',
            'viavel': 'INTEGER DEFAULT 0',
            'link_ml': "TEXT DEFAULT ''",
            'notas': "TEXT DEFAULT ''",
            'tipo_anuncio': "TEXT DEFAULT 'classico'",
            'escolhido': 'INTEGER DEFAULT 0',
            'custo_full': 'REAL DEFAULT 0',
            'custo_ads': 'REAL DEFAULT 0',
            'promo_percentual': 'REAL DEFAULT 0',
            'margem_alvo': 'REAL DEFAULT 25',
            'preco_ideal': 'REAL DEFAULT 0',
            'preco_final': 'REAL DEFAULT 0',
            'lucro_final': 'REAL DEFAULT 0',
            'margem_final': 'REAL DEFAULT 0',
        }
        for col, tipo in novas.items():
            if col not in existentes:
                try:
                    cur.execute(f"ALTER TABLE produtos ADD COLUMN {col} {tipo}")
                except Exception:
                    pass
        # Tabela de tokens ML
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ml_tokens (
                id TEXT PRIMARY KEY DEFAULT 'principal',
                access_token TEXT,
                refresh_token TEXT,
                user_id TEXT,
                expires_at TEXT,
                salvo_em TEXT
            )
        """)

    conn.commit()
    conn.close()


def dict_row(cur, row):
    if USAR_POSTGRES:
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))
    return dict(row)


def placeholder():
    return "%s" if USAR_POSTGRES else "?"


import logging as _log
_log = _log.getLogger(__name__)
_log.info(
    "Banco: %s",
    f"Supabase REST ({SUPABASE_URL})" if USE_REST
    else ("Postgres psycopg2" if USAR_POSTGRES else "SQLite local")
)
