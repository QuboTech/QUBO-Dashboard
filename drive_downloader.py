"""
drive_downloader.py - Baixa PDFs do Google Drive automático
"""
import os
import io
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class DriveDownloader:
    """Baixa PDFs do Google Drive"""
    
    def __init__(self):
        self.service = self._autenticar()
    
    def _autenticar(self):
        """Autentica na API Google Drive"""
        creds = None
        
        # Verifica se já tem token salvo
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        # Se não tem ou expirou, faz login
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Salva token para próxima vez
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        
        return build('drive', 'v3', credentials=creds)
    
    def listar_pdfs(self, pasta_id=None):
        """Lista todos os PDFs do Drive"""
        print("\n🔍 Buscando PDFs no Google Drive...")
        
        # Query para buscar só PDFs
        query = "mimeType='application/pdf' and trashed=false"
        
        if pasta_id:
            query += f" and '{pasta_id}' in parents"
        
        try:
            results = self.service.files().list(
                q=query,
                fields="files(id, name, size, modifiedTime, parents)",
                pageSize=1000,
                orderBy="name"
            ).execute()
            
            arquivos = results.get('files', [])
            print(f"   ✅ Encontrados {len(arquivos)} PDFs!")
            
            return arquivos
            
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            return []
    
    def baixar_arquivo(self, file_id, nome, destino='downloads'):
        """Baixa um arquivo específico"""
        Path(destino).mkdir(parents=True, exist_ok=True)
        
        caminho_completo = Path(destino) / nome
        
        # Se já existe, pula
        if caminho_completo.exists():
            print(f"   ⏭️  {nome} (já existe)")
            return caminho_completo
        
        try:
            request = self.service.files().get_media(fileId=file_id)
            
            with io.FileIO(caminho_completo, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                
                while not done:
                    status, done = downloader.next_chunk()
                    porcentagem = int(status.progress() * 100)
                    print(f"   ⬇️  {nome}: {porcentagem}%", end='\r')
            
            print(f"   ✅ {nome} baixado!        ")
            return caminho_completo
            
        except Exception as e:
            print(f"   ❌ Erro ao baixar {nome}: {e}")
            return None
    
    def baixar_todos(self, pasta_destino='catalogos_drive'):
        """Baixa todos os PDFs do Drive"""
        print("\n" + "="*70)
        print("  📥 DOWNLOAD AUTOMÁTICO - GOOGLE DRIVE")
        print("="*70)
        
        # Lista PDFs
        pdfs = self.listar_pdfs()
        
        if not pdfs:
            print("\n⚠️  Nenhum PDF encontrado no Drive!")
            return []
        
        print(f"\n📄 {len(pdfs)} PDFs para baixar")
        print(f"📁 Destino: {pasta_destino}/\n")
        
        baixados = []
        
        for i, pdf in enumerate(pdfs, 1):
            print(f"\n[{i}/{len(pdfs)}]", end=" ")
            
            caminho = self.baixar_arquivo(
                pdf['id'],
                pdf['name'],
                pasta_destino
            )
            
            if caminho:
                baixados.append(caminho)
        
        print("\n" + "="*70)
        print(f"✅ Download concluído: {len(baixados)}/{len(pdfs)} arquivos")
        print("="*70)
        
        return baixados


# TESTE
if __name__ == "__main__":
    print("\n🔥 GOOGLE DRIVE DOWNLOADER")
    print("="*70)
    print("\n⚠️  Na primeira vez, vai abrir o navegador para autorizar!")
    print("   Faça login com sua conta Google e autorize o acesso.\n")
    
    input("Pressione ENTER para continuar...")
    
    try:
        downloader = DriveDownloader()
        
        # Baixa tudo
        PASTA = r"C:\Users\Luiz Gustavo\OneDrive\Documents\Escalada Econ\Loja QUBO\Fornecedores\Drive"
        
        arquivos = downloader.baixar_todos(PASTA)
        
        print(f"\n📁 Arquivos salvos em: {PASTA}")
        print(f"✅ Total baixado: {len(arquivos)} PDFs")
        
    except Exception as e:
        print(f"\n❌ Erro: {e}")
    
    input("\n\nPressione ENTER para sair...")