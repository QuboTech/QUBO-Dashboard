"""
auth.py - Autenticação Vitrix/Qubo (multi-tenant)
==================================================
- Login via env vars (compat Qubo) OU via tabela `usuarios` no DB (novos signups)
- Sessão guarda: `usuario`, `tenant_id`, `tenant_slug`, `tenant_nome`
- Signup cria tenant + usuário admin no DB
"""
import os
import hashlib
import re
from functools import wraps
from flask import session, redirect, request, jsonify


def _hash(senha):
    return hashlib.sha256(str(senha).encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# ENV-VAR USERS (compat — Qubo e usuários legacy)
# ─────────────────────────────────────────────────────────────────────────────
def get_usuarios_env():
    """Monta dict de usuarios das env vars (modo Qubo / legado)."""
    usuarios = {}
    user1 = os.environ.get('QUBO_USER_1', 'gustavo')
    pass1 = os.environ.get('QUBO_PASS_1', 'qubo2026')
    ten1  = os.environ.get('QUBO_TENANT_1', 'qubo')
    usuarios[user1] = {
        'senha_hash': _hash(pass1),
        'tenant_id': ten1,
        'tenant_slug': ten1,
        'tenant_nome': 'Qubo',
        'nome': user1.title(),
        'fonte': 'env'
    }
    for i in range(2, 11):
        u = os.environ.get(f'QUBO_USER_{i}', '')
        p = os.environ.get(f'QUBO_PASS_{i}', '')
        t = os.environ.get(f'QUBO_TENANT_{i}', f'tenant{i}')
        if u and p:
            usuarios[u] = {
                'senha_hash': _hash(p),
                'tenant_id': t,
                'tenant_slug': t,
                'tenant_nome': t.title(),
                'nome': u.title(),
                'fonte': 'env'
            }
    return usuarios


# ─────────────────────────────────────────────────────────────────────────────
# DB USERS (novos signups via Vitrix)
# ─────────────────────────────────────────────────────────────────────────────
def _buscar_usuario_db(email_ou_login):
    """Busca usuário no DB por email. Retorna dict ou None."""
    try:
        from db import get_conn, USAR_POSTGRES
        ph = "%s" if USAR_POSTGRES else "?"
        conn = get_conn(); cur = conn.cursor()
        cur.execute(f"""
            SELECT u.email, u.senha_hash, u.nome, u.role, u.tenant_id, t.nome_empresa, t.slug
            FROM usuarios u
            LEFT JOIN tenants t ON t.slug = u.tenant_id
            WHERE LOWER(u.email) = LOWER({ph}) AND u.ativo = 1
        """, (email_ou_login.strip(),))
        r = cur.fetchone()
        conn.close()
        if not r:
            return None
        return {
            'email': r[0], 'senha_hash': r[1], 'nome': r[2] or r[0],
            'role': r[3] or 'admin',
            'tenant_id': r[4], 'tenant_slug': r[6] or r[4],
            'tenant_nome': r[5] or r[4],
            'fonte': 'db'
        }
    except Exception:
        return None


def verificar_login(usuario, senha):
    """Verifica credenciais. Retorna dict do usuário (com tenant) ou None."""
    # 1) Tenta env vars (compat Qubo)
    usuarios = get_usuarios_env()
    key = usuario.strip().lower()
    u = usuarios.get(key) or usuarios.get(usuario.strip())
    if u and u['senha_hash'] == _hash(senha):
        return u

    # 2) Tenta DB (Vitrix signup)
    u = _buscar_usuario_db(usuario)
    if u and u['senha_hash'] == _hash(senha):
        return u

    return None


# ─────────────────────────────────────────────────────────────────────────────
# SIGNUP
# ─────────────────────────────────────────────────────────────────────────────
def _slugify(texto):
    s = re.sub(r'[^a-z0-9]+', '-', (texto or '').lower()).strip('-')
    return s[:40] or 'empresa'


def criar_tenant_e_admin(nome_empresa: str, email: str, senha: str, nome_admin: str = '') -> dict:
    """Cria um tenant + primeiro usuário admin. Retorna dict ok/erro."""
    try:
        from db import get_conn, USAR_POSTGRES
        if not nome_empresa or not email or not senha:
            return {'ok': False, 'erro': 'Preencha nome da empresa, email e senha'}
        if len(senha) < 6:
            return {'ok': False, 'erro': 'Senha precisa ter ao menos 6 caracteres'}
        if '@' not in email:
            return {'ok': False, 'erro': 'Email inválido'}

        ph = "%s" if USAR_POSTGRES else "?"
        conn = get_conn(); cur = conn.cursor()

        # Email já existe?
        cur.execute(f"SELECT id FROM usuarios WHERE LOWER(email) = LOWER({ph})", (email.strip(),))
        if cur.fetchone():
            conn.close()
            return {'ok': False, 'erro': 'Este email já está cadastrado'}

        # Gera slug único
        base_slug = _slugify(nome_empresa)
        slug = base_slug
        n = 1
        while True:
            cur.execute(f"SELECT id FROM tenants WHERE slug = {ph}", (slug,))
            if not cur.fetchone():
                break
            n += 1; slug = f"{base_slug}-{n}"
            if n > 99: slug = f"{base_slug}-{int(__import__('time').time())}"; break

        # Cria tenant
        cur.execute(f"""
            INSERT INTO tenants (slug, nome_empresa, email_admin, plano, ativo)
            VALUES ({ph},{ph},{ph},'free',1)
        """, (slug, nome_empresa.strip(), email.strip()))

        # Cria usuário admin
        cur.execute(f"""
            INSERT INTO usuarios (tenant_id, email, senha_hash, nome, role, ativo)
            VALUES ({ph},{ph},{ph},{ph},'admin',1)
        """, (slug, email.strip(), _hash(senha), nome_admin or email.split('@')[0]))

        conn.commit(); conn.close()
        return {'ok': True, 'tenant_slug': slug, 'nome_empresa': nome_empresa.strip()}
    except Exception as e:
        return {'ok': False, 'erro': f'Erro ao criar conta: {e}'}


def convidar_usuario(tenant_slug: str, email: str, senha: str, nome: str = '', role: str = 'user') -> dict:
    """Admin convida novo usuário pro seu tenant."""
    try:
        from db import get_conn, USAR_POSTGRES
        if not email or not senha:
            return {'ok': False, 'erro': 'Preencha email e senha'}
        if len(senha) < 6:
            return {'ok': False, 'erro': 'Senha precisa ter ao menos 6 caracteres'}

        ph = "%s" if USAR_POSTGRES else "?"
        conn = get_conn(); cur = conn.cursor()
        cur.execute(f"SELECT id FROM usuarios WHERE LOWER(email) = LOWER({ph})", (email.strip(),))
        if cur.fetchone():
            conn.close()
            return {'ok': False, 'erro': 'Email já cadastrado'}

        cur.execute(f"""
            INSERT INTO usuarios (tenant_id, email, senha_hash, nome, role, ativo)
            VALUES ({ph},{ph},{ph},{ph},{ph},1)
        """, (tenant_slug, email.strip(), _hash(senha), nome or email.split('@')[0], role or 'user'))
        conn.commit(); conn.close()
        return {'ok': True, 'email': email.strip()}
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


def listar_usuarios_tenant(tenant_slug: str) -> list:
    try:
        from db import get_conn, USAR_POSTGRES
        ph = "%s" if USAR_POSTGRES else "?"
        conn = get_conn(); cur = conn.cursor()
        cur.execute(f"""
            SELECT id, email, nome, role, ativo, criado_em
            FROM usuarios WHERE tenant_id = {ph} ORDER BY id
        """, (tenant_slug,))
        rows = cur.fetchall(); conn.close()
        return [{
            'id': r[0], 'email': r[1], 'nome': r[2] or r[1],
            'role': r[3], 'ativo': bool(r[4]), 'criado_em': str(r[5] or '')[:16]
        } for r in rows]
    except Exception:
        return []


def remover_usuario_tenant(tenant_slug: str, usuario_id: int) -> dict:
    try:
        from db import get_conn, USAR_POSTGRES
        ph = "%s" if USAR_POSTGRES else "?"
        conn = get_conn(); cur = conn.cursor()
        cur.execute(f"UPDATE usuarios SET ativo=0 WHERE id={ph} AND tenant_id={ph}",
                    (usuario_id, tenant_slug))
        conn.commit(); conn.close()
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'erro': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# TENANT INFO
# ─────────────────────────────────────────────────────────────────────────────
def get_tenant_info(slug: str) -> dict:
    """Retorna dados completos do tenant."""
    try:
        from db import get_conn, USAR_POSTGRES
        ph = "%s" if USAR_POSTGRES else "?"
        conn = get_conn(); cur = conn.cursor()
        cur.execute(f"""
            SELECT slug, nome_empresa, plano, ativo, email_admin, cor_primaria, criado_em
            FROM tenants WHERE slug = {ph}
        """, (slug,))
        r = cur.fetchone(); conn.close()
        if not r:
            return {'slug': slug, 'nome_empresa': slug.title(), 'plano': 'free'}
        return {
            'slug': r[0], 'nome_empresa': r[1], 'plano': r[2],
            'ativo': bool(r[3]), 'email_admin': r[4],
            'cor_primaria': r[5] or '#667eea', 'criado_em': str(r[6] or '')[:10]
        }
    except Exception:
        return {'slug': slug, 'nome_empresa': slug.title(), 'plano': 'free'}


# ─────────────────────────────────────────────────────────────────────────────
# SESSION HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_tenant_id():
    """Retorna tenant_slug da sessão (fonte de isolamento)."""
    return session.get('tenant_slug') or session.get('tenant_id') or 'qubo'


def get_usuario_nome():
    return session.get('usuario_nome') or session.get('usuario', 'Usuário')


def get_tenant_nome():
    return session.get('tenant_nome', 'Vitrix')


def is_admin():
    return session.get('role') == 'admin'


def carregar_usuarios():
    pass  # compat


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('usuario'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'ok': False, 'erro': 'Não autenticado', 'redirect': '/login'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('usuario'):
            return redirect('/login')
        if session.get('role') != 'admin':
            if request.is_json:
                return jsonify({'ok': False, 'erro': 'Requer admin'}), 403
            return redirect('/')
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN PAGE (Vitrix branded)
# ─────────────────────────────────────────────────────────────────────────────
LOGIN_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vitrix — Login</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:radial-gradient(ellipse at top,#1a1f3a 0%,#0a0e27 60%);
     display:flex;justify-content:center;align-items:center;
     min-height:100vh;padding:20px;color:#e4e6eb}
.card{background:#1a1f3a;padding:40px;border-radius:14px;
      border:1px solid #2d3452;width:420px;max-width:100%;
      box-shadow:0 20px 60px rgba(0,0,0,.5)}
.logo{font-size:2.6rem;font-weight:900;
     background:linear-gradient(135deg,#667eea,#c084fc,#e879f9);
     -webkit-background-clip:text;-webkit-text-fill-color:transparent;
     margin-bottom:4px;letter-spacing:-1px}
.sub{color:#8b92a5;font-size:.85rem;margin-bottom:28px}
label{color:#8b92a5;font-size:.72rem;text-transform:uppercase;
      display:block;margin-bottom:6px;letter-spacing:.5px}
input{width:100%;padding:12px 14px;border:1px solid #2d3452;border-radius:8px;
      background:#0a0e27;color:#e4e6eb;font-size:.95rem;margin-bottom:16px;
      transition:border-color .15s}
input:focus{border-color:#667eea;outline:none}
button{width:100%;padding:14px;border:none;border-radius:8px;
       background:linear-gradient(135deg,#667eea,#764ba2);
       color:#fff;font-size:1rem;font-weight:700;cursor:pointer;
       transition:transform .1s}
button:hover{transform:translateY(-1px)}
.erro{background:#450a0a;color:#f87171;padding:10px 14px;border-radius:6px;
      font-size:.85rem;margin-bottom:16px;display:none}
.links{text-align:center;color:#8b92a5;font-size:.8rem;margin-top:20px}
.links a{color:#c084fc;text-decoration:none;font-weight:600}
.footer{text-align:center;color:#555a6e;font-size:.68rem;margin-top:24px;letter-spacing:.5px}
</style>
</head>
<body>
<div class="card">
  <div class="logo">Vitrix</div>
  <div class="sub">Inteligência de vendas para Mercado Livre</div>
  <div class="erro" id="erro"></div>
  <label>Email ou usuário</label>
  <input type="text" id="user" placeholder="seu@email.com" autocomplete="username">
  <label>Senha</label>
  <input type="password" id="pass" placeholder="sua senha"
         onkeydown="if(event.key==='Enter')entrar()">
  <button onclick="entrar()">Entrar</button>
  <div class="links">
    Não tem conta? <a href="/signup">Criar empresa grátis</a>
  </div>
  <div class="footer">VITRIX · powered by Qubo</div>
</div>
<script>
function entrar(){
    var u=document.getElementById('user').value.trim();
    var p=document.getElementById('pass').value;
    if(!u||!p){mostrarErro('Preencha email/usuário e senha');return;}
    fetch('/api/login',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({usuario:u,senha:p})})
    .then(function(r){return r.json();})
    .then(function(d){
        if(d.ok) window.location.href='/';
        else mostrarErro(d.erro||'Credenciais inválidas');
    }).catch(function(){mostrarErro('Erro de conexão');});
}
function mostrarErro(msg){
    var el=document.getElementById('erro');
    el.textContent=msg;el.style.display='block';
}
document.getElementById('user').focus();
</script>
</body>
</html>"""


SIGNUP_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vitrix — Criar conta</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:radial-gradient(ellipse at top,#1a1f3a 0%,#0a0e27 60%);
     display:flex;justify-content:center;align-items:center;
     min-height:100vh;padding:20px;color:#e4e6eb}
.card{background:#1a1f3a;padding:40px;border-radius:14px;
      border:1px solid #2d3452;width:460px;max-width:100%;
      box-shadow:0 20px 60px rgba(0,0,0,.5)}
.logo{font-size:2.6rem;font-weight:900;
     background:linear-gradient(135deg,#667eea,#c084fc,#e879f9);
     -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px}
.sub{color:#8b92a5;font-size:.85rem;margin-bottom:24px}
label{color:#8b92a5;font-size:.72rem;text-transform:uppercase;
      display:block;margin-bottom:6px;letter-spacing:.5px}
input{width:100%;padding:12px 14px;border:1px solid #2d3452;border-radius:8px;
      background:#0a0e27;color:#e4e6eb;font-size:.95rem;margin-bottom:14px}
input:focus{border-color:#667eea;outline:none}
button{width:100%;padding:14px;border:none;border-radius:8px;
       background:linear-gradient(135deg,#10b981,#059669);
       color:#fff;font-size:1rem;font-weight:700;cursor:pointer}
.erro{background:#450a0a;color:#f87171;padding:10px 14px;border-radius:6px;
      font-size:.85rem;margin-bottom:16px;display:none}
.ok{background:#064e3b;color:#4ade80;padding:10px 14px;border-radius:6px;
    font-size:.85rem;margin-bottom:16px;display:none}
.links{text-align:center;color:#8b92a5;font-size:.8rem;margin-top:18px}
.links a{color:#c084fc;text-decoration:none;font-weight:600}
.perk{display:flex;gap:8px;align-items:center;color:#4ade80;font-size:.78rem;margin-bottom:4px}
.perks{background:#064e3b2a;border-left:3px solid #10b981;padding:10px 12px;border-radius:6px;margin-bottom:18px}
</style>
</head>
<body>
<div class="card">
  <div class="logo">Vitrix</div>
  <div class="sub">Crie sua conta grátis — sem cartão</div>
  <div class="perks">
    <div class="perk">✓ Conecte sua conta do Mercado Livre</div>
    <div class="perk">✓ Espião de concorrentes + métricas</div>
    <div class="perk">✓ Dados 100% isolados da sua empresa</div>
  </div>
  <div class="erro" id="erro"></div>
  <div class="ok" id="ok"></div>
  <label>Nome da empresa</label>
  <input type="text" id="empresa" placeholder="Minha Loja LTDA" autofocus>
  <label>Seu nome</label>
  <input type="text" id="nome" placeholder="João da Silva">
  <label>Email</label>
  <input type="email" id="email" placeholder="voce@empresa.com.br">
  <label>Senha (mín. 6 caracteres)</label>
  <input type="password" id="senha" placeholder="••••••••"
         onkeydown="if(event.key==='Enter')criar()">
  <button onclick="criar()">Criar empresa + Entrar</button>
  <div class="links">
    Já tem conta? <a href="/login">Entrar</a>
  </div>
</div>
<script>
function criar(){
    var e=document.getElementById('empresa').value.trim();
    var n=document.getElementById('nome').value.trim();
    var m=document.getElementById('email').value.trim();
    var s=document.getElementById('senha').value;
    if(!e||!m||!s){mostrarErro('Preencha todos os campos obrigatórios');return;}
    fetch('/api/signup',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({nome_empresa:e,nome:n,email:m,senha:s})})
    .then(function(r){return r.json();})
    .then(function(d){
        if(d.ok){
            document.getElementById('ok').textContent='✓ Conta criada! Entrando...';
            document.getElementById('ok').style.display='block';
            setTimeout(function(){window.location.href='/ml';},800);
        } else mostrarErro(d.erro||'Erro ao criar conta');
    }).catch(function(){mostrarErro('Erro de conexão');});
}
function mostrarErro(msg){
    var el=document.getElementById('erro');
    el.textContent=msg;el.style.display='block';
    document.getElementById('ok').style.display='none';
}
</script>
</body>
</html>"""
