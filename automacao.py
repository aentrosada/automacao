import os
import logging
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
import time
import requests
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
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
        time.sleep(2)
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
        for char in texto:
            elem.send_keys(char)
            time.sleep(0.01)
        elem.send_keys(Keys.TAB)
    except: pass

def enviar_webhook(msg, status, link=None):
    if not WEBHOOK_MAKE_URL: return
    try: requests.post(WEBHOOK_MAKE_URL, json={"msg": msg, "status": status, "link": link}, timeout=5)
    except: pass

# --- MAPA DE REFEIÇÕES ---
MAPA_REFEICOES = {
    "cafe": {"op1": "PENDENTE", "op2": "OPÇÃO CAFÉ 2- Pão com requeijão", "op3": "CAFÉ OPÇÃO 3 - Pão com ovos"},
    "almoco": {"op1": "ALMOÇO/ JANTAR 1", "op2": "ALMOÇO/ JANTAR 2"}
}

def selecionar_itens(driver, wait, categoria, codigos_brutos):
    if not codigos_brutos: return
    logger.info(f">> Selecionando {categoria}: {codigos_brutos}")
    lista = str(codigos_brutos).split(",")
    for codigo in lista:
        nome = MAPA_REFEICOES.get(categoria, {}).get(codigo.strip().lower())
        if not nome: continue
        try:
            xpath = f"//span[contains(text(), '{nome}')]"
            elem = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath)))
            parent = elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'itemLista')]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", parent)
            click_js(driver, parent)
            time.sleep(0.5)
            try:
                # Confirmação individual
                btn_ok = driver.find_element(By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']")
                click_js(driver, btn_ok)
            except: 
                driver.execute_script("swal.clickConfirm()")
            time.sleep(0.5)
        except: pass

# ==============================================================================
# 🤖 ROBÔ V38 - SINCRONIA DE MODAIS
# ==============================================================================
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    matar_zumbis()
    logger.info("--- ⚡ Iniciando Robô V38 (Sincronia Planejamento -> Avançar) ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,720")
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(90)
    wait = WebDriverWait(driver, 20)
    link_app = "Não capturado"

    try:
        # 1. LOGIN
        driver.get("https://pt.webdiet.com.br/login/")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.find_element(By.ID, "senhaLogin").send_keys(senha + Keys.ENTER)
        
        # 2. CADASTRO
        logger.info(">> Abrindo formulário...")
        try:
            WebDriverWait(driver, 30).until(EC.url_contains("painel"))
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
            click_js(driver, btn)
        except:
            raise Exception("Falha ao abrir modal.")
        
        time.sleep(2)

        # 3. PREENCHIMENTO
        logger.info(f">> Preenchendo: {paciente['nome']}")
        digitar_humano(driver, "nomeAtalho", paciente['nome'])
        try: driver.find_element(By.ID, "generoAtalho").send_keys("M" if paciente['sexo'].lower().startswith('m') else "F")
        except: pass
        digitar_humano(driver, "nascimentoAtalho", "01011990")
        digitar_humano(driver, "telefoneAtalho", "11999999999")
        digitar_humano(driver, "emailAtalho", paciente['email'])

        # 4. SALVAR
        logger.info(">> Salvando...")
        click_js(driver, driver.find_element(By.ID, "novoPacienteBtnAtalho"))
        
        try:
            WebDriverWait(driver, 8).until(EC.invisibility_of_element_located((By.ID, "novoPacienteBtnAtalho")))
            logger.info("✅ Cadastro Salvo.")
        except:
            raise Exception("Botão salvar travou.")

        # 5. TRANSIÇÃO (GATILHO DO VÍDEO)
        logger.info(">> Aguardando Modal 'Registrar Nova Consulta'...")
        time.sleep(2)
        xpath_modal = "//div[contains(@class, 'botao') and contains(text(), 'registrar nova consulta')]"
        try:
            btn_modal = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath_modal)))
            click_js(driver, btn_modal)
            logger.info("✅ Modal clicado.")
        except:
            logger.warning("⚠️ Modal físico não clicado. Usando JS...")
            driver.execute_script("swal.clickConfirm()")

        # 6. CONFIRMAÇÃO DE ENTRADA NO PERFIL
        logger.info(">> Aguardando carga do Perfil...")
        try:
            xpath_titulo = "//div[contains(@class, 'titulo') and contains(text(), 'Dados básicos')]"
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, xpath_titulo)))
            logger.info("✅ PERFIL CARREGADO.")
        except:
            if "paciente" in driver.current_url:
                logger.info("✅ Perfil carregado (URL ok).")
            else:
                raise Exception("Não entrou no perfil após clicar no modal.")

        # ======================================================================
        # 7. PLANEJAMENTO (CLICK & CHECK & WAIT)
        # ======================================================================
        logger.info(">> Iniciando Fluxo de Dieta...")
        driver.execute_script("document.body.style.zoom='70%'")
        time.sleep(1)
        
        # --- PASSO A: CLICAR NO ÍCONE DO PLANEJAMENTO ---
        try:
            # Espera o botão existir
            btn_add = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "atalhoPlanejamento")))
            
            # Clica
            logger.info(">> Clicando em 'Adicionar Planejamento'...")
            click_js(driver, btn_add)
            
            # --- PASSO B: ESPERAR O MODAL 'AVANÇAR' APARECER ---
            # Aqui está a correção: Esperar explicitamente o próximo passo
            logger.info(">> Aguardando modal 'Avançar'...")
            
            xpath_avancar = "//div[contains(text(), 'avançar')]"
            try:
                btn_avancar = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath_avancar)))
                logger.info("✅ Modal de dieta abriu.")
            except TimeoutException:
                # Retry: Se não abriu em 5s, clica de novo no planejamento
                logger.warning("⚠️ Modal não abriu. Clicando novamente no planejamento...")
                click_js(driver, btn_add)
                btn_avancar = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.XPATH, xpath_avancar)))
                logger.info("✅ Modal abriu na segunda tentativa.")

            # --- PASSO C: CLICAR EM AVANÇAR ---
            logger.info(">> Clicando em 'Avançar'...")
            click_js(driver, btn_avancar)
            time.sleep(1)

            # --- PASSO D: CLICAR EM CONFIRMAR (CRIAR EM BRANCO) ---
            logger.info(">> Clicando em 'Confirmar'...")
            btn_criar = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "criarPlanejamento")))
            click_js(driver, btn_criar)
            
        except Exception as e:
            raise Exception(f"Erro na sequência de abertura da dieta: {e}")

        # 8. CRIAÇÃO DA DIETA
        time.sleep(3)
        
        # Link
        try:
            link_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'paciente.me/')]")
            link_app = link_elem.text.strip()
            logger.info(f"✅ LINK: {link_app}")
        except: pass

        # Limpeza
        logger.info(">> Limpando hábitos...")
        try:
            for _ in range(12):
                lixeira = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "i.fi-sr-trash")))
                click_js(driver, lixeira)
                time.sleep(0.3)
                driver.execute_script("swal.clickConfirm()")
                time.sleep(0.3)
        except: pass

        # Favoritos
        logger.info(">> Favoritos...")
        driver.execute_script("window.scrollTo(0, 0);")
        click_js(driver, WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']"))))
        time.sleep(3)
        
        selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
        selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
        
        try: driver.execute_script("document.querySelector('button.close[data-dismiss=\"modal\"]').click()")
        except: driver.execute_script("document.querySelector('.modal-backdrop').click()")
        
        # Finalização
        logger.info(">> Finalizando...")
        try:
            driver.execute_script("document.getElementById('horarioRotinaTemp0').value = '08:00';")
            driver.execute_script("document.getElementById('horarioRotinaTemp1').value = '12:00';")
        except: pass
        
        time.sleep(1)
        click_js(driver, driver.find_element(By.CSS_SELECTOR, "div[onclick*='salvarPrescricao']"))
        
        logger.info("✅ SUCESSO TOTAL!")
        enviar_webhook("Sucesso Total", "Concluido", link_app)
        return {"status": "sucesso", "link": link_app}

    except Exception as e:
        logger.error(f"❌ ERRO FATAL: {e}")
        enviar_webhook(f"Erro: {str(e)}", "Erro")
        return {"status": "erro", "msg": str(e)}
    finally:
        try: driver.quit()
        except: pass

# ==============================================================================
# API
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
def api_cadastrar(pedido: PedidoCadastro, background_tasks: BackgroundTasks):
    matar_zumbis()
    usuario, senha = ler_credenciais()
    background_tasks.add_task(executar_cadastro, usuario, senha, pedido.paciente.dict(), pedido.dados_clinicos)
    return {"mensagem": "Processando...", "paciente": pedido.paciente.nome}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
