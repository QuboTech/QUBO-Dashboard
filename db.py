"""
db.py - Banco de dados multi-tenant
Cada tenant_id isola completamente os dados do usuário.
"""
import os
import sqlite3
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "")
USAR_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgresql"))
DB_PATH = Path("data/viabilidade.db")


def get_conn():
    if USAR_POSTGRES:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def existe_banco():
    try:
        conn = get_conn()
        cur = conn.cursor()
        if USAR_POSTGRES:
            cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='produtos')")
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
    cur = conn.cursor()
    ph = "%s" if USAR_POSTGRES else "?"

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
        # Migração: adiciona colunas que faltam em tabelas antigas (v3 → v4)
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='produtos'")
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
                    cur.execute(f"ALTER TABLE produtos ADD COLUMN IF NOT EXISTS {col} {tipo}")
                except Exception as e:
                    pass
        # Índice para performance multi-tenant
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tenant ON produtos(tenant_id)")
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
_log.getLogger(__name__).info("Banco: %s", "Postgres (Supabase)" if USAR_POSTGRES else "SQLite (local)")
