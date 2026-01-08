import os
import logging
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn

# ==============================================================================
# 📝 CONFIGURAÇÃO DE LOGS
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ==============================================================================
# 🔐 CONFIGURAÇÃO DE AMBIENTE
# ==============================================================================
WEBHOOK_MAKE_URL = os.getenv("WEBHOOK_MAKE_URL")

def ler_credenciais():
    email = os.getenv("LOGIN_WEBDIET")
    senha = os.getenv("SENHA_WEBDIET")
    if email and senha: return email, senha
    
    if os.path.exists("login-web-diet.env"):
        with open("login-web-diet.env") as f:
            for l in f:
                if "LOGIN_WEBDIET" in l: email = l.split("=")[1].strip()
                if "SENHA_WEBDIET" in l: senha = l.split("=")[1].strip()
    return email, senha

# ==============================================================================
# 🍎 MAPA DE REFEIÇÕES COMPLETO
# ==============================================================================
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
def click_js(driver, elem):
    driver.execute_script("arguments[0].click();", elem)

def definir_horario(driver, id_elem, hora):
    try:
        driver.execute_script(f"document.getElementById('{id_elem}').value = '{hora}';")
    except: pass

def enviar_webhook(msg, link=""):
    if WEBHOOK_MAKE_URL:
        try: requests.post(WEBHOOK_MAKE_URL, json={"status": msg, "link": link}, timeout=5)
        except: pass

# ==============================================================================
# 🤖 ROBÔ ESTÁVEL (SEM OTIMIZAÇÕES DE RISCO)
# ==============================================================================
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    logger.info("🚀 INICIANDO ROBÔ ESTÁVEL")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # REMOVIDO: blink-settings=imagesEnabled=false (Deixa carregar imagens para estabilidade)
    # REMOVIDO: page_load_strategy = 'eager' (Espera a página carregar 100% antes de agir)
    
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 30) # Aumentei o timeout padrão para 30s
    short = WebDriverWait(driver, 5)
    
    link_final = "Não gerado"

    try:
        # 1. LOGIN
        driver.get("https://pt.webdiet.com.br/login/")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.switch_to.active_element.send_keys(Keys.TAB)
        driver.switch_to.active_element.send_keys(senha + Keys.ENTER)
        
        # 2. CADASTRAR PACIENTE
        # Espera generosa para o dashboard carregar após login
        time.sleep(5) 
        
        logger.info(">> Clicando 'Adicionar Paciente'...")
        # Volta para o seletor original que funcionava
        btn_add = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='novoPaciente']")))
        click_js(driver, btn_add)
        
        logger.info(">> Preenchendo dados...")
        wait.until(EC.visibility_of_element_located((By.ID, "nomeAtalho"))).send_keys(paciente["nome"])
        
        # Injeção JS para dados (Isso é seguro e rápido)
        driver.execute_script(f"""
            try {{ document.getElementById('generoAtalho').value = '{paciente['sexo'].upper()[0]}'; }} catch(e) {{}}
            document.getElementById('nascimentoAtalho').value = '01/01/2000';
            document.getElementById('emailAtalho').value = '{paciente['email']}';
            document.getElementById('telefoneAtalho').value = '{paciente['telefone']}';
        """)
        
        logger.info(">> Salvando...")
        click_js(driver, driver.find_element(By.ID, "novoPacienteBtnAtalho"))
        
        # 3. TRATAMENTO DO POPUP "NOVA CONSULTA" (Baseado no seu vídeo)
        logger.info(">> Aguardando Popup 'Nova Consulta'...")
        time.sleep(3) # Tempo para o modal de sucesso sumir e o novo aparecer
        
        try:
            # Clica no botão AZUL "Registrar nova consulta"
            btn_pos_save = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//div[contains(text(), 'registrar nova consulta')]")
            ))
            click_js(driver, btn_pos_save)
            logger.info("✅ Clicado em 'Registrar nova consulta'. Aguardando perfil...")
        except TimeoutException:
            logger.warning("⚠️ Popup não apareceu ou demorou. Verificando se já foi para o perfil...")

        # 4. VALIDAÇÃO DE TELA DE PERFIL
        try:
            # Agora estamos na tela do paciente, esperamos o botão da dieta aparecer
            wait.until(EC.visibility_of_element_located((By.ID, "atalhoPlanejamento")))
            logger.info("✅ Estamos no perfil do paciente!")
            try:
                link_final = driver.find_element(By.ID, "linkRef").text.strip()
                logger.info(f"🔗 Link: {link_final}")
            except: pass
        except TimeoutException:
            logger.error(f"❌ ERRO: Não chegou na tela de perfil. URL: {driver.current_url}")
            raise Exception("Falha de navegação pós-cadastro (Dashboard não carregou)")

        # 5. PLANEJAMENTO
        if dados_clinicos:
            logger.info(">> Iniciando Planejamento...")
            
            # Clica no botão Planejamento
            btn_plan = driver.find_element(By.ID, "atalhoPlanejamento")
            click_js(driver, btn_plan)
            
            # Passa pelo Wizard (Avançar -> Confirmar)
            try:
                time.sleep(2)
                btn_avancar = short.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'avançar')]")))
                click_js(driver, btn_avancar)
                time.sleep(1)
                btn_confirmar_mod = short.until(EC.element_to_be_clickable((By.ID, "criarPlanejamento")))
                click_js(driver, btn_confirmar_mod)
            except: pass
            
            time.sleep(3) # Carrega editor

            # --- LIMPEZA DOS HÁBITOS ---
            logger.info(">> Limpando (Delete)...")
            for _ in range(5):
                try:
                    lixo = short.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "i.fi-sr-trash")))
                    click_js(driver, lixo)
                    
                    conf = short.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'remover hábito')]")))
                    click_js(driver, conf)
                    time.sleep(1.5) # Tempo para processar exclusão
                except: break

            # --- ADICIONAR FAVORITOS ---
            logger.info(">> Adicionando Favoritos...")
            driver.execute_script("window.scrollTo(0, 0);")
            
            try:
                btn_fav = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']")))
                click_js(driver, btn_fav)
                time.sleep(4) # Espera lista carregar
                
                # Seleciona itens
                for cat in ["cafe", "almoco"]:
                    cods = dados_clinicos.get(cat)
                    if not cods: continue
                    
                    for cod in str(cods).split(","):
                        nome = MAPA_REFEICOES.get(cat, {}).get(cod.strip().lower())
                        if not nome: continue
                        
                        try:
                            # Clica no item
                            xpath_item = f"//span[contains(text(), '{nome}')]"
                            item = driver.find_element(By.XPATH, xpath_item)
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                            click_js(driver, item)
                            
                            # Confirma
                            try:
                                btn_ok = short.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm') and contains(text(), 'confirmar')]")))
                                click_js(driver, btn_ok)
                                time.sleep(1)
                            except: pass
                            logger.info(f"   + Adicionado: {nome}")
                        except:
                            logger.warning(f"   - Não achou: {nome}")
                
                # Fecha modal favoritos
                try: driver.execute_script("document.querySelector('.close[data-dismiss=\"modal\"]').click()")
                except: pass
                
            except Exception as e:
                logger.error(f"Erro nos favoritos: {e}")

            # Horários
            definir_horario(driver, "horarioRotinaTemp0", "08:00")
            definir_horario(driver, "horarioRotinaTemp1", "12:00")

            # --- SALVAR FINAL ---
            logger.info(">> Salvando Final...")
            time.sleep(1)
            btn_final = driver.find_element(By.CSS_SELECTOR, "div[onclick*='salvarPrescricao']")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_final)
            click_js(driver, btn_final)
            
            try:
                time.sleep(2)
                btn_liberar = short.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'liberar para paciente')]")))
                click_js(driver, btn_liberar)
            except: pass

            logger.info("✅ SUCESSO TOTAL!")
            enviar_webhook("Sucesso", link_final)

        return {"status": "ok", "link": link_final}

    except Exception as e:
        logger.error(f"❌ ERRO: {traceback.format_exc()}")
        enviar_webhook("Erro", str(e))
        return {"status": "erro", "msg": str(e)}
    finally:
        try: driver.quit()
        except: pass

# ==============================================================================
# API
# ==============================================================================
app = FastAPI()

class Payload(BaseModel):
    paciente: dict
    dados_clinicos: dict

@app.post("/cadastrar-paciente")
def run(p: Payload, bt: BackgroundTasks):
    creds = ler_credenciais()
    if not creds: raise HTTPException(500, "Sem credenciais")
    bt.add_task(executar_cadastro, creds[0], creds[1], p.paciente, p.dados_clinicos)
    return {"msg": "Processando"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
