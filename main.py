"""
main.py - QUBO v3 - Abre o Dashboard
Tudo é feito pelo Dashboard agora:
  /processar  → Processar PDFs
  /           → Viabilidade
  /escolhidos → Formação de Preço
"""
import sys
import subprocess

if __name__ == "__main__":
    print("\n🚀 Abrindo Dashboard QUBO...")
    print("   Acesse: http://localhost:5000\n")
    subprocess.run([sys.executable, "dashboard_web.py"])
