
import re, sys

arquivo = r"C:\sistema-catalogos\dashboard_web.py"

with open(arquivo, "r", encoding="utf-8") as f:
    src = f.read()

# Conta antes
antes = src.count("def api_alerta_diario")
print(f"Antes: {antes} ocorrencias")

if antes <= 1:
    print("Ja esta correto!")
    sys.exit(0)

# Encontra e remove o bloco duplicado (o que tem methods=['POST'])
# Usa split para ser preciso
marcador = "@app.route('/api/alerta-diario', methods=['POST'])"
if marcador not in src:
    marcador = '@app.route("/api/alerta-diario", methods=["POST"])'

if marcador in src:
    # Acha o inicio do bloco
    idx_start = src.index(marcador)
    # Acha o proximo @app.route depois desse bloco
    idx_next = src.index("\n\n@app.route", idx_start + 10)
    # Remove o bloco inteiro
    src = src[:idx_start] + src[idx_next + 2:]  # +2 para pular \n\n
    print(f"Bloco removido de {idx_start} ate {idx_next}")
else:
    print("Marcador nao encontrado. Tentando abordagem por linha...")
    # Abordagem linha por linha
    linhas = src.split("\n")
    nova = []
    pular = False
    for i, linha in enumerate(linhas):
        if "api/alerta-diario" in linha and "POST" in linha:
            pular = True
            print(f"  Inicio do bloco na linha {i+1}: {linha[:60]}")
        elif pular and linha.startswith("@app.route"):
            pular = False
            print(f"  Fim do bloco na linha {i+1}")
        if not pular:
            nova.append(linha)
    src = "\n".join(nova)

depois = src.count("def api_alerta_diario")
print(f"Depois: {depois} ocorrencias")

with open(arquivo, "w", encoding="utf-8") as f:
    f.write(src)

print("Arquivo salvo!")
