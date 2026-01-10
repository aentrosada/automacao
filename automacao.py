import os
import logging
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, NoSuchElementException
import time
import requests
from datetime import datetime
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
# 🛠️ AUXILIARY FUNCTIONS
# ==============================================================================
def kill_zombies():
    try:
        subprocess.run(['pkill', '-f', 'chrome'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['pkill', '-f', 'chromedriver'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
    except: pass

def read_credentials():
    email = os.getenv("LOGIN_WEBDIET")
    password = os.getenv("SENHA_WEBDIET")
    return (email, password) if email else (None, None)

def click_js(driver, element):
    try:
        driver.execute_script("arguments[0].click();", element)
    except:
        try: element.click()
        except: pass

def human_typing(driver, element_id, text):
    try:
        elem = driver.find_element(By.ID, element_id)
        elem.click()
        elem.clear()
        text_str = str(text)
        for char in text_str:
            elem.send_keys(char)
            time.sleep(0.01)
        elem.send_keys(Keys.TAB)
    except: pass

def format_date_for_input(iso_date):
    try:
        date_obj = datetime.strptime(iso_date, "%Y-%m-%d")
        return date_obj.strftime("%d%m%Y")
    except:
        return iso_date.replace("-", "").replace("/", "")

def send_webhook(msg, status, link=None):
    if not WEBHOOK_MAKE_URL: return
    try: requests.post(WEBHOOK_MAKE_URL, json={"msg": msg, "status": status, "link": link}, timeout=5)
    except: pass

# --- MEAL MAP ---
MEAL_MAP = {
    "cafe": {"op1": "PENDENTE", "op2": "OPÇÃO CAFÉ 2- Pão com requeijão", "op3": "CAFÉ OPÇÃO 3 - Pão com ovos"},
    "almoco": {"op1": "ALMOÇO/ JANTAR 1", "op2": "ALMOÇO/ JANTAR 2"}
}

# --- SELECTION FUNCTION (VIDEO LOGIC) ---
def select_items(driver, wait, category, raw_codes):
    if not raw_codes: return
    logger.info(f">> Selecting {category}: {raw_codes}")
    
    code_list = str(raw_codes).split(",")
    for code in code_list:
        name = MEAL_MAP.get(category, {}).get(code.strip().lower())
        if not name: continue
        
        logger.info(f"   > Item: {name}")
        try:
            # 1. Find text to locate the card
            xpath_text = f"//span[contains(text(), '{name}')]"
            
            # Scroll modal body
            driver.execute_script("document.querySelectorAll('.modal-body').forEach(e => e.scrollTop = e.scrollHeight)")
            time.sleep(0.5)

            elem_text = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath_text)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem_text)
            
            # 2. CLICK ON THE CARD (Video Logic: Click on the container, not just text)
            # Looks for the parent div that acts as the card/row
            parent = elem_text.find_element(By.XPATH, "./ancestor::div[contains(@class, 'itemLista') or contains(@class, 'card') or contains(@style, 'width')]")
            click_js(driver, parent)
            time.sleep(1) # Wait for "Add meal?" modal
            
            # 3. CONFIRM (Using the specific HTML you provided)
            # <div style="margin-top: 5px;" class="botao" onclick="swal.clickConfirm()">confirmar</div>
            try:
                btn_confirm = WebDriverWait(driver, 3).until(EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(@class, 'botao') and contains(text(), 'confirmar')]")
                ))
                click_js(driver, btn_confirm)
            except:
                # Fallback: Standard SweetAlert
                driver.execute_script("swal.clickConfirm()")
            
            time.sleep(1) # Wait for processing
            
        except Exception as e:
            logger.warning(f"   ⚠️ Failed to select item '{name}': {e}")

# ==============================================================================
# 🤖 ROBOT V50 - FINAL CONCILIATION
# ==============================================================================
def execute_registration(username, password, patient, clinical_data):
    kill_zombies()
    logger.info("--- ⚡ Starting Robot V50 (V46 Logic + Video Favorites) ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,720")
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(120)
    wait = WebDriverWait(driver, 20)
    app_link = "Not captured"

    try:
        # 1. LOGIN
        driver.get("https://pt.webdiet.com.br/login/")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(username)
        driver.find_element(By.ID, "senhaLogin").send_keys(password + Keys.ENTER)
        
        # 2. REGISTRATION (Opening Modal)
        logger.info(">> Opening form...")
        try:
            # Using the V46 button (Green button on Dashboard)
            btn = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
            click_js(driver, btn)
        except:
            raise Exception("Failed to open modal.")
        
        time.sleep(2)

        # 3. FILLING
        logger.info(f">> Filling: {patient['nome']}")
        human_typing(driver, "nomeAtalho", patient['nome'])
        try: driver.find_element(By.ID, "generoAtalho").send_keys("M" if patient['sexo'].lower().startswith('m') else "F")
        except: pass
        
        formatted_date = format_date_for_input(patient['nascimento'])
        human_typing(driver, "nascimentoAtalho", formatted_date)
        human_typing(driver, "telefoneAtalho", patient['telefone'])
        human_typing(driver, "emailAtalho", patient['email'])

        # 4. SAVE
        logger.info(">> Saving...")
        btn_save = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_save)
        
        try:
            WebDriverWait(driver, 10).until(EC.invisibility_of_element_located((By.ID, "novoPacienteBtnAtalho")))
            logger.info("✅ Registration Saved.")
        except:
            raise Exception("Save button stuck.")

        # 5. TRANSITION MODAL (HTML 3 from your list)
        logger.info(">> Transition...")
        time.sleep(2)
        # HTML 3: <div ... onclick="swal.clickConfirm()">registrar nova consulta</div>
        # We execute JS directly as requested in V46
        driver.execute_script("if(typeof swal !== 'undefined') { swal.clickConfirm(); }")
        time.sleep(2)

        # 6. SEARCH BY PHONE (V46/V48 Logic - Safest)
        logger.info(">> Searching by Phone...")
        try:
            driver.execute_script("swal.close(); $('.modal').modal('hide');")
            time.sleep(1)
            
            search_input = wait.until(EC.element_to_be_clickable((By.ID, "barraBuscaPaciente")))
            search_input.clear()
            search_input.send_keys(patient['telefone'])
            time.sleep(1)
            search_input.send_keys(Keys.ENTER)
            
            logger.info("   > Clicking on patient...")
            patient_row = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".pacienteLinha")))
            click_js(driver, patient_row)
            
            logger.info("   > Waiting for profile...")
            wait.until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            logger.info("✅ Profile loaded.")

        except Exception as e:
            raise Exception(f"Failed to enter profile: {e}")

        # 7. PLANNING FLOW (Using HTML 4, 5b1, 5b2)
        logger.info(">> Starting Diet Flow...")
        driver.execute_script("document.body.style.zoom='70%'")
        time.sleep(2)
        
        try:
            # HTML 4: atalhoPlanejamento
            btn_add = driver.find_element(By.ID, "atalhoPlanejamento")
            click_js(driver, btn_add)
            time.sleep(3)
            
            # HTML 5 b1: Avançar
            try:
                btn_next = driver.find_element(By.XPATH, "//div[contains(@class, 'botao') and contains(text(), 'avançar')]")
                click_js(driver, btn_next)
            except:
                driver.execute_script("swal.clickConfirm()") 
            time.sleep(3)
            
            # HTML 5 b2: Confirmar (Criar)
            try:
                btn_create = driver.find_element(By.ID, "criarPlanejamento")
                click_js(driver, btn_create)
            except:
                driver.execute_script("swal.clickConfirm()") 
            
            time.sleep(5)
            
        except Exception as e:
            raise Exception(f"Error opening diet: {e}")

        # 8. CAPTURE LINK
        try:
            link_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'paciente.me/')]")
            app_link = link_elem.text.strip()
            logger.info(f"✅ LINK: {app_link}")
        except: pass

        # 9. CLEAR HABITS (Using HTML 6 logic)
        logger.info(">> Clearing habits...")
        try:
            # Limit to 5 attempts
            for _ in range(5):
                # HTML 6: Lixeira (class btnAtalhos or i.fi-sr-trash)
                trash_cans = driver.find_elements(By.CSS_SELECTOR, "i.fi-sr-trash")
                if not trash_cans: break
                
                click_js(driver, trash_cans[0])
                time.sleep(0.8)
                
                # HTML 6: Confirmação (class botao background vermelho)
                try:
                    btn_remove = driver.find_element(By.XPATH, "//div[contains(@style, 'var(--vermelho)')]")
                    click_js(driver, btn_remove)
                except:
                    driver.execute_script("swal.clickConfirm()")
                
                time.sleep(1)
        except Exception as e: 
            logger.warning(f"Clearing error: {e}")

        # 10. FAVORITES (VIDEO LOGIC + HTML 2)
        logger.info(">> Inserting favorites...")
        driver.execute_script("window.scrollTo(0, 0);")
        
        # Click on "Refeições Favoritas" button
        click_js(driver, WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']"))))
        logger.info("   > Favorites list open.")
        time.sleep(3)
        
        # Select items using Video Logic (Click Card -> Confirm)
        select_items(driver, wait, "cafe", clinical_data.get("cafe"))
        select_items(driver, wait, "almoco", clinical_data.get("almoco"))
        
        # Close Modal (HTML 3)
        logger.info("   > Closing favorites...")
        try: 
            # HTML 3: <button class="close" ... data-dismiss="modal">
            btn_close = driver.find_element(By.CSS_SELECTOR, "button.close[data-dismiss='modal']")
            click_js(driver, btn_close)
        except: 
            # Fallback
            driver.execute_script("document.querySelector('.modal-backdrop').click()")
        
        # 11. FINALIZE (HTML 7)
        logger.info(">> Finalizing...")
        try:
            driver.execute_script("document.getElementById('horarioRotinaTemp0').value = '08:00';")
            driver.execute_script("document.getElementById('horarioRotinaTemp1').value = '12:00';")
        except: pass
        
        time.sleep(1)
        # HTML 7: salvarPrescricao()
        try:
            btn_final = driver.find_element(By.XPATH, "//div[contains(@onclick, 'salvarPrescricao()')]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_final)
            time.sleep(1)
            click_js(driver, btn_final)
        except:
            # Fallback
            btn_final_alt = driver.find_element(By.XPATH, "//div[contains(text(), 'salvar alterações')]")
            click_js(driver, btn_final_alt)
        
        logger.info("✅ TOTAL SUCCESS!")
        send_webhook("Success Total", "Completed", app_link)
        return {"status": "success", "link": app_link}

    except Exception as e:
        logger.error(f"❌ FATAL ERROR: {e}")
        send_webhook(f"Error: {str(e)}", "Error")
        return {"status": "error", "msg": str(e)}
    finally:
        try: driver.quit()
        except: pass

# ==============================================================================
# API
# ==============================================================================
app = FastAPI()

class PatientData(BaseModel):
    nome: str
    sexo: str
    email: str
    telefone: str
    nascimento: str

class RegistrationRequest(BaseModel):
    paciente: PatientData
    dados_clinicos: Optional[Dict[str, Any]] = {}

@app.post("/cadastrar-paciente")
def api_register(request: RegistrationRequest, background_tasks: BackgroundTasks):
    kill_zombies()
    username, password = read_credentials()
    background_tasks.add_task(execute_registration, username, password, request.paciente.dict(), request.dados_clinicos)
    return {"message": "Processing...", "patient": request.paciente.nome}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
