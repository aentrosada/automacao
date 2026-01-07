import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn

# ==============================================================================
# 🔐 CONFIGURAÇÃO DE AMBIENTE
# ==============================================================================
WEBHOOK_MAKE_URL = os.getenv("WEBHOOK_MAKE_URL")

# --- FUNÇÃO PARA LER CREDENCIAIS ---
def ler_credenciais():
    print("--- 🔍 BUSCANDO CREDENCIAIS ---")
    # 1. Tenta pegar direto das variáveis de ambiente do Render
    email = os.getenv("LOGIN_WEBDIET")
    senha = os.getenv("SENHA_WEBDIET")
    
    if email and senha:
        print("✅ Achei nas Variáveis de Ambiente!")
        return email, senha

    # 2. Se não achou, tenta ler arquivo local (fallback)
    nome_arquivo = "login-web-diet.env"
    if not os.path.exists(nome_arquivo):
        if os.path.exists(".env"): nome_arquivo = ".env"
        else: return None, None

    try:
        with open(nome_arquivo, "r", encoding="utf-8") as f:
            for linha in f:
                if "=" in linha:
                    chave, valor = linha.strip().split("=", 1)
                    if chave == "LOGIN_WEBDIET": email = valor
                    elif chave == "SENHA_WEBDIET": senha = valor
        return email, senha
    except: return None, None

# --- MAPA DE REFEIÇÕES ---
MAPA_REFEICOES = {
    "cafe": {
        "op1": "PENDENTE", 
        "op2": "OPÇÃO CAFÉ 2- Pão com requeijão",
        "op3": "CAFÉ OPÇÃO 3 - Pão com ovos",
        "op4": "CAFÉ OPÇÃO 4 - Rap 10 com queijo",
        "op5": "CAFÉ OPÇÃO 5 - Iogurte com whey",
        "op6": "CAFÉ OPÇÃO 6 - Mingau proteico de aveia",
        "op7": "CAFÉ OPÇÃO 7 - Pão de flocos de milho",
        "op8": "CAFÉ OPÇÃO 8 - Pão de queijo com tapioca",
        "op9": "CAFÉ OPÇÃO 9 - Pão com pasta de amendoim",
        "op10": "CAFÉ OPÇÃO 10 - Pão com creme de ricota + Shake whey",
        "op11": "CAFÉ OPÇÃO 11 - Pão francês com frango desfiado",
        "op12": "CAFÉ OPÇÃO 12 - Panqueca de banana",
        "op13": "CAFÉ OPÇÃO 13 - Biscoite de arroz com iogurte",
        "op14": "CAFÉ OPÇÃO 14 - Crepioca de frango com queijo",
        "op15": "CAFÉ OPÇÃO 15 - Aveia com fruta",
        "op16": "CAFÉ OPÇÃO 16- Pão de frango",
        "op17": "CAFÉ OPÇÃO 17- Pudim whey"
    },
    "almoco": {
        "op1": "ALMOÇO/ JANTAR 1",
        "op2": "ALMOÇO/ JANTAR 2",
        "op5": "ALMOÇO OPÇÃO 5- Hambúrguer"
    }
}

# --- FUNÇÕES AUXILIARES ---
def click_js(driver, elemento):
    driver.execute_script("arguments[0].click();", elemento)

def definir_horario(driver, element_id, horario):
    try:
        script = f"""
        var input = document.getElementById('{element_id}');
        if(input) {{
            input.value = '{horario}';
            input.dispatchEvent(new Event('input'));
            input.dispatchEvent(new Event('change'));
            input.dispatchEvent(new Event('blur'));
        }}
        """
        driver.execute_script(script)
    except: pass

def selecionar_itens(driver, wait, categoria, codigos_brutos):
    if not codigos_brutos: return
    print(f">> Processando {categoria}...")
    lista_codigos = str(codigos_brutos).split(",")
    for codigo in lista_codigos:
        codigo_limpo = codigo.strip().lower()
        nome_real = MAPA_REFEICOES.get(categoria, {}).get(codigo_limpo)
        if not nome_real: continue
        try:
            xpath_item = f"//div[contains(text(), '{nome_real}')] | //span[contains(text(), '{nome_real}')] | //label[contains(text(), '{nome_real}')]"
            elem = driver.find_element(By.XPATH, xpath_item)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(0.5)
            click_js(driver, elem)
            time.sleep(1) 
            btn_confirmar = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'confirmar')]")
            ))
            click_js(driver, btn_confirmar)
            time.sleep(1.5) 
        except: pass

def preencher_antropometria(driver, dados):
    print(">> Tentando preencher dados antropométricos...")
    campos_para_preencher = ["idade", "altura", "peso", "cintura", "pescoco", "quadril"]
    for campo in campos_para_preencher:
        valor = dados.get(campo)
        if valor and str(valor).strip() != "" and str(valor) != "0":
            try:
                input_elem = driver.find_element(By.ID, campo)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_elem)
                input_elem.clear()
                input_elem.send_keys(str(valor))
                print(f"   > Preenchido {campo}: {valor}")
                time.sleep(0.5)
            except: pass

def enviar_webhook(paciente_dados, dados_clinicos, link_app, status_msg):
    print(f"\n📡 TENTANDO ENVIAR WEBHOOK COMPLETO...")
    if not WEBHOOK_MAKE_URL: return
    payload = {"status": status_msg, "link_app": link_app, "paciente": paciente_dados, "dados_clinicos": dados_clinicos}
    try: requests.post(WEBHOOK_MAKE_URL, json=payload)
    except: pass

# --- ROBÔ PRINCIPAL (OTIMIZADO PARA MEMÓRIA) ---
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    print("--- 🔧 Configurando Chrome Ultra-Leve ---")
    chrome_options = Options()
    
    # --- CONFIGURAÇÕES ANTI-ESTOURO DE MEMÓRIA ---
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions") 
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false") # 🚫 SEM IMAGENS (Essencial)
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--window-size=1280,720") 
    # --------------------------------------------

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 30) # Tempo aumentado para segurança
    
    link_app_capturado = "Link não encontrado"

    try:
        print(f"--- 🚀 Iniciando: {paciente.get('nome', 'Sem Nome')} ---")
        driver.get("https://pt.webdiet.com.br/login/")
        
        # Login
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.switch_to.active_element.send_keys(Keys.TAB)
        driver.switch_to.active_element.send_keys(senha + Keys.ENTER)
        
        # Cadastro
        time.sleep(3)
        print(">> Criando ficha...")
        btn_novo_paciente = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
        click_js(driver, btn_novo_paciente)
        
        time.sleep(2)
        wait.until(EC.visibility_of_element_located((By.ID, "nomeAtalho"))).send_keys(paciente["nome"])
        try:
            opcao_genero = driver.find_element(By.XPATH, f"//option[@value='{paciente['sexo']}']")
            driver.execute_script("arguments[0].selected = true; arguments[0].parentElement.dispatchEvent(new Event('change'));", opcao_genero)
        except: pass

        # SEM NASCIMENTO (Mantido removido conforme solicitado)
        
        driver.find_element(By.ID, "emailAtalho").send_keys(paciente["email"])
        driver.find_element(By.ID, "telefoneAtalho").send_keys(paciente["telefone"])
        time.sleep(1)
        driver.find_element(By.ID, "novoPacienteBtnAtalho").click()

        # Dados Clínicos
        time.sleep(5) 
        if dados_clinicos: preencher_antropometria(driver, dados_clinicos)

        # Captura Link
        try:
            print(">> Tentando fechar menu se existir...")
            btn_abrir_menu = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'não registrar e abrir menu')]")))
            click_js(driver, btn_abrir_menu)
            time.sleep(3)
        except: pass

        try:
            print(">> Buscando Link...")
            elemento_link = wait.until(EC.visibility_of_element_located((By.ID, "linkRef")))
            link_app_capturado = elemento_link.text.strip()
            print(f"✅ LINK CAPTURADO: {link_app_capturado}")
        except: pass

        # Planejamento Alimentar
        if dados_clinicos and (dados_clinicos.get("cafe") or dados_clinicos.get("almoco")):
            print(">> Iniciando Planejamento...")
            btn_add_planejamento = wait.until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            click_js(driver, btn_add_planejamento)
            time.sleep(2)

            btn_avancar = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'avançar')]")))
            click_js(driver, btn_avancar)
            time.sleep(2)

            btn_confirmar = wait.until(EC.presence_of_element_located((By.ID, "criarPlanejamento")))
            click_js(driver, btn_confirmar)
            time.sleep(5) 

            # Limpeza
            for i in range(1, 4):
                try:
                    btn_lixeira = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'excluir(0)')]")))
                    click_js(driver, btn_lixeira)
                    time.sleep(1)
                    btn_remover_habito = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'remover hábito')]")))
                    click_js(driver, btn_remover_habito)
                    time.sleep(2)
                except: pass 

            # Seleção
            selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
            selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
            
            # Horários
            print(">> Ajustando horários...")
            time.sleep(1)
            definir_horario(driver, "horarioRotinaTemp0", "08:00")
            definir_horario(driver, "horarioRotinaTemp1", "08:00")
            time.sleep(1)

            # Salvar
            print(">> Salvando...")
            try:
                btn_fechar_modal = wait.until(EC.presence_of_element_located((By.XPATH, "//button[@class='close' and @data-dismiss='modal']")))
                click_js(driver, btn_fechar_modal)
            except: pass
            
            time.sleep(2)
            btn_salvar_final = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'salvarPrescricao()')]")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_salvar_final)
            time.sleep(1)
            click_js(driver, btn_salvar_final)
            print("✅ Salvo!")
            
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Finalizado com Sucesso")

        return {"status": "sucesso", "link": link_app_capturado}

    except Exception as e:
        print(f"❌ Erro Fatal: {e}")
        enviar_webhook(paciente, dados_clinicos, link_app_capturado, f"Erro: {str(e)}")
        return {"status": "erro", "mensagem": str(e)}
    finally:
        # Força o fechamento imediato para liberar memória
        try: driver.quit()
        except: pass

# ==============================================================================
# 🚀 API UNIFICADA
# ==============================================================================
app = FastAPI()

class DadosPaciente(BaseModel):
    nome: str
    sexo: str
    email: str
    telefone: str

class PedidoCadastro(BaseModel):
    paciente: DadosPaciente
    dados_clinicos: Optional[Dict[str, Any]] = {}

@app.post("/cadastrar-paciente")
def api_cadastrar_unificada(pedido: PedidoCadastro, background_tasks: BackgroundTasks):
    # 1. Lê as credenciais internamente
    usuario, senha = ler_credenciais()
    
    if not usuario or not senha:
        raise HTTPException(status_code=500, detail="Credenciais do WebDiet não configuradas no Render.")

    # 2. Manda rodar o robô
    background_tasks.add_task(
        executar_cadastro, 
        usuario, 
        senha, 
        pedido.paciente.dict(),
        pedido.dados_clinicos
    )

    return {"mensagem": "Processando...", "paciente": pedido.paciente.nome}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
