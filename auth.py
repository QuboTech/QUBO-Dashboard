"""
auth.py - Autenticacao QUBO
Login simples com usuario/senha via variaveis de ambiente.
"""
import os
import hashlib
from functools import wraps
from flask import session, redirect, request, jsonify


def _hash(senha):
    return hashlib.sha256(str(senha).encode()).hexdigest()


def get_usuarios():
    """Monta dict de usuarios sempre frescos das env vars"""
    usuarios = {}
    
    # Padrao garantido - funciona mesmo sem env vars
    user1 = os.environ.get('QUBO_USER_1', 'gustavo')
    pass1 = os.environ.get('QUBO_PASS_1', 'qubo2026')
    ten1  = os.environ.get('QUBO_TENANT_1', 'gustavo')
    usuarios[user1] = {'senha_hash': _hash(pass1), 'tenant_id': ten1, 'nome': user1.title()}

    # Usuarios extras opcionais
    for i in range(2, 11):
        u = os.environ.get(f'QUBO_USER_{i}', '')
        p = os.environ.get(f'QUBO_PASS_{i}', '')
        t = os.environ.get(f'QUBO_TENANT_{i}', f'tenant{i}')
        if u and p:
            usuarios[u] = {'senha_hash': _hash(p), 'tenant_id': t, 'nome': u.title()}
    
    return usuarios


def verificar_login(usuario, senha):
    """Verifica credenciais - sempre recarrega env vars"""
    usuarios = get_usuarios()
    u = usuarios.get(usuario.strip().lower()) or usuarios.get(usuario.strip())
    if u and u['senha_hash'] == _hash(senha):
        return True
    return False


def get_tenant_id():
    usuario = session.get('usuario', '')
    return get_usuarios().get(usuario, {}).get('tenant_id', 'default')


def get_usuario_nome():
    usuario = session.get('usuario', '')
    return get_usuarios().get(usuario, {}).get('nome', 'Usuario')


def carregar_usuarios():
    pass  # Compatibilidade - nao faz nada, get_usuarios() eh sempre fresh


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('usuario'):
            if request.is_json:
                return jsonify({'ok': False, 'erro': 'Nao autenticado', 'redirect': '/login'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


LOGIN_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QUBO - Login</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             background:#0a0e27;display:flex;justify-content:center;align-items:center;
             min-height:100vh;padding:20px}
        .card{background:#1a1f3a;padding:36px;border-radius:12px;
              border:1px solid #2d3452;width:380px;max-width:100%}
        h1{font-size:2.2rem;font-weight:900;background:linear-gradient(135deg,#667eea,#764ba2);
           -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}
        .sub{color:#8b92a5;font-size:.85rem;margin-bottom:28px}
        label{color:#8b92a5;font-size:.75rem;text-transform:uppercase;
              display:block;margin-bottom:5px}
        input{width:100%;padding:12px 14px;border:1px solid #2d3452;border-radius:6px;
              background:#0a0e27;color:#e4e6eb;font-size:.95rem;margin-bottom:16px}
        input:focus{border-color:#667eea;outline:none}
        button{width:100%;padding:13px;border:none;border-radius:6px;
               background:#667eea;color:#fff;font-size:1rem;font-weight:700;cursor:pointer}
        .erro{background:#450a0a;color:#f87171;padding:10px 14px;border-radius:6px;
              font-size:.85rem;margin-bottom:16px;display:none}
        .footer{text-align:center;color:#8b92a5;font-size:.72rem;margin-top:20px}
    </style>
</head>
<body>
<div class="card">
    <h1>QUBO</h1>
    <div class="sub">Dashboard de Gestao ML com IA</div>
    <div class="erro" id="erro"></div>
    <label>Usuario</label>
    <input type="text" id="user" placeholder="seu usuario" autocomplete="username">
    <label>Senha</label>
    <input type="password" id="pass" placeholder="sua senha"
           onkeydown="if(event.key==='Enter')entrar()">
    <button onclick="entrar()">Entrar</button>
    <div class="footer">QUBO v3 - QuboTech</div>
</div>
<script>
function entrar(){
    var u=document.getElementById('user').value.trim();
    var p=document.getElementById('pass').value;
    if(!u||!p){mostrarErro('Preencha usuario e senha');return;}
    fetch('/api/login',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({usuario:u,senha:p})})
    .then(function(r){return r.json();})
    .then(function(d){
        if(d.ok) window.location.href='/';
        else mostrarErro(d.erro||'Credenciais invalidas');
    }).catch(function(){mostrarErro('Erro de conexao - tente novamente');});
}
function mostrarErro(msg){
    var el=document.getElementById('erro');
    el.textContent=msg;el.style.display='block';
}
document.getElementById('user').focus();
</script>
</body>
</html>"""
