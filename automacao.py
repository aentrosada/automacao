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
# 🛠️ AUXILIARES (ESSENCIAIS)
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

# O SEGREDO DO SUCESSO DO SEU CÓDIGO ANTIGO: CLIQUE VIA JS
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
            
            # Garante que o elemento está visível para o JS pegar
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            
            # Clica no PAI (Card) como no seu código antigo, que é mais seguro
            parent = elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'itemLista')]")
            click_js(driver, parent)
            time.sleep(0.5)
            
            # Confirmação
            try:
                btn_ok = driver.find_element(By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']")
                click_js(driver, btn_ok)
            except: 
                driver.execute_script("swal.clickConfirm()")
            time.sleep(0.5)
        except: pass

# ==============================================================================
# 🤖 ROBÔ V39 - A VOLTA DO JS (HÍBRIDO ROBUSTO)
# ==============================================================================
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    matar_zumbis() # Mantive isso pq o Render precisa!
    logger.info("--- ⚡ Iniciando Robô V39 (Lógica Antiga + JS Click) ---")
    
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
            click_js(driver, btn) # JS Click
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
        # JS Click direto, sem esperar visibilidade (como no seu código antigo)
        btn_salvar = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_salvar)
        
        try:
            WebDriverWait(driver, 10).until(EC.invisibility_of_element_located((By.ID, "novoPacienteBtnAtalho")))
            logger.info("✅ Cadastro Salvo.")
        except:
            raise Exception("Botão salvar travou.")

        # 5. TRANSIÇÃO (REGISTRAR NOVA CONSULTA)
        logger.info(">> Aguardando Modal 'Registrar Nova Consulta'...")
        time.sleep(3)
        try:
            # Procura pelo texto, mas clica com JS
            xpath_modal = "//div[contains(text(), 'registrar nova consulta')]"
            btn_modal = driver.find_element(By.XPATH, xpath_modal)
            click_js(driver, btn_modal)
            logger.info("✅ Modal clicado (JS).")
        except:
            logger.warning("⚠️ Botão não achado via XPath. Tentando swal.clickConfirm()...")
            driver.execute_script("swal.clickConfirm()")

        # 6. CARREGAMENTO DO PERFIL
        logger.info(">> Aguardando carga do Perfil...")
        time.sleep(5) # O código antigo confiava no sleep, vamos confiar também
        
        # 7. PLANEJAMENTO (A PARTE QUE DEU ERRO - VOLTANDO AO ANTIGO)
        logger.info(">> Iniciando Planejamento (Modo Antigo)...")
        driver.execute_script("document.body.style.zoom='70%'")
        
        try:
            # 1. Acha o botão (mesmo que escondido)
            btn_add = wait.until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            
            # 2. CLIQUE JS FORÇADO (Ignora overlays)
            click_js(driver, btn_add)
            logger.info(">> Clicado no Planejamento (JS).")
            
            time.sleep(3) # Espera fixa do código antigo
            
            # 3. AVANÇAR (Procura o botão de confirmação do SweetAlert)
            logger.info(">> Tentando Avançar...")
            try:
                # Tenta o botão físico primeiro
                btn_avancar = driver.find_element(By.XPATH, "//div[contains(text(), 'avançar')]")
                click_js(driver, btn_avancar)
            except:
                # Se falhar, usa o genérico do modal
                driver.execute_script("swal.clickConfirm()")
            
            time.sleep(2)
            
            # 4. CRIAR (CONFIRMAR)
            logger.info(">> Tentando Criar...")
            btn_criar = driver.find_element(By.ID, "criarPlanejamento")
            click_js(driver, btn_criar)
            
        except Exception as e:
            raise Exception(f"Erro no fluxo de planejamento: {e}")

        # 8. RESTO DO FLUXO (HÁBITOS, FAVORITOS, ETC)
        time.sleep(4)
        
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
                lixeira = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.CSS_SELECTOR, "i.fi-sr-trash")))
                click_js(driver, lixeira)
                time.sleep(0.5)
                driver.execute_script("swal.clickConfirm()")
                time.sleep(0.5)
        except: pass

        # Favoritos
        logger.info(">> Favoritos...")
        driver.execute_script("window.scrollTo(0, 0);")
        try:
            btn_fav = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']")))
            click_js(driver, btn_fav)
            time.sleep(3)
        except:
            raise Exception("Falha ao abrir favoritos")
        
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
