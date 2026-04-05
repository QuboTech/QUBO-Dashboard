"""
dashboard_web.py - Dashboard V3 com Planilha ML Integrada
==========================================================
INTEGRAÇÃO COMPLETA com planilha oficial Mercado Livre:
  - Tabela de frete real (110 faixas: preço × peso)
  - Taxa ML % por categoria
  - Taxa fixa condicional (R$6.25 se < R$79)
  - Imposto configurável (alíquota global)
  - Peso e embalagem por produto
  - Margem de Contribuição % e Margem Líquida R$
  - Busca ML via API
  - Exportação Excel no formato da planilha oficial

Substitui: dashboard_web.py v2

Autor: Claude para QUBO
Data: 2026-02
"""
import os
import json
import io
import time
import threading
import webbrowser
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_file
from db import get_conn, existe_banco, garantir_schema, dict_row, placeholder, DB_PATH, USAR_POSTGRES
from auth import login_required, get_tenant_id, get_usuario_nome, verificar_login, LOGIN_HTML, carregar_usuarios

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "qubo-secret-2026-change-this")
logger = logging.getLogger(__name__)

# Filtro Jinja para formato brasileiro (vírgula decimal)
@app.template_filter('br')
def formato_br(value, decimais=2):
    """Formata número no padrão BR: 1.234,56"""
    try:
        if value is None or value == '':
            return '-'
        v = float(value)
        if decimais == 1:
            return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(value)


# ============================================================
# TABELA DE FRETE OFICIAL ML (extraída da planilha)
# 5 faixas de preço × 22 faixas de peso = 110 combinações
# ============================================================

TABELA_FRETE = [
    # Faixa 1: R$79 - R$99.99
    {"fp":1,"pm":79,"px":99.99,"wm":0,"wx":0.299,"fr":11.97},
    {"fp":1,"pm":79,"px":99.99,"wm":0.3,"wx":0.499,"fr":12.87},
    {"fp":1,"pm":79,"px":99.99,"wm":0.5,"wx":0.999,"fr":13.47},
    {"fp":1,"pm":79,"px":99.99,"wm":1,"wx":1.999,"fr":14.07},
    {"fp":1,"pm":79,"px":99.99,"wm":2,"wx":2.999,"fr":14.97},
    {"fp":1,"pm":79,"px":99.99,"wm":3,"wx":3.999,"fr":16.17},
    {"fp":1,"pm":79,"px":99.99,"wm":4,"wx":4.999,"fr":17.07},
    {"fp":1,"pm":79,"px":99.99,"wm":5,"wx":8.999,"fr":26.67},
    {"fp":1,"pm":79,"px":99.99,"wm":9,"wx":12.999,"fr":39.57},
    {"fp":1,"pm":79,"px":99.99,"wm":13,"wx":16.999,"fr":44.07},
    {"fp":1,"pm":79,"px":99.99,"wm":17,"wx":22.999,"fr":51.57},
    {"fp":1,"pm":79,"px":99.99,"wm":23,"wx":29.999,"fr":59.37},
    {"fp":1,"pm":79,"px":99.99,"wm":30,"wx":39.999,"fr":61.17},
    {"fp":1,"pm":79,"px":99.99,"wm":40,"wx":49.999,"fr":63.27},
    {"fp":1,"pm":79,"px":99.99,"wm":50,"wx":59.999,"fr":67.47},
    {"fp":1,"pm":79,"px":99.99,"wm":60,"wx":69.999,"fr":72.27},
    {"fp":1,"pm":79,"px":99.99,"wm":70,"wx":79.999,"fr":75.57},
    {"fp":1,"pm":79,"px":99.99,"wm":80,"wx":89.999,"fr":83.97},
    {"fp":1,"pm":79,"px":99.99,"wm":90,"wx":99.999,"fr":95.97},
    {"fp":1,"pm":79,"px":99.99,"wm":100,"wx":124.999,"fr":107.37},
    {"fp":1,"pm":79,"px":99.99,"wm":125,"wx":149.999,"fr":113.97},
    {"fp":1,"pm":79,"px":99.99,"wm":150,"wx":999,"fr":149.67},
    # Faixa 2: R$100 - R$119.99
    {"fp":2,"pm":100,"px":119.99,"wm":0,"wx":0.299,"fr":13.97},
    {"fp":2,"pm":100,"px":119.99,"wm":0.3,"wx":0.499,"fr":15.02},
    {"fp":2,"pm":100,"px":119.99,"wm":0.5,"wx":0.999,"fr":15.72},
    {"fp":2,"pm":100,"px":119.99,"wm":1,"wx":1.999,"fr":16.42},
    {"fp":2,"pm":100,"px":119.99,"wm":2,"wx":2.999,"fr":17.47},
    {"fp":2,"pm":100,"px":119.99,"wm":3,"wx":3.999,"fr":18.87},
    {"fp":2,"pm":100,"px":119.99,"wm":4,"wx":4.999,"fr":19.92},
    {"fp":2,"pm":100,"px":119.99,"wm":5,"wx":8.999,"fr":31.12},
    {"fp":2,"pm":100,"px":119.99,"wm":9,"wx":12.999,"fr":46.17},
    {"fp":2,"pm":100,"px":119.99,"wm":13,"wx":16.999,"fr":51.42},
    {"fp":2,"pm":100,"px":119.99,"wm":17,"wx":22.999,"fr":60.17},
    {"fp":2,"pm":100,"px":119.99,"wm":23,"wx":29.999,"fr":69.27},
    {"fp":2,"pm":100,"px":119.99,"wm":30,"wx":39.999,"fr":71.37},
    {"fp":2,"pm":100,"px":119.99,"wm":40,"wx":49.999,"fr":73.82},
    {"fp":2,"pm":100,"px":119.99,"wm":50,"wx":59.999,"fr":78.72},
    {"fp":2,"pm":100,"px":119.99,"wm":60,"wx":69.999,"fr":84.32},
    {"fp":2,"pm":100,"px":119.99,"wm":70,"wx":79.999,"fr":88.17},
    {"fp":2,"pm":100,"px":119.99,"wm":80,"wx":89.999,"fr":97.97},
    {"fp":2,"pm":100,"px":119.99,"wm":90,"wx":99.999,"fr":111.97},
    {"fp":2,"pm":100,"px":119.99,"wm":100,"wx":124.999,"fr":125.27},
    {"fp":2,"pm":100,"px":119.99,"wm":125,"wx":149.999,"fr":132.97},
    {"fp":2,"pm":100,"px":119.99,"wm":150,"wx":999,"fr":174.62},
    # Faixa 3: R$120 - R$149.99
    {"fp":3,"pm":120,"px":149.99,"wm":0,"wx":0.299,"fr":15.96},
    {"fp":3,"pm":120,"px":149.99,"wm":0.3,"wx":0.499,"fr":17.16},
    {"fp":3,"pm":120,"px":149.99,"wm":0.5,"wx":0.999,"fr":17.96},
    {"fp":3,"pm":120,"px":149.99,"wm":1,"wx":1.999,"fr":18.76},
    {"fp":3,"pm":120,"px":149.99,"wm":2,"wx":2.999,"fr":19.96},
    {"fp":3,"pm":120,"px":149.99,"wm":3,"wx":3.999,"fr":21.56},
    {"fp":3,"pm":120,"px":149.99,"wm":4,"wx":4.999,"fr":22.76},
    {"fp":3,"pm":120,"px":149.99,"wm":5,"wx":8.999,"fr":35.56},
    {"fp":3,"pm":120,"px":149.99,"wm":9,"wx":12.999,"fr":52.76},
    {"fp":3,"pm":120,"px":149.99,"wm":13,"wx":16.999,"fr":58.76},
    {"fp":3,"pm":120,"px":149.99,"wm":17,"wx":22.999,"fr":68.76},
    {"fp":3,"pm":120,"px":149.99,"wm":23,"wx":29.999,"fr":79.16},
    {"fp":3,"pm":120,"px":149.99,"wm":30,"wx":39.999,"fr":81.56},
    {"fp":3,"pm":120,"px":149.99,"wm":40,"wx":49.999,"fr":84.36},
    {"fp":3,"pm":120,"px":149.99,"wm":50,"wx":59.999,"fr":89.96},
    {"fp":3,"pm":120,"px":149.99,"wm":60,"wx":69.999,"fr":96.36},
    {"fp":3,"pm":120,"px":149.99,"wm":70,"wx":79.999,"fr":100.76},
    {"fp":3,"pm":120,"px":149.99,"wm":80,"wx":89.999,"fr":111.96},
    {"fp":3,"pm":120,"px":149.99,"wm":90,"wx":99.999,"fr":127.96},
    {"fp":3,"pm":120,"px":149.99,"wm":100,"wx":124.999,"fr":143.16},
    {"fp":3,"pm":120,"px":149.99,"wm":125,"wx":149.999,"fr":151.96},
    {"fp":3,"pm":120,"px":149.99,"wm":150,"wx":999,"fr":199.56},
    # Faixa 4: R$150 - R$199.99
    {"fp":4,"pm":150,"px":199.99,"wm":0,"wx":0.299,"fr":17.96},
    {"fp":4,"pm":150,"px":199.99,"wm":0.3,"wx":0.499,"fr":19.31},
    {"fp":4,"pm":150,"px":199.99,"wm":0.5,"wx":0.999,"fr":20.21},
    {"fp":4,"pm":150,"px":199.99,"wm":1,"wx":1.999,"fr":21.11},
    {"fp":4,"pm":150,"px":199.99,"wm":2,"wx":2.999,"fr":22.46},
    {"fp":4,"pm":150,"px":199.99,"wm":3,"wx":3.999,"fr":24.26},
    {"fp":4,"pm":150,"px":199.99,"wm":4,"wx":4.999,"fr":25.61},
    {"fp":4,"pm":150,"px":199.99,"wm":5,"wx":8.999,"fr":40.01},
    {"fp":4,"pm":150,"px":199.99,"wm":9,"wx":12.999,"fr":59.36},
    {"fp":4,"pm":150,"px":199.99,"wm":13,"wx":16.999,"fr":66.11},
    {"fp":4,"pm":150,"px":199.99,"wm":17,"wx":22.999,"fr":77.36},
    {"fp":4,"pm":150,"px":199.99,"wm":23,"wx":29.999,"fr":89.06},
    {"fp":4,"pm":150,"px":199.99,"wm":30,"wx":39.999,"fr":91.76},
    {"fp":4,"pm":150,"px":199.99,"wm":40,"wx":49.999,"fr":94.91},
    {"fp":4,"pm":150,"px":199.99,"wm":50,"wx":59.999,"fr":101.21},
    {"fp":4,"pm":150,"px":199.99,"wm":60,"wx":69.999,"fr":108.41},
    {"fp":4,"pm":150,"px":199.99,"wm":70,"wx":79.999,"fr":113.36},
    {"fp":4,"pm":150,"px":199.99,"wm":80,"wx":89.999,"fr":125.96},
    {"fp":4,"pm":150,"px":199.99,"wm":90,"wx":99.999,"fr":143.96},
    {"fp":4,"pm":150,"px":199.99,"wm":100,"wx":124.999,"fr":161.06},
    {"fp":4,"pm":150,"px":199.99,"wm":125,"wx":149.999,"fr":170.96},
    {"fp":4,"pm":150,"px":199.99,"wm":150,"wx":999,"fr":224.51},
    # Faixa 5: R$200+
    {"fp":5,"pm":200,"px":999999,"wm":0,"wx":0.299,"fr":19.95},
    {"fp":5,"pm":200,"px":999999,"wm":0.3,"wx":0.499,"fr":21.45},
    {"fp":5,"pm":200,"px":999999,"wm":0.5,"wx":0.999,"fr":22.45},
    {"fp":5,"pm":200,"px":999999,"wm":1,"wx":1.999,"fr":23.45},
    {"fp":5,"pm":200,"px":999999,"wm":2,"wx":2.999,"fr":24.95},
    {"fp":5,"pm":200,"px":999999,"wm":3,"wx":3.999,"fr":26.95},
    {"fp":5,"pm":200,"px":999999,"wm":4,"wx":4.999,"fr":28.45},
    {"fp":5,"pm":200,"px":999999,"wm":5,"wx":8.999,"fr":44.45},
    {"fp":5,"pm":200,"px":999999,"wm":9,"wx":12.999,"fr":65.95},
    {"fp":5,"pm":200,"px":999999,"wm":13,"wx":16.999,"fr":73.45},
    {"fp":5,"pm":200,"px":999999,"wm":17,"wx":22.999,"fr":85.95},
    {"fp":5,"pm":200,"px":999999,"wm":23,"wx":29.999,"fr":98.95},
    {"fp":5,"pm":200,"px":999999,"wm":30,"wx":39.999,"fr":101.95},
    {"fp":5,"pm":200,"px":999999,"wm":40,"wx":49.999,"fr":105.45},
    {"fp":5,"pm":200,"px":999999,"wm":50,"wx":59.999,"fr":112.45},
    {"fp":5,"pm":200,"px":999999,"wm":60,"wx":69.999,"fr":120.45},
    {"fp":5,"pm":200,"px":999999,"wm":70,"wx":79.999,"fr":125.95},
    {"fp":5,"pm":200,"px":999999,"wm":80,"wx":89.999,"fr":139.95},
    {"fp":5,"pm":200,"px":999999,"wm":90,"wx":99.999,"fr":159.95},
    {"fp":5,"pm":200,"px":999999,"wm":100,"wx":124.999,"fr":178.95},
    {"fp":5,"pm":200,"px":999999,"wm":125,"wx":149.999,"fr":189.95},
    {"fp":5,"pm":200,"px":999999,"wm":150,"wx":999,"fr":249.45},
]


def calcular_frete(preco_venda, peso_kg):
    """
    Calcula frete usando a tabela oficial ML.
    Mesma lógica da planilha: faixa preço × faixa peso → frete.
    Se preço < R$79.90, frete = 0 (comprador paga).
    """
    if not preco_venda or not peso_kg or preco_venda < 79.90:
        return 0.0
    
    for entry in TABELA_FRETE:
        if entry['pm'] <= preco_venda <= entry['px']:
            if entry['wm'] <= peso_kg <= entry['wx']:
                return entry['fr']
    
    # Fallback: última faixa da faixa 5
    if preco_venda >= 200:
        return 249.45
    return 0.0


def calcular_viabilidade_completa(custo, preco_ml, taxa_categoria=0.165, peso_kg=0, 
                                    embalagem=0, aliquota_imposto=0, custo_ads=0):
    """
    Calcula viabilidade COMPLETA.
    Fórmula: Margem = Venda - Custo - TaxaML - TaxaFixa - Imposto - Embalagem - Frete - ADS
    """
    if not preco_ml or preco_ml <= 0:
        return {
            'taxa_ml_valor': 0, 'taxa_fixa': 0, 'imposto_valor': 0,
            'custo_frete': 0, 'custo_ads': custo_ads or 0, 'custo_total': custo or 0,
            'margem_reais': 0, 'margem_percentual': 0, 'viavel': 0
        }
    
    custo = custo or 0
    peso_kg = peso_kg or 0
    embalagem = embalagem or 0
    custo_ads = custo_ads or 0
    
    taxa_ml_valor = round(preco_ml * taxa_categoria, 2)
    taxa_fixa = 6.25 if preco_ml < 79 else 0
    imposto_valor = round(preco_ml * aliquota_imposto, 2)
    custo_frete = calcular_frete(preco_ml, peso_kg)
    
    # Custo Total INCLUI ADS
    custo_total = round(custo + taxa_ml_valor + taxa_fixa + imposto_valor + embalagem + custo_frete + custo_ads, 2)
    margem_reais = round(preco_ml - custo_total, 2)
    margem_percentual = round((margem_reais / preco_ml) * 100, 1) if preco_ml > 0 else 0
    viavel = 1 if margem_percentual >= 20 else 0
    
    return {
        'taxa_ml_valor': taxa_ml_valor,
        'taxa_fixa': taxa_fixa,
        'imposto_valor': imposto_valor,
        'custo_frete': custo_frete,
        'custo_ads': custo_ads,
        'custo_total': custo_total,
        'margem_reais': margem_reais,
        'margem_percentual': margem_percentual,
        'viavel': viavel
    }


def calcular_preco_ideal(custo, taxa_categoria=0.165, peso_kg=0, embalagem=0,
                          aliquota_imposto=0, custo_full=0, custo_ads=0,
                          promo_pct=0, margem_alvo=25):
    """
    MODO 1: Dado margem alvo, calcula preço ideal de venda.
    Preço = (Custo + Fixos) / (1 - TaxaML% - Imposto% - Promo% - MargemAlvo%)
    """
    custo = custo or 0
    if custo <= 0:
        return {'preco_ideal': 0, 'erro': 'Custo zerado'}
    pct_total = taxa_categoria + aliquota_imposto + (promo_pct / 100) + (margem_alvo / 100)
    if pct_total >= 1:
        return {'preco_ideal': 0, 'erro': 'Custos % excedem 100%'}
    fixos = embalagem + custo_full + custo_ads
    preco_est = (custo + fixos) / (1 - pct_total)
    frete = calcular_frete(preco_est, peso_kg)
    preco_ideal = (custo + fixos + frete) / (1 - pct_total)
    frete2 = calcular_frete(preco_ideal, peso_kg)
    if abs(frete2 - frete) > 0.01:
        preco_ideal = (custo + fixos + frete2) / (1 - pct_total)
        frete = frete2
    taxa_fixa = 6.25 if preco_ideal < 79 else 0
    if taxa_fixa > 0:
        preco_ideal = (custo + fixos + frete + taxa_fixa) / (1 - pct_total)
    preco_ideal = round(preco_ideal, 2)
    return {'preco_ideal': preco_ideal, 'frete_est': frete, 'taxa_fixa': taxa_fixa, 'erro': None}


def calcular_formacao_completa(custo, preco_final, taxa_categoria=0.165, peso_kg=0,
                                embalagem=0, aliquota_imposto=0, custo_full=0,
                                custo_ads=0, promo_pct=0):
    """
    MODO 2: Dado preço de venda, calcula breakdown completo com extras.
    """
    if not preco_final or preco_final <= 0:
        return {'erro': 'Preço zerado'}
    custo = custo or 0
    v = calcular_viabilidade_completa(custo, preco_final, taxa_categoria, peso_kg, embalagem, aliquota_imposto)
    custo_promo = round(preco_final * promo_pct / 100, 2)
    custo_total_full = round(v['custo_total'] + custo_full + custo_ads + custo_promo, 2)
    lucro_final = round(preco_final - custo_total_full, 2)
    margem_final = round((lucro_final / preco_final) * 100, 1) if preco_final > 0 else 0
    return {
        'taxa_ml_valor': v['taxa_ml_valor'], 'taxa_fixa': v['taxa_fixa'],
        'custo_frete': v['custo_frete'], 'imposto_valor': v['imposto_valor'],
        'custo_promo': custo_promo, 'custo_total_full': custo_total_full,
        'lucro_final': lucro_final, 'margem_final': margem_final,
        'viavel': 1 if margem_final >= 20 else 0, 'erro': None
    }


# ============================================================
# SCHEMA DO BANCO
# ============================================================

def garantir_schema():
    """Adiciona colunas novas se não existirem"""
    if not DB_PATH.exists():
        return
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(produtos)")
    existentes = {row[1] for row in cursor.fetchall()}
    
    novas = {
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
        'pagina_origem': 'INTEGER DEFAULT 0',
        'tipo_anuncio': "TEXT DEFAULT 'classico'",
        # Campos Escolhidos / Formação de Preço
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
                cursor.execute(f"ALTER TABLE produtos ADD COLUMN {col} {tipo}")
            except:
                pass
    conn.commit()
    conn.close()

garantir_schema()

# Alíquota de imposto global (configurável via dashboard)
ALIQUOTA_IMPOSTO_FILE = Path("data/aliquota_imposto.json")

def get_aliquota():
    if ALIQUOTA_IMPOSTO_FILE.exists():
        try:
            return json.loads(ALIQUOTA_IMPOSTO_FILE.read_text()).get('aliquota', 0)
        except:
            pass
    return 0

def set_aliquota(valor):
    ALIQUOTA_IMPOSTO_FILE.parent.mkdir(exist_ok=True)
    ALIQUOTA_IMPOSTO_FILE.write_text(json.dumps({'aliquota': valor}))


# ============================================================
# HTML TEMPLATE
# ============================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 Dashboard QUBO v3</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e27;color:#e4e6eb;padding:14px;font-size:13px}
        .container{max-width:1920px;margin:0 auto}
        h1{font-size:1.5rem;margin-bottom:14px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;display:inline-block}
        .header-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:8px}
        .header-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
        
        .stats{display:grid;grid-template-columns:repeat(7,1fr);gap:10px;margin-bottom:14px}
        .stat-card{background:#1a1f3a;padding:10px;border-radius:7px;border:1px solid #2d3452;text-align:center}
        .stat-value{font-size:1.4rem;font-weight:bold;color:#667eea}
        .stat-value.green{color:#4ade80}.stat-value.red{color:#f87171}.stat-value.yellow{color:#fbbf24}.stat-value.purple{color:#c084fc}
        .stat-label{color:#8b92a5;font-size:0.65rem;text-transform:uppercase;margin-top:3px}
        
        .filters{background:#1a1f3a;padding:10px 14px;border-radius:7px;margin-bottom:10px;border:1px solid #2d3452}
        .filter-row{display:grid;grid-template-columns:repeat(8,1fr);gap:7px;margin-bottom:7px}
        .filter-group label{color:#8b92a5;font-size:0.63rem;text-transform:uppercase;display:block;margin-bottom:2px}
        .filter-group input,.filter-group select{width:100%;padding:5px 7px;border:1px solid #2d3452;border-radius:4px;background:#0a0e27;color:#e4e6eb;font-size:0.8rem}
        
        button,.btn{padding:5px 12px;border:none;border-radius:4px;cursor:pointer;font-size:0.78rem;font-weight:600;transition:all .15s;text-decoration:none;display:inline-block}
        .btn-primary{background:#667eea;color:#fff}.btn-primary:hover{background:#5568d3}
        .btn-secondary{background:#2d3452;color:#e4e6eb}.btn-success{background:#059669;color:#fff}
        .btn-sm{padding:3px 8px;font-size:0.7rem}
        
        .table-wrapper{overflow-x:auto;border-radius:7px}
        table{width:100%;border-collapse:collapse;background:#1a1f3a;font-size:0.78rem}
        th,td{padding:5px 6px;text-align:left;border-bottom:1px solid #2d3452;white-space:nowrap}
        th{background:#252a47;font-weight:600;color:#8b92a5;text-transform:uppercase;font-size:0.63rem;position:sticky;top:0;z-index:10}
        tr:hover{background:#252a47}
        
        .codigo{color:#667eea;font-weight:600}.fornecedor{color:#f093fb}.custo{color:#fbbf24;font-weight:600}
        .preco-ml{color:#4ade80;font-weight:600}
        .margem-pos{color:#4ade80;font-weight:700}.margem-neg{color:#f87171;font-weight:700}.margem-zero{color:#8b92a5}
        .margem-warn{color:#fbbf24;font-weight:600}
        
        .viavel-sim{background:#059669;color:#fff;padding:2px 7px;border-radius:10px;font-size:.67rem;font-weight:700}
        .viavel-nao{background:#7f1d1d;color:#fca5a5;padding:2px 7px;border-radius:10px;font-size:.67rem}
        .viavel-pendente{background:#2d3452;color:#8b92a5;padding:2px 7px;border-radius:10px;font-size:.67rem}
        
        .inp{width:70px;padding:2px 5px;border:1px solid #2d3452;border-radius:3px;background:#0a0e27;color:#4ade80;font-size:.8rem;font-weight:600;text-align:right}
        .inp:focus{border-color:#667eea;outline:none;box-shadow:0 0 0 2px rgba(102,126,234,.3)}
        .inp-sm{width:50px;color:#8b92a5}
        .inp-xs{width:42px;color:#8b92a5}
        
        .toast{position:fixed;bottom:20px;right:20px;background:#059669;color:#fff;padding:10px 18px;border-radius:7px;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,.3);transform:translateY(100px);opacity:0;transition:all .3s;z-index:1000}
        .toast.show{transform:translateY(0);opacity:1}.toast.error{background:#dc2626}
        
        .total-info{margin-top:10px;color:#8b92a5;text-align:center;font-size:.8rem}
        .desc-col{max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .arq-col{max-width:120px;overflow:hidden;text-overflow:ellipsis;color:#8b92a5;font-size:.68rem}
        
        .config-bar{background:#1a1f3a;padding:8px 14px;border-radius:7px;margin-bottom:10px;border:1px solid #2d3452;display:flex;align-items:center;gap:15px;font-size:.82rem}
        .config-bar label{color:#8b92a5;font-size:.72rem;text-transform:uppercase}
        .config-bar input{width:60px;padding:4px;border:1px solid #2d3452;border-radius:4px;background:#0a0e27;color:#fbbf24;font-weight:700;text-align:center;font-size:.85rem}
        
        .pagination{display:flex;justify-content:center;gap:5px;margin-top:10px}
        .pagination a,.pagination span{padding:4px 9px;border-radius:4px;font-size:.78rem;text-decoration:none}
        .pagination a{background:#2d3452;color:#e4e6eb}.pagination a:hover{background:#3d4562}
        .pagination .current{background:#667eea;color:#fff;font-weight:700}
        
        @media(max-width:1400px){.stats{grid-template-columns:repeat(4,1fr)}.filter-row{grid-template-columns:repeat(4,1fr)}}
    </style>
</head>
<body>
<div class="container">
    <div class="header-row">
        <h1>📊 QUBO v3 — {{ stats.total }} Produtos</h1>
        <span style="color:#8b92a5;font-size:.75rem">👤 {{ usuario_nome }}</span>
        <div class="header-actions">
            <button class="btn btn-sm" onclick="abrirAlertaDiario()" style="background:#f59e0b;color:#000" title="Resumo diário: vendas, perguntas, estoque, concorrentes">🔔 Alerta Diário</button>
            <a href="/logout" class="btn btn-sm" style="background:#2d3452;color:#e4e6eb">Sair</a>
            <button class="btn btn-sm" onclick="abrirTendencias()" style="background:#ec4899;color:#fff">🔥 Tendências</button>
            <button class="btn btn-sm" onclick="abrirSaudeAnuncios()" style="background:#0284c7;color:#fff">🏥 Saúde</button>
            <button class="btn btn-sm" onclick="abrirAlertaDiario()" style="background:#f59e0b;color:#000">📊 Alerta Diário</button>
            <button class="btn btn-secondary btn-sm" onclick="mostrarModalProduto()">➕ Produto</button>
            <button class="btn btn-primary btn-sm" onclick="location.href='/processar'" style="background:#f59e0b">🚀 Processar PDFs</button>
            <button class="btn btn-primary btn-sm" onclick="abrirUploadPDF()" style="background:#7c3aed;color:#fff">📤 Enviar PDF</button>
            <button class="btn btn-sm" onclick="location.href='/ml-auth'" style="background:#2563eb;color:#fff">🔗 ML Auth</button>
            <button class="btn btn-sm" onclick="atualizarTaxasML()" style="background:#c084fc;color:#000" id="btnTaxas">📊 Atualizar Taxas ML</button>
            <a href="/exportar" class="btn btn-success btn-sm">📥 Exportar Excel</a>
            <a href="/escolhidos" class="btn btn-primary btn-sm">⭐ Escolhidos (<span id="escolhidosCount">{{ stats.escolhidos }}</span>)</a>
            <button class="btn btn-secondary btn-sm" onclick="recalcularTodos()">⚡ Recalcular Tudo</button>
            <button class="btn btn-success btn-sm" onclick="enviarEscolhidos()" id="btnEnviar" style="display:none">⭐ Enviar Selecionados</button>
        </div>
    </div>

    <!-- CONFIG GLOBAL -->
    <div class="config-bar">
        <div>
            <label>🏛️ Alíquota Imposto (%)</label>
            <input type="number" id="aliquotaGlobal" value="{{ aliquota_imposto_pct }}" step="0.1" min="0" max="30"
                   onchange="salvarAliquota(this.value)">
        </div>
        <div style="color:#8b92a5;font-size:.72rem">
            Mesmo campo da planilha oficial (aba Introdução). Aplica a todos os produtos ao recalcular.
        </div>
    </div>

    <!-- STATS -->
    <div class="stats">
        <div class="stat-card"><div class="stat-value">{{ stats.total }}</div><div class="stat-label">Total</div></div>
        <div class="stat-card"><div class="stat-value purple">{{ stats.fornecedores }}</div><div class="stat-label">Fornecedores</div></div>
        <div class="stat-card"><div class="stat-value green">{{ stats.com_preco_ml }}</div><div class="stat-label">Com Preço ML</div></div>
        <div class="stat-card"><div class="stat-value yellow">{{ stats.sem_preco_ml }}</div><div class="stat-label">Sem Preço ML</div></div>
        <div class="stat-card"><div class="stat-value green">{{ stats.viaveis }}</div><div class="stat-label">✅ Viáveis (≥20%)</div></div>
        <div class="stat-card"><div class="stat-value red">{{ stats.nao_viaveis }}</div><div class="stat-label">❌ Não Viáveis</div></div>
        <div class="stat-card"><div class="stat-value yellow">{{ stats.pendentes }}</div><div class="stat-label">⏳ Pendentes</div></div>
    </div>

    <!-- FILTROS -->
    <div class="filters">
        <form method="GET" action="/">
            <div class="filter-row">
                <div class="filter-group"><label>💰 Custo Min</label><input type="number" name="custo_min" step="0.01" value="{{ f.custo_min }}" placeholder="0"></div>
                <div class="filter-group"><label>💰 Custo Max</label><input type="number" name="custo_max" step="0.01" value="{{ f.custo_max }}" placeholder="999"></div>
                <div class="filter-group"><label>🏢 Fornecedor</label>
                    <select name="fornecedor"><option value="">Todos</option>
                    {% for fn in fornecedores %}<option value="{{ fn }}" {% if f.fornecedor==fn %}selected{% endif %}>{{ fn }}</option>{% endfor %}</select>
                </div>
                <div class="filter-group"><label>📦 Produto</label><input type="text" name="produto" value="{{ f.produto }}" placeholder="Nome..."></div>
                <div class="filter-group"><label>🔢 Código</label><input type="text" name="codigo" value="{{ f.codigo }}" placeholder="Cód..."></div>
                <div class="filter-group"><label>📊 Status</label>
                    <select name="viabilidade"><option value="">Todos</option>
                    <option value="viavel" {% if f.viabilidade=='viavel' %}selected{% endif %}>✅ Viáveis</option>
                    <option value="nao" {% if f.viabilidade=='nao' %}selected{% endif %}>❌ Não Viáveis</option>
                    <option value="pendente" {% if f.viabilidade=='pendente' %}selected{% endif %}>⏳ Pendentes</option>
                    <option value="com_preco" {% if f.viabilidade=='com_preco' %}selected{% endif %}>💰 Com Preço</option></select>
                </div>
                <div class="filter-group"><label>📄 /Pág</label>
                    <select name="pp"><option value="100" {% if f.pp==100 %}selected{% endif %}>100</option>
                    <option value="250" {% if f.pp==250 %}selected{% endif %}>250</option>
                    <option value="500" {% if f.pp==500 %}selected{% endif %}>500</option></select>
                </div>
                <div class="filter-group" style="display:flex;align-items:end;gap:5px;padding-bottom:1px">
                    <button type="submit" class="btn btn-primary">🔍</button>
                    <button type="button" onclick="window.location.href='/'" class="btn btn-secondary">🔄</button>
                </div>
            </div>
        </form>
    </div>

    <!-- TABELA -->
    {% if produtos %}
    <div class="table-wrapper">
    <table>
        <thead><tr>
            <th><input type="checkbox" id="selAll" onchange="toggleAll(this)"></th>
            <th>Cód</th><th>Fornec.</th><th>Produto</th><th>Custo</th>
            <th>Preço ML</th><th>Tipo</th><th>Taxa%</th><th>TxML R$</th><th>TxFixa</th>
            <th>Peso kg</th><th>Frete</th><th>Embal.</th><th>ADS R$</th><th>Imp.</th>
            <th>C.Total</th><th>Lucro</th><th>Margem%</th><th>Status</th>
            <th>ML</th><th>Pg</th><th>🗑️</th>
        </tr></thead>
        <tbody>
        {% for p in produtos %}
        <tr id="r-{{ p.id }}" {% if p.escolhido %}style="background:#1a2a1a"{% endif %}>
            <td><input type="checkbox" class="sel-cb" value="{{ p.id }}" onchange="toggleEnviarBtn()" {% if p.escolhido %}checked{% endif %}></td>
            <td class="codigo">{{ p.codigo or '-' }}</td>
            <td class="fornecedor">{{ p.fornecedor }}</td>
            <td class="desc-col" title="{{ p.descricao }}">{{ p.descricao }}</td>
            <td class="custo">{{ p.custo|br }}</td>
            <td><input class="inp" id="pml-{{ p.id }}" value="{{ '%.2f'|format(p.preco_ml) if p.preco_ml else '' }}" step="0.01" min="0" placeholder="0,00" data-id="{{ p.id }}" data-custo="{{ p.custo }}" onchange="salvar(this)" onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td><select class="inp inp-xs" id="tipo-{{ p.id }}" style="width:62px;color:#f093fb;font-size:.7rem;padding:2px" data-id="{{ p.id }}" onchange="salvar(document.getElementById('pml-{{ p.id }}'))">
                <option value="classico" {% if (p.tipo_anuncio or 'classico')=='classico' %}selected{% endif %}>CLS</option>
                <option value="premium" {% if p.tipo_anuncio=='premium' %}selected{% endif %}>PRM</option>
            </select></td>
            <td><input class="inp inp-xs" id="tx-{{ p.id }}" value="{{ '%.1f'|format(p.taxa_categoria*100) if p.taxa_categoria else '' }}" step="0.5" data-id="{{ p.id }}" onchange="salvar(document.getElementById('pml-{{ p.id }}'))" placeholder="0"></td>
            <td id="tml-{{ p.id }}" style="color:#8b92a5">{{ (p.preco_ml * p.taxa_categoria)|br if p.preco_ml and p.taxa_categoria else '-' }}</td>
            <td id="tfix-{{ p.id }}" style="color:#8b92a5">{{ (6.25 if p.preco_ml and p.preco_ml < 79 else 0)|br if p.preco_ml else '-' }}</td>
            <td><input class="inp inp-xs" id="peso-{{ p.id }}" value="{{ '%.2f'|format(p.peso_kg) if p.peso_kg else '' }}" step="0.01" data-id="{{ p.id }}" onchange="salvar(document.getElementById('pml-{{ p.id }}'))" placeholder="0"></td>
            <td id="fr-{{ p.id }}" style="color:#8b92a5">{{ (p.custo_frete or 0)|br if p.preco_ml else '-' }}</td>
            <td><input class="inp inp-xs" id="emb-{{ p.id }}" value="{{ '%.2f'|format(p.custo_embalagem) if p.custo_embalagem else '' }}" step="0.10" data-id="{{ p.id }}" onchange="salvar(document.getElementById('pml-{{ p.id }}'))" placeholder="0"></td>
            <td><input class="inp inp-xs" id="ads-{{ p.id }}" value="{{ '%.2f'|format(p.custo_ads) if p.custo_ads else '' }}" step="0.50" data-id="{{ p.id }}" onchange="salvar(document.getElementById('pml-{{ p.id }}'))" placeholder="0" style="color:#f59e0b"></td>
            <td id="imp-{{ p.id }}" style="color:#8b92a5">{{ (p.imposto_valor or 0)|br if p.preco_ml else '-' }}</td>
            <td id="ct-{{ p.id }}" style="font-weight:600;color:#fbbf24">{{ (p.custo_total or 0)|br if p.preco_ml else '-' }}</td>
            <td id="luc-{{ p.id }}" class="{% if p.margem_reais and p.margem_reais > 0 %}margem-pos{% elif p.preco_ml and p.preco_ml > 0 %}margem-neg{% else %}margem-zero{% endif %}">{{ p.margem_reais|br if p.preco_ml and p.preco_ml > 0 else '-' }}</td>
            <td id="mg-{{ p.id }}" class="{% if p.margem_percentual and p.margem_percentual >= 20 %}margem-pos{% elif p.margem_percentual and p.margem_percentual > 0 %}margem-warn{% elif p.preco_ml and p.preco_ml > 0 %}margem-neg{% else %}margem-zero{% endif %}">{{ p.margem_percentual|br(1) if p.preco_ml and p.preco_ml > 0 else '-' }}{% if p.preco_ml and p.preco_ml > 0 %}%{% endif %}</td>
            <td id="st-{{ p.id }}">{% if p.preco_ml and p.preco_ml > 0 %}{% if p.viavel %}<span class="viavel-sim">VIÁVEL</span>{% else %}<span class="viavel-nao">NÃO</span>{% endif %}{% else %}<span class="viavel-pendente">—</span>{% endif %}</td>
            <td style="display:flex;gap:3px">
                <button class="btn btn-primary btn-sm" data-id="{{ p.id }}" data-desc="{{ p.descricao|e }}" onclick="buscarML(this.dataset.id, this.dataset.desc)" title="Buscar preço médio no ML">🔍</button>
                <button class="btn btn-sm" style="background:#7c3aed;color:#fff" data-id="{{ p.id }}" onclick="pesquisarProduto({{ p.id }})" title="Agente: análise de mercado">🤖</button>
                <button class="btn btn-sm" style="background:#059669;color:#fff" data-id="{{ p.id }}" onclick="precificarProduto({{ p.id }})" title="Agente: precificação inteligente">💰</button>
                <button class="btn btn-sm" style="background:#0891b2;color:#fff" data-id="{{ p.id }}" data-desc="{{ p.descricao|e }}" data-custo="{{ p.custo }}" data-peso="{{ p.peso_kg or 0 }}" data-emb="{{ p.custo_embalagem or 0 }}" onclick="analisarViabilidade(this)" title="Agente: viabilidade de produto">📈</button>
            </td>
            <td style="color:#fbbf24">{{ p.pagina_origem or '-' }}</td>
            <td><button class="btn btn-sm" style="background:#7f1d1d;color:#fca5a5;padding:2px 6px;font-size:.65rem" onclick="deletarProduto({{ p.id }})" title="Deletar">🗑️</button></td>
        </tr>
        {% endfor %}
        </tbody>
    </table>
    </div>
    {% if total_paginas > 1 %}
    <div class="pagination">
        {% if pg > 1 %}<a href="{{ url_pg(pg-1) }}">←</a>{% endif %}
        {% for p in range(1, total_paginas+1) %}
            {% if p == pg %}<span class="current">{{ p }}</span>
            {% elif p<=2 or p>=total_paginas-1 or (p>=pg-2 and p<=pg+2) %}<a href="{{ url_pg(p) }}">{{ p }}</a>
            {% elif p==3 or p==total_paginas-2 %}<span style="color:#8b92a5">…</span>{% endif %}
        {% endfor %}
        {% if pg < total_paginas %}<a href="{{ url_pg(pg+1) }}">→</a>{% endif %}
    </div>
    {% endif %}
    <div class="total-info">{{ produtos|length }} de {{ stats.total_filtrado }} filtrados ({{ stats.total }} total) — Pág {{ pg }}/{{ total_paginas }}</div>
    {% else %}
    <div style="text-align:center;padding:40px;color:#8b92a5">📭 Nenhum produto encontrado</div>
    {% endif %}
</div>

<div class="toast" id="toast"></div>

<script>
function fmt(v,d){return v.toFixed(d||2).replace('.',',')}

function salvar(el){
    const id=el.dataset.id;
    const custo=parseFloat(el.dataset.custo)||0;
    const pml=parseFloat(document.getElementById('pml-'+id).value)||0;
    const tipo=document.getElementById('tipo-'+id).value;
    const taxa=(parseFloat(document.getElementById('tx-'+id).value)||0)/100;
    const peso=parseFloat(document.getElementById('peso-'+id).value)||0;
    const emb=parseFloat(document.getElementById('emb-'+id).value)||0;
    const ads=parseFloat(document.getElementById('ads-'+id).value)||0;
    const aliq=(parseFloat(document.getElementById('aliquotaGlobal').value)||0)/100;
    
    fetch('/api/atualizar',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:parseInt(id),preco_ml:pml,tipo_anuncio:tipo,taxa_categoria:taxa,peso_kg:peso,custo_embalagem:emb,custo_ads:ads,aliquota_imposto:aliq})
    }).then(r=>r.json()).then(d=>{
        if(d.ok){
            document.getElementById('tml-'+id).textContent=fmt(d.taxa_ml_valor);
            document.getElementById('tfix-'+id).textContent=fmt(d.taxa_fixa);
            document.getElementById('fr-'+id).textContent=fmt(d.custo_frete);
            document.getElementById('imp-'+id).textContent=fmt(d.imposto_valor);
            document.getElementById('ct-'+id).textContent=fmt(d.custo_total);
            document.getElementById('luc-'+id).textContent=fmt(d.margem_reais);
            document.getElementById('luc-'+id).className=d.margem_reais>0?'margem-pos':'margem-neg';
            document.getElementById('mg-'+id).textContent=fmt(d.margem_percentual,1)+'%';
            document.getElementById('mg-'+id).className=d.margem_percentual>=20?'margem-pos':d.margem_percentual>0?'margem-warn':'margem-neg';
            document.getElementById('st-'+id).innerHTML=d.viavel?'<span class="viavel-sim">VIÁVEL</span>':'<span class="viavel-nao">NÃO</span>';
            showToast('✅ '+d.desc.substring(0,25));
        } else showToast('❌ '+d.erro,true);
    }).catch(()=>showToast('❌ Erro conexão',true));
}

function limparTermo(desc){
    let t = desc.toUpperCase();
    // Remove medidas (ex: 50mm, 1.5kg)
    t = t.replace(/[0-9]+[.,]?[0-9]*(MM|CM|M|KG|G|ML|L|UN|PCS|PC|UND)/gi, '');
    // Remove dimensões (ex: 50x780)
    t = t.replace(/[0-9]+[Xx][0-9]+/g, '');
    // Remove números 2+ dígitos
    t = t.replace(/[0-9][0-9]+/g, '');
    // Remove palavras comuns
    t = t.replace(/(COM|PARA|POR|SEM|DOS|DAS|DEL|UMA|UNS|NAS|NOS|TIPO|REF|COD|MODELO|UNID|COR|TAM)/gi, '');
    // Remove símbolos
    t = t.replace(/[+*(){}#@&%$!;:='",-]+/g, ' ');
    t = t.replace(/  +/g, ' ').trim();
    let palavras = t.split(' ').filter(function(p){return p.length >= 3});
    if(palavras.length > 5) palavras = palavras.slice(0, 5);
    return palavras.join(' ');
}

function buscarML(id,desc){
    const termoLimpo = limparTermo(desc);
    const termo = prompt('Buscar no Mercado Livre - Edite o termo se necessario:', termoLimpo);
    if(!termo || !termo.trim()) return;
    
    const btn=event.target;btn.disabled=true;btn.textContent='...';
    fetch('/api/buscar-ml',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,termo:termo.trim()})})
    .then(r=>r.json()).then(d=>{
        btn.disabled=false;btn.textContent='🔍';
        if(d.ok){
            document.getElementById('pml-'+id).value=d.preco_medio.toFixed(2);
            if(d.taxa_percentual){
                document.getElementById('tx-'+id).value=d.taxa_percentual.toFixed(1);
                showToast('ML: R$'+fmt(d.preco_medio)+' | Taxa: '+fmt(d.taxa_percentual,1)+'% ('+d.total+' result.)');
            } else {
                showToast('ML: R$'+fmt(d.preco_medio)+' ('+d.total+' result.) - Taxa nao encontrada');
            }
            salvar(document.getElementById('pml-'+id));
        } else showToast(d.erro||'Nao encontrado',true);
    }).catch(()=>{btn.disabled=false;btn.textContent='🔍';showToast('Erro conexao',true);});
}

function recalcularTodos(){
    if(!confirm('Recalcular TODOS com preço ML?'))return;
    fetch('/api/recalcular-todos',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({aliquota:(parseFloat(document.getElementById('aliquotaGlobal').value)||0)/100})
    }).then(r=>r.json()).then(d=>{showToast('✅ '+d.atualizados+' recalculados');setTimeout(()=>location.reload(),800);})
    .catch(()=>showToast('❌ Erro',true));
}

function salvarAliquota(v){
    fetch('/api/aliquota',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({aliquota:parseFloat(v)||0})})
    .then(r=>r.json()).then(d=>{if(d.ok)showToast('✅ Alíquota: '+v+'%');});
}

function toggleAll(el){document.querySelectorAll('.sel-cb').forEach(cb=>{cb.checked=el.checked});toggleEnviarBtn()}
function toggleEnviarBtn(){const n=document.querySelectorAll('.sel-cb:checked').length;document.getElementById('btnEnviar').style.display=n>0?'inline-block':'none';document.getElementById('btnEnviar').textContent='⭐ Enviar '+n+' Selecionados'}
function enviarEscolhidos(){
    const ids=[...document.querySelectorAll('.sel-cb:checked')].map(cb=>parseInt(cb.value));
    if(!ids.length)return;
    fetch('/api/escolher',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:ids})})
    .then(r=>r.json()).then(d=>{
        if(d.ok){showToast('⭐ '+d.total+' produtos enviados para Escolhidos');
            document.getElementById('escolhidosCount').textContent=d.total_escolhidos;
            ids.forEach(id=>{const r=document.getElementById('r-'+id);if(r)r.style.background='#1a2a1a'});
        }else showToast('❌ '+d.erro,true);
    });
}

function deletarProduto(id){
    if(!confirm('Tem certeza que deseja DELETAR este produto?'))return;
    fetch('/api/deletar-produto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})})
    .then(r=>r.json()).then(d=>{
        if(d.ok){
            const row=document.getElementById('r-'+id);
            if(row)row.remove();
            showToast('🗑️ Produto deletado');
        } else showToast('❌ '+d.erro,true);
    });
}

function atualizarTaxasML(){
    if(!confirm('Buscar taxa ML real para TODOS os produtos? Isso pode demorar alguns minutos. Produtos sem resultado mantêm a taxa atual.'))return;
    const btn=document.getElementById('btnTaxas');
    btn.disabled=true;btn.textContent='⏳ Buscando taxas...';
    fetch('/api/atualizar-taxas-ml',{method:'POST'})
    .then(r=>r.json()).then(d=>{
        btn.disabled=false;btn.textContent='📊 Atualizar Taxas ML';
        if(d.ok){
            showToast('✅ '+d.atualizados+'/'+d.total+' taxas atualizadas!');
            setTimeout(()=>location.reload(),1000);
        } else showToast('❌ '+d.erro,true);
    }).catch(()=>{btn.disabled=false;btn.textContent='📊 Atualizar Taxas ML';showToast('❌ Erro',true);});
}

function abrirAlertaDiario(){
    // Abre modal de loading imediatamente
    const loadingHtml = `<div id="modalAlerta" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.85);display:flex;justify-content:center;align-items:center;z-index:9999;padding:20px">
    <div style="background:#1a1f3a;padding:24px;border-radius:10px;border:1px solid #f59e0b;width:860px;max-width:95vw;max-height:90vh;overflow-y:auto">
        <div style="text-align:center;padding:30px;color:#f59e0b">
            <div style="font-size:2rem;margin-bottom:12px">🔔</div>
            <div style="font-size:1.1rem;font-weight:700">Gerando Alerta Diário...</div>
            <div style="color:#8b92a5;font-size:.85rem;margin-top:8px">Buscando vendas, perguntas, estoque e concorrentes no ML</div>
        </div>
    </div></div>`;
    document.getElementById('modalAlerta')?.remove();
    document.body.insertAdjacentHTML('beforeend', loadingHtml);

    // Pega top 3 produtos do dashboard como termos de monitoramento
    const termos = [...document.querySelectorAll('.desc-col')].slice(0,3).map(el => el.title || el.textContent.trim()).filter(Boolean);

    fetch('/api/alerta-diario', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({termos})
    })
    .then(r => r.json())
    .then(d => {
        document.getElementById('modalAlerta')?.remove();
        if(!d.ok){showToast('❌ '+d.erro, true); return;}
        mostrarModalAlerta(d);
    })
    .catch(() => {
        document.getElementById('modalAlerta')?.remove();
        showToast('❌ Erro ao gerar alerta', true);
    });
}

function mostrarModalAlerta(d){
    const fmt = (v, dec=2) => v != null ? parseFloat(v).toFixed(dec).replace('.',',') : '-';
    const v = d.vendas || {};
    const p = d.perguntas || {};
    const r = d.reputacao || {};
    const eb = d.estoque_baixo || [];
    const pc = d.precos_concorrentes || [];

    // Perguntas pendentes
    const perguntasHtml = p.total > 0
        ? `<div style="margin-top:6px">${(p.exemplos||[]).map(q =>
            `<div style="padding:5px 8px;background:#0a0e27;border-radius:4px;margin-bottom:4px;font-size:.78rem">
                <span style="color:#8b92a5">${q.data}</span>
                <span style="color:#e4e6eb;margin-left:8px">${q.texto}...</span>
                <a href="https://www.mercadolivre.com.br/perguntas" target="_blank" style="color:#667eea;margin-left:8px;font-size:.72rem">Responder ↗</a>
            </div>`).join('')}
          </div>`
        : `<div style="color:#4ade80;font-size:.85rem;margin-top:6px">✅ Nenhuma pergunta pendente!</div>`;

    // Estoque baixo
    const estoqueHtml = eb.length > 0
        ? eb.map(e => `<div style="padding:5px 8px;background:#450a0a;border-radius:4px;margin-bottom:4px;font-size:.78rem;display:flex;justify-content:space-between">
            <span style="color:#fca5a5">${e.titulo}</span>
            <span style="color:#f87171;font-weight:700">${e.estoque} un.</span>
          </div>`).join('')
        : `<div style="color:#4ade80;font-size:.85rem">✅ Estoque OK em todos os produtos!</div>`;

    // Preços concorrentes
    const precosHtml = pc.length > 0
        ? `<table style="width:100%;border-collapse:collapse;font-size:.78rem;margin-top:8px">
            <thead><tr>
                <th style="text-align:left;padding:4px 8px;color:#8b92a5;border-bottom:1px solid #2d3452">Produto</th>
                <th style="text-align:right;padding:4px 8px;color:#8b92a5;border-bottom:1px solid #2d3452">Mín</th>
                <th style="text-align:right;padding:4px 8px;color:#8b92a5;border-bottom:1px solid #2d3452">Médio</th>
                <th style="text-align:right;padding:4px 8px;color:#8b92a5;border-bottom:1px solid #2d3452">Máx</th>
                <th style="text-align:right;padding:4px 8px;color:#8b92a5;border-bottom:1px solid #2d3452">Anúncios</th>
            </tr></thead>
            <tbody>${pc.map(c => `<tr style="border-bottom:1px solid #1a1f3a">
                <td style="padding:4px 8px;color:#e4e6eb">${c.termo}</td>
                <td style="padding:4px 8px;text-align:right;color:#f87171">R$ ${fmt(c.preco_min)}</td>
                <td style="padding:4px 8px;text-align:right;color:#fbbf24">R$ ${fmt(c.preco_medio)}</td>
                <td style="padding:4px 8px;text-align:right;color:#4ade80">R$ ${fmt(c.preco_max)}</td>
                <td style="padding:4px 8px;text-align:right;color:#8b92a5">${(c.total_anuncios||0).toLocaleString('pt-BR')}</td>
            </tr>`).join('')}</tbody>
          </table>`
        : `<div style="color:#8b92a5;font-size:.85rem">Nenhum produto monitorado.</div>`;

    const corRep = r.nivel?.includes('Verde') ? '#4ade80' : r.nivel?.includes('Amarelo') ? '#fbbf24' : '#f87171';

    const h = `<div id="modalAlerta" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.85);display:flex;justify-content:center;align-items:center;z-index:9999;padding:20px">
    <div style="background:#1a1f3a;padding:20px;border-radius:10px;border:1px solid #f59e0b;width:860px;max-width:95vw;max-height:90vh;overflow-y:auto">

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
            <div>
                <h3 style="color:#f59e0b;margin-bottom:2px">🔔 Alerta Diário QUBO</h3>
                <div style="color:#8b92a5;font-size:.75rem">Gerado em ${d.gerado_em} · ${d.tempo_segundos}s</div>
            </div>
            <button onclick="document.getElementById('modalAlerta').remove()" style="background:#2d3452;color:#e4e6eb;border:none;border-radius:5px;padding:6px 12px;cursor:pointer">✕ Fechar</button>
        </div>

        <!-- Vendas -->
        <div style="margin-bottom:14px">
            <div style="color:#8b92a5;font-size:.72rem;text-transform:uppercase;margin-bottom:8px">📦 Vendas</div>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">
                <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                    <div style="font-size:1.4rem;font-weight:700;color:#4ade80">${v.vendas_24h||0}</div>
                    <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase">Pedidos 24h</div>
                </div>
                <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                    <div style="font-size:1.4rem;font-weight:700;color:#4ade80">R$ ${fmt(v.valor_24h)}</div>
                    <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase">Faturamento 24h</div>
                </div>
                <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                    <div style="font-size:1.4rem;font-weight:700;color:#fbbf24">${v.vendas_7d||0}</div>
                    <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase">Pedidos 7 dias</div>
                </div>
                <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                    <div style="font-size:1.4rem;font-weight:700;color:#fbbf24">R$ ${fmt(v.valor_7d)}</div>
                    <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase">Faturamento 7d</div>
                </div>
            </div>
        </div>

        <!-- Reputação + Perguntas -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px">
            <div style="background:#0a0e27;padding:12px;border-radius:6px">
                <div style="color:#8b92a5;font-size:.72rem;text-transform:uppercase;margin-bottom:8px">⭐ Reputação</div>
                <div style="font-size:1.1rem;font-weight:700;color:${corRep}">${r.nivel||'—'}</div>
                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px">
                    <div style="text-align:center">
                        <div style="font-size:.9rem;font-weight:700;color:#4ade80">${r.vendas_concluidas||0}</div>
                        <div style="font-size:.62rem;color:#8b92a5">Vendas</div>
                    </div>
                    <div style="text-align:center">
                        <div style="font-size:.9rem;font-weight:700;color:${(r.reclamacoes_pct||0)>0.02?'#f87171':'#4ade80'}">${fmt(r.reclamacoes_pct*100||0,1)}%</div>
                        <div style="font-size:.62rem;color:#8b92a5">Reclamações</div>
                    </div>
                    <div style="text-align:center">
                        <div style="font-size:.9rem;font-weight:700;color:${(r.cancelamentos_pct||0)>0.02?'#f87171':'#4ade80'}">${fmt(r.cancelamentos_pct*100||0,1)}%</div>
                        <div style="font-size:.62rem;color:#8b92a5">Cancelamentos</div>
                    </div>
                </div>
            </div>
            <div style="background:#0a0e27;padding:12px;border-radius:6px">
                <div style="color:#8b92a5;font-size:.72rem;text-transform:uppercase;margin-bottom:4px">
                    💬 Perguntas Pendentes
                    ${p.total>0 ? `<span style="background:#f87171;color:#fff;padding:1px 7px;border-radius:10px;margin-left:6px;font-size:.7rem">${p.total}</span>` : ''}
                </div>
                ${perguntasHtml}
            </div>
        </div>

        <!-- Estoque Baixo -->
        <div style="margin-bottom:14px">
            <div style="color:#8b92a5;font-size:.72rem;text-transform:uppercase;margin-bottom:8px">
                📉 Estoque Baixo (≤ 3 unidades)
                ${eb.length>0 ? `<span style="background:#f59e0b;color:#000;padding:1px 7px;border-radius:10px;margin-left:6px;font-size:.7rem">${eb.length} produto(s)</span>` : ''}
            </div>
            ${estoqueHtml}
        </div>

        <!-- Preços Concorrentes -->
        <div>
            <div style="color:#8b92a5;font-size:.72rem;text-transform:uppercase;margin-bottom:4px">📊 Preços Concorrentes</div>
            ${precosHtml}
        </div>

    </div></div>`;

    document.getElementById('modalAlerta')?.remove();
    document.body.insertAdjacentHTML('beforeend', h);
}


    showToast('🤖 Analisando mercado...');
    fetch('/api/pesquisar-produto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})})
    .then(r=>r.json()).then(d=>{
        if(!d.ok){showToast('❌ '+d.erro,true);return;}
        mostrarModalPesquisa(d);
    }).catch(()=>showToast('❌ Erro conexão',true));
}

function mostrarModalPesquisa(d){
    const cor = (m) => m===null ? '#8b92a5' : m>=20 ? '#4ade80' : m>=10 ? '#fbbf24' : '#f87171';
    const fmt = (v,dec=2) => v!=null ? v.toFixed(dec).replace('.',',') : '-';
    
    const topAnuncios = (d.top_anuncios||[]).map((a,i)=>`
        <tr style="border-bottom:1px solid #1a1f3a">
            <td style="padding:4px 8px;color:#8b92a5">${i+1}</td>
            <td style="padding:4px 8px;color:#e4e6eb;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${a.titulo}">${a.titulo}</td>
            <td style="padding:4px 8px;color:#4ade80;font-weight:700">R$ ${fmt(a.preco)}</td>
            <td style="padding:4px 8px;color:#fbbf24">${a.vendas.toLocaleString('pt-BR')}</td>
            <td style="padding:4px 8px;color:#f093fb;font-size:.75rem">${a.vendedor}</td>
            <td style="padding:4px 8px"><a href="${a.link}" target="_blank" style="color:#667eea;font-size:.75rem">Ver ↗</a></td>
        </tr>`).join('');
    
    const margemBox = d.custo > 0 ? `
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px">
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase;margin-bottom:4px">Margem no mínimo</div>
                <div style="font-size:1.1rem;font-weight:700;color:${cor(d.margem_no_minimo)}">${fmt(d.margem_no_minimo,1)}%</div>
                <div style="font-size:.7rem;color:#8b92a5">R$ ${fmt(d.preco_min)}</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase;margin-bottom:4px">Margem no mediano</div>
                <div style="font-size:1.1rem;font-weight:700;color:${cor(d.margem_no_mediano)}">${fmt(d.margem_no_mediano,1)}%</div>
                <div style="font-size:.7rem;color:#8b92a5">R$ ${fmt(d.preco_mediano)}</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase;margin-bottom:4px">Preço p/ 25% marg.</div>
                <div style="font-size:1.1rem;font-weight:700;color:#667eea">R$ ${fmt(d.preco_sugerido_25pct)}</div>
                <div style="font-size:.7rem;color:#8b92a5">Custo: R$ ${fmt(d.custo)}</div>
            </div>
        </div>` : `<div style="color:#8b92a5;font-size:.8rem;margin-top:8px">⚠️ Cadastre o custo do produto para ver análise de margem.</div>`;
    
    const h = `<div id="modalPesquisa" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);display:flex;justify-content:center;align-items:center;z-index:9999;padding:20px">
    <div style="background:#1a1f3a;padding:20px;border-radius:10px;border:1px solid #7c3aed;width:800px;max-width:95vw;max-height:90vh;overflow-y:auto">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px">
            <div>
                <h3 style="color:#7c3aed;margin-bottom:4px">🤖 Análise de Mercado ML</h3>
                <div style="color:#e4e6eb;font-size:.85rem">${d.produto_nome}</div>
                <div style="color:#8b92a5;font-size:.75rem">Termo buscado: "${d.termo_buscado}" · ${d.total_anuncios_ml.toLocaleString('pt-BR')} anúncios no ML</div>
            </div>
            <button onclick="document.getElementById('modalPesquisa').remove()" style="background:#2d3452;color:#e4e6eb;border:none;border-radius:5px;padding:6px 12px;cursor:pointer;font-size:.85rem">✕ Fechar</button>
        </div>
        
        <!-- Resumo de preços -->
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px">
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase;margin-bottom:4px">Mínimo</div>
                <div style="font-size:1.2rem;font-weight:700;color:#f87171">R$ ${fmt(d.preco_min)}</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase;margin-bottom:4px">Mediano</div>
                <div style="font-size:1.2rem;font-weight:700;color:#4ade80">R$ ${fmt(d.preco_mediano)}</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase;margin-bottom:4px">Médio</div>
                <div style="font-size:1.2rem;font-weight:700;color:#fbbf24">R$ ${fmt(d.preco_medio)}</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase;margin-bottom:4px">Máximo</div>
                <div style="font-size:1.2rem;font-weight:700;color:#c084fc">R$ ${fmt(d.preco_max)}</div>
            </div>
        </div>
        
        <!-- Vendas e taxa -->
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px">
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase;margin-bottom:4px">Total vendas (top 20)</div>
                <div style="font-size:1.2rem;font-weight:700;color:#4ade80">${(d.vendas_totais_top20||0).toLocaleString('pt-BR')}</div>
                <div style="font-size:.7rem;color:#8b92a5">unidades acumuladas</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase;margin-bottom:4px">Média p/ anúncio</div>
                <div style="font-size:1.2rem;font-weight:700;color:#fbbf24">${(d.media_vendas_por_anuncio||0).toLocaleString('pt-BR')}</div>
                <div style="font-size:.7rem;color:#8b92a5">unidades acumuladas</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.65rem;color:#8b92a5;text-transform:uppercase;margin-bottom:4px">Taxa ML (categoria)</div>
                <div style="font-size:1.2rem;font-weight:700;color:#f093fb">${fmt(d.taxa_percentual,1)}%</div>
                <div style="font-size:.7rem;color:#8b92a5">${d.categoria_id||'—'}</div>
            </div>
        </div>
        
        <!-- Análise de margem -->
        ${margemBox}
        
        <!-- Top anúncios -->
        <div style="margin-top:14px">
            <div style="color:#8b92a5;font-size:.72rem;text-transform:uppercase;margin-bottom:6px">Top Anúncios por Vendas</div>
            <div style="overflow-x:auto;border-radius:5px">
            <table style="width:100%;border-collapse:collapse;background:#0a0e27;font-size:.78rem">
                <thead><tr style="border-bottom:1px solid #2d3452">
                    <th style="padding:5px 8px;text-align:left;color:#8b92a5">#</th>
                    <th style="padding:5px 8px;text-align:left;color:#8b92a5">Título</th>
                    <th style="padding:5px 8px;text-align:left;color:#8b92a5">Preço</th>
                    <th style="padding:5px 8px;text-align:left;color:#8b92a5">Vendas</th>
                    <th style="padding:5px 8px;text-align:left;color:#8b92a5">Vendedor</th>
                    <th style="padding:5px 8px;text-align:left;color:#8b92a5">Link</th>
                </tr></thead>
                <tbody>${topAnuncios}</tbody>
            </table>
            </div>
        </div>
        
        <!-- Ação rápida -->
        <div style="margin-top:14px;display:flex;gap:8px;justify-content:flex-end">
            <button onclick="usarPrecoMediano(${d.produto_id}, ${d.preco_mediano}, ${d.taxa_percentual})" 
                style="padding:8px 16px;border:none;border-radius:5px;background:#4ade80;color:#000;font-weight:700;cursor:pointer">
                💰 Usar preço mediano (R$ ${fmt(d.preco_mediano)})
            </button>
        </div>
    </div></div>`;
    
    document.getElementById('modalPesquisa')?.remove();
    document.body.insertAdjacentHTML('beforeend', h);
}





function abrirUploadPDF(){
    const h=`<div id="modalUpload" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);display:flex;justify-content:center;align-items:center;z-index:9999;padding:20px">
    <div style="background:#1a1f3a;padding:24px;border-radius:10px;border:1px solid #7c3aed;width:480px;max-width:95vw">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
            <h3 style="color:#7c3aed">📤 Enviar Catálogo PDF</h3>
            <button onclick="document.getElementById('modalUpload').remove()" style="background:#2d3452;color:#e4e6eb;border:none;border-radius:5px;padding:4px 10px;cursor:pointer">✕</button>
        </div>
        <div style="background:#0a0e27;border:2px dashed #2d3452;border-radius:8px;padding:24px;text-align:center;margin-bottom:16px;cursor:pointer" 
             onclick="document.getElementById('pdfInput').click()"
             ondragover="event.preventDefault();this.style.borderColor='#7c3aed'"
             ondragleave="this.style.borderColor='#2d3452'"
             ondrop="event.preventDefault();handleDrop(event)">
            <div style="font-size:2.5rem;margin-bottom:8px">📄</div>
            <div style="color:#e4e6eb;font-weight:600">Clique para selecionar ou arraste o PDF aqui</div>
            <div style="color:#8b92a5;font-size:.78rem;margin-top:4px">O nome do arquivo será usado como nome do fornecedor</div>
        </div>
        <input type="file" id="pdfInput" accept=".pdf" style="display:none" onchange="uploadPDF(this.files[0])">
        <div id="uploadStatus" style="display:none;background:#0a0e27;border-radius:6px;padding:12px;font-size:.83rem">
            <div id="uploadMsg" style="color:#fbbf24">⏳ Processando...</div>
            <div id="uploadBar" style="height:4px;background:#667eea;border-radius:2px;width:0%;margin-top:8px;transition:width .5s"></div>
        </div>
    </div></div>`;
    document.getElementById('modalUpload')?.remove();
    document.body.insertAdjacentHTML('beforeend',h);
}

function handleDrop(e){
    const file=e.dataTransfer.files[0];
    if(file&&file.name.toLowerCase().endsWith('.pdf')) uploadPDF(file);
    else showToast('❌ Apenas arquivos PDF',true);
}

function uploadPDF(file){
    if(!file) return;
    document.getElementById('uploadStatus').style.display='block';
    document.getElementById('uploadMsg').innerHTML='⏳ Enviando <strong>'+file.name+'</strong>...';
    document.getElementById('uploadBar').style.width='30%';
    
    const fd=new FormData();
    fd.append('arquivo',file);
    
    fetch('/api/upload-pdf',{method:'POST',body:fd})
    .then(r=>r.json()).then(d=>{
        document.getElementById('uploadBar').style.width='100%';
        if(d.ok){
            document.getElementById('uploadMsg').innerHTML=
                '✅ <strong>'+d.arquivo+'</strong> — '+d.produtos_extraidos+' produtos extraídos via '+d.provider+'!';
            document.getElementById('uploadMsg').style.color='#4ade80';
            setTimeout(()=>{
                document.getElementById('modalUpload')?.remove();
                location.reload();
            },2000);
        } else {
            document.getElementById('uploadMsg').innerHTML='❌ '+d.erro;
            document.getElementById('uploadMsg').style.color='#f87171';
            document.getElementById('uploadBar').style.background='#f87171';
        }
    }).catch(()=>{
        document.getElementById('uploadMsg').innerHTML='❌ Erro de conexão';
        document.getElementById('uploadMsg').style.color='#f87171';
    });
}

function abrirTendencias(){
    showToast('🔥 Buscando tendências do ML...');
    fetch('/api/tendencias')
    .then(r=>r.json()).then(d=>{
        if(!d.ok){showToast('❌ '+d.erro,true);return;}
        mostrarModalTendencias(d);
    }).catch(()=>showToast('❌ Erro conexão',true));
}

function mostrarModalTendencias(d){
    const fmt=(v,dec=2)=>v!=null?parseFloat(v).toFixed(dec).replace('.',','):'-';
    const linhas=(d.tendencias||[]).map((t,i)=>{
        const op=t.oportunidade||{};
        const jaTemBadge=t.ja_tenho_no_catalogo
            ?'<span style="background:#065f46;color:#4ade80;padding:1px 6px;border-radius:8px;font-size:.63rem;margin-left:4px">✅ Tenho</span>':'';
        return `<tr style="border-bottom:1px solid #1a1f3a;${t.ja_tenho_no_catalogo?'background:#0a1a0a':''}">
            <td style="padding:5px 8px;color:#8b92a5;font-weight:700">${i+1}</td>
            <td style="padding:5px 8px;color:#e4e6eb;font-weight:600">${t.keyword}${jaTemBadge}</td>
            <td style="padding:5px 8px;color:#4ade80">${t.preco_min?'R$ '+fmt(t.preco_min):'-'}</td>
            <td style="padding:5px 8px;color:#fbbf24">${t.preco_medio?'R$ '+fmt(t.preco_medio):'-'}</td>
            <td style="padding:5px 8px;color:#c084fc">${t.vendas_acum_top5?parseInt(t.vendas_acum_top5).toLocaleString('pt-BR'):'-'}</td>
            <td style="padding:5px 8px">
                <span style="color:${op.cor||'#8b92a5'};font-size:.8rem">${op.icone||''} ${op.label||''}</span>
            </td>
            <td style="padding:5px 8px">
                <a href="${t.url_ml||'https://www.mercadolivre.com.br/'+encodeURIComponent(t.keyword)}" target="_blank"
                   style="color:#667eea;font-size:.75rem">Ver ↗</a>
            </td>
        </tr>`;
    }).join('');

    const tenhoCount=(d.tendencias||[]).filter(t=>t.ja_tenho_no_catalogo).length;
    const altaOp=(d.tendencias||[]).filter(t=>t.score>=50).length;

    const h=`<div id="modalTend" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);display:flex;justify-content:center;align-items:center;z-index:9999;padding:20px">
    <div style="background:#1a1f3a;padding:20px;border-radius:10px;border:1px solid #ec4899;width:900px;max-width:95vw;max-height:90vh;overflow-y:auto">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px">
            <div>
                <h3 style="color:#ec4899">🔥 Tendências do Mercado Livre</h3>
                <div style="color:#8b92a5;font-size:.75rem">${d.total} produtos em alta agora</div>
            </div>
            <button onclick="document.getElementById('modalTend').remove()" style="background:#2d3452;color:#e4e6eb;border:none;border-radius:5px;padding:5px 10px;cursor:pointer">✕</button>
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px">
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Tendências hoje</div>
                <div style="font-size:1.4rem;font-weight:700;color:#ec4899">${d.total}</div>
            </div>
            <div style="background:#0a1a0a;padding:10px;border-radius:6px;text-align:center;border:1px solid #065f46">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Você já tem</div>
                <div style="font-size:1.4rem;font-weight:700;color:#4ade80">${tenhoCount}</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Alta oportunidade</div>
                <div style="font-size:1.4rem;font-weight:700;color:#fbbf24">${altaOp}</div>
            </div>
        </div>
        <div style="overflow-x:auto;border-radius:5px">
        <table style="width:100%;border-collapse:collapse;background:#0a0e27;font-size:.8rem">
            <thead><tr style="border-bottom:1px solid #2d3452">
                <th style="padding:6px 8px;color:#8b92a5">#</th>
                <th style="padding:6px 8px;color:#8b92a5">Produto em Alta</th>
                <th style="padding:6px 8px;color:#8b92a5">Preço Min</th>
                <th style="padding:6px 8px;color:#8b92a5">Preço Médio</th>
                <th style="padding:6px 8px;color:#8b92a5">Vendas Top 5</th>
                <th style="padding:6px 8px;color:#8b92a5">Oportunidade</th>
                <th style="padding:6px 8px;color:#8b92a5">ML</th>
            </tr></thead>
            <tbody>${linhas}</tbody>
        </table>
        </div>
    </div></div>`;
    document.getElementById('modalTend')?.remove();
    document.body.insertAdjacentHTML('beforeend',h);
}

function abrirSaudeAnuncios(){
    showToast('🏥 Verificando saúde dos anúncios...');
    fetch('/api/saude-anuncios')
    .then(r=>r.json()).then(d=>{
        if(!d.ok){showToast('❌ '+d.erro,true);return;}
        mostrarModalSaude(d);
    }).catch(()=>showToast('❌ Erro conexão',true));
}

function mostrarModalSaude(d){
    const fmt=(v,dec=2)=>v!=null?parseFloat(v).toFixed(dec).replace('.',','):'-';
    const r=d.resumo||{};
    const scoreCor=d.score_saude>=90?'#4ade80':d.score_saude>=70?'#fbbf24':'#f87171';

    const renderLista=(lista,titulo,cor,icone)=>{
        if(!lista||lista.length===0)return'';
        const items=lista.map(a=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 10px;border-bottom:1px solid #1a1f3a;font-size:.8rem">
            <span style="color:#e4e6eb;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${a.titulo||a.id}</span>
            ${a.preco?'<span style="color:#4ade80">R$ '+fmt(a.preco)+'</span>':''}
            ${a.visitas_30d!=null?'<span style="color:#8b92a5">'+a.visitas_30d+' visitas/30d</span>':''}
            ${a.link?'<a href="'+a.link+'" target="_blank" style="color:#667eea;font-size:.72rem">Ver ↗</a>':''}
        </div>`).join('');
        return `<div style="margin-bottom:12px">
            <div style="color:${cor};font-weight:700;font-size:.82rem;margin-bottom:5px">${icone} ${titulo} (${lista.length})</div>
            <div style="background:#0a0e27;border-radius:6px;border:1px solid #2d3452">${items}</div>
        </div>`;
    };

    const anunciosHTML=(d.anuncios||[]).map(a=>`
        <tr style="border-bottom:1px solid #1a1f3a">
            <td style="padding:4px 7px;color:#e4e6eb;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.78rem">${a.titulo}</td>
            <td style="padding:4px 7px;color:#4ade80;font-weight:600">R$ ${fmt(a.preco)}</td>
            <td style="padding:4px 7px;color:#fbbf24">${a.visitas_30d||0}</td>
            <td style="padding:4px 7px;color:#c084fc">${a.sold_quantity||0}</td>
            <td style="padding:4px 7px;color:${a.conversao_pct>=2?'#4ade80':a.conversao_pct>=1?'#fbbf24':'#f87171'}">${a.conversao_pct||0}%</td>
            <td style="padding:4px 7px;color:#8b92a5">${a.estoque||0}</td>
            <td><a href="${a.link}" target="_blank" style="color:#667eea;font-size:.72rem">Ver ↗</a></td>
        </tr>`).join('');

    const h=`<div id="modalSaude" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);display:flex;justify-content:center;align-items:center;z-index:9999;padding:20px">
    <div style="background:#1a1f3a;padding:20px;border-radius:10px;border:1px solid #0284c7;width:900px;max-width:95vw;max-height:90vh;overflow-y:auto">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px">
            <div>
                <h3 style="color:#0284c7">🏥 Saúde dos Anúncios</h3>
                <div style="color:#8b92a5;font-size:.72rem">Gerado em ${d.gerado_em}</div>
            </div>
            <div style="text-align:center">
                <div style="font-size:2.2rem;font-weight:900;color:${scoreCor}">${d.score_saude}</div>
                <div style="font-size:.75rem;color:${scoreCor}">${d.classificacao_saude}</div>
            </div>
            <button onclick="document.getElementById('modalSaude').remove()" style="background:#2d3452;color:#e4e6eb;border:none;border-radius:5px;padding:5px 10px;cursor:pointer;align-self:flex-start">✕</button>
        </div>

        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px">
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Total anúncios</div>
                <div style="font-size:1.3rem;font-weight:700;color:#667eea">${r.total_anuncios||0}</div>
            </div>
            <div style="background:#064e3b;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Saudáveis</div>
                <div style="font-size:1.3rem;font-weight:700;color:#4ade80">${r.total_saudaveis||0}</div>
            </div>
            <div style="background:#3b2700;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Em risco</div>
                <div style="font-size:1.3rem;font-weight:700;color:#fbbf24">${r.total_warning||0}</div>
            </div>
            <div style="background:#450a0a;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Críticos</div>
                <div style="font-size:1.3rem;font-weight:700;color:#f87171">${r.total_unhealthy||0}</div>
            </div>
        </div>

        ${renderLista(d.unhealthy,'Anúncios Críticos — Perdendo Exposição','#f87171','🚨')}
        ${renderLista(d.warning,'Anúncios em Risco','#fbbf24','⚠️')}
        ${renderLista(d.sem_visitas,'Anúncios Ativos Sem Visitas (últimos 30 dias)','#8b92a5','👻')}

        ${anunciosHTML?`<div style="color:#8b92a5;font-size:.7rem;text-transform:uppercase;margin-bottom:5px;margin-top:10px">Detalhes — Top 10 Anúncios (Visitas 30d)</div>
        <table style="width:100%;border-collapse:collapse;background:#0a0e27;font-size:.77rem;border-radius:5px">
            <thead><tr style="border-bottom:1px solid #2d3452">
                <th style="padding:4px 7px;color:#8b92a5">Título</th>
                <th style="padding:4px 7px;color:#8b92a5">Preço</th>
                <th style="padding:4px 7px;color:#8b92a5">Visitas 30d</th>
                <th style="padding:4px 7px;color:#8b92a5">Vendas</th>
                <th style="padding:4px 7px;color:#8b92a5">Conversão</th>
                <th style="padding:4px 7px;color:#8b92a5">Estoque</th>
                <th style="padding:4px 7px;color:#8b92a5">Link</th>
            </tr></thead>
            <tbody>${anunciosHTML}</tbody>
        </table>`:''}
    </div></div>`;
    document.getElementById('modalSaude')?.remove();
    document.body.insertAdjacentHTML('beforeend',h);
}

function analisarViabilidade(btn){
    const id = btn.dataset.id;
    const desc = btn.dataset.desc;
    const custo = parseFloat(btn.dataset.custo)||0;
    const peso = parseFloat(btn.dataset.peso)||0;
    const emb = parseFloat(btn.dataset.emb)||0;
    const margem = parseFloat(prompt('Margem mínima desejada (%):', '20'))||20;
    showToast('📈 Analisando viabilidade...');
    fetch('/api/viabilidade',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:parseInt(id), termo:desc, custo, peso, embalagem:emb, margem_minima:margem})})
    .then(r=>r.json()).then(d=>{
        if(!d.ok){showToast('❌ '+d.erro,true);return;}
        mostrarModalViabilidade(d);
    }).catch(()=>showToast('❌ Erro conexão',true));
}

function mostrarModalViabilidade(d){
    const fmt=(v,dec=2)=>v!=null?parseFloat(v).toFixed(dec).replace('.',','):'-';
    const corM=(m)=>m==null?'#8b92a5':m>=20?'#4ade80':m>=10?'#fbbf24':'#f87171';
    const corInsight=(t)=>t==='positivo'?'#4ade80':t==='negativo'?'#f87171':t==='info'?'#93c5fd':'#fbbf24';

    const scoreCor = d.score>=70?'#4ade80':d.score>=45?'#fbbf24':'#f87171';
    const insightsHTML=(d.insights||[]).map(ins=>`
        <div style="display:flex;gap:8px;align-items:flex-start;padding:6px 0;border-bottom:1px solid #2d3452">
            <span style="color:${corInsight(ins.tipo)};font-size:1rem">${ins.tipo==='positivo'?'✅':ins.tipo==='negativo'?'❌':ins.tipo==='info'?'ℹ️':'⚠️'}</span>
            <span style="color:#e4e6eb;font-size:.82rem">${ins.msg}</span>
        </div>`).join('');

    const topHTML=(d.top_anuncios||[]).map((a,i)=>`
        <tr style="border-bottom:1px solid #1a1f3a">
            <td style="padding:3px 7px;color:#8b92a5">${i+1}</td>
            <td style="padding:3px 7px;color:#e4e6eb;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${a.titulo}</td>
            <td style="padding:3px 7px;color:#4ade80;font-weight:700">R$ ${fmt(a.preco)}</td>
            <td style="padding:3px 7px;color:#fbbf24">${parseInt(a.vendas_acumuladas).toLocaleString('pt-BR')}</td>
            <td style="padding:3px 7px;color:#8b92a5;font-size:.72rem">${a.vendedor}</td>
            <td><a href="${a.link}" target="_blank" style="color:#667eea;font-size:.72rem">Ver ↗</a></td>
        </tr>`).join('');

    const margemBlock = d.custo > 0 ? `
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px">
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Margem no mínimo</div>
                <div style="font-size:1.1rem;font-weight:700;color:${corM(d.margem_no_min)}">${fmt(d.margem_no_min,1)}%</div>
                <div style="font-size:.7rem;color:#8b92a5">R$ ${fmt(d.preco_min)}</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Margem no mediano</div>
                <div style="font-size:1.1rem;font-weight:700;color:${corM(d.margem_no_mediano)}">${fmt(d.margem_no_mediano,1)}%</div>
                <div style="font-size:.7rem;color:#8b92a5">R$ ${fmt(d.preco_mediano)}</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Lucro mensal est.</div>
                <div style="font-size:1.1rem;font-weight:700;color:#c084fc">R$ ${fmt(d.lucro_mensal_estimado)}</div>
                <div style="font-size:.7rem;color:#8b92a5">estimativa 5% do mercado</div>
            </div>
        </div>` : '<div style="color:#8b92a5;font-size:.8rem;margin-bottom:12px">⚠️ Cadastre o custo do produto para ver análise de margem.</div>';

    const h=`<div id="modalViab" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);display:flex;justify-content:center;align-items:center;z-index:9999;padding:20px">
    <div style="background:#1a1f3a;padding:20px;border-radius:10px;border:1px solid #0891b2;width:820px;max-width:95vw;max-height:90vh;overflow-y:auto">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px">
            <div>
                <h3 style="color:#0891b2">📈 Análise de Viabilidade</h3>
                <div style="color:#e4e6eb;font-size:.83rem">${d.termo_buscado}</div>
                <div style="color:#8b92a5;font-size:.72rem">${d.total_anuncios} anúncios · Taxa ML: ${fmt(d.taxa_percentual,1)}% · ${d.categoria_id||''}</div>
            </div>
            <div style="text-align:center">
                <div style="font-size:2rem;font-weight:900;color:${scoreCor}">${d.score}</div>
                <div style="font-size:.75rem;color:${scoreCor}">${d.cor} ${d.classificacao}</div>
            </div>
            <button onclick="document.getElementById('modalViab').remove()" style="background:#2d3452;color:#e4e6eb;border:none;border-radius:5px;padding:5px 10px;cursor:pointer;align-self:flex-start">✕</button>
        </div>

        <!-- Demanda -->
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px">
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Vendas acum. top 20</div>
                <div style="font-size:1.2rem;font-weight:700;color:#4ade80">${parseInt(d.total_vendas_top20_acumulado).toLocaleString('pt-BR')}</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Demanda/mês estimada</div>
                <div style="font-size:1.2rem;font-weight:700;color:#fbbf24">${fmt(d.demanda_mercado_mensal,0)}</div>
                <div style="font-size:.65rem;color:#8b92a5">total mercado</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Preço mínimo</div>
                <div style="font-size:1.2rem;font-weight:700;color:#f87171">R$ ${fmt(d.preco_min)}</div>
            </div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center">
                <div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Preço mediano</div>
                <div style="font-size:1.2rem;font-weight:700;color:#4ade80">R$ ${fmt(d.preco_mediano)}</div>
            </div>
        </div>

        ${margemBlock}

        <!-- Insights -->
        <div style="background:#0a0e27;border-radius:7px;padding:12px;margin-bottom:12px">
            <div style="color:#8b92a5;font-size:.7rem;text-transform:uppercase;margin-bottom:6px">💡 Insights do Agente</div>
            ${insightsHTML}
        </div>

        <!-- Top anúncios -->
        <div style="color:#8b92a5;font-size:.7rem;text-transform:uppercase;margin-bottom:5px">Top Anúncios por Vendas</div>
        <table style="width:100%;border-collapse:collapse;background:#0a0e27;font-size:.77rem;border-radius:5px">
            <thead><tr style="border-bottom:1px solid #2d3452">
                <th style="padding:4px 7px;color:#8b92a5">#</th>
                <th style="padding:4px 7px;color:#8b92a5">Título</th>
                <th style="padding:4px 7px;color:#8b92a5">Preço</th>
                <th style="padding:4px 7px;color:#8b92a5">Vendas</th>
                <th style="padding:4px 7px;color:#8b92a5">Vendedor</th>
                <th style="padding:4px 7px;color:#8b92a5">Link</th>
            </tr></thead>
            <tbody>${topHTML}</tbody>
        </table>
    </div></div>`;
    document.getElementById('modalViab')?.remove();
    document.body.insertAdjacentHTML('beforeend',h);
}

function precificarProduto(id){
    const margem = prompt('Margem mínima desejada (%):', '20');
    if(margem === null) return;
    showToast('💰 Analisando precificação...');
    fetch('/api/precificar',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:id, margem_minima:parseFloat(margem)||20})})
    .then(r=>r.json()).then(d=>{
        if(!d.ok){showToast('❌ '+d.erro,true);return;}
        mostrarModalPrecificacao(d);
    }).catch(()=>showToast('❌ Erro conexão',true));
}

function mostrarModalPrecificacao(d){
    const fmt=(v,dec=2)=>v!=null?v.toFixed(dec).replace('.',','):'-';
    const corM=(m)=>m==null?'#8b92a5':m>=20?'#4ade80':m>=10?'#fbbf24':'#f87171';
    const rec=d.recomendacao||{};
    const c=d.cenarios||{};
    const renderCenario=(nome,dados,emoji)=>{
        if(!dados)return'';
        const dest=rec.cenario===nome?'border:2px solid #667eea;':'';
        const recTag=rec.cenario===nome?'<span style="background:#667eea;color:#fff;padding:1px 6px;border-radius:8px;font-size:.6rem;margin-left:4px">⭐ RECOMENDADO</span>':'';
        const badge=dados.viavel?'<span style="background:#065f46;color:#4ade80;padding:1px 5px;border-radius:8px;font-size:.6rem">VIÁVEL</span>':'<span style="background:#450a0a;color:#f87171;padding:1px 5px;border-radius:8px;font-size:.6rem">INVIÁVEL</span>';
        return `<div style="background:#0a0e27;padding:12px;border-radius:7px;${dest}">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                <span style="font-weight:700;font-size:.83rem">${emoji} ${nome.charAt(0).toUpperCase()+nome.slice(1)}${recTag}</span>${badge}</div>
            <div style="font-size:1.3rem;font-weight:700;color:#4ade80">R$ ${fmt(dados.preco)}</div>
            <div style="color:${corM(dados.margem)};font-size:.83rem">Margem: ${fmt(dados.margem,1)}%</div>
            <div style="color:#8b92a5;font-size:.7rem;margin-top:3px">${dados.descricao}</div>
            <button onclick="aplicarPreco(${d.produto_id},${dados.preco},${d.taxa_percentual});document.getElementById('modalPrec').remove()"
                style="margin-top:8px;padding:3px 10px;border:none;border-radius:4px;background:#2d3452;color:#e4e6eb;cursor:pointer;font-size:.72rem">Usar este preço</button>
        </div>`;
    };
    const rivais=(d.top_concorrentes||[]).map((r,i)=>`<tr style="border-bottom:1px solid #1a1f3a">
        <td style="padding:3px 7px;color:#8b92a5">${i+1}</td>
        <td style="padding:3px 7px;color:#e4e6eb;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.titulo}</td>
        <td style="padding:3px 7px;color:#4ade80;font-weight:700">R$ ${fmt(r.preco)}</td>
        <td style="padding:3px 7px;color:#fbbf24">${(r.vendas||0).toLocaleString('pt-BR')}</td>
        <td><a href="${r.link}" target="_blank" style="color:#667eea;font-size:.72rem">Ver ↗</a></td>
    </tr>`).join('');
    const h=`<div id="modalPrec" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);display:flex;justify-content:center;align-items:center;z-index:9999;padding:20px">
    <div style="background:#1a1f3a;padding:20px;border-radius:10px;border:1px solid #059669;width:820px;max-width:95vw;max-height:90vh;overflow-y:auto">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px">
            <div><h3 style="color:#059669">💰 Precificação Inteligente</h3>
            <div style="color:#e4e6eb;font-size:.83rem">${d.produto_nome}</div>
            <div style="color:#8b92a5;font-size:.72rem">${d.total_concorrentes} concorrentes · Taxa ML: ${fmt(d.taxa_percentual,1)}% · "${d.termo_buscado}"</div></div>
            <button onclick="document.getElementById('modalPrec').remove()" style="background:#2d3452;color:#e4e6eb;border:none;border-radius:5px;padding:5px 10px;cursor:pointer">✕</button>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px">
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Menor rival</div><div style="font-size:1.1rem;font-weight:700;color:#f87171">R$ ${fmt(d.preco_min_ml)}</div></div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Mediano</div><div style="font-size:1.1rem;font-weight:700;color:#4ade80">R$ ${fmt(d.preco_mediano)}</div></div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Seu custo</div><div style="font-size:1.1rem;font-weight:700;color:#fbbf24">R$ ${fmt(d.custo)}</div></div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Mín viável ${fmt(d.margem_minima_alvo,0)}%</div><div style="font-size:1.1rem;font-weight:700;color:#c084fc">R$ ${fmt(d.preco_minimo_viavel)}</div></div>
        </div>
        ${rec.motivo?`<div style="background:#1a2a1a;border:1px solid #059669;border-radius:6px;padding:10px;margin-bottom:12px"><span style="color:#4ade80;font-weight:700">💡 </span><span style="color:#e4e6eb;font-size:.83rem">${rec.motivo}</span></div>`:''}
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:12px">
            ${renderCenario('agressivo',c.agressivo,'🔥')}
            ${renderCenario('competitivo',c.competitivo,'⚖️')}
            ${renderCenario('premium',c.premium,'👑')}
        </div>
        <div style="color:#8b92a5;font-size:.7rem;text-transform:uppercase;margin-bottom:5px">Top Concorrentes</div>
        <table style="width:100%;border-collapse:collapse;background:#0a0e27;font-size:.77rem;border-radius:5px">
            <thead><tr style="border-bottom:1px solid #2d3452"><th style="padding:4px 7px;color:#8b92a5">#</th><th style="padding:4px 7px;color:#8b92a5">Título</th><th style="padding:4px 7px;color:#8b92a5">Preço</th><th style="padding:4px 7px;color:#8b92a5">Vendas</th><th style="padding:4px 7px;color:#8b92a5">Link</th></tr></thead>
            <tbody>${rivais}</tbody>
        </table>
    </div></div>`;
    document.getElementById('modalPrec')?.remove();
    document.body.insertAdjacentHTML('beforeend',h);
}

function abrirAlertaDiario(){
    showToast('📊 Gerando alerta diário...');
    fetch('/api/alerta-diario')
    .then(r=>r.json()).then(d=>{
        if(!d.ok){showToast('❌ '+d.erro,true);return;}
        mostrarModalAlerta(d);
    }).catch(()=>showToast('❌ Erro conexão',true));
}

function mostrarModalAlerta(d){
    const fmt=(v)=>v!=null?parseFloat(v).toFixed(2).replace('.',','):'0,00';
    const vendas=d.vendas||{};
    const rep=d.reputacao||{};
    const perguntas=d.perguntas||{};
    const alertasHTML=(d.alertas||[]).map(a=>{
        const bg=a.tipo==='urgente'?'#450a0a':a.tipo==='aviso'?'#3b2700':a.tipo==='ok'?'#064e3b':'#1e3a5f';
        const cor=a.tipo==='urgente'?'#f87171':a.tipo==='aviso'?'#fbbf24':a.tipo==='ok'?'#4ade80':'#93c5fd';
        return `<div style="background:${bg};border-radius:5px;padding:9px 12px;display:flex;align-items:center;gap:9px">
            <span style="font-size:1.2rem">${a.icone}</span><span style="color:${cor};font-size:.83rem">${a.msg}</span></div>`;
    }).join('');
    const varHTML=(d.variacao_precos||[]).map(v=>`
        <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid #2d3452;font-size:.78rem">
            <span style="color:#e4e6eb;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${v.produto}</span>
            <span style="color:#8b92a5">Meu: R$ ${fmt(v.seu_preco)}</span>
            <span style="color:#fbbf24">Rival: R$ ${fmt(v.menor_concorrente)}</span>
            <span style="color:${v.variacao_pct>=0?'#4ade80':'#f87171'}">${v.status}</span>
        </div>`).join('');
    const h=`<div id="modalAlerta" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);display:flex;justify-content:center;align-items:center;z-index:9999;padding:20px">
    <div style="background:#1a1f3a;padding:20px;border-radius:10px;border:1px solid #f59e0b;width:680px;max-width:95vw;max-height:90vh;overflow-y:auto">
        <div style="display:flex;justify-content:space-between;margin-bottom:14px">
            <div><h3 style="color:#f59e0b">📊 Alerta Diário</h3>
            <div style="color:#8b92a5;font-size:.72rem">Gerado em ${d.gerado_em}</div></div>
            <button onclick="document.getElementById('modalAlerta').remove()" style="background:#2d3452;color:#e4e6eb;border:none;border-radius:5px;padding:5px 10px;cursor:pointer">✕</button>
        </div>
        <div style="display:flex;flex-direction:column;gap:7px;margin-bottom:14px">${alertasHTML||'<div style="color:#8b92a5">Nenhum alerta.</div>'}</div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px">
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Vendas hoje</div><div style="font-size:1.2rem;font-weight:700;color:#4ade80">${vendas.hoje_qtd||0}</div><div style="font-size:.75rem;color:#8b92a5">R$ ${fmt(vendas.hoje_valor)}</div></div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Vendas semana</div><div style="font-size:1.2rem;font-weight:700;color:#667eea">${vendas.semana_qtd||0}</div><div style="font-size:.75rem;color:#8b92a5">R$ ${fmt(vendas.semana_valor)}</div></div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Perguntas abertas</div><div style="font-size:1.2rem;font-weight:700;color:${(perguntas.nao_respondidas||0)>0?'#f87171':'#4ade80'}">${perguntas.nao_respondidas||0}</div></div>
            <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5;text-transform:uppercase">Reputação</div><div style="font-size:.85rem;font-weight:700;color:#fbbf24">${(rep.nivel||'N/A').replace(/_/g,' ')}</div></div>
        </div>
        ${varHTML?`<div style="color:#8b92a5;font-size:.7rem;text-transform:uppercase;margin-bottom:6px">Variação de Preços (Escolhidos)</div>${varHTML}`:''}
    </div></div>`;
    document.getElementById('modalAlerta')?.remove();
    document.body.insertAdjacentHTML('beforeend',h);
}

function usarPrecoMediano(id, preco, taxa){
    document.getElementById('modalPesquisa')?.remove();
    const pmlEl = document.getElementById('pml-'+id);
    const txEl = document.getElementById('tx-'+id);
    if(pmlEl){
        pmlEl.value = preco.toFixed(2);
        if(txEl) txEl.value = taxa.toFixed(1);
        salvar(pmlEl);
        showToast('✅ Preço mediano aplicado!');
    }
}



function mostrarModalProduto(){
    const h=`<div id="modalProd" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.7);display:flex;justify-content:center;align-items:center;z-index:9999">
    <div style="background:#1a1f3a;padding:24px;border-radius:10px;border:1px solid #667eea;width:460px;max-width:95vw">
        <h3 style="color:#4ade80;margin-bottom:14px">➕ Cadastrar Produto Manual</h3>
        <div style="display:grid;gap:10px">
            <div><label style="color:#8b92a5;font-size:.75rem">Código</label><input id="npCod" style="width:100%;padding:7px;border:1px solid #2d3452;border-radius:4px;background:#0a0e27;color:#e4e6eb" placeholder="Ex: ABC-001"></div>
            <div><label style="color:#8b92a5;font-size:.75rem">Fornecedor</label><input id="npForn" style="width:100%;padding:7px;border:1px solid #2d3452;border-radius:4px;background:#0a0e27;color:#e4e6eb" placeholder="Ex: TRAMONTINA"></div>
            <div><label style="color:#8b92a5;font-size:.75rem">Descrição</label><input id="npDesc" style="width:100%;padding:7px;border:1px solid #2d3452;border-radius:4px;background:#0a0e27;color:#e4e6eb" placeholder="Nome do produto"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
                <div><label style="color:#8b92a5;font-size:.75rem">Custo R$</label><input id="npCusto" type="number" step="0.01" style="width:100%;padding:7px;border:1px solid #2d3452;border-radius:4px;background:#0a0e27;color:#fbbf24;font-weight:700" placeholder="0.00"></div>
                <div><label style="color:#8b92a5;font-size:.75rem">Peso kg</label><input id="npPeso" type="number" step="0.01" style="width:100%;padding:7px;border:1px solid #2d3452;border-radius:4px;background:#0a0e27;color:#e4e6eb" placeholder="0.00"></div>
                <div><label style="color:#8b92a5;font-size:.75rem">Embal. R$</label><input id="npEmb" type="number" step="0.10" style="width:100%;padding:7px;border:1px solid #2d3452;border-radius:4px;background:#0a0e27;color:#e4e6eb" placeholder="0.00"></div>
            </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:14px;justify-content:flex-end">
            <button onclick="document.getElementById('modalProd').remove()" style="padding:8px 16px;border:none;border-radius:5px;background:#2d3452;color:#e4e6eb;cursor:pointer">Cancelar</button>
            <button onclick="salvarNovoProduto()" style="padding:8px 16px;border:none;border-radius:5px;background:#4ade80;color:#000;font-weight:700;cursor:pointer">💾 Salvar</button>
        </div>
    </div></div>`;
    document.body.insertAdjacentHTML('beforeend',h);
    document.getElementById('npCod').focus();
}

function salvarNovoProduto(){
    const cod=document.getElementById('npCod').value.trim();
    const forn=document.getElementById('npForn').value.trim();
    const desc=document.getElementById('npDesc').value.trim();
    const custo=parseFloat(document.getElementById('npCusto').value)||0;
    const peso=parseFloat(document.getElementById('npPeso').value)||0;
    const emb=parseFloat(document.getElementById('npEmb').value)||0;
    if(!desc){showToast('❌ Preencha a descrição',true);return;}
    fetch('/api/adicionar-produto',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({codigo:cod,fornecedor:forn,descricao:desc,custo:custo,peso_kg:peso,custo_embalagem:emb})
    }).then(r=>r.json()).then(d=>{
        if(d.ok){showToast('✅ Produto cadastrado!');document.getElementById('modalProd').remove();setTimeout(()=>location.reload(),500);}
        else showToast('❌ '+d.erro,true);
    });
}
</script>
</body>
</html>
"""


# ============================================================
# ROTAS
# ============================================================


@app.route('/login')
def pagina_login():
    return LOGIN_HTML

@app.route('/api/login', methods=['POST'])
def api_login():
    d = request.get_json()
    usuario = d.get('usuario', '').strip()
    senha = d.get('senha', '')
    if verificar_login(usuario, senha):
        session['usuario'] = usuario
        session.permanent = True
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'erro': 'Usuário ou senha incorretos'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
@login_required
def index():
    if not DB_PATH.exists():
        return render_template_string(HTML_TEMPLATE,produtos=[],stats={'total':0,'fornecedores':0,'com_preco_ml':0,'sem_preco_ml':0,'viaveis':0,'nao_viaveis':0,'pendentes':0,'total_filtrado':0},fornecedores=[],f={},pg=1,total_paginas=1,url_pg=lambda p:'/',aliquota_imposto_pct=0)
    
    conn = get_conn()
    cur = conn.cursor()
    
    f = {k: request.args.get(k,'') for k in ['custo_min','custo_max','fornecedor','produto','codigo','viabilidade']}
    f['pp'] = int(request.args.get('pp', 250))
    pg = int(request.args.get('pagina', 1))
    
    w, p = [], []
    if f['custo_min']: w.append("custo >= ?"); p.append(float(f['custo_min']))
    if f['custo_max']: w.append("custo <= ?"); p.append(float(f['custo_max']))
    if f['fornecedor']: w.append("fornecedor = ?"); p.append(f['fornecedor'])
    if f['produto']: w.append("descricao LIKE ?"); p.append(f"%{f['produto']}%")
    if f['codigo']: w.append("codigo LIKE ?"); p.append(f"%{f['codigo']}%")
    if f['viabilidade'] == 'viavel': w.append("viavel = 1")
    elif f['viabilidade'] == 'nao': w.append("viavel = 0 AND preco_ml > 0")
    elif f['viabilidade'] == 'pendente': w.append("(preco_ml IS NULL OR preco_ml = 0)")
    elif f['viabilidade'] == 'com_preco': w.append("preco_ml > 0")
    
    where = " AND ".join(w) if w else "1=1"
    
    tenant = get_tenant_id()
    if "tenant_id" not in where:
        w.append("tenant_id = ?")
        p.append(tenant)
        where = " AND ".join(w) if w else "1=1"
    cur.execute(f"SELECT COUNT(*) FROM produtos WHERE {where}", p)
    total_f = cur.fetchone()[0]
    total_pg = max(1, (total_f + f['pp'] - 1) // f['pp'])
    pg = max(1, min(pg, total_pg))
    
    cur.execute(f"SELECT * FROM produtos WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?", p + [f['pp'], (pg-1)*f['pp']])
    produtos = [dict(r) for r in cur.fetchall()]
    
    cur.execute("SELECT COUNT(*) FROM produtos"); total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT fornecedor) FROM produtos"); forn_c = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM produtos WHERE preco_ml > 0"); com_p = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM produtos WHERE viavel = 1"); viaveis = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM produtos WHERE viavel = 0 AND preco_ml > 0"); nao_v = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM produtos WHERE escolhido = 1"); escolhidos = cur.fetchone()[0]
    cur.execute("SELECT DISTINCT fornecedor FROM produtos ORDER BY fornecedor"); fornecedores = [r[0] for r in cur.fetchall()]
    conn.close()
    
    stats = {'total':total,'fornecedores':forn_c,'com_preco_ml':com_p,'sem_preco_ml':total-com_p,'viaveis':viaveis,'nao_viaveis':nao_v,'pendentes':total-com_p,'total_filtrado':total_f,'escolhidos':escolhidos}
    
    def url_pg(p):
        a = dict(request.args); a['pagina'] = p
        return '/?' + '&'.join(f'{k}={v}' for k,v in a.items() if v)
    
    return render_template_string(HTML_TEMPLATE, produtos=produtos, stats=stats, fornecedores=fornecedores, f=f, pg=pg, total_paginas=total_pg, url_pg=url_pg, aliquota_imposto_pct=round(get_aliquota()*100, 1), usuario_nome=get_usuario_nome())


@app.route('/api/atualizar', methods=['POST'])
def api_atualizar():
    try:
        d = request.get_json()
        pid = d['id']
        preco_ml = float(d.get('preco_ml', 0))
        tipo_anuncio = d.get('tipo_anuncio', 'classico')
        taxa_cat = float(d.get('taxa_categoria', 0.165))
        peso_kg = float(d.get('peso_kg', 0))
        embalagem = float(d.get('custo_embalagem', 0))
        custo_ads = float(d.get('custo_ads', 0))
        aliq = float(d.get('aliquota_imposto', get_aliquota()))
        
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT custo, descricao FROM produtos WHERE id = ?", (pid,))
        row = cur.fetchone()
        if not row: conn.close(); return jsonify({'ok': False, 'erro': 'Não encontrado'})
        
        custo, desc = row[0] or 0, row[1] or ''
        r = calcular_viabilidade_completa(custo, preco_ml, taxa_cat, peso_kg, embalagem, aliq, custo_ads)
        
        cur.execute("""UPDATE produtos SET preco_ml=?,tipo_anuncio=?,taxa_categoria=?,peso_kg=?,custo_embalagem=?,custo_ads=?,
            taxa_fixa_ml=?,imposto_valor=?,custo_frete=?,custo_total=?,margem_percentual=?,margem_reais=?,viavel=? WHERE id=?""",
            (preco_ml, tipo_anuncio, taxa_cat, peso_kg, embalagem, custo_ads, r['taxa_fixa'], r['imposto_valor'],
             r['custo_frete'], r['custo_total'], r['margem_percentual'], r['margem_reais'], r['viavel'], pid))
        conn.commit(); conn.close()
        
        return jsonify({'ok':True,'desc':desc,**r})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


@app.route('/api/adicionar-produto', methods=['POST'])
def api_adicionar_produto():
    """Cadastra produto manualmente"""
    try:
        d = request.get_json()
        desc = d.get('descricao', '').strip()
        if not desc:
            return jsonify({'ok': False, 'erro': 'Descrição obrigatória'})
        
        conn = get_conn()
        cur = conn.cursor()
        garantir_schema()
        
        cur.execute("""INSERT INTO produtos (codigo, fornecedor, descricao, custo, peso_kg, custo_embalagem, 
            data_analise, arquivo_origem) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (d.get('codigo', '').strip(), d.get('fornecedor', '').strip(), desc,
             float(d.get('custo', 0)), float(d.get('peso_kg', 0)), float(d.get('custo_embalagem', 0)),
             datetime.now().isoformat(), 'MANUAL'))
        
        conn.commit()
        novo_id = cur.lastrowid
        conn.close()
        
        return jsonify({'ok': True, 'id': novo_id})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


@app.route('/api/deletar-produto', methods=['POST'])
def api_deletar_produto():
    """Deleta um produto do banco"""
    try:
        d = request.get_json()
        pid = d.get('id')
        if not pid:
            return jsonify({'ok': False, 'erro': 'ID obrigatório'})
        
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM produtos WHERE id = ?", (pid,))
        conn.commit()
        conn.close()
        
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


@app.route('/api/buscar-ml', methods=['POST'])
def api_buscar_ml():
    try:
        from ml_buscador import MLBuscador
        d = request.get_json()
        pid, termo = d['id'], d.get('termo','')
        if not termo: return jsonify({'ok':False,'erro':'Termo vazio'})
        
        ml = MLBuscador()
        if not ml.esta_autenticado():
            return jsonify({'ok':False,'erro':'Conecte-se ao ML primeiro! Clique em ML Auth'})
        
        resultado = ml.buscar_preco_medio(termo, limite=10)
        if resultado.get('encontrado'):
            conn = get_conn()
            cur = conn.cursor()
            
            preco_medio = resultado['preco_medio']
            cur.execute("UPDATE produtos SET preco_ml=?, link_ml=? WHERE id=?",
                (preco_medio, resultado.get('link_top',''), pid))
            
            # Busca taxa real da categoria
            taxa_pct_retorno = None
            cat = resultado.get('categoria_top', '')
            if cat:
                taxa_info = ml.calcular_taxa_ml(preco_medio, category_id=cat)
                if taxa_info.get('ok') and taxa_info.get('taxa_percentual'):
                    taxa_pct = taxa_info['taxa_percentual'] / 100
                    cur.execute("UPDATE produtos SET taxa_categoria=? WHERE id=?", (taxa_pct, pid))
                    taxa_pct_retorno = taxa_info['taxa_percentual']
                    
                    # Recalcula viabilidade com a nova taxa
                    cur.execute("SELECT custo, peso_kg, custo_embalagem, custo_ads FROM produtos WHERE id=?", (pid,))
                    row = cur.fetchone()
                    if row:
                        custo, peso, emb, ads = row[0] or 0, row[1] or 0, row[2] or 0, row[3] or 0
                        aliq = get_aliquota()
                        r = calcular_viabilidade_completa(custo, preco_medio, taxa_pct, peso, emb, aliq, ads)
                        cur.execute("""UPDATE produtos SET taxa_fixa_ml=?,imposto_valor=?,custo_frete=?,custo_total=?,
                            margem_percentual=?,margem_reais=?,viavel=? WHERE id=?""",
                            (r['taxa_fixa'],r['imposto_valor'],r['custo_frete'],r['custo_total'],
                             r['margem_percentual'],r['margem_reais'],r['viavel'],pid))
            
            conn.commit(); conn.close()
            resp = {'ok':True, 'preco_medio':preco_medio,
                'preco_min':resultado['preco_min'], 'preco_max':resultado['preco_max'],
                'total':resultado['total_encontrados'],
                'categoria': cat}
            if taxa_pct_retorno is not None:
                resp['taxa_percentual'] = taxa_pct_retorno
            return jsonify(resp)
        return jsonify({'ok':False,'erro':'Nao encontrado no ML'})
    except ImportError:
        return jsonify({'ok':False,'erro':'ml_buscador.py nao encontrado'})
    except Exception as e:
        return jsonify({'ok':False,'erro':str(e)})


@app.route('/api/recalcular-todos', methods=['POST'])
def api_recalcular_todos():
    try:
        d = request.get_json() or {}
        aliq = float(d.get('aliquota', get_aliquota()))
        
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, custo, preco_ml, taxa_categoria, peso_kg, custo_embalagem, custo_ads FROM produtos WHERE preco_ml > 0")
        rows = cur.fetchall()
        
        n = 0
        for pid, custo, pml, taxa, peso, emb, ads in rows:
            r = calcular_viabilidade_completa(custo or 0, pml, taxa or 0.165, peso or 0, emb or 0, aliq, ads or 0)
            cur.execute("""UPDATE produtos SET taxa_fixa_ml=?,imposto_valor=?,custo_frete=?,custo_total=?,
                margem_percentual=?,margem_reais=?,viavel=? WHERE id=?""",
                (r['taxa_fixa'],r['imposto_valor'],r['custo_frete'],r['custo_total'],r['margem_percentual'],r['margem_reais'],r['viavel'],pid))
            n += 1
        conn.commit(); conn.close()
        return jsonify({'ok':True,'atualizados':n})
    except Exception as e:
        return jsonify({'ok':False,'erro':str(e)})


@app.route('/api/aliquota', methods=['POST'])
def api_aliquota():
    try:
        d = request.get_json()
        v = float(d.get('aliquota', 0)) / 100
        set_aliquota(v)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


@app.route('/exportar')
@login_required
def exportar():
    try:
        import pandas as pd
        conn = get_conn()
        df = pd.read_sql_query("SELECT * FROM produtos ORDER BY fornecedor, codigo", conn)
        conn.close()
        
        rename = {'codigo':'Código','fornecedor':'Fornecedor','descricao':'Produto',
            'custo':'Custo','preco_ml':'Preço ML','taxa_categoria':'Taxa Cat.',
            'taxa_fixa_ml':'Taxa Fixa','peso_kg':'Peso kg','custo_frete':'Frete',
            'custo_embalagem':'Embalagem','imposto_valor':'Imposto','custo_total':'Custo Total',
            'margem_reais':'Lucro R$','margem_percentual':'Margem %','viavel':'Viável',
            'link_ml':'Link ML','arquivo_origem':'Arquivo','pagina_origem':'Página'}
        df = df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
        df = df.drop(columns=[c for c in ['id','notas','data_analise'] if c in df.columns], errors='ignore')
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as w:
            df.to_excel(w, index=False, sheet_name='Produtos')
        output.seek(0)
        
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True, download_name=f"QUBO_Viabilidade_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
    except Exception as e:
        return f"Erro: {e}", 500


@app.route('/api/escolher', methods=['POST'])
def api_escolher():
    try:
        d = request.get_json()
        ids = d.get('ids', [])
        conn = get_conn()
        cur = conn.cursor()
        for pid in ids:
            cur.execute("UPDATE produtos SET escolhido = 1 WHERE id = ?", (pid,))
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM produtos WHERE escolhido = 1")
        total = cur.fetchone()[0]
        conn.close()
        return jsonify({'ok': True, 'total': len(ids), 'total_escolhidos': total})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


@app.route('/api/descartar', methods=['POST'])
def api_descartar():
    try:
        d = request.get_json()
        ids = d.get('ids', [])
        conn = get_conn()
        cur = conn.cursor()
        for pid in ids:
            cur.execute("UPDATE produtos SET escolhido = 0, custo_full = 0, custo_ads = 0, promo_percentual = 0, preco_ideal = 0, preco_final = 0, lucro_final = 0, margem_final = 0 WHERE id = ?", (pid,))
        conn.commit(); conn.close()
        return jsonify({'ok': True, 'removidos': len(ids)})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


@app.route('/api/formacao', methods=['POST'])
def api_formacao():
    """Calcula formação de preço para produto escolhido"""
    try:
        d = request.get_json()
        pid = d['id']
        modo = d.get('modo', 'preco')  # 'preco' ou 'margem'
        
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT custo, descricao, taxa_categoria, peso_kg, custo_embalagem FROM produtos WHERE id = ?", (pid,))
        row = cur.fetchone()
        if not row: conn.close(); return jsonify({'ok': False, 'erro': 'Não encontrado'})
        
        custo, desc, taxa_cat, peso, emb = row
        custo = custo or 0; taxa_cat = taxa_cat or 0.165; peso = peso or 0; emb = emb or 0
        aliq = get_aliquota()
        
        custo_full = float(d.get('custo_full', 0))
        custo_ads = float(d.get('custo_ads', 0))
        promo_pct = float(d.get('promo_pct', 0))
        
        if modo == 'margem':
            margem_alvo = float(d.get('margem_alvo', 25))
            r = calcular_preco_ideal(custo, taxa_cat, peso, emb, aliq, custo_full, custo_ads, promo_pct, margem_alvo)
            if r.get('erro'):
                conn.close(); return jsonify({'ok': False, 'erro': r['erro']})
            preco = r['preco_ideal']
        else:
            preco = float(d.get('preco_final', 0))
        
        # Calcula breakdown completo
        fc = calcular_formacao_completa(custo, preco, taxa_cat, peso, emb, aliq, custo_full, custo_ads, promo_pct)
        if fc.get('erro'):
            conn.close(); return jsonify({'ok': False, 'erro': fc['erro']})
        
        # Salva no banco
        cur.execute("""UPDATE produtos SET custo_full=?, custo_ads=?, promo_percentual=?,
            preco_final=?, lucro_final=?, margem_final=?,
            margem_alvo=? WHERE id=?""",
            (custo_full, custo_ads, promo_pct, preco, fc['lucro_final'], fc['margem_final'],
             float(d.get('margem_alvo', 25)) if modo == 'margem' else 0, pid))
        conn.commit(); conn.close()
        
        return jsonify({
            'ok': True, 'desc': desc, 'preco_calculado': preco,
            'taxa_ml_valor': fc['taxa_ml_valor'], 'taxa_fixa': fc['taxa_fixa'],
            'custo_frete': fc['custo_frete'], 'imposto_valor': fc['imposto_valor'],
            'custo_promo': fc['custo_promo'], 'custo_total_full': fc['custo_total_full'],
            'lucro_final': fc['lucro_final'], 'margem_final': fc['margem_final'],
            'viavel': fc['viavel']
        })
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


# ============================================================
# PÁGINA ESCOLHIDOS
# ============================================================

ESCOLHIDOS_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⭐ Escolhidos — QUBO</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e27;color:#e4e6eb;padding:14px;font-size:13px}
        .container{max-width:1920px;margin:0 auto}
        h1{font-size:1.5rem;margin-bottom:14px;background:linear-gradient(135deg,#f093fb 0%,#f5576c 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;display:inline-block}
        .header-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:8px}
        .header-actions{display:flex;gap:6px;flex-wrap:wrap}
        
        .stats{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:14px}
        .stat-card{background:#1a1f3a;padding:10px;border-radius:7px;border:1px solid #2d3452;text-align:center}
        .stat-value{font-size:1.4rem;font-weight:bold;color:#f093fb}
        .stat-value.green{color:#4ade80}.stat-value.red{color:#f87171}.stat-value.yellow{color:#fbbf24}
        .stat-label{color:#8b92a5;font-size:0.65rem;text-transform:uppercase;margin-top:3px}
        
        .mode-bar{background:#1a1f3a;padding:10px 14px;border-radius:7px;margin-bottom:10px;border:1px solid #2d3452;display:flex;align-items:center;gap:15px;flex-wrap:wrap}
        .mode-bar label{color:#8b92a5;font-size:.72rem;text-transform:uppercase}
        .mode-bar input,.mode-bar select{padding:5px 8px;border:1px solid #2d3452;border-radius:4px;background:#0a0e27;color:#fbbf24;font-weight:700;text-align:center;font-size:.85rem;width:70px}
        .mode-bar select{width:auto;color:#e4e6eb}
        .mode-toggle{display:flex;border-radius:5px;overflow:hidden;border:1px solid #2d3452}
        .mode-toggle button{padding:6px 14px;border:none;background:#2d3452;color:#8b92a5;cursor:pointer;font-size:.78rem;font-weight:600}
        .mode-toggle button.active{background:#667eea;color:#fff}
        
        button,.btn{padding:5px 12px;border:none;border-radius:4px;cursor:pointer;font-size:.78rem;font-weight:600;transition:all .15s;text-decoration:none;display:inline-block}
        .btn-primary{background:#667eea;color:#fff}.btn-secondary{background:#2d3452;color:#e4e6eb}
        .btn-success{background:#059669;color:#fff}.btn-danger{background:#dc2626;color:#fff}
        .btn-sm{padding:3px 8px;font-size:.7rem}
        
        .table-wrapper{overflow-x:auto;border-radius:7px}
        table{width:100%;border-collapse:collapse;background:#1a1f3a;font-size:.78rem}
        th,td{padding:6px 7px;text-align:left;border-bottom:1px solid #2d3452;white-space:nowrap}
        th{background:#252a47;font-weight:600;color:#8b92a5;text-transform:uppercase;font-size:.63rem;position:sticky;top:0;z-index:10}
        tr:hover{background:#252a47}
        
        .codigo{color:#667eea;font-weight:600}.fornecedor{color:#f093fb}
        .custo{color:#fbbf24;font-weight:600}.desc-col{max-width:200px;overflow:hidden;text-overflow:ellipsis}
        .margem-pos{color:#4ade80;font-weight:700}.margem-neg{color:#f87171;font-weight:700}
        .margem-warn{color:#fbbf24;font-weight:600}.margem-zero{color:#8b92a5}
        
        .inp{width:65px;padding:2px 5px;border:1px solid #2d3452;border-radius:3px;background:#0a0e27;color:#4ade80;font-size:.8rem;font-weight:600;text-align:right}
        .inp:focus{border-color:#667eea;outline:none;box-shadow:0 0 0 2px rgba(102,126,234,.3)}
        .inp-orange{color:#fbbf24}.inp-pink{color:#f093fb}
        
        .viavel-sim{background:#059669;color:#fff;padding:2px 7px;border-radius:10px;font-size:.67rem;font-weight:700}
        .viavel-nao{background:#7f1d1d;color:#fca5a5;padding:2px 7px;border-radius:10px;font-size:.67rem}
        
        .breakdown{font-size:.7rem;color:#8b92a5;padding:4px 8px}
        .breakdown span{margin-right:8px}
        
        .toast{position:fixed;bottom:20px;right:20px;background:#059669;color:#fff;padding:10px 18px;border-radius:7px;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,.3);transform:translateY(100px);opacity:0;transition:all .3s;z-index:1000}
        .toast.show{transform:translateY(0);opacity:1}.toast.error{background:#dc2626}
        
        .empty{text-align:center;padding:50px;color:#8b92a5}
        .empty h2{color:#667eea;margin-bottom:10px}
    </style>
</head>
<body>
<div class="container">
    <div class="header-row">
        <h1>⭐ Produtos Escolhidos — Formação de Preço</h1>
        <div class="header-actions">
            <a href="/" class="btn btn-secondary btn-sm">← Voltar ao Dashboard</a>
            <a href="/exportar-escolhidos" class="btn btn-success btn-sm">📥 Exportar Escolhidos</a>
            <button class="btn btn-danger btn-sm" onclick="descartarTodos()">🗑️ Limpar Todos</button>
        </div>
    </div>

    {% if produtos %}
    <!-- STATS -->
    <div class="stats">
        <div class="stat-card"><div class="stat-value">{{ produtos|length }}</div><div class="stat-label">Escolhidos</div></div>
        <div class="stat-card"><div class="stat-value green">{{ viaveis }}</div><div class="stat-label">Viáveis c/ Extras</div></div>
        <div class="stat-card"><div class="stat-value red">{{ nao_viaveis }}</div><div class="stat-label">Não Viáveis</div></div>
        <div class="stat-card"><div class="stat-value yellow">R$ {{ lucro_total|br }}</div><div class="stat-label">Lucro Total Estimado</div></div>
        <div class="stat-card"><div class="stat-value">{{ margem_media|br(1) }}%</div><div class="stat-label">Margem Média</div></div>
    </div>

    <!-- BARRA MODO -->
    <div class="mode-bar">
        <div>
            <label>Modo</label>
            <div class="mode-toggle">
                <button id="modoPreco" class="active" onclick="setModo('preco')">💰 Defino Preço</button>
                <button id="modoMargem" onclick="setModo('margem')">📊 Defino Margem</button>
            </div>
        </div>
        <div id="margemAlvoBox" style="display:none">
            <label>Margem Alvo (%)</label>
            <input type="number" id="margemAlvoGlobal" value="25" step="1" min="5" max="60">
        </div>
        <div>
            <label>Full R$ (global)</label>
            <input type="number" id="fullGlobal" value="0" step="0.50" min="0">
        </div>
        <div>
            <label>ADS R$ (global)</label>
            <input type="number" id="adsGlobal" value="0" step="0.50" min="0">
        </div>
        <div>
            <label>Promo % (global)</label>
            <input type="number" id="promoGlobal" value="0" step="1" min="0" max="30">
        </div>
        <button class="btn btn-primary btn-sm" onclick="aplicarGlobal()">⚡ Aplicar a Todos</button>
    </div>

    <!-- TABELA -->
    <div class="table-wrapper">
    <table>
        <thead><tr>
            <th>Cód</th><th>Fornec.</th><th>Produto</th><th>Custo</th>
            <th>Full R$</th><th>ADS R$</th><th>Promo %</th>
            <th id="colPrecoMargem">Preço Venda</th>
            <th>TxML</th><th>Frete</th><th>Imp+Emb</th><th>Promo R$</th>
            <th>C.Total</th><th>Lucro</th><th>Margem%</th><th>Status</th><th></th>
        </tr></thead>
        <tbody>
        {% for p in produtos %}
        <tr id="er-{{ p.id }}">
            <td class="codigo">{{ p.codigo or '-' }}</td>
            <td class="fornecedor">{{ p.fornecedor }}</td>
            <td class="desc-col" title="{{ p.descricao }}">{{ p.descricao }}</td>
            <td class="custo">{{ p.custo|br }}</td>
            <td><input class="inp inp-orange" id="full-{{ p.id }}" value="{{ '%.2f'|format(p.custo_full or 0) }}" step="0.50" data-id="{{ p.id }}" onchange="calcular({{ p.id }})"></td>
            <td><input class="inp inp-orange" id="ads-{{ p.id }}" value="{{ '%.2f'|format(p.custo_ads or 0) }}" step="0.50" data-id="{{ p.id }}" onchange="calcular({{ p.id }})"></td>
            <td><input class="inp inp-pink" style="width:45px" id="promo-{{ p.id }}" value="{{ '%.0f'|format(p.promo_percentual or 0) }}" step="1" data-id="{{ p.id }}" onchange="calcular({{ p.id }})"></td>
            <td><input class="inp" id="pf-{{ p.id }}" value="{{ '%.2f'|format(p.preco_final or p.preco_ml or 0) }}" step="0.01" data-id="{{ p.id }}" data-custo="{{ p.custo }}" onchange="calcular({{ p.id }})" onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td id="etx-{{ p.id }}" style="color:#8b92a5">-</td>
            <td id="efr-{{ p.id }}" style="color:#8b92a5">-</td>
            <td id="eie-{{ p.id }}" style="color:#8b92a5">-</td>
            <td id="epr-{{ p.id }}" style="color:#f093fb">-</td>
            <td id="ect-{{ p.id }}" style="font-weight:600;color:#fbbf24">-</td>
            <td id="eluc-{{ p.id }}" class="margem-zero">-</td>
            <td id="emg-{{ p.id }}" class="margem-zero">-</td>
            <td id="est-{{ p.id }}"><span class="viavel-nao">—</span></td>
            <td><button class="btn btn-danger btn-sm" onclick="descartar({{ p.id }})">✕</button></td>
        </tr>
        {% endfor %}
        </tbody>
    </table>
    </div>
    {% else %}
    <div class="empty">
        <h2>⭐ Nenhum produto escolhido ainda</h2>
        <p>Volte ao <a href="/" style="color:#667eea">Dashboard</a>, marque produtos com checkbox e clique "Enviar p/ Escolhidos"</p>
    </div>
    {% endif %}
</div>

<div class="toast" id="toast2"></div>

<script>
let modo = 'preco';
function fmt(v,d){return v.toFixed(d||2).replace('.',',')}

function setModo(m){
    modo = m;
    document.getElementById('modoPreco').className = m==='preco'?'active':'';
    document.getElementById('modoMargem').className = m==='margem'?'active':'';
    document.getElementById('margemAlvoBox').style.display = m==='margem'?'block':'none';
    document.getElementById('colPrecoMargem').textContent = m==='preco'?'Preço Venda':'Margem Alvo %';
    // Troca inputs
    document.querySelectorAll('[id^="pf-"]').forEach(el => {
        if(m==='margem'){el.value='25';el.step='1';el.style.color='#c084fc'}
        else{el.step='0.01';el.style.color='#4ade80'}
    });
}

function calcular(id){
    const full=parseFloat(document.getElementById('full-'+id).value)||0;
    const ads=parseFloat(document.getElementById('ads-'+id).value)||0;
    const promo=parseFloat(document.getElementById('promo-'+id).value)||0;
    const val=parseFloat(document.getElementById('pf-'+id).value)||0;
    
    const body = {id:id, custo_full:full, custo_ads:ads, promo_pct:promo, modo:modo};
    if(modo==='margem') body.margem_alvo=val; else body.preco_final=val;
    
    fetch('/api/formacao',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{
        if(d.ok){
            if(modo==='margem') document.getElementById('pf-'+id).value=d.preco_calculado.toFixed(2);
            document.getElementById('etx-'+id).textContent=fmt(d.taxa_ml_valor);
            document.getElementById('efr-'+id).textContent=fmt(d.custo_frete);
            document.getElementById('eie-'+id).textContent=fmt(d.imposto_valor);
            document.getElementById('epr-'+id).textContent=fmt(d.custo_promo);
            document.getElementById('ect-'+id).textContent=fmt(d.custo_total_full);
            document.getElementById('eluc-'+id).textContent=fmt(d.lucro_final);
            document.getElementById('eluc-'+id).className=d.lucro_final>0?'margem-pos':'margem-neg';
            document.getElementById('emg-'+id).textContent=fmt(d.margem_final,1)+'%';
            document.getElementById('emg-'+id).className=d.margem_final>=20?'margem-pos':d.margem_final>0?'margem-warn':'margem-neg';
            document.getElementById('est-'+id).innerHTML=d.viavel?'<span class="viavel-sim">VIÁVEL</span>':'<span class="viavel-nao">NÃO</span>';
        } else showT('❌ '+d.erro,true);
    });
}

function aplicarGlobal(){
    const full=document.getElementById('fullGlobal').value;
    const ads=document.getElementById('adsGlobal').value;
    const promo=document.getElementById('promoGlobal').value;
    const margem=document.getElementById('margemAlvoGlobal').value;
    
    document.querySelectorAll('[id^="full-"]').forEach(el=>{el.value=full});
    document.querySelectorAll('[id^="ads-"]').forEach(el=>{el.value=ads});
    document.querySelectorAll('[id^="promo-"]').forEach(el=>{el.value=promo});
    if(modo==='margem') document.querySelectorAll('[id^="pf-"]').forEach(el=>{el.value=margem});
    
    // Recalcula todos
    document.querySelectorAll('[id^="full-"]').forEach(el=>{
        const id=el.dataset.id;
        calcular(parseInt(id));
    });
    showT('⚡ Valores globais aplicados');
}

function descartar(id){
    fetch('/api/descartar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[id]})})
    .then(r=>r.json()).then(d=>{if(d.ok){document.getElementById('er-'+id).remove();showT('🗑️ Removido')}});
}

function descartarTodos(){
    if(!confirm('Remover TODOS os escolhidos?'))return;
    const ids=[...document.querySelectorAll('[id^="er-"]')].map(el=>parseInt(el.id.split('-')[1]));
    fetch('/api/descartar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:ids})})
    .then(r=>r.json()).then(d=>{if(d.ok)location.reload()});
}

function showT(m,e){const t=document.getElementById('toast2');t.textContent=m;t.className='toast show'+(e?' error':'');setTimeout(()=>{t.className='toast'},2500)}

// Auto-calcula ao carregar
window.addEventListener('load',()=>{
    document.querySelectorAll('[id^="full-"]').forEach(el=>{
        const id=el.dataset.id;
        const pf=document.getElementById('pf-'+id);
        if(pf && parseFloat(pf.value)>0) calcular(parseInt(id));
    });
});
</script>
</body>
</html>
"""


@app.route('/escolhidos')
@login_required
def escolhidos():
    if not DB_PATH.exists():
        return render_template_string(ESCOLHIDOS_HTML, produtos=[], viaveis=0, nao_viaveis=0, lucro_total=0, margem_media=0)
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM produtos WHERE escolhido = 1 ORDER BY fornecedor, codigo")
    produtos = [dict(r) for r in cur.fetchall()]
    conn.close()
    
    viaveis = sum(1 for p in produtos if (p.get('margem_final') or 0) >= 20)
    nao_viaveis = len(produtos) - viaveis
    lucros = [p.get('lucro_final') or 0 for p in produtos if p.get('lucro_final')]
    lucro_total = sum(lucros)
    margens = [p.get('margem_final') or 0 for p in produtos if p.get('margem_final')]
    margem_media = sum(margens) / len(margens) if margens else 0
    
    return render_template_string(ESCOLHIDOS_HTML, produtos=produtos, viaveis=viaveis, nao_viaveis=nao_viaveis, lucro_total=lucro_total, margem_media=margem_media)


@app.route('/exportar-escolhidos')
@login_required
def exportar_escolhidos():
    try:
        import pandas as pd
        conn = get_conn()
        df = pd.read_sql_query("SELECT * FROM produtos WHERE escolhido = 1 ORDER BY fornecedor, codigo", conn)
        conn.close()
        rename = {'codigo':'Código','fornecedor':'Fornecedor','descricao':'Produto',
            'custo':'Custo','preco_ml':'Preço ML Ref','preco_final':'Preço Venda',
            'taxa_categoria':'Taxa Cat.','custo_full':'Full R$','custo_ads':'ADS R$',
            'promo_percentual':'Promo %','peso_kg':'Peso kg','custo_frete':'Frete',
            'custo_embalagem':'Embalagem','imposto_valor':'Imposto',
            'lucro_final':'Lucro R$','margem_final':'Margem %','link_ml':'Link ML'}
        df = df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
        df = df.drop(columns=[c for c in ['id','viavel','escolhido','notas','data_analise','taxa_fixa_ml','custo_total','margem_percentual','margem_reais','margem_alvo','pagina_origem','arquivo_origem'] if c in df.columns], errors='ignore')
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as w:
            df.to_excel(w, index=False, sheet_name='Escolhidos')
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True, download_name=f"QUBO_Escolhidos_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
    except Exception as e:
        return f"Erro: {e}", 500


# ============================================================
# PÁGINA PROCESSAR PDFs
# ============================================================

# Estado global do processamento
processamento_status = {
    'rodando': False,
    'total_pdfs': 0,
    'processados': 0,
    'pdf_atual': '',
    'produtos_extraidos': 0,
    'erros': 0,
    'log': [],
    'concluido': False
}

PROCESSAR_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚀 Processar PDFs — QUBO</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e27;color:#e4e6eb;padding:14px;font-size:13px}
        .container{max-width:1200px;margin:0 auto}
        h1{font-size:1.5rem;margin-bottom:14px;background:linear-gradient(135deg,#f59e0b 0%,#ef4444 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;display:inline-block}
        .header-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
        
        button,.btn{padding:8px 18px;border:none;border-radius:5px;cursor:pointer;font-size:.85rem;font-weight:600;transition:all .15s;text-decoration:none;display:inline-block}
        .btn-primary{background:#667eea;color:#fff}.btn-secondary{background:#2d3452;color:#e4e6eb}
        .btn-start{background:#f59e0b;color:#000;font-size:1rem;padding:12px 30px}.btn-start:hover{background:#d97706}
        .btn-start:disabled{background:#4b5563;color:#8b92a5;cursor:not-allowed}
        
        .card{background:#1a1f3a;padding:14px;border-radius:7px;border:1px solid #2d3452;margin-bottom:12px}
        .card h3{color:#8b92a5;font-size:.75rem;text-transform:uppercase;margin-bottom:8px}
        
        .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
        .stat-card{background:#1a1f3a;padding:12px;border-radius:7px;border:1px solid #2d3452;text-align:center}
        .stat-value{font-size:1.6rem;font-weight:bold;color:#667eea}
        .stat-value.green{color:#4ade80}.stat-value.red{color:#f87171}.stat-value.yellow{color:#fbbf24}
        .stat-label{color:#8b92a5;font-size:.68rem;text-transform:uppercase;margin-top:3px}
        
        .api-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
        .api-item{background:#0a0e27;padding:10px;border-radius:5px;display:flex;justify-content:space-between;align-items:center}
        .api-name{font-weight:600;font-size:.85rem}
        .api-ok{color:#4ade80}.api-no{color:#f87171}
        
        .progress-wrap{margin:14px 0}
        .progress-bar{height:24px;background:#2d3452;border-radius:12px;overflow:hidden;position:relative}
        .progress-fill{height:100%;background:linear-gradient(90deg,#667eea,#4ade80);border-radius:12px;transition:width .5s;width:0%}
        .progress-text{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-weight:700;font-size:.8rem;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.5)}
        
        .pdf-atual{font-size:1rem;color:#fbbf24;font-weight:600;margin:8px 0}
        
        .log-box{background:#0a0e27;border:1px solid #2d3452;border-radius:5px;padding:10px;max-height:300px;overflow-y:auto;font-family:monospace;font-size:.75rem;line-height:1.6}
        .log-ok{color:#4ade80}.log-err{color:#f87171}.log-info{color:#8b92a5}.log-warn{color:#fbbf24}
    </style>
</head>
<body>
<div class="container">
    <div class="header-row">
        <h1>🚀 Processar Catálogos PDF</h1>
        <a href="/" class="btn btn-secondary">← Dashboard</a>
    </div>

    <!-- STATUS APIs -->
    <div class="card">
        <h3>🔑 Status dos Providers</h3>
        <div class="api-grid" id="apiGrid">
            {% for api in apis %}
            <div class="api-item">
                <span class="api-name">{{ api.icon }} {{ api.nome }}</span>
                <span class="{{ 'api-ok' if api.ok else 'api-no' }}">
                    {{ '✅ ' + api.info if api.ok else '❌ Não configurado' }}
                </span>
            </div>
            {% endfor %}
        </div>
    </div>

    <!-- STATS PDFs -->
    <div class="stats">
        <div class="stat-card"><div class="stat-value">{{ pdf_stats.total }}</div><div class="stat-label">PDFs na Pasta</div></div>
        <div class="stat-card"><div class="stat-value green">{{ pdf_stats.processados }}</div><div class="stat-label">Já Processados</div></div>
        <div class="stat-card"><div class="stat-value yellow">{{ pdf_stats.pendentes }}</div><div class="stat-label">Pendentes</div></div>
        <div class="stat-card"><div class="stat-value">{{ pdf_stats.produtos_banco }}</div><div class="stat-label">Produtos no Banco</div></div>
    </div>

    <!-- BOTÃO INICIAR -->
    <div style="text-align:center;margin:16px 0">
        <button class="btn btn-start" id="btnIniciar" onclick="iniciarProcessamento()" {% if pdf_stats.pendentes == 0 %}disabled{% endif %}>
            🚀 Processar {{ pdf_stats.pendentes }} PDFs Pendentes
        </button>
    </div>

    <!-- CONFERÊNCIA: PRODUTOS POR PDF -->
    {% if pdf_stats.por_arquivo %}
    <div class="card">
        <h3>📋 Conferência — Produtos por Catálogo ({{ pdf_stats.por_arquivo|length }} PDFs → {{ pdf_stats.produtos_banco }} produtos)</h3>
        <table style="width:100%;border-collapse:collapse;font-size:.8rem;margin-top:8px">
            <thead><tr>
                <th style="text-align:left;padding:5px 8px;border-bottom:1px solid #2d3452;color:#8b92a5">#</th>
                <th style="text-align:left;padding:5px 8px;border-bottom:1px solid #2d3452;color:#8b92a5">Fornecedor</th>
                <th style="text-align:left;padding:5px 8px;border-bottom:1px solid #2d3452;color:#8b92a5">Arquivo</th>
                <th style="text-align:right;padding:5px 8px;border-bottom:1px solid #2d3452;color:#8b92a5">Produtos</th>
            </tr></thead>
            <tbody>
            {% for item in pdf_stats.por_arquivo %}
            <tr style="border-bottom:1px solid #1a1f3a">
                <td style="padding:4px 8px;color:#8b92a5">{{ loop.index }}</td>
                <td style="padding:4px 8px;color:#f093fb;font-weight:600">{{ item.fornecedor }}</td>
                <td style="padding:4px 8px;color:#8b92a5;font-size:.75rem">{{ item.arquivo }}</td>
                <td style="padding:4px 8px;text-align:right;color:#4ade80;font-weight:700">{{ item.qtd }}</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}

    <!-- PROGRESSO -->
    <div id="progressArea" style="display:none">
        <div class="card">
            <h3>📊 Progresso</h3>
            <div class="progress-wrap">
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill"></div>
                    <div class="progress-text" id="progressText">0%</div>
                </div>
            </div>
            <div class="pdf-atual" id="pdfAtual">Preparando...</div>
            <div class="stats" style="margin-bottom:0">
                <div class="stat-card"><div class="stat-value" id="stProc">0</div><div class="stat-label">Processados</div></div>
                <div class="stat-card"><div class="stat-value green" id="stProd">0</div><div class="stat-label">Produtos</div></div>
                <div class="stat-card"><div class="stat-value red" id="stErro">0</div><div class="stat-label">Erros</div></div>
                <div class="stat-card"><div class="stat-value yellow" id="stRest">0</div><div class="stat-label">Restantes</div></div>
            </div>
        </div>

        <!-- LOG -->
        <div class="card">
            <h3>📋 Log</h3>
            <div class="log-box" id="logBox"></div>
        </div>
    </div>
</div>

<script>
let polling = null;

function iniciarProcessamento(){
    document.getElementById('btnIniciar').disabled=true;
    document.getElementById('btnIniciar').textContent='⏳ Processando...';
    document.getElementById('progressArea').style.display='block';
    
    fetch('/api/processar-pdfs',{method:'POST'})
    .then(r=>r.json()).then(d=>{
        if(d.ok){
            polling=setInterval(atualizarStatus,1500);
        }
    });
}

function atualizarStatus(){
    fetch('/api/status-processamento')
    .then(r=>r.json()).then(d=>{
        const pct = d.total_pdfs>0 ? Math.round((d.processados/d.total_pdfs)*100) : 0;
        document.getElementById('progressFill').style.width=pct+'%';
        document.getElementById('progressText').textContent=pct+'%';
        document.getElementById('pdfAtual').textContent=d.pdf_atual||'...';
        document.getElementById('stProc').textContent=d.processados;
        document.getElementById('stProd').textContent=d.produtos_extraidos;
        document.getElementById('stErro').textContent=d.erros;
        document.getElementById('stRest').textContent=d.total_pdfs-d.processados;
        
        // Log
        const box=document.getElementById('logBox');
        box.innerHTML=d.log.map(l=>{
            let cls='log-info';
            if(l.includes('✅'))cls='log-ok';
            else if(l.includes('❌'))cls='log-err';
            else if(l.includes('⚠'))cls='log-warn';
            return '<div class="'+cls+'">'+l+'</div>';
        }).join('');
        box.scrollTop=box.scrollHeight;
        
        if(d.concluido){
            clearInterval(polling);
            document.getElementById('btnIniciar').textContent='✅ Concluído! Recarregar';
            document.getElementById('btnIniciar').disabled=false;
            document.getElementById('btnIniciar').onclick=()=>location.reload();
            document.getElementById('pdfAtual').textContent='🎉 Processamento finalizado!';
        }
    });
}
</script>
</body>
</html>
"""

@app.route('/processar')
@login_required
def pagina_processar():
    import os as _os
    from dotenv import load_dotenv
    load_dotenv()
    
    # Status APIs
    apis = []
    
    # Groq
    groq_keys = []
    k1 = _os.getenv('GROQ_API_KEY', '')
    if k1: groq_keys.append(k1)
    for i in range(2, 31):
        k = _os.getenv(f'GROQ_API_KEY_{i}', '')
        if k: groq_keys.append(k)
    apis.append({'nome': 'Groq', 'icon': '🟦', 'ok': len(groq_keys) > 0, 'info': f'{len(groq_keys)} keys'})
    
    # Mistral
    mk = _os.getenv('MISTRAL_API_KEY', '')
    apis.append({'nome': 'Mistral', 'icon': '🟧', 'ok': bool(mk) and mk != 'SUA_KEY_MISTRAL_AQUI', 'info': 'Ativa'})
    
    # Together
    tk = _os.getenv('TOGETHER_API_KEY', '')
    apis.append({'nome': 'Together AI', 'icon': '🟩', 'ok': bool(tk) and tk != 'SUA_KEY_TOGETHER_AQUI', 'info': 'Ativa'})
    
    # OpenRouter
    ork = _os.getenv('OPENROUTER_API_KEY', '')
    apis.append({'nome': 'OpenRouter', 'icon': '🟪', 'ok': bool(ork) and ork != 'SUA_KEY_OPENROUTER_AQUI', 'info': 'Ativa'})
    
    # Stats PDFs
    pasta = _os.getenv('PASTA_MONITORADA', '')
    pdf_stats = {'total': 0, 'processados': 0, 'pendentes': 0, 'produtos_banco': 0}
    
    if pasta and Path(pasta).exists():
        pdfs = list(Path(pasta).rglob("*.pdf"))
        pdf_stats['total'] = len(pdfs)
        
        proc_file = Path("data/pdfs_processados.json")
        processados = set()
        if proc_file.exists():
            try:
                processados = set(json.loads(proc_file.read_text()))
            except:
                pass
        pdf_stats['processados'] = sum(1 for p in pdfs if str(p) in processados)
        pdf_stats['pendentes'] = pdf_stats['total'] - pdf_stats['processados']
    
    if DB_PATH.exists():
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM produtos")
        pdf_stats['produtos_banco'] = cur.fetchone()[0]
        # Contagem por arquivo/fornecedor para conferência
        cur.execute("""SELECT fornecedor, arquivo_origem, COUNT(*) as qtd 
            FROM produtos GROUP BY arquivo_origem ORDER BY fornecedor""")
        pdf_stats['por_arquivo'] = [{'fornecedor': r[0], 'arquivo': r[1], 'qtd': r[2]} for r in cur.fetchall()]
        conn.close()
    else:
        pdf_stats['por_arquivo'] = []
    
    return render_template_string(PROCESSAR_HTML, apis=apis, pdf_stats=pdf_stats)


@app.route('/api/processar-pdfs', methods=['POST'])
def api_processar_pdfs():
    """Inicia processamento em background"""
    global processamento_status
    
    if processamento_status['rodando']:
        return jsonify({'ok': False, 'erro': 'Já está processando!'})
    
    # Reset status
    processamento_status = {
        'rodando': True, 'total_pdfs': 0, 'processados': 0,
        'pdf_atual': '', 'produtos_extraidos': 0, 'erros': 0,
        'log': ['🚀 Iniciando processamento...'], 'concluido': False
    }
    
    # Roda em background
    t = threading.Thread(target=_processar_background, daemon=True)
    t.start()
    
    return jsonify({'ok': True})


def _processar_background():
    """Processamento real em thread separada"""
    global processamento_status
    
    try:
        import os as _os
        from dotenv import load_dotenv
        load_dotenv()
        
        pasta = _os.getenv('PASTA_MONITORADA', '')
        if not pasta or not Path(pasta).exists():
            processamento_status['log'].append('❌ Pasta não configurada ou não existe!')
            processamento_status['concluido'] = True
            processamento_status['rodando'] = False
            return
        
        # Lista PDFs pendentes
        proc_file = Path("data/pdfs_processados.json")
        processados = set()
        if proc_file.exists():
            try:
                processados = set(json.loads(proc_file.read_text()))
            except:
                pass
        
        pdfs = [p for p in Path(pasta).rglob("*.pdf") if str(p) not in processados]
        processamento_status['total_pdfs'] = len(pdfs)
        processamento_status['log'].append(f'📄 {len(pdfs)} PDFs pendentes encontrados')
        
        if not pdfs:
            processamento_status['log'].append('✅ Nenhum PDF pendente!')
            processamento_status['concluido'] = True
            processamento_status['rodando'] = False
            return
        
        # Importa extrator
        try:
            from multi_extractor import MultiExtractor
            extractor = MultiExtractor()
            processamento_status['log'].append(f'🤖 Extrator inicializado ({len(extractor.providers)} providers)')
        except Exception as e:
            processamento_status['log'].append(f'❌ Erro ao carregar extrator: {str(e)[:80]}')
            processamento_status['concluido'] = True
            processamento_status['rodando'] = False
            return
        
        # Processa cada PDF
        for i, pdf_path in enumerate(pdfs):
            try:
                nome_pdf = pdf_path.name
                # Fornecedor = nome do arquivo sem extensão
                fornecedor = pdf_path.stem
                
                processamento_status['pdf_atual'] = f'📄 [{i+1}/{len(pdfs)}] {nome_pdf}'
                processamento_status['log'].append(f'📄 Processando: {nome_pdf}')
                
                # Extrai
                produtos, info = extractor.extrair_de_pdf(str(pdf_path), fornecedor)
                
                if produtos:
                    # Salva no banco
                    conn = get_conn()
                    cur = conn.cursor()
                    
                    # Garante tabela existe
                    cur.execute("""CREATE TABLE IF NOT EXISTS produtos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codigo TEXT, fornecedor TEXT, descricao TEXT, custo REAL,
                        data_analise TEXT, arquivo_origem TEXT, pagina_origem INTEGER DEFAULT 0
                    )""")
                    
                    salvos = 0
                    for p in produtos:
                        try:
                            # Fornecedor = nome do arquivo, página do catálogo
                            pagina = getattr(p, 'pagina_origem', 0) or getattr(p, 'pagina', 0) or 0
                            cur.execute("""INSERT INTO produtos (codigo, fornecedor, descricao, custo, data_analise, arquivo_origem, pagina_origem)
                                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (p.codigo, fornecedor, p.descricao,
                                 p.preco_unitario, datetime.now().isoformat(), nome_pdf, pagina))
                            salvos += 1
                        except Exception:
                            pass
                    
                    conn.commit()
                    conn.close()
                    
                    processamento_status['produtos_extraidos'] += salvos
                    processamento_status['log'].append(f'   ✅ {salvos} produtos extraídos de {nome_pdf}')
                else:
                    processamento_status['log'].append(f'   ⚠️ Nenhum produto encontrado em {nome_pdf}')
                
                # Marca como processado
                processados.add(str(pdf_path))
                proc_file.parent.mkdir(exist_ok=True)
                proc_file.write_text(json.dumps(list(processados), indent=2))
                
                processamento_status['processados'] = i + 1
                
            except Exception as e:
                processamento_status['erros'] += 1
                processamento_status['log'].append(f'   ❌ Erro: {str(e)[:80]}')
                processamento_status['processados'] = i + 1
        
        # Garante schema completo
        garantir_schema()
        
        total_p = processamento_status['produtos_extraidos']
        processamento_status['log'].append(f'')
        processamento_status['log'].append(f'🎉 CONCLUÍDO! {processamento_status["processados"]} PDFs → {total_p} produtos')
        
    except Exception as e:
        processamento_status['log'].append(f'❌ Erro fatal: {str(e)[:100]}')
    
    processamento_status['concluido'] = True
    processamento_status['rodando'] = False


@app.route('/api/status-processamento')
def api_status_processamento():
    return jsonify(processamento_status)


# ============================================================
# INTEGRAÇÃO ML - OAUTH + LISTING PRICES
# ============================================================

ML_AUTH_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>🔗 Autenticação Mercado Livre — QUBO</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e27;color:#e4e6eb;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}
        .card{background:#1a1f3a;padding:30px;border-radius:12px;border:1px solid #2d3452;max-width:600px;width:100%}
        h1{font-size:1.5rem;margin-bottom:20px;background:linear-gradient(135deg,#fbbf24 0%,#f59e0b 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
        .step{background:#0a0e27;padding:16px;border-radius:8px;margin-bottom:14px;border-left:3px solid #667eea}
        .step-num{color:#667eea;font-weight:700;font-size:1.1rem;margin-bottom:6px}
        .step p{color:#8b92a5;font-size:.88rem;line-height:1.5}
        a.link{color:#fbbf24;text-decoration:none;font-weight:600;word-break:break-all}
        a.link:hover{text-decoration:underline}
        input{width:100%;padding:10px 14px;border:1px solid #2d3452;border-radius:6px;background:#0a0e27;color:#4ade80;font-size:1rem;font-family:monospace;margin-top:8px}
        input:focus{border-color:#667eea;outline:none;box-shadow:0 0 0 2px rgba(102,126,234,.3)}
        button{padding:10px 24px;border:none;border-radius:6px;cursor:pointer;font-size:.95rem;font-weight:700;margin-top:12px;transition:all .15s}
        .btn-auth{background:#f59e0b;color:#000}.btn-auth:hover{background:#d97706}
        .btn-back{background:#2d3452;color:#e4e6eb;margin-left:8px}
        .status{margin-top:16px;padding:12px;border-radius:6px;font-weight:600}
        .status-ok{background:#064e3b;color:#4ade80;border:1px solid #065f46}
        .status-err{background:#450a0a;color:#fca5a5;border:1px solid #7f1d1d}
        .status-info{background:#1e3a5f;color:#93c5fd;border:1px solid #2563eb}
        .current{margin-bottom:20px;padding:12px;border-radius:8px}
        .current-ok{background:#064e3b;border:1px solid #065f46}
        .current-no{background:#450a0a;border:1px solid #7f1d1d}
    </style>
</head>
<body>
<div class="card">
    <h1>🔗 Autenticação Mercado Livre</h1>
    
    <!-- STATUS ATUAL -->
    <div class="current {{ 'current-ok' if autenticado else 'current-no' }}">
        {% if autenticado %}
            ✅ <strong>Conectado!</strong> user_id: {{ user_id }}
            <br><span style="color:#8b92a5;font-size:.8rem">Token válido. Busca ML e taxas automáticas funcionando.</span>
        {% else %}
            ❌ <strong>Não conectado</strong>
            <br><span style="color:#8b92a5;font-size:.8rem">Siga os 3 passos abaixo para conectar.</span>
        {% endif %}
    </div>

    <!-- PASSO 1 -->
    <div class="step">
        <div class="step-num">Passo 1 — Clique no link abaixo</div>
        <p>Vai abrir a página do Mercado Livre para autorizar.</p>
        <a href="{{ auth_url }}" target="_blank" class="link">🔗 Clique aqui para autorizar no ML</a>
    </div>

    <!-- PASSO 2 -->
    <div class="step">
        <div class="step-num">Passo 2 — Copie o código</div>
        <p>Depois de autorizar, o ML vai redirecionar para o Google.<br>
        Na <strong>barra de endereço</strong> do navegador, copie o valor depois de <code>code=</code></p>
        <p style="color:#fbbf24;font-size:.78rem;margin-top:6px">
            Exemplo: https://www.google.com?<strong>code=TG-67b83...</strong><br>
            Copie tudo depois de <code>code=</code>
        </p>
    </div>

    <!-- PASSO 3 -->
    <div class="step">
        <div class="step-num">Passo 3 — Cole aqui e conecte</div>
        <p>Cole o código completo (começa com TG-):</p>
        <input type="text" id="codeInput" placeholder="TG-67b83abc-1234-5678-abcd..." autofocus>
        <div>
            <button class="btn-auth" onclick="conectar()">🚀 Conectar</button>
            <button class="btn-back" onclick="location.href='/'">← Dashboard</button>
        </div>
    </div>

    <div id="statusMsg"></div>
</div>

<script>
function conectar(){
    const code = document.getElementById('codeInput').value.trim();
    if(!code){alert('Cole o código primeiro!');return;}
    
    const btn = document.querySelector('.btn-auth');
    btn.disabled=true; btn.textContent='⏳ Conectando...';
    
    fetch('/api/ml-auth',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({code:code})
    }).then(r=>r.json()).then(d=>{
        btn.disabled=false; btn.textContent='🚀 Conectar';
        const el = document.getElementById('statusMsg');
        if(d.ok){
            el.innerHTML='<div class="status status-ok">✅ Conectado com sucesso! user_id: '+d.user_id+'<br>Recarregando...</div>';
            setTimeout(()=>location.reload(),1500);
        } else {
            el.innerHTML='<div class="status status-err">❌ Erro: '+d.erro+'</div>';
        }
    }).catch(()=>{
        btn.disabled=false; btn.textContent='🚀 Conectar';
        document.getElementById('statusMsg').innerHTML='<div class="status status-err">❌ Erro de conexão</div>';
    });
}
document.getElementById('codeInput').addEventListener('keydown',e=>{if(e.key==='Enter')conectar()});
</script>
</body>
</html>
"""

@app.route('/ml-auth')
@login_required
def pagina_ml_auth():
    try:
        from ml_buscador import MLBuscador
        ml = MLBuscador()
        return render_template_string(ML_AUTH_HTML,
            autenticado=ml.esta_autenticado(),
            user_id=ml.auth.user_id or '',
            auth_url=ml.get_auth_url())
    except Exception as e:
        return render_template_string(ML_AUTH_HTML,
            autenticado=False, user_id='', auth_url='#',
            erro=str(e))


@app.route('/api/ml-auth', methods=['POST'])
def api_ml_auth():
    try:
        from ml_buscador import MLBuscador
        d = request.get_json()
        code = d.get('code', '').strip()
        if not code:
            return jsonify({'ok': False, 'erro': 'Código vazio'})
        
        ml = MLBuscador()
        resultado = ml.trocar_codigo(code)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


@app.route('/api/ml-status')
def api_ml_status():
    try:
        from ml_buscador import MLBuscador
        ml = MLBuscador()
        return jsonify({
            'autenticado': ml.esta_autenticado(),
            'user_id': ml.auth.user_id
        })
    except:
        return jsonify({'autenticado': False})


@app.route('/api/ml-teste')
def api_ml_teste():
    """Rota de diagnostico - testa busca ML e mostra resposta crua"""
    try:
        from ml_buscador import MLBuscador
        import requests as req
        
        ml = MLBuscador()
        
        if not ml.auth.esta_autenticado():
            return jsonify({'erro': 'Nao autenticado', 'token': None})
        
        # Teste 1: busca simples
        headers = ml.auth.get_headers()
        termo = request.args.get('q', 'garrafa termica')
        
        resp = req.get(
            f'https://api.mercadolibre.com/sites/MLB/search',
            headers=headers,
            params={'q': termo, 'limit': 3},
            timeout=15
        )
        
        busca_raw = {
            'status_code': resp.status_code,
            'termo': termo,
        }
        
        if resp.status_code == 200:
            data = resp.json()
            busca_raw['total'] = data.get('paging', {}).get('total', 0)
            busca_raw['resultados'] = len(data.get('results', []))
            if data.get('results'):
                r0 = data['results'][0]
                busca_raw['primeiro'] = {
                    'id': r0.get('id'),
                    'titulo': r0.get('title'),
                    'preco': r0.get('price'),
                    'categoria': r0.get('category_id'),
                }
                
                # Teste 2: listing_prices com a categoria
                cat = r0.get('category_id', '')
                preco = r0.get('price', 100)
                if cat:
                    resp2 = req.get(
                        f'https://api.mercadolibre.com/sites/MLB/listing_prices',
                        headers=headers,
                        params={'price': preco, 'category_id': cat, 'currency_id': 'BRL'},
                        timeout=15
                    )
                    busca_raw['listing_prices'] = {
                        'status': resp2.status_code,
                        'resposta': resp2.json() if resp2.status_code == 200 else resp2.text[:200]
                    }
        else:
            busca_raw['resposta_erro'] = resp.text[:500]
        
        return jsonify({
            'autenticado': True,
            'user_id': ml.auth.user_id,
            'token_prefixo': ml.auth.access_token[:20] + '...' if ml.auth.access_token else None,
            'busca': busca_raw
        })
    except Exception as e:
        return jsonify({'erro': str(e)})


@app.route('/api/ml-taxa', methods=['POST'])
def api_ml_taxa():
    """Calcula taxa real ML via listing_prices"""
    try:
        from ml_buscador import MLBuscador
        d = request.get_json()
        termo = d.get('termo', '')
        preco = float(d.get('preco', 0))
        
        ml = MLBuscador()
        if not ml.esta_autenticado():
            return jsonify({'ok': False, 'erro': 'Conecte-se ao ML em /ml-auth'})
        
        resultado = ml.buscar_taxa_por_produto(termo, preco if preco > 0 else None)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


@app.route('/api/atualizar-taxas-ml', methods=['POST'])
def api_atualizar_taxas_ml():
    """Busca taxa ML real para todos os produtos de uma vez"""
    try:
        from ml_buscador import MLBuscador
        import re
        
        ml = MLBuscador()
        if not ml.esta_autenticado():
            return jsonify({'ok': False, 'erro': 'Conecte-se ao ML primeiro! Clique em 🔗 ML Auth'})
        
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, descricao, preco_ml, taxa_categoria FROM produtos")
        produtos = [dict(r) for r in cur.fetchall()]
        
        total = len(produtos)
        atualizados = 0
        erros = 0
        
        for p in produtos:
            try:
                desc = p['descricao'] or ''
                if not desc:
                    continue
                
                # Limpa descrição pra buscar (mesmo regex do JS)
                termo = desc.upper()
                termo = re.sub(r'\d+[\.,]?\d*\s*(MM|CM|M|KG|G|ML|L|UN|PCS|PÇS|PC|UND)\b', '', termo, flags=re.IGNORECASE)
                termo = re.sub(r'\b\d+[Xx×]\d+\b', '', termo)
                termo = re.sub(r'\b\d{2,}\b', '', termo)
                termo = re.sub(r'\b(COM|PARA|POR|SEM|DOS|DAS|DEL|UMA|UNS|NAS|NOS|TIPO|REF|COD|MODELO|UNID|COR|TAM)\b', '', termo, flags=re.IGNORECASE)
                termo = re.sub(r'[+\-\*\/\(\)\[\]\{\}#@&%$!;:=\'"]+', ' ', termo)
                termo = re.sub(r'\s+', ' ', termo).strip()
                
                # Pega até 4 palavras com 3+ chars
                palavras = [w for w in termo.split() if len(w) >= 3]
                if len(palavras) > 4:
                    palavras = palavras[:4]
                termo_busca = ' '.join(palavras)
                
                if not termo_busca or len(termo_busca) < 3:
                    continue
                
                # Busca no ML pra pegar categoria
                busca = ml.buscar_produto(termo_busca, limite=3)
                
                if not busca.get('encontrado') or not busca.get('resultados'):
                    continue
                
                categoria = busca['resultados'][0].get('categoria', '')
                preco_ref = p['preco_ml'] or busca['resultados'][0].get('preco', 100)
                
                if not categoria:
                    continue
                
                # Busca taxa real dessa categoria
                taxa_info = ml.calcular_taxa_ml(preco_ref, category_id=categoria)
                
                if taxa_info.get('ok') and taxa_info.get('taxa_percentual'):
                    taxa_pct = taxa_info['taxa_percentual'] / 100  # Converte pra decimal
                    
                    # Só atualiza se é diferente
                    taxa_atual = p['taxa_categoria'] or 0.165
                    if abs(taxa_pct - taxa_atual) > 0.001:
                        cur.execute("UPDATE produtos SET taxa_categoria=? WHERE id=?", (taxa_pct, p['id']))
                        atualizados += 1
                    else:
                        atualizados += 1  # Já estava certa
                
                # Delay pra não estourar rate limit do ML
                time.sleep(0.4)
                
            except Exception as e:
                erros += 1
                logger.warning(f"⚠️ Erro ao buscar taxa para #{p['id']}: {e}")
                continue
        
        conn.commit()
        
        # Recalcula viabilidade de todos com novas taxas
        aliq = get_aliquota()
        cur.execute("SELECT id, custo, preco_ml, taxa_categoria, peso_kg, custo_embalagem, custo_ads FROM produtos WHERE preco_ml > 0")
        rows = cur.fetchall()
        for row in rows:
            pid, custo, pml, taxa, peso, emb, ads = row['id'], row['custo'], row['preco_ml'], row['taxa_categoria'], row['peso_kg'], row['custo_embalagem'], row['custo_ads']
            r = calcular_viabilidade_completa(custo or 0, pml, taxa or 0.165, peso or 0, emb or 0, aliq, ads or 0)
            cur.execute("""UPDATE produtos SET taxa_fixa_ml=?,imposto_valor=?,custo_frete=?,custo_total=?,
                margem_percentual=?,margem_reais=?,viavel=? WHERE id=?""",
                (r['taxa_fixa'],r['imposto_valor'],r['custo_frete'],r['custo_total'],r['margem_percentual'],r['margem_reais'],r['viavel'],pid))
        
        conn.commit()
        conn.close()
        
        return jsonify({'ok': True, 'total': total, 'atualizados': atualizados, 'erros': erros})
    except ImportError:
        return jsonify({'ok': False, 'erro': 'ml_buscador.py não encontrado'})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})



@app.route('/api/upload-pdf', methods=['POST'])
@login_required
def api_upload_pdf():
    """Upload e processamento de PDF diretamente pelo dashboard"""
    import tempfile
    import os as _os
    
    try:
        if 'arquivo' not in request.files:
            return jsonify({'ok': False, 'erro': 'Nenhum arquivo enviado'})
        
        arquivo = request.files['arquivo']
        if not arquivo.filename.lower().endswith('.pdf'):
            return jsonify({'ok': False, 'erro': 'Apenas arquivos PDF são aceitos'})
        
        from multi_extractor import MultiExtractor
        from auth import get_tenant_id
        
        tenant = get_tenant_id()
        fornecedor = _os.path.splitext(arquivo.filename)[0]
        nome_arquivo = arquivo.filename
        
        # Salva temporariamente
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            arquivo.save(tmp.name)
            tmp_path = tmp.name
        
        try:
            extractor = MultiExtractor()
            produtos, info = extractor.extrair_de_pdf(tmp_path, fornecedor)
        finally:
            try:
                _os.unlink(tmp_path)
            except Exception:
                pass
        
        if not produtos:
            return jsonify({'ok': False, 'erro': f'Nenhum produto encontrado em {nome_arquivo}'})
        
        # Salva no banco com tenant_id
        conn = get_conn()
        cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        
        # Garante schema
        garantir_schema()
        
        salvos = 0
        from datetime import datetime
        for p in produtos:
            try:
                cur.execute(
                    f"""INSERT INTO produtos 
                        (tenant_id, codigo, fornecedor, descricao, custo, data_analise, arquivo_origem)
                        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
                    (tenant, p.codigo, fornecedor, p.descricao,
                     p.preco_unitario, datetime.now().isoformat(), nome_arquivo)
                )
                salvos += 1
            except Exception as e:
                logger.warning(f"Erro ao salvar produto: {e}")
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'ok': True,
            'arquivo': nome_arquivo,
            'fornecedor': fornecedor,
            'produtos_extraidos': salvos,
            'provider': info.get('provider', 'desconhecido')
        })
        
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/tendencias')
def api_tendencias():
    """Painel de Tendências ML"""
    try:
        from ml_buscador import MLBuscador
        from agente_tendencias import buscar_tendencias
        ml = MLBuscador()
        if not ml.esta_autenticado():
            return jsonify({'ok': False, 'erro': 'Conecte-se ao ML primeiro!'})
        resultado = buscar_tendencias(ml.auth.access_token)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


@app.route('/api/saude-anuncios')
def api_saude_anuncios():
    """Monitor de Saúde dos Anúncios"""
    try:
        from ml_buscador import MLBuscador
        from agente_saude import monitorar_saude
        ml = MLBuscador()
        if not ml.esta_autenticado():
            return jsonify({'ok': False, 'erro': 'Conecte-se ao ML primeiro!'})
        resultado = monitorar_saude(ml.auth.access_token, ml.auth.user_id)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/viabilidade', methods=['POST'])
def api_viabilidade():
    """Agente de Viabilidade de Produto"""
    try:
        from ml_buscador import MLBuscador
        from agente_viabilidade import analisar_viabilidade
        d = request.get_json()
        produto_id = d.get('id')
        termo = d.get('termo', '')
        custo = float(d.get('custo', 0))
        peso = float(d.get('peso', 0))
        emb = float(d.get('embalagem', 0))
        imp = float(d.get('imposto', 0))
        margem = float(d.get('margem_minima', 20))
        ml = MLBuscador()
        if not ml.esta_autenticado():
            return jsonify({'ok': False, 'erro': 'Conecte-se ao ML primeiro!'})
        resultado = analisar_viabilidade(
            termo_ou_id=termo,
            token_ml=ml.auth.access_token,
            custo=custo, peso_kg=peso, embalagem=emb,
            imposto_pct=imp, margem_minima=margem,
            produto_id=produto_id
        )
        return jsonify(resultado)
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/precificar', methods=['POST'])
def api_precificar():
    """Agente de Precificação Inteligente"""
    try:
        from ml_buscador import MLBuscador
        from agente_precificacao import precificar_produto

        d = request.get_json()
        produto_id = d.get('id')
        margem_minima = float(d.get('margem_minima', 20))
        imposto_pct = float(d.get('imposto_pct', 0))

        if not produto_id:
            return jsonify({'ok': False, 'erro': 'ID obrigatório'})

        ml = MLBuscador()
        if not ml.esta_autenticado():
            return jsonify({'ok': False, 'erro': 'Conecte-se ao ML primeiro!'})

        resultado = precificar_produto(produto_id, ml.auth.access_token,
                                        margem_minima, imposto_pct)
        return jsonify(resultado)

    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


@app.route('/api/alerta-diario')
def api_alerta_diario():
    """Agente de Alerta Diário"""
    try:
        from ml_buscador import MLBuscador
        from agente_alerta import gerar_alerta_diario

        ml = MLBuscador()
        if not ml.esta_autenticado():
            return jsonify({'ok': False, 'erro': 'Conecte-se ao ML primeiro!'})

        resultado = gerar_alerta_diario(ml.auth.access_token, ml.auth.user_id)
        return jsonify(resultado)

    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


@app.route('/api/pesquisar-produto', methods=['POST'])
def api_pesquisar_produto():
    """Agente de Pesquisa de Produto — analisa mercado no ML"""
    try:
        from ml_buscador import MLBuscador
        from agente_pesquisa import analisar_produto_ml
        
        d = request.get_json()
        produto_id = d.get('id')
        
        if not produto_id:
            return jsonify({'ok': False, 'erro': 'ID do produto obrigatório'})
        
        ml = MLBuscador()
        if not ml.esta_autenticado():
            return jsonify({'ok': False, 'erro': 'Conecte-se ao ML primeiro! Clique em 🔗 ML Auth'})
        
        token = ml.auth.access_token
        resultado = analisar_produto_ml(produto_id, token)
        
        return jsonify(resultado)
        
    except ImportError as e:
        return jsonify({'ok': False, 'erro': f'Módulo não encontrado: {e}'})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})


def abrir_nav():
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000')

if __name__ == "__main__":
    import os as _os
    # Render usa PORT dinamico; local usa 5000
    port = int(_os.getenv("PORT", 5000))
    host = "0.0.0.0"  # Obrigatorio para Render
    
    is_local = port == 5000 and not _os.getenv("RENDER")
    
    print("\n" + "="*70)
    print("  QUBO Dashboard v3")
    print("="*70)
    print(f"\n  Rodando em: http://{host}:{port}")
    print("  Ambiente:", "LOCAL" if is_local else "RENDER (producao)")
    print("\n  /processar  -> Processar PDFs")
    print("  /           -> Viabilidade")
    print("  /escolhidos -> Formacao de Preco")
    print("  /ml-auth    -> Conectar Mercado Livre")
    print("="*70)
    
    if is_local:
        threading.Thread(target=abrir_nav, daemon=True).start()
    
    app.run(host=host, port=port, debug=False)
