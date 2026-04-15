"""
dashboard_web.py - QUBO Dashboard v4
=====================================
Dashboard principal focado nos produtos da loja.
P�gina /config separada para uploads, ML Auth e configurações.

Autor: Claude para QUBO
Data: 2026-04
"""
import os, json, io, time, threading, logging
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_file, session, redirect
from db import get_conn, garantir_schema, USAR_POSTGRES
from auth import login_required, get_tenant_id, get_usuario_nome, verificar_login, LOGIN_HTML

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "qubo-secret-2026")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Filtro Jinja ─────────────────────────────────────────────────────
@app.template_filter('br')
def fmt_br(v, d=2):
    try:
        return f"{float(v):,.{d}f}".replace(",","X").replace(".",",").replace("X",".")
    except:
        return "0,00"

# ── Tabela de frete ML (110 faixas preço x peso) ─────────────────────
FRETE = [
    (79,99.99,0,0.299,11.97),(79,99.99,0.3,0.499,12.87),(79,99.99,0.5,0.999,13.47),
    (79,99.99,1,1.999,14.07),(79,99.99,2,2.999,14.97),(79,99.99,3,3.999,16.17),
    (79,99.99,4,4.999,17.07),(79,99.99,5,8.999,26.67),
    (100,119.99,0,0.299,13.97),(100,119.99,0.3,0.499,15.02),(100,119.99,0.5,0.999,15.72),
    (100,119.99,1,1.999,16.42),(100,119.99,2,2.999,17.47),(100,119.99,3,3.999,18.87),
    (100,119.99,4,4.999,19.92),(100,119.99,5,8.999,31.12),
    (120,149.99,0,0.299,15.96),(120,149.99,0.3,0.499,17.16),(120,149.99,0.5,0.999,17.96),
    (120,149.99,1,1.999,18.76),(120,149.99,2,2.999,19.96),(120,149.99,3,3.999,21.56),
    (120,149.99,4,4.999,22.76),(120,149.99,5,8.999,35.56),
    (150,199.99,0,0.299,17.96),(150,199.99,0.3,0.499,19.31),(150,199.99,0.5,0.999,20.21),
    (150,199.99,1,1.999,21.11),(150,199.99,2,2.999,22.46),(150,199.99,3,3.999,24.26),
    (150,199.99,4,4.999,25.61),(150,199.99,5,8.999,40.01),
    (200,9999,0,0.299,19.95),(200,9999,0.3,0.499,21.45),(200,9999,0.5,0.999,22.45),
    (200,9999,1,1.999,23.45),(200,9999,2,2.999,24.95),(200,9999,3,3.999,26.95),
    (200,9999,4,4.999,28.45),(200,9999,5,8.999,44.45),
]

def calcular_frete(preco, peso):
    if not preco or preco < 79.90 or not peso: return 0.0
    for pm,px,wm,wx,fr in FRETE:
        if pm <= preco <= px and wm <= peso <= wx: return fr
    return 0.0

def calcular(custo, preco_ml, taxa_pct=16.5, peso=0, emb=0, imp_pct=0):
    if not custo or not preco_ml or preco_ml <= 0:
        return dict(custo_total=0,margem_pct=0,margem_r=0,viavel=0,frete=0,taxa_fixa=0)
    taxa = taxa_pct/100; imp = imp_pct/100
    taxa_fixa = 6.25 if preco_ml < 79 else 0
    frete = calcular_frete(preco_ml, peso)
    custo_total = custo + preco_ml*taxa + taxa_fixa + preco_ml*imp + emb + frete
    margem_r = round(preco_ml - custo_total, 2)
    margem_pct = round(margem_r / preco_ml * 100, 1) if preco_ml > 0 else 0
    return dict(custo_total=round(custo_total,2), margem_pct=margem_pct,
                margem_r=margem_r, viavel=1 if margem_pct >= 20 else 0,
                frete=round(frete,2), taxa_fixa=taxa_fixa)

def get_aliquota():
    try:
        conn = get_conn(); cur = conn.cursor()
        ph = "%s" if USAR_POSTGRES else "?"
        cur.execute(f"SELECT valor FROM config WHERE chave = {ph}", ("aliquota_imposto",))
        r = cur.fetchone(); conn.close()
        return float(r[0]) if r else 0.0
    except: return 0.0

def ph(): return "%s" if USAR_POSTGRES else "?"

# ════════════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════════════
@app.route('/login')
def pagina_login():
    return LOGIN_HTML

@app.route('/api/login', methods=['POST'])
def api_login():
    d = request.get_json() or {}
    u = d.get('usuario','').strip()
    s = d.get('senha','')
    if verificar_login(u, s):
        session['usuario'] = u
        session.permanent = True
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'erro': 'Usuário ou senha incorretos'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ════════════════════════════════════════════════════════════════════
# DASHBOARD PRINCIPAL
# ════════════════════════════════════════════════════════════════════
@app.route('/api/debug-erro')
@login_required
def debug_erro():
    """Endpoint temporário para diagnóstico — remove após corrigir."""
    import traceback
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM produtos")
        total = cur.fetchone()[0]
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='produtos' ORDER BY column_name")
        cols = [r[0] for r in cur.fetchall()]
        conn.close()
        return jsonify({'ok': True, 'total_produtos': total, 'colunas': cols})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e), 'tb': traceback.format_exc()})

@app.route('/')
@login_required
def index():
    conn = get_conn(); cur = conn.cursor()
    tenant = get_tenant_id()
    p = ph()

    # Filtros
    f = {
        'forn': request.args.get('forn',''),
        'produto': request.args.get('produto',''),
        'status': request.args.get('status',''),
        'cmin': request.args.get('cmin','0'),
        'cmax': request.args.get('cmax','999'),
        'pp': int(request.args.get('pp', 100)),
    }
    pg = max(1, int(request.args.get('pg', 1)))

    w = [f"tenant_id = {p}"]; params = [tenant]
    if f['forn']: w.append(f"fornecedor ILIKE {p}" if USAR_POSTGRES else f"fornecedor LIKE {p}"); params.append(f"%{f['forn']}%")
    if f['produto']: w.append(f"descricao ILIKE {p}" if USAR_POSTGRES else f"descricao LIKE {p}"); params.append(f"%{f['produto']}%")
    if f['status'] == 'viavel': w.append("viavel = 1")
    elif f['status'] == 'nao_viavel': w.append("viavel = 0 AND preco_ml > 0")
    elif f['status'] == 'pendente': w.append("preco_ml = 0 OR preco_ml IS NULL")
    elif f['status'] == 'escolhido': w.append("escolhido = 1")
    try:
        w.append(f"custo >= {p}"); params.append(float(f['cmin']))
        w.append(f"custo <= {p}"); params.append(float(f['cmax']))
    except: pass

    where = " AND ".join(w)
    cur.execute(f"SELECT COUNT(*) FROM produtos WHERE {where}", params)
    total_f = cur.fetchone()[0]
    total_pg = max(1, (total_f + f['pp'] - 1) // f['pp'])
    pg = min(pg, total_pg)

    cur.execute(f"SELECT * FROM produtos WHERE {where} ORDER BY id DESC LIMIT {p} OFFSET {p}",
                params + [f['pp'], (pg-1)*f['pp']])
    cols = [d[0] for d in cur.description]
    produtos = [dict(zip(cols, r)) for r in cur.fetchall()]

    # Stats
    cur.execute(f"SELECT COUNT(*) FROM produtos WHERE tenant_id = {p}", [tenant]); total = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(DISTINCT fornecedor) FROM produtos WHERE tenant_id = {p}", [tenant]); forn_c = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM produtos WHERE tenant_id = {p} AND preco_ml > 0", [tenant]); c_preco = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM produtos WHERE tenant_id = {p} AND viavel = 1", [tenant]); c_viavel = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM produtos WHERE tenant_id = {p} AND viavel = 0 AND preco_ml > 0", [tenant]); c_nviavel = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM produtos WHERE tenant_id = {p} AND (preco_ml = 0 OR preco_ml IS NULL)", [tenant]); c_pend = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM produtos WHERE tenant_id = {p} AND escolhido = 1", [tenant]); c_escolhido = cur.fetchone()[0]
    cur.execute(f"SELECT DISTINCT fornecedor FROM produtos WHERE tenant_id = {p} ORDER BY fornecedor", [tenant])
    fornecedores = [r[0] for r in cur.fetchall() if r[0]]
    conn.close()

    stats = dict(total=total, fornecedores=forn_c, com_preco=c_preco, sem_preco=total-c_preco,
                 viaveis=c_viavel, nao_viaveis=c_nviavel, pendentes=c_pend, escolhidos=c_escolhido)

    imp_pct = round(get_aliquota()*100, 1)
    usuario = get_usuario_nome()

    def url_pg(p_num):
        args = request.args.to_dict(); args['pg'] = p_num
        return '?' + '&'.join(f"{k}={v}" for k,v in args.items())

    return render_template_string(HTML_DASH, produtos=produtos, stats=stats,
        fornecedores=fornecedores, f=f, pg=pg, total_paginas=total_pg,
        url_pg=url_pg, imp_pct=imp_pct, usuario=usuario, total_filtrado=total_f)

# ════════════════════════════════════════════════════════════════════
# APIS CRUD PRODUTOS
# ════════════════════════════════════════════════════════════════════
@app.route('/api/atualizar', methods=['POST'])
@login_required
def api_atualizar():
    d = request.get_json(); pid = d.get('id'); campo = d.get('campo'); valor = d.get('valor')
    if not all([pid, campo]): return jsonify({'ok': False})
    campos_ok = ['preco_ml','taxa_categoria','peso_kg','custo_embalagem','custo_ads',
                 'custo_full','link_ml','notas','tipo_anuncio','promo_percentual','margem_alvo']
    if campo not in campos_ok: return jsonify({'ok': False, 'erro': 'Campo não permitido'})
    try:
        conn = get_conn(); cur = conn.cursor(); p = ph(); tenant = get_tenant_id()
        cur.execute(f"UPDATE produtos SET {campo} = {p} WHERE id = {p} AND tenant_id = {p}", [valor, pid, tenant])
        # Recalcula se tem preco_ml
        cur.execute(f"SELECT custo, preco_ml, taxa_categoria, peso_kg, custo_embalagem FROM produtos WHERE id = {p}", [pid])
        row = cur.fetchone()
        if row:
            custo, preco_ml, taxa, peso, emb = row
            imp_pct = get_aliquota() * 100
            r = calcular(custo or 0, preco_ml or 0, (taxa or 0.165)*100, peso or 0, emb or 0, imp_pct)
            cur.execute(f"""UPDATE produtos SET custo_total={p}, margem_percentual={p},
                margem_reais={p}, viavel={p} WHERE id = {p}""",
                [r['custo_total'], r['margem_pct'], r['margem_r'], r['viavel'], pid])
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/adicionar-produto', methods=['POST'])
@login_required
def api_adicionar_produto():
    d = request.get_json(); tenant = get_tenant_id()
    try:
        conn = get_conn(); cur = conn.cursor(); p = ph()
        cur.execute(f"""INSERT INTO produtos (tenant_id, fornecedor, descricao, custo, codigo)
            VALUES ({p},{p},{p},{p},{p}) RETURNING id""" if USAR_POSTGRES else
            f"""INSERT INTO produtos (tenant_id, fornecedor, descricao, custo, codigo)
            VALUES ({p},{p},{p},{p},{p})""",
            [tenant, d.get('fornecedor',''), d.get('descricao',''), float(d.get('custo',0)), d.get('codigo','')])
        if USAR_POSTGRES: pid = cur.fetchone()[0]
        else: pid = cur.lastrowid
        conn.commit(); conn.close()
        return jsonify({'ok': True, 'id': pid, 'desc': d.get('descricao','')[:25]})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/deletar-produto', methods=['POST'])
@login_required
def api_deletar_produto():
    d = request.get_json(); pid = d.get('id'); tenant = get_tenant_id()
    try:
        conn = get_conn(); cur = conn.cursor(); p = ph()
        cur.execute(f"DELETE FROM produtos WHERE id = {p} AND tenant_id = {p}", [pid, tenant])
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/escolher', methods=['POST'])
@login_required
def api_escolher():
    d = request.get_json(); tenant = get_tenant_id()
    try:
        conn = get_conn(); cur = conn.cursor(); p = ph()
        cur.execute(f"UPDATE produtos SET escolhido = 1 WHERE id = {p} AND tenant_id = {p}", [d.get('id'), tenant])
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/descartar', methods=['POST'])
@login_required
def api_descartar():
    d = request.get_json(); tenant = get_tenant_id()
    try:
        conn = get_conn(); cur = conn.cursor(); p = ph()
        cur.execute(f"UPDATE produtos SET escolhido = 0 WHERE id = {p} AND tenant_id = {p}", [d.get('id'), tenant])
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/aliquota', methods=['POST'])
@login_required
def api_aliquota():
    d = request.get_json()
    try:
        conn = get_conn(); cur = conn.cursor(); p = ph()
        val = float(d.get('valor', 0)) / 100
        if USAR_POSTGRES:
            cur.execute(f"INSERT INTO config (chave, valor) VALUES ({p},{p}) ON CONFLICT (chave) DO UPDATE SET valor={p}",
                       ['aliquota_imposto', str(val), str(val)])
        else:
            cur.execute(f"INSERT OR REPLACE INTO config (chave, valor) VALUES ({p},{p})", ['aliquota_imposto', str(val)])
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/recalcular-todos', methods=['POST'])
@login_required
def api_recalcular_todos():
    tenant = get_tenant_id(); imp_pct = get_aliquota() * 100
    try:
        conn = get_conn(); cur = conn.cursor(); p = ph()
        cur.execute(f"SELECT id, custo, preco_ml, taxa_categoria, peso_kg, custo_embalagem FROM produtos WHERE tenant_id = {p}", [tenant])
        rows = cur.fetchall(); atualizados = 0
        for row in rows:
            pid, custo, preco_ml, taxa, peso, emb = row
            if not custo: continue
            r = calcular(custo or 0, preco_ml or 0, (taxa or 0.165)*100, peso or 0, emb or 0, imp_pct)
            cur.execute(f"UPDATE produtos SET custo_total={p}, margem_percentual={p}, margem_reais={p}, viavel={p} WHERE id={p}",
                       [r['custo_total'], r['margem_pct'], r['margem_r'], r['viavel'], pid])
            atualizados += 1
        conn.commit(); conn.close()
        return jsonify({'ok': True, 'atualizados': atualizados})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/buscar-ml', methods=['POST'])
@login_required
def api_buscar_ml():
    import requests as req
    d = request.get_json(); pid = d.get('id'); termo = d.get('termo','')
    if not termo: return jsonify({'ok': False, 'erro': 'Termo vazio'})
    try:
        from ml_buscador import MLBuscador
        ml = MLBuscador()
        if not ml.esta_autenticado(): return jsonify({'ok': False, 'erro': 'ML não conectado. Vá em Configurações → ML Auth'})
        headers = {"Authorization": f"Bearer {ml.auth.access_token}"}
        r = req.get("https://api.mercadolibre.com/sites/MLB/search",
                   headers=headers, params={"q": termo, "limit": 10}, timeout=15)
        if r.status_code != 200: return jsonify({'ok': False, 'erro': f'Erro ML: {r.status_code}'})
        results = r.json().get('results', [])
        if not results: return jsonify({'ok': False, 'erro': 'Sem resultados'})
        precos = [x.get('price',0) for x in results if x.get('price',0) > 0]
        preco_medio = round(sum(precos)/len(precos), 2) if precos else 0
        # Taxa real
        taxa_pct = 16.5
        cat = results[0].get('category_id','')
        if cat:
            r2 = req.get("https://api.mercadolibre.com/sites/MLB/listing_prices",
                        headers=headers, params={"price": preco_medio, "category_id": cat, "currency_id": "BRL"}, timeout=10)
            if r2.status_code == 200:
                for lst in r2.json():
                    if lst.get('listing_type_id') in ('gold_special','gold_pro'):
                        for comp in lst.get('sale_fee_components',[]):
                            if comp.get('type') == 'fee': taxa_pct = round(comp.get('ratio',0.165)*100, 1)
        return jsonify({'ok': True, 'preco_medio': preco_medio, 'taxa_percentual': taxa_pct, 'total': len(results)})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/atualizar-taxas-ml', methods=['POST'])
@login_required
def api_atualizar_taxas_ml():
    return jsonify({'ok': True, 'atualizados': 0})

@app.route('/exportar')
@login_required
def exportar():
    import openpyxl; from openpyxl.styles import PatternFill, Font, Alignment
    tenant = get_tenant_id()
    conn = get_conn(); cur = conn.cursor(); p = ph()
    cur.execute(f"SELECT * FROM produtos WHERE tenant_id = {p} ORDER BY fornecedor, descricao", [tenant])
    cols = [d[0] for d in cur.description]; rows = cur.fetchall(); conn.close()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Produtos QUBO"
    headers = ['ID','Fornecedor','Código','Descrição','Custo','Preço ML','Taxa %','Frete','Custo Total','Margem %','Margem R$','Viável','Escolhido']
    col_map = {'id':0,'fornecedor':1,'codigo':2,'descricao':3,'custo':4,'preco_ml':5,'taxa_categoria':6,'custo_frete':7,'custo_total':8,'margem_percentual':9,'margem_reais':10,'viavel':11,'escolhido':12}
    header_fill = PatternFill(fgColor="1a1f3a", fill_type="solid")
    for i, h in enumerate(headers, 1):
        cell = ws.cell(1, i, h); cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True); cell.alignment = Alignment(horizontal='center')
    for row in rows:
        d = dict(zip(cols, row))
        ws.append([d.get('id'), d.get('fornecedor'), d.get('codigo'), d.get('descricao'),
                   d.get('custo'), d.get('preco_ml'), round((d.get('taxa_categoria') or 0)*100, 1),
                   d.get('custo_frete'), d.get('custo_total'), d.get('margem_percentual'),
                   d.get('margem_reais'), 'SIM' if d.get('viavel') else 'NÃO',
                   'SIM' if d.get('escolhido') else ''])
    output = io.BytesIO(); wb.save(output); output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True, download_name=f'qubo_produtos_{datetime.now().strftime("%Y%m%d")}.xlsx')

# ════════════════════════════════════════════════════════════════════
# AGENTES IA
# ════════════════════════════════════════════════════════════════════
@app.route('/api/pesquisar-produto', methods=['POST'])
@login_required
def api_pesquisar_produto():
    try:
        from agente_pesquisa import pesquisar_produto
        from ml_buscador import MLBuscador
        d = request.get_json(); ml = MLBuscador()
        if not ml.esta_autenticado(): return jsonify({'ok': False, 'erro': 'ML não conectado'})
        return jsonify(pesquisar_produto(d.get('id'), ml.auth.access_token))
    except Exception as e: return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/precificar', methods=['POST'])
@login_required
def api_precificar():
    try:
        from agente_precificacao import precificar_produto
        from ml_buscador import MLBuscador
        d = request.get_json(); ml = MLBuscador()
        if not ml.esta_autenticado(): return jsonify({'ok': False, 'erro': 'ML não conectado'})
        return jsonify(precificar_produto(d.get('id'), ml.auth.access_token,
                       float(d.get('margem_minima',20)), float(d.get('imposto_pct',0))))
    except Exception as e: return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/viabilidade', methods=['POST'])
@login_required
def api_viabilidade():
    try:
        from agente_viabilidade import analisar_viabilidade
        from ml_buscador import MLBuscador
        d = request.get_json(); ml = MLBuscador()
        if not ml.esta_autenticado(): return jsonify({'ok': False, 'erro': 'ML não conectado'})
        return jsonify(analisar_viabilidade(d.get('termo',''), ml.auth.access_token,
            float(d.get('custo',0)), float(d.get('peso',0)), float(d.get('embalagem',0)),
            float(d.get('imposto',0)), float(d.get('margem_minima',20)), d.get('id')))
    except Exception as e: return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/alerta-diario')
@login_required
def api_alerta_diario():
    try:
        from agente_alerta import gerar_alerta_diario
        from ml_buscador import MLBuscador
        ml = MLBuscador()
        if not ml.esta_autenticado(): return jsonify({'ok': False, 'erro': 'ML não conectado'})
        return jsonify(gerar_alerta_diario(ml.auth.access_token, ml.auth.user_id))
    except Exception as e: return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/tendencias')
@login_required
def api_tendencias():
    try:
        from agente_tendencias import buscar_tendencias
        from ml_buscador import MLBuscador
        ml = MLBuscador()
        if not ml.esta_autenticado(): return jsonify({'ok': False, 'erro': 'ML não conectado'})
        return jsonify(buscar_tendencias(ml.auth.access_token))
    except Exception as e: return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/saude-anuncios')
@login_required
def api_saude_anuncios():
    try:
        from agente_saude import monitorar_saude
        from ml_buscador import MLBuscador
        ml = MLBuscador()
        if not ml.esta_autenticado(): return jsonify({'ok': False, 'erro': 'ML não conectado'})
        return jsonify(monitorar_saude(ml.auth.access_token, ml.auth.user_id))
    except Exception as e: return jsonify({'ok': False, 'erro': str(e)})

# ════════════════════════════════════════════════════════════════════
# PÁGINA DE CONFIGURAÇÕES
# ════════════════════════════════════════════════════════════════════
@app.route('/config')
@login_required
def pagina_config():
    from ml_buscador import MLBuscador
    try:
        ml = MLBuscador(); ml_ok = ml.esta_autenticado(); ml_user = ml.auth.user_id if ml_ok else None
    except: ml_ok = False; ml_user = None
    usuario = get_usuario_nome()
    return render_template_string(HTML_CONFIG, ml_ok=ml_ok, ml_user=ml_user, usuario=usuario)

@app.route('/api/ml-auth', methods=['POST'])
@login_required
def api_ml_auth():
    from ml_buscador import MLBuscador
    d = request.get_json(); code = d.get('code','').strip()
    if not code: return jsonify({'ok': False, 'erro': 'Código obrigatório'})
    try:
        ml = MLBuscador()
        ok = ml.autenticar_com_code(code)
        return jsonify({'ok': ok, 'user_id': ml.auth.user_id if ok else None,
                       'erro': None if ok else 'Código inválido ou expirado'})
    except Exception as e: return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/ml-status')
@login_required
def api_ml_status():
    try:
        from ml_buscador import MLBuscador
        ml = MLBuscador()
        return jsonify({'ok': True, 'autenticado': ml.esta_autenticado(), 'user_id': ml.auth.user_id})
    except Exception as e: return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/watcher-upload', methods=['POST'])
def api_watcher_upload():
    """Endpoint para o File Watcher local — autenticado por API key, sem sessão."""
    import tempfile, os as _os
    api_key = request.headers.get('X-API-Key', '')
    expected = os.getenv('WATCHER_API_KEY', 'qubo-watcher-2026')
    if api_key != expected:
        return jsonify({'ok': False, 'erro': 'Chave de API inválida'}), 401
    if 'arquivo' not in request.files:
        return jsonify({'ok': False, 'erro': 'Nenhum arquivo enviado'})
    arquivo = request.files['arquivo']
    if not arquivo.filename.lower().endswith('.pdf'):
        return jsonify({'ok': False, 'erro': 'Apenas arquivos PDF'})
    tenant = request.form.get('tenant_id', 'gustavo')
    try:
        from multi_extractor import MultiExtractor
        fornecedor = _os.path.splitext(arquivo.filename)[0]; nome = arquivo.filename
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            arquivo.save(tmp.name); tmp_path = tmp.name
        try:
            extractor = MultiExtractor()
            produtos, info = extractor.extrair_de_pdf(tmp_path, fornecedor)
        finally:
            try: _os.unlink(tmp_path)
            except: pass
        if not produtos:
            return jsonify({'ok': False, 'erro': f'Nenhum produto encontrado em {nome}'})
        conn = get_conn(); cur = conn.cursor(); p = ph(); salvos = 0
        for prod in produtos:
            try:
                cur.execute(f"""INSERT INTO produtos (tenant_id, codigo, fornecedor, descricao, custo, data_analise, arquivo_origem)
                    VALUES ({p},{p},{p},{p},{p},{p},{p})""",
                    [tenant, prod.codigo, fornecedor, prod.descricao, prod.preco_unitario,
                     datetime.now().isoformat(), nome])
                salvos += 1
            except: pass
        conn.commit(); conn.close()
        return jsonify({'ok': True, 'arquivo': nome, 'fornecedor': fornecedor,
                       'produtos_extraidos': salvos, 'provider': info.get('provider','?')})
    except Exception as e:
        return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/upload-pdf', methods=['POST'])
@login_required
def api_upload_pdf():
    import tempfile, os as _os
    if 'arquivo' not in request.files:
        return jsonify({'ok': False, 'erro': 'Nenhum arquivo enviado'})
    arquivo = request.files['arquivo']
    if not arquivo.filename.lower().endswith('.pdf'):
        return jsonify({'ok': False, 'erro': 'Apenas arquivos PDF'})
    try:
        from multi_extractor import MultiExtractor
        tenant = get_tenant_id(); fornecedor = _os.path.splitext(arquivo.filename)[0]; nome = arquivo.filename
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            arquivo.save(tmp.name); tmp_path = tmp.name
        try:
            extractor = MultiExtractor()
            produtos, info = extractor.extrair_de_pdf(tmp_path, fornecedor)
        finally:
            try: _os.unlink(tmp_path)
            except: pass
        if not produtos: return jsonify({'ok': False, 'erro': f'Nenhum produto encontrado em {nome}'})
        conn = get_conn(); cur = conn.cursor(); p = ph(); salvos = 0
        for prod in produtos:
            try:
                cur.execute(f"""INSERT INTO produtos (tenant_id, codigo, fornecedor, descricao, custo, data_analise, arquivo_origem)
                    VALUES ({p},{p},{p},{p},{p},{p},{p})""",
                    [tenant, prod.codigo, fornecedor, prod.descricao, prod.preco_unitario,
                     datetime.now().isoformat(), nome])
                salvos += 1
            except: pass
        conn.commit(); conn.close()
        return jsonify({'ok': True, 'arquivo': nome, 'fornecedor': fornecedor,
                       'produtos_extraidos': salvos, 'provider': info.get('provider','?')})
    except Exception as e: return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/config-pasta', methods=['POST'])
@login_required
def api_config_pasta():
    d = request.get_json(); pasta = d.get('pasta','')
    try:
        conn = get_conn(); cur = conn.cursor(); p = ph()
        if USAR_POSTGRES:
            cur.execute(f"INSERT INTO config (chave,valor) VALUES ({p},{p}) ON CONFLICT (chave) DO UPDATE SET valor={p}",
                       ['pasta_monitorada', pasta, pasta])
        else:
            cur.execute(f"INSERT OR REPLACE INTO config (chave,valor) VALUES ({p},{p})", ['pasta_monitorada', pasta])
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e: return jsonify({'ok': False, 'erro': str(e)})

@app.route('/api/verificar-pdfs')
@login_required
def api_verificar_pdfs():
    try:
        conn = get_conn(); cur = conn.cursor(); p = ph()
        cur.execute(f"SELECT valor FROM config WHERE chave = {p}", ['pasta_monitorada'])
        r = cur.fetchone(); conn.close()
        pasta = r[0] if r else ''
        if not pasta: return jsonify({'ok': False, 'erro': 'Pasta não configurada'})
        from pathlib import Path as P
        path = P(pasta)
        if not path.exists(): return jsonify({'ok': False, 'erro': f'Pasta não encontrada: {pasta}'})
        pdfs = list(path.glob('*.pdf'))
        enviados = list(path.glob('*.enviado'))
        return jsonify({'ok': True, 'pasta': pasta, 'pdfs': len(pdfs),
                       'enviados': len(enviados), 'arquivos': [f.name for f in pdfs[:20]]})
    except Exception as e: return jsonify({'ok': False, 'erro': str(e)})

# ════════════════════════════════════════════════════════════════════
# SCHEMA CONFIG TABLE
# ════════════════════════════════════════════════════════════════════
def garantir_config():
    try:
        conn = get_conn(); cur = conn.cursor()
        if USAR_POSTGRES:
            cur.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT DEFAULT '')")
        else:
            cur.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT DEFAULT '')")
        conn.commit(); conn.close()
    except: pass


# ════════════════════════════════════════════════════════════════════
# HTML — DASHBOARD PRINCIPAL
# ════════════════════════════════════════════════════════════════════
HTML_DASH = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QUBO Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0e27;--card:#1a1f3a;--border:#2d3452;--text:#e4e6eb;--muted:#8b92a5;
  --green:#4ade80;--red:#f87171;--yellow:#fbbf24;--blue:#667eea;--purple:#c084fc}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);font-size:.85rem}
.topbar{background:var(--card);border-bottom:1px solid var(--border);padding:8px 16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;position:sticky;top:0;z-index:100}
.logo{font-size:1.1rem;font-weight:900;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-right:8px}
.btn{padding:5px 12px;border:none;border-radius:5px;cursor:pointer;font-size:.78rem;font-weight:600;transition:opacity .15s}
.btn:hover{opacity:.85}.btn-blue{background:#667eea;color:#fff}.btn-green{background:#059669;color:#fff}
.btn-yellow{background:#f59e0b;color:#000}.btn-pink{background:#ec4899;color:#fff}
.btn-cyan{background:#0891b2;color:#fff}.btn-purple{background:#7c3aed;color:#fff}
.btn-gray{background:#2d3452;color:var(--text)}.btn-red{background:#dc2626;color:#fff}
.spacer{flex:1}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;padding:12px 16px}
.stat{background:var(--card);border-radius:8px;padding:12px;text-align:center;border:1px solid var(--border)}
.stat-n{font-size:1.5rem;font-weight:800;margin-bottom:2px}
.stat-l{font-size:.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.filters{background:var(--card);border-bottom:1px solid var(--border);padding:10px 16px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.filters input,.filters select{background:var(--bg);border:1px solid var(--border);color:var(--text);padding:5px 8px;border-radius:5px;font-size:.78rem}
.filters input:focus,.filters select:focus{border-color:var(--blue);outline:none}
.aliquota-bar{background:var(--card);border-bottom:1px solid var(--border);padding:6px 16px;display:flex;align-items:center;gap:10px;font-size:.78rem;color:var(--muted)}
.aliquota-bar input{width:60px;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:3px 6px;border-radius:4px;text-align:center}
.table-wrap{overflow-x:auto;padding:0 16px 80px}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:8px;overflow:hidden;font-size:.78rem}
thead{background:#0f1328}
th{padding:8px 6px;color:var(--muted);font-weight:600;text-align:left;white-space:nowrap;border-bottom:1px solid var(--border)}
td{padding:5px 6px;border-bottom:1px solid #151929;vertical-align:middle}
tr:hover td{background:#1f2544}
.badge-ok{background:#064e3b;color:var(--green);padding:1px 6px;border-radius:8px;font-size:.65rem;font-weight:700}
.badge-no{background:#450a0a;color:var(--red);padding:1px 6px;border-radius:8px;font-size:.65rem;font-weight:700}
.badge-pend{background:#3b2700;color:var(--yellow);padding:1px 6px;border-radius:8px;font-size:.65rem;font-weight:700}
.inline-input{background:transparent;border:none;color:var(--text);width:70px;text-align:right;font-size:.78rem;padding:2px 4px;border-radius:3px}
.inline-input:focus{background:#2d3452;outline:none}
.inline-input:hover{background:#2d3452}
.pagination{display:flex;gap:6px;justify-content:center;padding:12px}
.pg-btn{background:var(--card);border:1px solid var(--border);color:var(--text);padding:4px 10px;border-radius:4px;cursor:pointer;font-size:.75rem;text-decoration:none}
.pg-btn.active{background:var(--blue);border-color:var(--blue);font-weight:700}
.modal-bg{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);display:flex;justify-content:center;align-items:center;z-index:9999;padding:20px}
.modal{background:var(--card);padding:20px;border-radius:10px;width:500px;max-width:95vw;max-height:90vh;overflow-y:auto}
.modal h3{margin-bottom:14px;font-size:1rem}
.modal label{display:block;color:var(--muted);font-size:.72rem;text-transform:uppercase;margin-bottom:4px}
.modal input,.modal select{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:8px 10px;border-radius:5px;margin-bottom:12px;font-size:.85rem}
.toast{position:fixed;bottom:20px;right:20px;padding:10px 16px;border-radius:6px;font-size:.82rem;font-weight:600;z-index:9999;animation:fadeIn .2s}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
</style>
</head>
<body>

<div class="topbar">
  <span class="logo">QUBO</span>
  <span style="color:var(--muted);font-size:.75rem">{{ usuario }}</span>
  <div class="spacer"></div>
  <button class="btn btn-yellow" onclick="abrirAlertaDiario()">📊 Alerta</button>
  <button class="btn btn-pink" onclick="abrirTendencias()">🔥 Tendências</button>
  <button class="btn btn-cyan" onclick="abrirSaude()">🏥 Saúde</button>
  <button class="btn btn-green" onclick="mostrarModalProduto()">➕ Produto</button>
  <button class="btn btn-blue" onclick="exportar()">📥 Excel</button>
  <button class="btn btn-gray" onclick="window.location='/escolhidos'">⭐ Escolhidos ({{ stats.escolhidos }})</button>
  <button class="btn btn-gray" onclick="location.href='/config'">⚙️ Config</button>
  <button class="btn btn-gray" onclick="location.href='/logout'">Sair</button>
</div>

<div class="aliquota-bar">
  <span>🏛️ Alíquota Imposto (%):</span>
  <input type="number" id="aliquota" value="{{ imp_pct }}" min="0" max="100" step="0.5" onchange="salvarAliquota(this.value)">
  <span style="font-size:.7rem">Aplica a todos ao recalcular</span>
  <button class="btn btn-gray" style="padding:3px 8px;font-size:.7rem" onclick="recalcularTodos()">⚡ Recalcular Tudo</button>
</div>

<div class="stats">
  <div class="stat"><div class="stat-n" style="color:var(--blue)">{{ stats.total }}</div><div class="stat-l">Total</div></div>
  <div class="stat"><div class="stat-n" style="color:var(--muted)">{{ stats.fornecedores }}</div><div class="stat-l">Fornecedores</div></div>
  <div class="stat"><div class="stat-n" style="color:var(--green)">{{ stats.viaveis }}</div><div class="stat-l">✅ Viáveis ≥20%</div></div>
  <div class="stat"><div class="stat-n" style="color:var(--red)">{{ stats.nao_viaveis }}</div><div class="stat-l">❌ Não Viáveis</div></div>
  <div class="stat"><div class="stat-n" style="color:var(--yellow)">{{ stats.pendentes }}</div><div class="stat-l">⏳ Pendentes</div></div>
  <div class="stat"><div class="stat-n" style="color:var(--purple)">{{ stats.escolhidos }}</div><div class="stat-l">⭐ Escolhidos</div></div>
</div>

<div class="filters">
  <span style="color:var(--muted);font-size:.72rem">Filtros:</span>
  <input type="text" placeholder="Fornecedor" id="ff" value="{{ f.forn }}" onkeydown="if(event.key=='Enter')filtrar()">
  <input type="text" placeholder="Produto" id="fp" value="{{ f.produto }}" onkeydown="if(event.key=='Enter')filtrar()">
  <select id="fs" onchange="filtrar()">
    <option value="" {% if f.status=='' %}selected{% endif %}>Todos Status</option>
    <option value="viavel" {% if f.status=='viavel' %}selected{% endif %}>✅ Viáveis</option>
    <option value="nao_viavel" {% if f.status=='nao_viavel' %}selected{% endif %}>❌ Não Viáveis</option>
    <option value="pendente" {% if f.status=='pendente' %}selected{% endif %}>⏳ Pendentes</option>
    <option value="escolhido" {% if f.status=='escolhido' %}selected{% endif %}>⭐ Escolhidos</option>
  </select>
  <input type="number" placeholder="Custo mín" id="fcmin" value="{{ f.cmin }}" style="width:90px" onkeydown="if(event.key=='Enter')filtrar()">
  <input type="number" placeholder="Custo máx" id="fcmax" value="{{ f.cmax }}" style="width:90px" onkeydown="if(event.key=='Enter')filtrar()">
  <select id="fpp" onchange="filtrar()">
    <option value="50" {% if f.pp==50 %}selected{% endif %}>50/pág</option>
    <option value="100" {% if f.pp==100 %}selected{% endif %}>100/pág</option>
    <option value="200" {% if f.pp==200 %}selected{% endif %}>200/pág</option>
  </select>
  <button class="btn btn-blue" onclick="filtrar()">🔍</button>
  <button class="btn btn-gray" onclick="limparFiltros()">✕</button>
  <span style="color:var(--muted);font-size:.72rem;margin-left:auto">{{ total_filtrado }} produto(s)</span>
</div>

<div class="table-wrap">
<table>
<thead><tr>
  <th style="width:30px"></th>
  <th>Fornecedor</th><th>Código</th><th style="min-width:200px">Descrição</th>
  <th>Custo</th><th>Preço ML</th><th>Taxa%</th><th>Frete</th>
  <th>Custo Total</th><th>Margem%</th><th>Margem R$</th><th>Status</th>
  <th>Ações</th>
</tr></thead>
<tbody>
{% for p in produtos %}
<tr>
  <td>
    {% if p.escolhido %}
    <button title="Descartar" onclick="descartar({{ p.id }}, this)" style="background:none;border:none;cursor:pointer;font-size:.9rem">⭐</button>
    {% else %}
    <button title="Escolher" onclick="escolher({{ p.id }}, this)" style="background:none;border:none;cursor:pointer;font-size:.9rem;opacity:.4">☆</button>
    {% endif %}
  </td>
  <td style="max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)" title="{{ p.fornecedor }}">{{ p.fornecedor }}</td>
  <td style="color:var(--muted)">{{ p.codigo or '' }}</td>
  <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{{ p.descricao }}">{{ p.descricao }}</td>
  <td style="color:var(--yellow)">R$ {{ p.custo|br }}</td>
  <td><input class="inline-input" id="pml-{{ p.id }}" value="{{ p.preco_ml or '' }}" placeholder="0,00" onblur="salvar(this,'preco_ml',{{ p.id }})" onkeydown="if(event.key=='Enter')this.blur()"></td>
  <td><input class="inline-input" id="tx-{{ p.id }}" value="{{ ((p.taxa_categoria or 0.165)*100)|br(1) }}" style="width:50px" onblur="salvarTaxa(this,{{ p.id }})" onkeydown="if(event.key=='Enter')this.blur()"></td>
  <td style="color:var(--muted)">{{ p.custo_frete|br if p.custo_frete else '-' }}</td>
  <td>{{ p.custo_total|br if p.custo_total else '-' }}</td>
  <td style="color:{{ '#4ade80' if (p.margem_percentual or 0) >= 20 else '#f87171' if p.preco_ml else '#8b92a5' }};font-weight:700">
    {{ p.margem_percentual|br(1) if p.preco_ml else '-' }}%
  </td>
  <td style="color:{{ '#4ade80' if (p.margem_reais or 0) >= 0 else '#f87171' }}">
    {{ p.margem_reais|br if p.preco_ml else '-' }}
  </td>
  <td>
    {% if not p.preco_ml %}<span class="badge-pend">PENDENTE</span>
    {% elif p.viavel %}<span class="badge-ok">VIÁVEL</span>
    {% else %}<span class="badge-no">BAIXO</span>{% endif %}
  </td>
  <td style="display:flex;gap:3px;flex-wrap:nowrap">
    <button class="btn btn-gray" style="padding:2px 6px;font-size:.7rem" 
            onclick="buscarML({{ p.id }}, '{{ p.descricao|replace("'", "\\'") }}')" title="Buscar preço ML">🔍</button>
    <button class="btn btn-purple" style="padding:2px 6px;font-size:.7rem"
            onclick="pesquisarProduto({{ p.id }})" title="Agente: Pesquisa">🤖</button>
    <button class="btn btn-green" style="padding:2px 6px;font-size:.7rem"
            data-id="{{ p.id }}" data-desc="{{ p.descricao|e }}" data-custo="{{ p.custo or 0 }}" data-peso="{{ p.peso_kg or 0 }}"
            onclick="precificar(this)" title="Agente: Precificação">💰</button>
    <button class="btn" style="padding:2px 6px;font-size:.7rem;background:#0891b2;color:#fff"
            data-id="{{ p.id }}" data-desc="{{ p.descricao|e }}" data-custo="{{ p.custo or 0 }}" data-peso="{{ p.peso_kg or 0 }}"
            onclick="viabilidade(this)" title="Agente: Viabilidade">📈</button>
    <button class="btn btn-red" style="padding:2px 6px;font-size:.7rem"
            onclick="deletar({{ p.id }})" title="Deletar">🗑️</button>
  </td>
</tr>
{% else %}
<tr><td colspan="13" style="text-align:center;padding:40px;color:var(--muted)">
  📭 Nenhum produto encontrado. <a href="/config" style="color:var(--blue)">Envie PDFs em Configurações →</a>
</td></tr>
{% endfor %}
</tbody>
</table>
</div>

{% if total_paginas > 1 %}
<div class="pagination">
  {% if pg > 1 %}<a class="pg-btn" href="{{ url_pg(pg-1) }}">← Anterior</a>{% endif %}
  {% for i in range([1,pg-2]|max, [total_paginas+1,pg+3]|min) %}
    <a class="pg-btn {% if i==pg %}active{% endif %}" href="{{ url_pg(i) }}">{{ i }}</a>
  {% endfor %}
  {% if pg < total_paginas %}<a class="pg-btn" href="{{ url_pg(pg+1) }}">Próxima →</a>{% endif %}
</div>
{% endif %}

<!-- Modal Produto -->
<div id="modalProd" style="display:none" class="modal-bg">
<div class="modal" style="border:1px solid var(--green)">
  <h3 style="color:var(--green)">➕ Novo Produto</h3>
  <label>Fornecedor</label><input id="np-forn" placeholder="Ex: Fornecedor ABC">
  <label>Descrição</label><input id="np-desc" placeholder="Nome do produto">
  <label>Custo (R$)</label><input id="np-custo" type="number" placeholder="0,00">
  <label>Código</label><input id="np-cod" placeholder="Código interno (opcional)">
  <div style="display:flex;gap:8px">
    <button class="btn btn-green" style="flex:1" onclick="adicionarProduto()">Adicionar</button>
    <button class="btn btn-gray" style="flex:1" onclick="document.getElementById('modalProd').style.display='none'">Cancelar</button>
  </div>
</div>
</div>

<script>
const fmt = (v,d=2) => v!=null ? parseFloat(v).toFixed(d).replace('.',',') : '-';

function showToast(msg, erro=false){
  document.querySelectorAll('.toast').forEach(t=>t.remove());
  const t = document.createElement('div');
  t.className='toast'; t.textContent=msg;
  t.style.background = erro ? '#450a0a' : '#064e3b';
  t.style.color = erro ? '#f87171' : '#4ade80';
  t.style.border = `1px solid ${erro?'#f87171':'#4ade80'}`;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(), 3500);
}

function filtrar(){
  const p = new URLSearchParams();
  const forn = document.getElementById('ff').value;
  const prod = document.getElementById('fp').value;
  const st = document.getElementById('fs').value;
  const cmin = document.getElementById('fcmin').value;
  const cmax = document.getElementById('fcmax').value;
  const pp = document.getElementById('fpp').value;
  if(forn) p.set('forn',forn); if(prod) p.set('produto',prod);
  if(st) p.set('status',st); if(cmin) p.set('cmin',cmin);
  if(cmax && cmax!='999') p.set('cmax',cmax); if(pp!='100') p.set('pp',pp);
  window.location = '/?' + p.toString();
}

function limparFiltros(){ window.location = '/'; }
function exportar(){ window.open('/exportar','_blank'); }

function salvar(el, campo, id){
  let val = el.value.replace(',','.');
  if(!val || isNaN(parseFloat(val))) return;
  fetch('/api/atualizar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id,campo,valor:parseFloat(val)})})
  .then(r=>r.json()).then(d=>{ if(d.ok) setTimeout(()=>location.reload(),300); else showToast('❌ '+d.erro,true); })
  .catch(()=>showToast('❌ Erro',true));
}

function salvarTaxa(el, id){
  let val = parseFloat(el.value.replace(',','.')) / 100;
  if(isNaN(val)) return;
  fetch('/api/atualizar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id,campo:'taxa_categoria',valor:val})})
  .then(r=>r.json()).then(d=>{ if(d.ok) setTimeout(()=>location.reload(),300); });
}

function salvarAliquota(v){
  fetch('/api/aliquota',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({valor:parseFloat(v)||0})}).then(r=>r.json())
  .then(d=>{ if(d.ok) showToast('✅ Alíquota salva'); });
}

function recalcularTodos(){
  showToast('⚡ Recalculando...');
  fetch('/api/recalcular-todos',{method:'POST'}).then(r=>r.json())
  .then(d=>{ showToast('✅ '+d.atualizados+' produtos recalculados'); setTimeout(()=>location.reload(),800); })
  .catch(()=>showToast('❌ Erro',true));
}

function escolher(id, btn){
  fetch('/api/escolher',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})})
  .then(r=>r.json()).then(d=>{ if(d.ok){btn.textContent='⭐';btn.style.opacity='1';showToast('⭐ Escolhido!'); } });
}
function descartar(id, btn){
  fetch('/api/descartar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})})
  .then(r=>r.json()).then(d=>{ if(d.ok){btn.textContent='☆';btn.style.opacity='.4'; } });
}

function deletar(id){
  if(!confirm('Deletar este produto?')) return;
  fetch('/api/deletar-produto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})})
  .then(r=>r.json()).then(d=>{ if(d.ok){showToast('🗑️ Deletado');setTimeout(()=>location.reload(),500);}else showToast('❌ '+d.erro,true); });
}

function mostrarModalProduto(){ document.getElementById('modalProd').style.display='flex'; document.getElementById('np-forn').focus(); }

function adicionarProduto(){
  const forn=document.getElementById('np-forn').value.trim();
  const desc=document.getElementById('np-desc').value.trim();
  const custo=parseFloat(document.getElementById('np-custo').value||0);
  const cod=document.getElementById('np-cod').value.trim();
  if(!desc){showToast('❌ Descrição obrigatória',true);return;}
  fetch('/api/adicionar-produto',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({fornecedor:forn,descricao:desc,custo,codigo:cod})})
  .then(r=>r.json()).then(d=>{
    if(d.ok){document.getElementById('modalProd').style.display='none';showToast('✅ '+d.desc+' adicionado!');setTimeout(()=>location.reload(),600);}
    else showToast('❌ '+d.erro,true);
  });
}

function buscarML(id, desc){
  const btn = event.target;
  btn.textContent='⏳'; btn.disabled=true;
  fetch('/api/buscar-ml',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,termo:desc})})
  .then(r=>r.json()).then(d=>{
    btn.textContent='🔍'; btn.disabled=false;
    if(d.ok){
      const el=document.getElementById('pml-'+id);
      const tx=document.getElementById('tx-'+id);
      if(el && !el.value){ el.value=fmt(d.preco_medio); }
      if(tx && d.taxa_percentual) tx.value=fmt(d.taxa_percentual,1);
      showToast('ML: R$ '+fmt(d.preco_medio)+' | Taxa: '+fmt(d.taxa_percentual,1)+'% ('+d.total+' res.)');
    } else showToast('❌ '+d.erro,true);
  }).catch(()=>{btn.textContent='🔍';btn.disabled=false;showToast('❌ Erro',true);});
}

// ── Agentes IA ────────────────────────────────────────────────────
function pesquisarProduto(id){
  showToast('🤖 Pesquisando...');
  fetch('/api/pesquisar-produto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})})
  .then(r=>r.json()).then(d=>{ if(!d.ok){showToast('❌ '+d.erro,true);return;} mostrarModalAgente('🤖 Pesquisa de Produto',d); })
  .catch(()=>showToast('❌ Erro',true));
}

function precificar(btn){
  const id=btn.dataset.id; const desc=btn.dataset.desc; const custo=btn.dataset.custo; const peso=btn.dataset.peso;
  const margem=prompt('Margem mínima (%):', '20'); if(margem===null)return;
  showToast('💰 Calculando precificação...');
  fetch('/api/precificar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:parseInt(id),margem_minima:parseFloat(margem)||20})})
  .then(r=>r.json()).then(d=>{ if(!d.ok){showToast('❌ '+d.erro,true);return;} mostrarModalPrecificacao(d); })
  .catch(()=>showToast('❌ Erro',true));
}

function viabilidade(btn){
  const id=btn.dataset.id; const desc=btn.dataset.desc; const custo=parseFloat(btn.dataset.custo)||0; const peso=parseFloat(btn.dataset.peso)||0;
  const margem=prompt('Margem mínima (%):', '20'); if(margem===null)return;
  showToast('📈 Analisando viabilidade...');
  fetch('/api/viabilidade',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:parseInt(id),termo:desc,custo,peso,margem_minima:parseFloat(margem)||20})})
  .then(r=>r.json()).then(d=>{ if(!d.ok){showToast('❌ '+d.erro,true);return;} mostrarModalViabilidade(d); })
  .catch(()=>showToast('❌ Erro',true));
}

function abrirAlertaDiario(){
  showToast('📊 Gerando alerta...');
  fetch('/api/alerta-diario').then(r=>r.json()).then(d=>{
    if(!d.ok){showToast('❌ '+d.erro,true);return;} mostrarModalAlerta(d);
  }).catch(()=>showToast('❌ Erro',true));
}

function abrirTendencias(){
  showToast('🔥 Buscando tendências...');
  fetch('/api/tendencias').then(r=>r.json()).then(d=>{
    if(!d.ok){showToast('❌ '+d.erro,true);return;} mostrarModalTendencias(d);
  }).catch(()=>showToast('❌ Erro',true));
}

function abrirSaude(){
  showToast('🏥 Verificando anúncios...');
  fetch('/api/saude-anuncios').then(r=>r.json()).then(d=>{
    if(!d.ok){showToast('❌ '+d.erro,true);return;} mostrarModalSaude(d);
  }).catch(()=>showToast('❌ Erro',true));
}

function mostrarModalAgente(titulo, d){
  const h = `<div class="modal-bg" onclick="this.remove()"><div class="modal" style="border:1px solid #7c3aed;max-width:600px" onclick="event.stopPropagation()">
    <h3 style="color:#c084fc;margin-bottom:12px">${titulo}</h3>
    <pre style="background:#0a0e27;padding:12px;border-radius:6px;overflow-x:auto;font-size:.75rem;color:#e4e6eb;white-space:pre-wrap">${JSON.stringify(d,null,2)}</pre>
    <button class="btn btn-gray" style="margin-top:10px;width:100%" onclick="this.closest('.modal-bg').remove()">Fechar</button>
  </div></div>`;
  document.body.insertAdjacentHTML('beforeend',h);
}

function mostrarModalPrecificacao(d){
  const fmt2=(v,dc=2)=>v!=null?parseFloat(v).toFixed(dc).replace('.',','):'-';
  const c=d.cenarios||{}; const rec=d.recomendacao||{};
  const renderC=(nome,dados,emoji)=>{
    if(!dados)return'';
    const dest=rec.cenario===nome?'border:2px solid #667eea;':'';
    const recTag=rec.cenario===nome?'<span style="background:#667eea;color:#fff;padding:1px 5px;border-radius:8px;font-size:.6rem;margin-left:4px">⭐</span>':'';
    const cor=dados.viavel?'#4ade80':'#f87171';
    return `<div style="background:#0a0e27;padding:10px;border-radius:6px;${dest}">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px">
        <span style="font-size:.8rem;font-weight:700">${emoji} ${nome}${recTag}</span>
        <span style="color:${cor};font-size:.65rem;font-weight:700">${dados.viavel?'VIÁVEL':'INVIÁVEL'}</span>
      </div>
      <div style="font-size:1.2rem;font-weight:700;color:#4ade80">R$ ${fmt2(dados.preco)}</div>
      <div style="color:${cor};font-size:.8rem">Margem: ${fmt2(dados.margem,1)}%</div>
      <div style="color:#8b92a5;font-size:.68rem;margin-top:3px">${dados.descricao}</div>
      <button onclick="aplicarPreco(${d.produto_id},${dados.preco},${d.taxa_percentual})"
        style="margin-top:6px;padding:2px 8px;border:none;border-radius:3px;background:#2d3452;color:#e4e6eb;cursor:pointer;font-size:.7rem">Usar</button>
    </div>`;
  };
  const rivais=(d.top_concorrentes||[]).map((r,i)=>`<tr style="border-bottom:1px solid #1a1f3a">
    <td style="padding:3px 6px;color:#8b92a5">${i+1}</td>
    <td style="padding:3px 6px;color:#e4e6eb;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.titulo}</td>
    <td style="padding:3px 6px;color:#4ade80">R$ ${fmt2(r.preco)}</td>
    <td style="padding:3px 6px;color:#fbbf24">${parseInt(r.vendas_acumuladas||0).toLocaleString('pt-BR')}</td>
    <td><a href="${r.link}" target="_blank" style="color:#667eea;font-size:.7rem">↗</a></td>
  </tr>`).join('');
  const h=`<div class="modal-bg" onclick="this.remove()"><div class="modal" style="border:1px solid #059669;width:820px" onclick="event.stopPropagation()">
    <div style="display:flex;justify-content:space-between;margin-bottom:10px">
      <div><h3 style="color:#059669">💰 Precificação Inteligente</h3>
      <div style="color:#8b92a5;font-size:.72rem">${d.produto_nome} · Taxa: ${fmt2(d.taxa_percentual,1)}% · "${d.termo_buscado}"</div></div>
      <button class="btn btn-gray" onclick="this.closest('.modal-bg').remove()">✕</button>
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px">
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Menor Rival</div><div style="font-size:1.1rem;font-weight:700;color:#f87171">R$ ${fmt2(d.preco_min_ml)}</div></div>
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Mediano</div><div style="font-size:1.1rem;font-weight:700;color:#4ade80">R$ ${fmt2(d.preco_mediano)}</div></div>
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Seu Custo</div><div style="font-size:1.1rem;font-weight:700;color:#fbbf24">R$ ${fmt2(d.custo)}</div></div>
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Mín Viável</div><div style="font-size:1.1rem;font-weight:700;color:#c084fc">R$ ${fmt2(d.preco_minimo_viavel)}</div></div>
    </div>
    ${rec.motivo?`<div style="background:#1a2a1a;border:1px solid #059669;border-radius:5px;padding:10px;margin-bottom:12px;font-size:.82rem;color:#e4e6eb">💡 ${rec.motivo}</div>`:''}
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px">
      ${renderC('agressivo',c.agressivo,'🔥')}
      ${renderC('competitivo',c.competitivo,'⚖️')}
      ${renderC('premium',c.premium,'👑')}
    </div>
    <table style="width:100%;border-collapse:collapse;background:#0a0e27;font-size:.75rem">
      <thead><tr style="border-bottom:1px solid #2d3452"><th style="padding:3px 6px;color:#8b92a5">#</th><th style="padding:3px 6px;color:#8b92a5">Título</th><th style="padding:3px 6px;color:#8b92a5">Preço</th><th style="padding:3px 6px;color:#8b92a5">Vendas</th><th></th></tr></thead>
      <tbody>${rivais}</tbody>
    </table>
  </div></div>`;
  document.querySelectorAll('.modal-bg').forEach(m=>m.remove());
  document.body.insertAdjacentHTML('beforeend',h);
}

function aplicarPreco(id,preco,taxa){
  document.querySelectorAll('.modal-bg').forEach(m=>m.remove());
  const el=document.getElementById('pml-'+id); const tx=document.getElementById('tx-'+id);
  if(el){ el.value=preco.toFixed(2); if(tx&&taxa) tx.value=taxa.toFixed(1); salvar(el,'preco_ml',id); showToast('✅ Preço aplicado!'); }
}

function mostrarModalViabilidade(d){
  const fmt2=(v,dc=2)=>v!=null?parseFloat(v).toFixed(dc).replace('.',','):'-';
  const corS=d.score>=70?'#4ade80':d.score>=45?'#fbbf24':'#f87171';
  const ins=(d.insights||[]).map(i=>`<div style="display:flex;gap:8px;padding:5px 0;border-bottom:1px solid #2d3452;font-size:.8rem">
    <span>${i.tipo==='positivo'?'✅':i.tipo==='negativo'?'❌':'⚠️'}</span>
    <span style="color:#e4e6eb">${i.msg}</span></div>`).join('');
  const top=(d.top_anuncios||[]).map((a,i)=>`<tr style="border-bottom:1px solid #1a1f3a">
    <td style="padding:3px 6px;color:#8b92a5">${i+1}</td>
    <td style="padding:3px 6px;color:#e4e6eb;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${a.titulo}</td>
    <td style="padding:3px 6px;color:#4ade80">R$ ${fmt2(a.preco)}</td>
    <td style="padding:3px 6px;color:#fbbf24">${parseInt(a.vendas_acumuladas||0).toLocaleString('pt-BR')}</td>
    <td><a href="${a.link}" target="_blank" style="color:#667eea;font-size:.7rem">↗</a></td>
  </tr>`).join('');
  const h=`<div class="modal-bg" onclick="this.remove()"><div class="modal" style="border:1px solid #0891b2;width:820px" onclick="event.stopPropagation()">
    <div style="display:flex;justify-content:space-between;margin-bottom:12px">
      <div><h3 style="color:#0891b2">📈 Viabilidade de Produto</h3>
      <div style="color:#8b92a5;font-size:.72rem">${d.termo_buscado} · ${d.total_anuncios} anúncios</div></div>
      <div style="text-align:center"><div style="font-size:2rem;font-weight:900;color:${corS}">${d.score}</div><div style="font-size:.7rem;color:${corS}">${d.cor} ${d.classificacao}</div></div>
      <button class="btn btn-gray" onclick="this.closest('.modal-bg').remove()">✕</button>
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px">
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Vendas Top20</div><div style="font-size:1.1rem;font-weight:700;color:#4ade80">${parseInt(d.total_vendas_top20_acumulado||0).toLocaleString('pt-BR')}</div></div>
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Demanda/mês</div><div style="font-size:1.1rem;font-weight:700;color:#fbbf24">${fmt2(d.demanda_mercado_mensal,0)}</div></div>
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Preço Mínimo</div><div style="font-size:1.1rem;font-weight:700;color:#f87171">R$ ${fmt2(d.preco_min)}</div></div>
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Mediano</div><div style="font-size:1.1rem;font-weight:700;color:#4ade80">R$ ${fmt2(d.preco_mediano)}</div></div>
    </div>
    <div style="background:#0a0e27;border-radius:6px;padding:10px;margin-bottom:12px">${ins}</div>
    <table style="width:100%;border-collapse:collapse;background:#0a0e27;font-size:.75rem">
      <thead><tr style="border-bottom:1px solid #2d3452"><th style="padding:3px 6px;color:#8b92a5">#</th><th style="padding:3px 6px;color:#8b92a5">Título</th><th style="padding:3px 6px;color:#8b92a5">Preço</th><th style="padding:3px 6px;color:#8b92a5">Vendas</th><th></th></tr></thead>
      <tbody>${top}</tbody>
    </table>
  </div></div>`;
  document.querySelectorAll('.modal-bg').forEach(m=>m.remove());
  document.body.insertAdjacentHTML('beforeend',h);
}

function mostrarModalAlerta(d){
  const vendas=d.vendas||{}; const rep=d.reputacao||{}; const pergs=d.perguntas||{};
  const fmt2=(v)=>v!=null?parseFloat(v).toFixed(2).replace('.',','):'0,00';
  const alertasH=(d.alertas||[]).map(a=>{
    const bg=a.tipo==='urgente'?'#450a0a':a.tipo==='aviso'?'#3b2700':a.tipo==='ok'?'#064e3b':'#1e3a5f';
    const cor=a.tipo==='urgente'?'#f87171':a.tipo==='aviso'?'#fbbf24':a.tipo==='ok'?'#4ade80':'#93c5fd';
    return `<div style="background:${bg};border-radius:5px;padding:8px 12px;display:flex;align-items:center;gap:8px">
      <span>${a.icone}</span><span style="color:${cor};font-size:.82rem">${a.msg}</span></div>`;
  }).join('');
  const h=`<div class="modal-bg" onclick="this.remove()"><div class="modal" style="border:1px solid #f59e0b;width:650px" onclick="event.stopPropagation()">
    <div style="display:flex;justify-content:space-between;margin-bottom:12px">
      <div><h3 style="color:#f59e0b">📊 Alerta Diário</h3><div style="color:#8b92a5;font-size:.72rem">${d.gerado_em}</div></div>
      <button class="btn btn-gray" onclick="this.closest('.modal-bg').remove()">✕</button>
    </div>
    <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:12px">${alertasH||'<div style="color:#8b92a5">Sem alertas.</div>'}</div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Vendas Hoje</div><div style="font-size:1.2rem;font-weight:700;color:#4ade80">${vendas.hoje_qtd||0}</div><div style="font-size:.72rem;color:#8b92a5">R$ ${fmt2(vendas.hoje_valor)}</div></div>
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Vendas Semana</div><div style="font-size:1.2rem;font-weight:700;color:#667eea">${vendas.semana_qtd||0}</div><div style="font-size:.72rem;color:#8b92a5">R$ ${fmt2(vendas.semana_valor)}</div></div>
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Perguntas</div><div style="font-size:1.2rem;font-weight:700;color:${(pergs.nao_respondidas||0)>0?'#f87171':'#4ade80'}">${pergs.nao_respondidas||0}</div></div>
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Reputação</div><div style="font-size:.82rem;font-weight:700;color:#fbbf24">${(rep.nivel||'N/A').replace(/_/g,' ')}</div></div>
    </div>
  </div></div>`;
  document.querySelectorAll('.modal-bg').forEach(m=>m.remove());
  document.body.insertAdjacentHTML('beforeend',h);
}

function mostrarModalTendencias(d){
  const fmt2=(v,dc=2)=>v!=null?parseFloat(v).toFixed(dc).replace('.',','):'-';
  const linhas=(d.tendencias||[]).map((t,i)=>{
    const op=t.oportunidade||{};
    const badge=t.ja_tenho_no_catalogo?'<span style="background:#065f46;color:#4ade80;padding:0 5px;border-radius:8px;font-size:.62rem">✅ Tenho</span>':'';
    return `<tr style="border-bottom:1px solid #1a1f3a;${t.ja_tenho_no_catalogo?'background:#0a1a0a':''}">
      <td style="padding:4px 7px;color:#8b92a5">${i+1}</td>
      <td style="padding:4px 7px;color:#e4e6eb;font-weight:600">${t.keyword} ${badge}</td>
      <td style="padding:4px 7px;color:#4ade80">${t.preco_min?'R$ '+fmt2(t.preco_min):'-'}</td>
      <td style="padding:4px 7px;color:#fbbf24">${t.preco_medio?'R$ '+fmt2(t.preco_medio):'-'}</td>
      <td style="padding:4px 7px"><span style="color:${op.cor||'#8b92a5'};font-size:.78rem">${op.icone||''} ${op.label||''}</span></td>
      <td><a href="${t.url_ml||'https://www.mercadolivre.com.br/'+encodeURIComponent(t.keyword)}" target="_blank" style="color:#667eea;font-size:.72rem">↗</a></td>
    </tr>`;
  }).join('');
  const tenhoC=(d.tendencias||[]).filter(t=>t.ja_tenho_no_catalogo).length;
  const h=`<div class="modal-bg" onclick="this.remove()"><div class="modal" style="border:1px solid #ec4899;width:850px" onclick="event.stopPropagation()">
    <div style="display:flex;justify-content:space-between;margin-bottom:12px">
      <div><h3 style="color:#ec4899">🔥 Tendências ML</h3><div style="color:#8b92a5;font-size:.72rem">${d.total} produtos em alta · ${tenhoC} você tem</div></div>
      <button class="btn btn-gray" onclick="this.closest('.modal-bg').remove()">✕</button>
    </div>
    <div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;background:#0a0e27;font-size:.8rem">
      <thead><tr style="border-bottom:1px solid #2d3452"><th style="padding:5px 7px;color:#8b92a5">#</th><th style="padding:5px 7px;color:#8b92a5">Produto</th><th style="padding:5px 7px;color:#8b92a5">Mín</th><th style="padding:5px 7px;color:#8b92a5">Médio</th><th style="padding:5px 7px;color:#8b92a5">Oportunidade</th><th style="padding:5px 7px;color:#8b92a5">ML</th></tr></thead>
      <tbody>${linhas}</tbody>
    </table></div>
  </div></div>`;
  document.querySelectorAll('.modal-bg').forEach(m=>m.remove());
  document.body.insertAdjacentHTML('beforeend',h);
}

function mostrarModalSaude(d){
  const r=d.resumo||{}; const corS=d.score_saude>=90?'#4ade80':d.score_saude>=70?'#fbbf24':'#f87171';
  const renderL=(lista,titulo,cor,icone)=>{
    if(!lista||!lista.length)return'';
    return `<div style="margin-bottom:10px"><div style="color:${cor};font-weight:700;font-size:.8rem;margin-bottom:4px">${icone} ${titulo} (${lista.length})</div>
      <div style="background:#0a0e27;border-radius:5px">${lista.map(a=>`<div style="display:flex;justify-content:space-between;padding:5px 10px;border-bottom:1px solid #1a1f3a;font-size:.78rem">
        <span style="color:#e4e6eb">${a.titulo||a.id}</span>
        ${a.link?`<a href="${a.link}" target="_blank" style="color:#667eea">↗</a>`:''}
      </div>`).join('')}</div></div>`;
  };
  const h=`<div class="modal-bg" onclick="this.remove()"><div class="modal" style="border:1px solid #0284c7;width:750px" onclick="event.stopPropagation()">
    <div style="display:flex;justify-content:space-between;margin-bottom:12px">
      <div><h3 style="color:#0284c7">🏥 Saúde dos Anúncios</h3><div style="color:#8b92a5;font-size:.72rem">${d.gerado_em}</div></div>
      <div style="text-align:center"><div style="font-size:2rem;font-weight:900;color:${corS}">${d.score_saude}</div><div style="font-size:.72rem;color:${corS}">${d.classificacao_saude}</div></div>
      <button class="btn btn-gray" onclick="this.closest('.modal-bg').remove()">✕</button>
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px">
      <div style="background:#0a0e27;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Total</div><div style="font-size:1.3rem;font-weight:700;color:#667eea">${r.total_anuncios||0}</div></div>
      <div style="background:#064e3b;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Saudáveis</div><div style="font-size:1.3rem;font-weight:700;color:#4ade80">${r.total_saudaveis||0}</div></div>
      <div style="background:#3b2700;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Em Risco</div><div style="font-size:1.3rem;font-weight:700;color:#fbbf24">${r.total_warning||0}</div></div>
      <div style="background:#450a0a;padding:10px;border-radius:6px;text-align:center"><div style="font-size:.6rem;color:#8b92a5">Críticos</div><div style="font-size:1.3rem;font-weight:700;color:#f87171">${r.total_unhealthy||0}</div></div>
    </div>
    ${renderL(d.unhealthy,'Críticos — Perdendo Exposição','#f87171','🚨')}
    ${renderL(d.warning,'Em Risco','#fbbf24','⚠️')}
    ${renderL(d.sem_visitas,'Sem Visitas (30 dias)','#8b92a5','👻')}
  </div></div>`;
  document.querySelectorAll('.modal-bg').forEach(m=>m.remove());
  document.body.insertAdjacentHTML('beforeend',h);
}

// Atalho Enter no filtro
document.addEventListener('keydown', e => { if(e.key === 'Escape') document.querySelectorAll('.modal-bg').forEach(m=>m.remove()); });
</script>
</body></html>"""


# ════════════════════════════════════════════════════════════════════
# HTML — PÁGINA DE CONFIGURAÇÕES
# ════════════════════════════════════════════════════════════════════
HTML_CONFIG = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QUBO — Configurações</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e27;color:#e4e6eb;font-size:.85rem}
.topbar{background:#1a1f3a;border-bottom:1px solid #2d3452;padding:10px 20px;display:flex;align-items:center;gap:12px}
.logo{font-size:1.1rem;font-weight:900;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.btn{padding:6px 14px;border:none;border-radius:5px;cursor:pointer;font-size:.78rem;font-weight:600}
.btn-blue{background:#667eea;color:#fff}.btn-green{background:#059669;color:#fff}
.btn-gray{background:#2d3452;color:#e4e6eb}.btn-yellow{background:#f59e0b;color:#000}
.btn-red{background:#dc2626;color:#fff}
.btn:hover{opacity:.85}
.page{max-width:800px;margin:0 auto;padding:24px 20px}
.section{background:#1a1f3a;border-radius:10px;border:1px solid #2d3452;margin-bottom:20px;overflow:hidden}
.section-header{padding:14px 18px;border-bottom:1px solid #2d3452;display:flex;align-items:center;gap:10px}
.section-header h2{font-size:.95rem;font-weight:700}
.section-body{padding:18px}
label{display:block;color:#8b92a5;font-size:.72rem;text-transform:uppercase;margin-bottom:5px}
input,select,textarea{width:100%;background:#0a0e27;border:1px solid #2d3452;color:#e4e6eb;padding:9px 12px;border-radius:6px;font-size:.85rem;margin-bottom:14px}
input:focus,select:focus,textarea:focus{border-color:#667eea;outline:none}
.status-ok{background:#064e3b;color:#4ade80;padding:8px 14px;border-radius:6px;font-size:.82rem;display:flex;align-items:center;gap:8px}
.status-err{background:#450a0a;color:#f87171;padding:8px 14px;border-radius:6px;font-size:.82rem;display:flex;align-items:center;gap:8px}
.upload-zone{background:#0a0e27;border:2px dashed #2d3452;border-radius:8px;padding:32px;text-align:center;cursor:pointer;transition:border-color .2s;margin-bottom:14px}
.upload-zone:hover{border-color:#667eea}
.upload-icon{font-size:2.5rem;margin-bottom:10px}
.progress-bar{height:5px;background:#2d3452;border-radius:3px;margin-top:10px;overflow:hidden;display:none}
.progress-fill{height:100%;background:#667eea;width:0%;transition:width .5s;border-radius:3px}
.info-box{background:#0a0e27;border-radius:6px;padding:10px 14px;font-size:.78rem;color:#8b92a5;margin-bottom:14px}
.row{display:flex;gap:10px;align-items:flex-end}
.row>*{flex:1}
.row>.btn{flex:0 0 auto;margin-bottom:14px}
.result-box{background:#0a0e27;border-radius:6px;padding:12px;font-size:.8rem;margin-top:10px;display:none}
</style>
</head>
<body>
<div class="topbar">
  <span class="logo">QUBO</span>
  <span style="color:#667eea;font-size:.85rem">⚙️ Configurações</span>
  <div style="flex:1"></div>
  <span style="color:#8b92a5;font-size:.75rem">{{ usuario }}</span>
  <a href="/" class="btn btn-blue">← Dashboard</a>
  <a href="/logout" class="btn btn-gray">Sair</a>
</div>

<div class="page">

  <!-- ML AUTH -->
  <div class="section">
    <div class="section-header">
      <span style="font-size:1.3rem">🔗</span>
      <div>
        <h2>Conexão Mercado Livre</h2>
        <div style="color:#8b92a5;font-size:.72rem">Token OAuth — renova automaticamente</div>
      </div>
      <div style="margin-left:auto">
        {% if ml_ok %}
        <div class="status-ok">✅ Conectado · User: {{ ml_user }}</div>
        {% else %}
        <div class="status-err">❌ Não conectado</div>
        {% endif %}
      </div>
    </div>
    <div class="section-body">
      {% if ml_ok %}
      <div class="info-box">✅ ML conectado! O token é renovado automaticamente a cada 6h. Você não precisa reconectar.</div>
      <button class="btn btn-gray" onclick="reconectarML()">🔄 Reconectar (novo token)</button>
      {% else %}
      <div class="info-box">Para conectar, clique no link abaixo, autorize o app QUBO no Mercado Livre, e cole o código que aparecer na URL.</div>
      <a href="https://auth.mercadolivre.com.br/authorization?response_type=code&client_id=5055987535998228&redirect_uri=https://www.google.com"
         target="_blank" class="btn btn-yellow" style="display:inline-block;margin-bottom:14px;text-decoration:none">
         1. Clique aqui para autorizar no ML →
      </a>
      <label>2. Cole o código TG-... que apareceu na URL</label>
      <div class="row">
        <input type="text" id="ml-code" placeholder="TG-XXXXXXXXXXX..." style="margin-bottom:0">
        <button class="btn btn-green" onclick="conectarML()" style="margin-bottom:0">Conectar</button>
      </div>
      <div id="ml-result" class="result-box"></div>
      {% endif %}
    </div>
  </div>

  <!-- UPLOAD PDF EM LOTE -->
  <div class="section">
    <div class="section-header">
      <span style="font-size:1.3rem">📤</span>
      <div>
        <h2>Importar Catálogos PDF</h2>
        <div style="color:#8b92a5;font-size:.72rem">Múltiplos PDFs de uma vez — extração com IA (Groq + Mistral)</div>
      </div>
    </div>
    <div class="section-body">
      <div class="upload-zone" id="upload-zone"
           onclick="document.getElementById('pdfInput').click()"
           ondragover="event.preventDefault();this.style.borderColor='#667eea'"
           ondragleave="this.style.borderColor='#2d3452'"
           ondrop="event.preventDefault();handleDrop(event)">
        <div class="upload-icon">📁</div>
        <div style="color:#e4e6eb;font-weight:600;margin-bottom:6px">Clique ou arraste PDFs aqui</div>
        <div style="color:#8b92a5;font-size:.75rem">Selecione um ou vários PDFs · O nome do arquivo vira o fornecedor</div>
      </div>
      <input type="file" id="pdfInput" accept=".pdf" multiple style="display:none" onchange="iniciarFila(this.files)">

      <!-- Barra de progresso geral -->
      <div class="progress-bar" id="progress-bar">
        <div class="progress-fill" id="progress-fill"></div>
      </div>

      <!-- Contador geral -->
      <div id="batch-counter" style="display:none;font-size:.78rem;color:#8b92a5;margin-top:8px;margin-bottom:8px"></div>

      <!-- Fila de arquivos -->
      <div id="fila-upload" style="display:none;margin-top:12px">
        <div style="font-size:.72rem;color:#8b92a5;text-transform:uppercase;margin-bottom:8px;font-weight:600">Fila de processamento</div>
        <div id="fila-itens"></div>
      </div>

      <!-- Resumo final -->
      <div id="upload-result" class="result-box"></div>
    </div>
  </div>

  <!-- VERIFICAR PDFs LOCAL -->
  <div class="section">
    <div class="section-header">
      <span style="font-size:1.3rem">📁</span>
      <div>
        <h2>Pasta de Monitoramento (File Watcher)</h2>
        <div style="color:#8b92a5;font-size:.72rem">Pasta local monitorada pelo watcher automático</div>
      </div>
    </div>
    <div class="section-body">
      <label>Caminho da pasta de PDFs</label>
      <div class="row">
        <input type="text" id="pasta-input" placeholder="C:\\Users\\...\\pasta-dos-catalogos" style="margin-bottom:0"
               value="C:\\Users\\Luiz Gustavo\\OneDrive\\Documents\\Escalada Econ\\Loja QUBO\\Fornecedores\\1 -SISTEMA CATALOGOS AUTOMATICO">
        <button class="btn btn-blue" onclick="salvarPasta()" style="margin-bottom:0">Salvar</button>
      </div>
      <div style="height:10px"></div>
      <button class="btn btn-gray" onclick="verificarPDFs()">🔍 Verificar PDFs na Pasta</button>
      <div id="pasta-result" class="result-box"></div>
    </div>
  </div>

  <!-- INFO -->
  <div class="section">
    <div class="section-header">
      <span style="font-size:1.3rem">ℹ️</span>
      <h2>Informações do Sistema</h2>
    </div>
    <div class="section-body">
      <div class="info-box" style="line-height:1.8">
        <strong>Dashboard:</strong> https://qubo-dashboard.onrender.com<br>
        <strong>Banco:</strong> Supabase PostgreSQL<br>
        <strong>File Watcher:</strong> QUBO_FileWatcher (Tarefa Windows — inicia com o login)<br>
        <strong>Credenciais:</strong> gustavo / qubo2026<br>
        <strong>ML Client ID:</strong> 5055987535998228
      </div>
    </div>
  </div>

</div>

<script>
function showToast(msg, ok=true){
  const box = document.createElement('div');
  box.textContent = msg;
  box.style.cssText = `position:fixed;bottom:20px;right:20px;padding:10px 16px;border-radius:6px;
    font-size:.82rem;font-weight:600;z-index:9999;
    background:${ok?'#064e3b':'#450a0a'};color:${ok?'#4ade80':'#f87171'};
    border:1px solid ${ok?'#4ade80':'#f87171'}`;
  document.body.appendChild(box);
  setTimeout(()=>box.remove(), 3500);
}

function conectarML(){
  const code = document.getElementById('ml-code').value.trim();
  if(!code){ showToast('Cole o código primeiro!', false); return; }
  showToast('🔄 Conectando...');
  fetch('/api/ml-auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})})
  .then(r=>r.json()).then(d=>{
    const box = document.getElementById('ml-result');
    box.style.display='block';
    if(d.ok){
      box.style.color='#4ade80';
      box.innerHTML='✅ Conectado! User ID: '+d.user_id+'<br>Recarregando...';
      setTimeout(()=>location.reload(), 1500);
    } else {
      box.style.color='#f87171';
      box.innerHTML='❌ '+d.erro;
    }
  }).catch(()=>showToast('❌ Erro de conexão',false));
}

function reconectarML(){
  if(!confirm('Tem certeza? Você precisará autorizar novamente no ML.')) return;
  window.open('https://auth.mercadolivre.com.br/authorization?response_type=code&client_id=5055987535998228&redirect_uri=https://www.google.com','_blank');
}

function handleDrop(e){
  const files = Array.from(e.dataTransfer.files).filter(f=>f.name.toLowerCase().endsWith('.pdf'));
  if(!files.length){ showToast('❌ Apenas arquivos PDF', false); return; }
  iniciarFila(files);
}

function iniciarFila(fileList){
  const files = Array.from(fileList).filter(f=>f.name.toLowerCase().endsWith('.pdf'));
  if(!files.length){ showToast('❌ Nenhum PDF selecionado', false); return; }

  // Reseta UI
  const bar = document.getElementById('progress-bar');
  const fill = document.getElementById('progress-fill');
  const result = document.getElementById('upload-result');
  const counter = document.getElementById('batch-counter');
  const fila = document.getElementById('fila-upload');
  const itens = document.getElementById('fila-itens');

  bar.style.display='block'; fill.style.width='0%';
  result.style.display='none';
  fila.style.display='block';
  itens.innerHTML='';
  counter.style.display='block';
  counter.textContent='Preparando '+files.length+' arquivo(s)...';

  // Cria uma linha por arquivo na fila
  files.forEach((f,i)=>{
    const row = document.createElement('div');
    row.id='fila-item-'+i;
    row.style.cssText='display:flex;align-items:center;gap:10px;padding:7px 10px;border-radius:5px;background:#0a0e27;margin-bottom:6px;font-size:.78rem';
    row.innerHTML=`<span id="fila-icon-${i}" style="font-size:1rem">⏳</span>
      <span style="flex:1;color:#c4c9d4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${f.name}</span>
      <span id="fila-status-${i}" style="color:#8b92a5;white-space:nowrap">Aguardando...</span>`;
    itens.appendChild(row);
  });

  // Processa sequencialmente
  let totalSalvos=0, ok=0, erros=0;
  (async()=>{
    for(let i=0;i<files.length;i++){
      const f=files[i];
      const icon=document.getElementById('fila-icon-'+i);
      const status=document.getElementById('fila-status-'+i);
      const row=document.getElementById('fila-item-'+i);

      icon.textContent='🔄';
      status.style.color='#667eea';
      status.textContent='Enviando...';
      counter.textContent=`Processando ${i+1} de ${files.length}...`;
      fill.style.width=((i/files.length)*100)+'%';

      try{
        const fd=new FormData(); fd.append('arquivo',f);
        const r=await fetch('/api/upload-pdf',{method:'POST',body:fd});
        const d=await r.json();
        if(d.ok){
          icon.textContent='✅';
          status.style.color='#4ade80';
          status.textContent=d.produtos_extraidos+' produtos ('+d.provider+')';
          row.style.background='#052e16';
          totalSalvos+=d.produtos_extraidos; ok++;
        } else {
          icon.textContent='❌';
          status.style.color='#f87171';
          status.textContent=d.erro||'Erro desconhecido';
          row.style.background='#2d0a0a';
          erros++;
        }
      }catch(e){
        icon.textContent='❌';
        status.style.color='#f87171';
        status.textContent='Erro de conexão';
        row.style.background='#2d0a0a';
        erros++;
      }
    }

    // Resumo final
    fill.style.width='100%';
    counter.style.display='none';
    result.style.display='block';
    if(ok>0 && erros===0){
      result.style.color='#4ade80';
      result.innerHTML=`✅ <strong>${ok} PDF(s)</strong> importados com sucesso · <strong>${totalSalvos} produtos</strong> extraídos!<br><a href="/" style="color:#667eea">Ver no Dashboard →</a>`;
      showToast('✅ '+totalSalvos+' produtos importados!');
    } else if(ok>0){
      result.style.color='#f59e0b';
      result.innerHTML=`⚠️ <strong>${ok} OK</strong> (${totalSalvos} produtos) · <strong>${erros} com erro</strong><br><a href="/" style="color:#667eea">Ver no Dashboard →</a>`;
      showToast('⚠️ '+ok+' OK, '+erros+' com erro', false);
    } else {
      result.style.color='#f87171';
      result.innerHTML='❌ Todos os uploads falharam. Verifique os erros acima.';
      showToast('❌ Falha no upload', false);
    }
    setTimeout(()=>{bar.style.display='none';fill.style.width='0%';},3000);
  })();
}

function salvarPasta(){
  const pasta = document.getElementById('pasta-input').value.trim();
  if(!pasta){ showToast('Digite o caminho da pasta', false); return; }
  fetch('/api/config-pasta',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pasta})})
  .then(r=>r.json()).then(d=>{ if(d.ok) showToast('✅ Pasta salva!'); else showToast('❌ '+d.erro,false); });
}

function verificarPDFs(){
  showToast('🔍 Verificando...');
  fetch('/api/verificar-pdfs').then(r=>r.json()).then(d=>{
    const box = document.getElementById('pasta-result');
    box.style.display='block';
    if(d.ok){
      box.style.color='#4ade80';
      box.innerHTML='📁 <strong>'+d.pasta+'</strong><br>'+
        '📄 PDFs pendentes: <strong>'+d.pdfs+'</strong> | ✅ Enviados: <strong>'+d.enviados+'</strong>'+
        (d.pdfs>0?'<br><br>Arquivos:<br>'+d.arquivos.map(f=>'• '+f).join('<br>'):'');
    } else {
      box.style.color='#f87171';
      box.innerHTML='❌ '+d.erro;
    }
  }).catch(()=>showToast('❌ Erro',false));
}
</script>
</body></html>"""


# ════════════════════════════════════════════════════════════════════
# PÁGINA ESCOLHIDOS (Formação de Preço)
# ════════════════════════════════════════════════════════════════════
@app.route('/escolhidos')
@login_required
def escolhidos():
    tenant = get_tenant_id(); p = ph()
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"SELECT * FROM produtos WHERE tenant_id = {p} AND escolhido = 1 ORDER BY fornecedor, descricao", [tenant])
    cols = [d[0] for d in cur.description]
    produtos = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    usuario = get_usuario_nome()
    return render_template_string(HTML_ESCOLHIDOS, produtos=produtos, usuario=usuario, total=len(produtos))

@app.route('/exportar-escolhidos')
@login_required
def exportar_escolhidos():
    import openpyxl; from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    tenant = get_tenant_id(); p = ph()
    conn = get_conn(); cur = conn.cursor()
    cur.execute(f"SELECT * FROM produtos WHERE tenant_id = {p} AND escolhido = 1 ORDER BY fornecedor", [tenant])
    cols = [d[0] for d in cur.description]; rows = cur.fetchall(); conn.close()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Escolhidos QUBO"
    headers = ['Fornecedor','Código','Descrição','Custo','Preço ML','Taxa %','Frete','Custo Total','Margem %','Margem R$','Viável']
    fill = PatternFill(fgColor="1a1f3a", fill_type="solid")
    for i, h in enumerate(headers, 1):
        c = ws.cell(1, i, h); c.fill = fill; c.font = Font(color="FFFFFF", bold=True)
    for row in rows:
        d = dict(zip(cols, row))
        ws.append([d.get('fornecedor'), d.get('codigo'), d.get('descricao'), d.get('custo'),
                   d.get('preco_ml'), round((d.get('taxa_categoria') or 0)*100,1),
                   d.get('custo_frete'), d.get('custo_total'), d.get('margem_percentual'),
                   d.get('margem_reais'), 'SIM' if d.get('viavel') else 'NÃO'])
    output = io.BytesIO(); wb.save(output); output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True, download_name=f'qubo_escolhidos_{datetime.now().strftime("%Y%m%d")}.xlsx')

HTML_ESCOLHIDOS = """<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>QUBO — Escolhidos</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#0a0e27;color:#e4e6eb;font-size:.85rem}
.topbar{background:#1a1f3a;border-bottom:1px solid #2d3452;padding:8px 16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;position:sticky;top:0}
.logo{font-size:1.1rem;font-weight:900;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.btn{padding:5px 12px;border:none;border-radius:5px;cursor:pointer;font-size:.78rem;font-weight:600;text-decoration:none;display:inline-block}
.btn-blue{background:#667eea;color:#fff}.btn-green{background:#059669;color:#fff}.btn-gray{background:#2d3452;color:#e4e6eb}
.table-wrap{overflow-x:auto;padding:16px}
table{width:100%;border-collapse:collapse;background:#1a1f3a;border-radius:8px;overflow:hidden;font-size:.78rem}
thead{background:#0f1328}
th,td{padding:7px 8px;border-bottom:1px solid #151929;text-align:left}
th{color:#8b92a5;font-weight:600}
tr:hover td{background:#1f2544}
.badge-ok{background:#064e3b;color:#4ade80;padding:1px 6px;border-radius:8px;font-size:.65rem;font-weight:700}
.badge-no{background:#450a0a;color:#f87171;padding:1px 6px;border-radius:8px;font-size:.65rem;font-weight:700}
</style></head>
<body>
<div class="topbar">
  <span class="logo">QUBO</span>
  <span style="color:#8b92a5">⭐ Escolhidos ({{ total }})</span>
  <div style="flex:1"></div>
  <a href="/exportar-escolhidos" class="btn btn-green">📥 Exportar Excel</a>
  <a href="/" class="btn btn-blue">← Dashboard</a>
</div>
<div class="table-wrap">
<table>
<thead><tr>
  <th>Fornecedor</th><th>Código</th><th>Descrição</th><th>Custo</th><th>Preço ML</th>
  <th>Taxa%</th><th>Frete</th><th>Custo Total</th><th>Margem%</th><th>Margem R$</th><th>Status</th>
</tr></thead>
<tbody>
{% for p in produtos %}
<tr>
  <td style="color:#8b92a5">{{ p.fornecedor }}</td>
  <td style="color:#8b92a5">{{ p.codigo or '' }}</td>
  <td>{{ p.descricao }}</td>
  <td style="color:#fbbf24">R$ {{ p.custo|br }}</td>
  <td style="color:#4ade80;font-weight:700">R$ {{ p.preco_ml|br }}</td>
  <td style="color:#8b92a5">{{ ((p.taxa_categoria or 0.165)*100)|br(1) }}%</td>
  <td>{{ p.custo_frete|br if p.custo_frete else '-' }}</td>
  <td>{{ p.custo_total|br if p.custo_total else '-' }}</td>
  <td style="color:{{ '#4ade80' if (p.margem_percentual or 0) >= 20 else '#f87171' }};font-weight:700">
    {{ p.margem_percentual|br(1) }}%</td>
  <td style="color:{{ '#4ade80' if (p.margem_reais or 0) >= 0 else '#f87171' }}">
    R$ {{ p.margem_reais|br }}</td>
  <td>{% if p.viavel %}<span class="badge-ok">VIÁVEL</span>{% else %}<span class="badge-no">BAIXO</span>{% endif %}</td>
</tr>
{% else %}
<tr><td colspan="11" style="text-align:center;padding:40px;color:#8b92a5">
  Nenhum produto escolhido ainda. <a href="/" style="color:#667eea">Voltar ao Dashboard →</a>
</td></tr>
{% endfor %}
</tbody>
</table>
</div>
</body></html>"""

# ════════════════════════════════════════════════════════════════════
# STARTUP — roda tanto com gunicorn quanto com python direto
# ════════════════════════════════════════════════════════════════════
def _startup():
    """Inicializa banco e config. Erros são logados, nunca crasham o app."""
    try:
        garantir_schema()
        logger.info("Schema OK")
    except Exception as e:
        logger.error(f"garantir_schema falhou: {e}")
    try:
        garantir_config()
        logger.info("Config OK")
    except Exception as e:
        logger.error(f"garantir_config falhou: {e}")

_startup()   # executa ao importar o módulo (gunicorn + python direto)

if __name__ == '__main__':
    PORT = int(os.getenv('PORT', 10000))
    logger.info(f"QUBO Dashboard v4 | 0.0.0.0:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
