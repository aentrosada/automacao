import os
import logging
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import requests
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import uvicorn

# ==============================================================================
# 📝 LOGS & CONFIG
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)
WEBHOOK_MAKE_URL = os.getenv("WEBHOOK_MAKE_URL")

# ==============================================================================
# 🛠️ AUXILIARES
# ==============================================================================
def matar_zumbis():
    try:
        subprocess.run(['pkill', '-f', 'chrome'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['pkill', '-f', 'chromedriver'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except: pass

def ler_credenciais():
    email = os.getenv("LOGIN_WEBDIET")
    senha = os.getenv("SENHA_WEBDIET")
    return (email, senha) if email else (None, None)

def click_js(driver, elemento):
    try:
        driver.execute_script("arguments[0].click();", elemento)
    except:
        try: elemento.click()
        except: pass

def digitar_humano(driver, id_elemento, texto):
    try:
        elem = driver.find_element(By.ID, id_elemento)
        elem.click()
        elem.clear()
        elem.send_keys(str(texto))
        time.sleep(0.05)
        elem.send_keys(Keys.TAB)
    except: pass

def formatar_data_para_input(data_iso):
    try:
        data_obj = datetime.strptime(data_iso, "%Y-%m-%d")
        return data_obj.strftime("%d%m%Y")
    except:
        return data_iso.replace("-", "").replace("/", "")

def enviar_webhook(msg, status, paciente_nome=None):
    if not WEBHOOK_MAKE_URL: return
    try: 
        requests.post(WEBHOOK_MAKE_URL, json={
            "msg": msg, 
            "status": status, 
            "paciente": paciente_nome,
            "etapa": "cadastro_apenas"
        }, timeout=3)
    except: pass

# ==============================================================================
# 🤖 ROBÔ CADASTRO EXPRESS V2 (COM TOLERÂNCIA A LENTIDÃO)
# ==============================================================================
def executar_cadastro_express(usuario, senha, paciente):
    matar_zumbis()
    logger.info("--- ⚡ Robô de Cadastro Express V2 Iniciado ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.page_load_strategy = 'eager'
    chrome_options.add_argument("--window-size=1280,720")
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(90) # Aumentei um pouco o timeout geral
    wait = WebDriverWait(driver, 20)

    try:
        # 1. LOGIN
        driver.get("https://pt.webdiet.com.br/login/")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.find_element(By.ID, "senhaLogin").send_keys(senha + Keys.ENTER)
        
        # 2. ABRIR MODAL
        logger.info(">> Abrindo formulário...")
        try:
            try: driver.execute_script("if (typeof jQuery !== 'undefined') { jQuery.fx.off = true; }")
            except: pass

            btn = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
            click_js(driver, btn)
        except:
            raise Exception("Falha ao abrir modal de cadastro.")
        
        time.sleep(1.5)

        # 3. PREENCHIMENTO
        logger.info(f">> Cadastrando: {paciente['nome']}")
        digitar_humano(driver, "nomeAtalho", paciente['nome'])
        
        try: 
            driver.find_element(By.ID, "generoAtalho").send_keys("M" if paciente['sexo'].lower().startswith('m') else "F")
        except: pass
        
        data_fmt = formatar_data_para_input(paciente['nascimento'])
        digitar_humano(driver, "nascimentoAtalho", data_fmt)
        digitar_humano(driver, "telefoneAtalho", paciente['telefone'])
        digitar_humano(driver, "emailAtalho", paciente['email'])

        # 4. SALVAR (COM DUPLA VERIFICAÇÃO)
        logger.info(">> Salvando...")
        btn_salvar = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_salvar)
        
        # Verifica se precisa clicar de novo (Double Tap)
        time.sleep(2)
        try:
            if btn_salvar.is_displayed():
                logger.info("   > Botão ainda visível, clicando novamente...")
                click_js(driver, btn_salvar)
        except: pass # Se sumiu, ótimo

        try:
            # Aumentei para 30s de paciência
            WebDriverWait(driver, 30).until(EC.invisibility_of_element_located((By.ID, "novoPacienteBtnAtalho")))
            logger.info("✅ PACIENTE SALVO COM SUCESSO.")
        except TimeoutException:
            # Se deu timeout, verifica se tem msg de erro na tela
            try:
                erro = driver.find_element(By.CSS_SELECTOR, ".toast-message").text
                raise Exception(f"Site recusou: {erro}")
            except:
                # Se não tem mensagem de erro, assume lentidão extrema
                raise Exception("Erro ao salvar: O site demorou demais ou travou.")

        # 5. LIMPEZA FINAL
        time.sleep(1)
        try:
            driver.execute_script("if(typeof swal !== 'undefined') { swal.close(); }")
        except: pass

        enviar_webhook("Cadastro Realizado", "Sucesso", paciente['nome'])
        return {"status": "sucesso", "paciente": paciente['nome']}

    except Exception as e:
        logger.error(f"❌ ERRO NO CADASTRO: {e}")
        enviar_webhook(f"Erro: {str(e)}", "Erro")
        return {"status": "erro", "msg": str(e)}
    finally:
        try: driver.quit()
        except: pass

# ==============================================================================
# API SIMPLIFICADA
# ==============================================================================
app = FastAPI()

class DadosPaciente(BaseModel):
    nome: str
    sexo: str
    email: str
    telefone: str
    nascimento: str

class PedidoCadastro(BaseModel):
    paciente: DadosPaciente

@app.post("/cadastrar-paciente")
def api_cadastrar(pedido: PedidoCadastro, background_tasks: BackgroundTasks):
    matar_zumbis()
    usuario, senha = ler_credenciais()
    
    if not usuario or not senha:
        return {"status": "erro", "msg": "Credenciais não configuradas"}

    background_tasks.add_task(executar_cadastro_express, usuario, senha, pedido.paciente.dict())
    return {"mensagem": "Processando cadastro...", "paciente": pedido.paciente.nome}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
