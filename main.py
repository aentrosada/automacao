from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from automacao import executar_cadastro
import os

app = FastAPI()

class DadosPaciente(BaseModel):
    nome: str
    sexo: str
    # nascimento removido daqui
    email: str
    telefone: str

class PedidoCadastro(BaseModel):
    paciente: DadosPaciente
    dados_clinicos: Optional[Dict[str, Any]] = {}

def ler_credenciais():
    print("--- 🔍 BUSCANDO CREDENCIAIS ---")
    
    # 1. Tenta pegar direto do sistema (Ideal para o Render/Nuvem)
    email = os.getenv("LOGIN_WEBDIET")
    senha = os.getenv("SENHA_WEBDIET")
    
    if email and senha:
        print("✅ Achei nas Variáveis de Ambiente (Modo Nuvem)!")
        return email, senha

    # 2. Se não achou, tenta ler o arquivo local
    nome_arquivo = "login-web-diet.env"
    
    if not os.path.exists(nome_arquivo):
        if os.path.exists(".env"):
            nome_arquivo = ".env"
        else:
            return None, None

    try:
        with open(nome_arquivo, "r", encoding="utf-8") as f:
            linhas = f.readlines()
            for linha in linhas:
                linha = linha.strip()
                if not linha or linha.startswith("#"): continue
                
                if "=" in linha:
                    chave, valor = linha.split("=", 1)
                    if chave == "LOGIN_WEBDIET":
                        email = valor.strip()
                    elif chave == "SENHA_WEBDIET":
                        senha = valor.strip()
        
        if email and senha:
            return email, senha
        else:
            return None, None

    except Exception as e:
        print(f"❌ Erro ao ler arquivo: {e}")
        return None, None

@app.post("/cadastrar-paciente")
def api_cadastrar(pedido: PedidoCadastro, background_tasks: BackgroundTasks):
    usuario, senha = ler_credenciais()
    
    if not usuario or not senha:
        print("🚨 ERRO FATAL: Credenciais vazias.")
        raise HTTPException(status_code=500, detail="Credenciais não encontradas. Verifique o terminal do servidor.")

    background_tasks.add_task(
        executar_cadastro, 
        usuario, 
        senha, 
        pedido.paciente.dict(),
        pedido.dados_clinicos
    )

    return {"mensagem": "Processando...", "paciente": pedido.paciente.nome}
