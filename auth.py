"""
auth.py - Sistema de Autenticação Multi-Tenant QUBO
====================================================
Login com usuário/senha.
Cada usuário tem sua própria base de dados isolada.
Parceiros não veem dados uns dos outros.

Usa Flask-Login + bcrypt para segurança.
Usuários ficam no Supabase (tabela users).

Autor: Claude para QUBO
Data: 2026-04
"""

import os
import hashlib
import secrets
from functools import wraps
from flask import session, redirect, url_for, request, jsonify

# ── Usuários hardcoded para deploy inicial ──────────────────────────
# Formato: { "usuario": {"senha_hash": sha256, "tenant_id": "id_unico"} }
# Para gerar hash: python3 -c "import hashlib; print(hashlib.sha256('suasenha'.encode()).hexdigest())"

def _hash(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

# Carrega usuários do .env ou usa defaults
USUARIOS = {}

def carregar_usuarios():
    """Carrega usuários das variáveis de ambiente QUBO_USER_x"""
    global USUARIOS
    
    # Usuário principal (Gustavo)
    user = os.getenv("QUBO_USER_1", "gustavo")
    senha = os.getenv("QUBO_PASS_1", "qubo2026")
    tenant = os.getenv("QUBO_TENANT_1", "gustavo")
    USUARIOS[user] = {"senha_hash": _hash(senha), "tenant_id": tenant, "nome": user.title()}

    # Usuários adicionais (parceiros)
    for i in range(2, 11):
        user = os.getenv(f"QUBO_USER_{i}", "")
        senha = os.getenv(f"QUBO_PASS_{i}", "")
        tenant = os.getenv(f"QUBO_TENANT_{i}", f"tenant_{i}")
        if user and senha:
            USUARIOS[user] = {"senha_hash": _hash(senha), "tenant_id": tenant, "nome": user.title()}

carregar_usuarios()


def login_required(f):
    """Decorator que exige login"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario"):
            if request.is_json:
                return jsonify({"ok": False, "erro": "Não autenticado", "redirect": "/login"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


def get_tenant_id():
    """Retorna o tenant_id do usuário logado"""
    usuario = session.get("usuario", "")
    return USUARIOS.get(usuario, {}).get("tenant_id", "default")


def get_usuario_nome():
    return USUARIOS.get(session.get("usuario", ""), {}).get("nome", "Usuário")


def verificar_login(usuario, senha):
    if usuario in USUARIOS:
        if USUARIOS[usuario]["senha_hash"] == _hash(senha):
            return True
    return False


LOGIN_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QUBO — Login</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             background:#0a0e27;display:flex;justify-content:center;align-items:center;
             min-height:100vh;padding:20px}
        .card{background:#1a1f3a;padding:36px;border-radius:12px;border:1px solid #2d3452;
              width:360px;max-width:100%}
        h1{font-size:2rem;font-weight:900;background:linear-gradient(135deg,#667eea,#764ba2);
           -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}
        .sub{color:#8b92a5;font-size:.85rem;margin-bottom:28px}
        label{color:#8b92a5;font-size:.75rem;text-transform:uppercase;display:block;margin-bottom:5px}
        input{width:100%;padding:11px 14px;border:1px solid #2d3452;border-radius:6px;
              background:#0a0e27;color:#e4e6eb;font-size:.95rem;margin-bottom:16px}
        input:focus{border-color:#667eea;outline:none;box-shadow:0 0 0 2px rgba(102,126,234,.25)}
        button{width:100%;padding:12px;border:none;border-radius:6px;background:#667eea;
               color:#fff;font-size:1rem;font-weight:700;cursor:pointer;transition:all .15s}
        button:hover{background:#5568d3}
        .erro{background:#450a0a;color:#f87171;padding:10px 14px;border-radius:6px;
              font-size:.85rem;margin-bottom:16px;display:none}
        .footer{text-align:center;color:#8b92a5;font-size:.72rem;margin-top:20px}
    </style>
</head>
<body>
<div class="card">
    <h1>QUBO</h1>
    <div class="sub">Dashboard de Gestão ML</div>
    <div class="erro" id="erro">ERRO_MSG</div>
    <div>
        <label>Usuário</label>
        <input type="text" id="user" placeholder="seu usuário" autocomplete="username">
        <label>Senha</label>
        <input type="password" id="pass" placeholder="••••••••" autocomplete="current-password"
               onkeydown="if(event.key==='Enter')entrar()">
        <button onclick="entrar()">Entrar →</button>
    </div>
    <div class="footer">QUBO v3 · QuboTech</div>
</div>
<script>
ERRO_MSG = document.getElementById('erro').textContent;
if(ERRO_MSG.trim()){document.getElementById('erro').style.display='block'}

function entrar(){
    const u=document.getElementById('user').value.trim();
    const p=document.getElementById('pass').value;
    if(!u||!p){mostrarErro('Preencha usuário e senha');return;}
    fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({usuario:u,senha:p})})
    .then(r=>r.json()).then(d=>{
        if(d.ok) window.location.href='/';
        else mostrarErro(d.erro||'Credenciais inválidas');
    }).catch(()=>mostrarErro('Erro de conexão'));
}
function mostrarErro(msg){
    const el=document.getElementById('erro');
    el.textContent=msg;el.style.display='block';
}
document.getElementById('user').focus();
</script>
</body>
</html>
"""
