import os
import logging
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import time
import requests
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn

# ==============================================================================
# 📝 LOGS
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
        texto_str = str(texto)
        for char in texto_str:
            elem.send_keys(char)
            time.sleep(0.01)
        elem.send_keys(Keys.TAB)
    except: pass

def formatar_data_para_input(data_iso):
    try:
        data_obj = datetime.strptime(data_iso, "%Y-%m-%d")
        return data_obj.strftime("%d%m%Y")
    except:
        return data_iso.replace("-", "").replace("/", "")

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
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            
            parent = elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'itemLista')]")
            click_js(driver, parent)
            time.sleep(0.5)
            
            driver.execute_script("swal.clickConfirm()")
            time.sleep(0.5)
        except: pass

# ==============================================================================
# 🤖 ROBÔ V43 - ABERTURA FORÇADA VIA FUNÇÃO NATIVA
# ==============================================================================
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    matar_zumbis()
    logger.info("--- ⚡ Iniciando Robô V43 (Execução Direta JS) ---")
    
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
            btn = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
            click_js(driver, btn)
        except:
            raise Exception("Falha ao abrir modal.")
        
        time.sleep(2)

        # 3. PREENCHIMENTO
        logger.info(f">> Preenchendo: {paciente['nome']}")
        digitar_humano(driver, "nomeAtalho", paciente['nome'])
        try: driver.find_element(By.ID, "generoAtalho").send_keys("M" if paciente['sexo'].lower().startswith('m') else "F")
        except: pass
        
        data_formatada = formatar_data_para_input(paciente['nascimento'])
        digitar_humano(driver, "nascimentoAtalho", data_formatada)
        digitar_humano(driver, "telefoneAtalho", paciente['telefone'])
        digitar_humano(driver, "emailAtalho", paciente['email'])

        # 4. SALVAR
        logger.info(">> Salvando...")
        btn_salvar = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_salvar)
        
        try:
            WebDriverWait(driver, 10).until(EC.invisibility_of_element_located((By.ID, "novoPacienteBtnAtalho")))
            logger.info("✅ Cadastro Salvo.")
        except:
            raise Exception("Botão salvar travou.")

        # 5. BUSCA E ABERTURA (O PULO DO GATO)
        logger.info(">> Iniciando Busca...")
        time.sleep(2)
        
        try:
            # Garante limpeza
            driver.execute_script("swal.close(); $('.modal').modal('hide');")
            
            # Busca
            search_input = wait.until(EC.element_to_be_clickable((By.ID, "barraBuscaPaciente")))
            search_input.clear()
            logger.info(f"   > Buscando: {paciente['telefone']}")
            search_input.send_keys(paciente['telefone'])
            time.sleep(1)
            search_input.send_keys(Keys.ENTER)
            
            # Espera resultado aparecer
            logger.info("   > Aguardando resultado na tela...")
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".pacienteLinha")))
            
            # --- A MUDANÇA CRUCIAL AQUI ---
            logger.info("✅ Resultado visto. Executando abrirPaciente(0)...")
            # Em vez de clicar, executamos a função do site diretamente
            driver.execute_script("abrirPaciente(0)")
            
            # Aguarda carregar o perfil
            logger.info("   > Aguardando perfil carregar...")
            wait.until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            logger.info("✅ Perfil carregado com sucesso.")

        except Exception as e:
            raise Exception(f"Falha na etapa de busca/abertura: {e}")

        # 6. PLANEJAMENTO
        logger.info(">> Iniciando Fluxo de Dieta...")
        driver.execute_script("document.body.style.zoom='70%'")
        time.sleep(1)
        
        try:
            # 1. Clicar no atalho
            btn_add = driver.find_element(By.ID, "atalhoPlanejamento")
            click_js(driver, btn_add)
            logger.info("   > Clicado em 'Adicionar Planejamento'")
            time.sleep(2)
            
            # 2. Confirmar (Avançar)
            logger.info("   > Avançar (1)...")
            driver.execute_script("swal.clickConfirm()")
            time.sleep(2)
            
            # 3. Confirmar (Criar)
            logger.info("   > Criar (2)...")
            driver.execute_script("swal.clickConfirm()")
            
            # Aguarda tela de edição
            time.sleep(5)
            
        except Exception as e:
            raise Exception(f"Erro na abertura da dieta: {e}")

        # 7. CAPTURA LINK
        try:
            link_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'paciente.me/')]")
            link_app = link_elem.text.strip()
            logger.info(f"✅ LINK: {link_app}")
        except: pass

        # Limpeza
        logger.info(">> Limpando hábitos...")
        try:
            for _ in range(12):
                lixeira = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.CSS_SELECTOR, "i.fi-sr-trash")))
                click_js(driver, lixeira)
                time.sleep(0.4)
                driver.execute_script("swal.clickConfirm()")
                time.sleep(0.4)
        except: pass

        # Favoritos
        logger.info(">> Inserindo favoritos...")
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
        btn_final = driver.find_element(By.CSS_SELECTOR, "div[onclick*='salvarPrescricao']")
        click_js(driver, btn_final)
        
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
    nascimento: str

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
