import os
import logging
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn

# ==============================================================================
# 📝 CONFIGURATION & LOGS
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)
WEBHOOK_MAKE_URL = os.getenv("WEBHOOK_MAKE_URL")

# ==============================================================================
# 🛠️ HELPER FUNCTIONS
# ==============================================================================
def ler_credenciais():
    email = os.getenv("LOGIN_WEBDIET")
    senha = os.getenv("SENHA_WEBDIET")
    if not email: return None, None
    return email, senha

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
            time.sleep(0.05) 
        elem.send_keys(Keys.TAB)
    except Exception as e:
        logger.error(f"Error typing in {id_elemento}: {e}")

def verificar_erro_formulario(driver):
    try:
        div_erro = driver.find_element(By.ID, "erroPacienteAtalho")
        if div_erro.is_displayed() and div_erro.text.strip():
            msg = div_erro.text.strip()
            logger.error(f"❌ SITE REFUSED REGISTRATION: '{msg}'")
            return msg
    except: pass
    return None

def enviar_webhook(msg, status, link=None, erro_detalhe=None):
    if not WEBHOOK_MAKE_URL: return
    try: 
        payload = {"msg": msg, "status": status, "link": link, "erro": erro_detalhe}
        requests.post(WEBHOOK_MAKE_URL, json=payload, timeout=5)
    except: pass

# --- MEAL MAP ---
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

def selecionar_itens(driver, wait, categoria, codigos_brutos):
    if not codigos_brutos: return
    logger.info(f">> Selecting {categoria}: {codigos_brutos}")
    lista = str(codigos_brutos).split(",")
    
    for codigo in lista:
        nome_real = MAPA_REFEICOES.get(categoria, {}).get(codigo.strip().lower())
        if not nome_real: continue
        
        try:
            xpath_span = f"//span[contains(text(), '{nome_real}')]"
            span_element = wait.until(EC.presence_of_element_located((By.XPATH, xpath_span)))
            parent_div = span_element.find_element(By.XPATH, "./ancestor::div[contains(@class, 'itemLista')]")
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", parent_div)
            click_js(driver, parent_div)
            
            time.sleep(0.5)
            try:
                btn_confirmar = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']")))
                click_js(driver, btn_confirmar)
                time.sleep(0.5)
            except:
                driver.execute_script("swal.clickConfirm()")
                
        except Exception as e:
            logger.warning(f"⚠️ Failed to add {nome_real}: {e}")

# ==============================================================================
# 🤖 MAIN ROBOT (V27 - UNIVERSAL SEARCH RESGATE)
# ==============================================================================
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    logger.info("--- ⚡ Starting Robot V27 (Universal Search Resgate) ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1366,768")
    
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20)
    link_app = "Not generated"

    try:
        # 1. LOGIN
        driver.get("https://pt.webdiet.com.br/login/")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.find_element(By.ID, "senhaLogin").send_keys(senha + Keys.ENTER)
        
        # 2. OPEN NEW PATIENT
        logger.info(">> Opening form...")
        try:
            WebDriverWait(driver, 30).until(EC.url_contains("painel"))
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
            click_js(driver, btn)
        except:
            raise Exception("Failed to open registration modal.")
        
        time.sleep(2)

        # 3. FILL FORM
        logger.info(f">> Filling data for: {paciente['nome']}")
        digitar_humano(driver, "nomeAtalho", paciente['nome'])
        try:
            sexo_letra = "M" if paciente['sexo'].lower().startswith('m') else "F"
            driver.find_element(By.ID, "generoAtalho").send_keys(sexo_letra)
        except: pass
        digitar_humano(driver, "nascimentoAtalho", "01011990")
        digitar_humano(driver, "telefoneAtalho", "11999999999")
        digitar_humano(driver, "emailAtalho", paciente['email'])

        # 4. SAVE
        logger.info(">> Clicking REGISTER...")
        btn_salvar = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_salvar)
        
        logger.info(">> Validating submission...")
        try:
            WebDriverWait(driver, 8).until(EC.invisibility_of_element_located((By.ID, "novoPacienteBtnAtalho")))
            logger.info("✅ Success (Save button disappeared).")
        except:
            msg = verificar_erro_formulario(driver)
            if msg: raise Exception(f"Form Error: {msg}")
            logger.warning("⚠️ Button persisted, attempting to proceed...")

        # 5. TRANSITION
        logger.info(">> Waiting for Consultation Modal (3s)...")
        time.sleep(3)
        
        try:
            xpath_modal = "//div[contains(text(), 'registrar nova consulta')]"
            btn_modal = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath_modal)))
            click_js(driver, btn_modal)
            logger.info("✅ Modal confirmed!")
        except:
            logger.warning("⚠️ Modal click failed (trying direct JS)...")
            driver.execute_script("swal.clickConfirm()")

        # 6. WAIT FOR PROFILE PAGE
        logger.info(">> ⏳ Waiting for profile page load (URL change)...")
        time.sleep(5)
        try: driver.execute_script("document.body.style.zoom='70%'")
        except: pass

        # 7. ENTER PLANNING (WITH UNIVERSAL SEARCH RESGATE)
        logger.info(">> Looking for Planning Button...")
        
        try:
            btn_add = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            click_js(driver, btn_add)
            logger.info("✅ Entered Planning (Direct ID)!")
        except:
            logger.warning("⚠️ Button not found. Trying RESGATE VIA UNIVERSAL SEARCH...")
            try:
                try: driver.execute_script("swal.close()")
                except: pass
                
                # BUSCA UNIVERSAL: Procura qualquer input de texto visível que possa ser busca
                logger.info("   > Searching for search box...")
                
                # Lista de seletores possíveis para a busca
                seletores_busca = [
                    "input[type='search']",
                    "input[placeholder*='usque']", # "Busque" ou "Pesquise"
                    "input[placeholder*='nome']",
                    ".dataTables_filter input"
                ]
                
                search_box = None
                for sel in seletores_busca:
                    try:
                        elementos = driver.find_elements(By.CSS_SELECTOR, sel)
                        for el in elementos:
                            if el.is_displayed():
                                search_box = el
                                break
                        if search_box: break
                    except: continue
                
                if not search_box:
                    raise Exception("Could not find search box for resgate.")

                search_box.clear()
                search_box.send_keys(paciente['nome'])
                search_box.send_keys(Keys.ENTER)
                time.sleep(4)
                
                # Clica no primeiro resultado que contém o nome
                xpath_res = f"//*[contains(text(), '{paciente['nome']}')]"
                driver.find_element(By.XPATH, xpath_res).click()
                
                time.sleep(5)
                # Tenta achar o botão de novo
                btn_final = driver.find_element(By.ID, "atalhoPlanejamento")
                click_js(driver, btn_final)
                logger.info("✅ Accessed via Search Resgate!")
                
            except Exception as e:
                # Se falhar tudo, tenta URL direta (se conseguirmos o ID no futuro)
                raise Exception(f"Critical failure accessing patient profile: {e}")

        # 8. DIET CREATION FLOW
        time.sleep(3)
        try:
            el_link = driver.find_element(By.ID, "linkRef")
            link_app = el_link.text.strip()
            logger.info(f"✅ Link Captured: {link_app}")
        except: pass

        try:
            click_js(driver, WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'avançar')]"))))
            time.sleep(1)
            click_js(driver, driver.find_element(By.ID, "criarPlanejamento"))
        except: pass
        
        time.sleep(3)

        # Clean Habits
        logger.info(">> Cleaning standard habits...")
        try:
            for _ in range(10):
                lixeira = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "i.fi-sr-trash")))
                click_js(driver, lixeira)
                time.sleep(0.3)
                driver.execute_script("swal.clickConfirm()")
                time.sleep(0.5)
        except: pass

        # Favorites
        logger.info(">> Adding Favorites...")
        driver.execute_script("window.scrollTo(0, 0);")
        click_js(driver, WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']"))))
        time.sleep(3)
        
        selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
        selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
        
        try: driver.execute_script("document.querySelector('button.close[data-dismiss=\"modal\"]').click()")
        except: driver.execute_script("document.querySelector('.modal-backdrop').click()")
        
        # Times
        try:
            driver.execute_script("document.getElementById('horarioRotinaTemp0').value = '08:00';")
            driver.execute_script("document.getElementById('horarioRotinaTemp1').value = '12:00';")
        except: pass
        
        # Save Final
        logger.info(">> Saving Prescription...")
        time.sleep(1)
        click_js(driver, driver.find_element(By.CSS_SELECTOR, "div[onclick*='salvarPrescricao']"))
        
        logger.info("✅ TOTAL SUCCESS!")
        enviar_webhook("Processo concluído", "Sucesso Total", link_app)
        return {"status": "sucesso", "link": link_app}

    except Exception as e:
        logger.error(f"❌ ERROR: {e}")
        # Webhook de erro simplificado para não falhar
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
    usuario, senha = ler_credenciais()
    background_tasks.add_task(executar_cadastro, usuario, senha, pedido.paciente.dict(), pedido.dados_clinicos)
    return {"mensagem": "Starting process...", "paciente": pedido.paciente.nome}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
