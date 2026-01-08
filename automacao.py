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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==============================================================================
# 🔐 CONFIGURAÇÃO DE AMBIENTE
# ==============================================================================
WEBHOOK_MAKE_URL = os.getenv("WEBHOOK_MAKE_URL")

def ler_credenciais():
    logger.info("--- 🔍 BUSCANDO CREDENCIAIS ---")
    email = os.getenv("LOGIN_WEBDIET")
    senha = os.getenv("SENHA_WEBDIET")
    
    if email and senha:
        return email, senha

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
    except Exception as e:
        logger.error(f"Erro credenciais: {e}")
        return None, None

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
    try:
        driver.execute_script("arguments[0].click();", elemento)
    except:
        try:
            elemento.click()
        except: pass

def definir_horario(driver, element_id, horario):
    try:
        script = f"""
        var input = document.getElementById('{element_id}');
        if(input) {{
            input.value = '{horario}';
            input.dispatchEvent(new Event('change'));
            input.dispatchEvent(new Event('blur'));
        }}
        """
        driver.execute_script(script)
    except: pass

def selecionar_itens(driver, wait, categoria, codigos_brutos):
    if not codigos_brutos: return
    logger.info(f">> Selecionando {categoria}: {codigos_brutos}")
    lista_codigos = str(codigos_brutos).split(",")
    
    for codigo in lista_codigos:
        codigo_limpo = codigo.strip().lower()
        nome_real = MAPA_REFEICOES.get(categoria, {}).get(codigo_limpo)
        if not nome_real: continue
            
        try:
            xpath_item = f"//span[contains(text(), '{nome_real}')]"
            elem = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath_item)))
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            click_js(driver, elem)
            
            try:
                btn_confirmar = WebDriverWait(driver, 3).until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']")
                ))
                click_js(driver, btn_confirmar)
                time.sleep(0.5)
                logger.info(f"✅ Adicionado: {nome_real}")
            except TimeoutException:
                click_js(driver, elem)
                time.sleep(0.5)
                try:
                    btn_retry = driver.find_element(By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']")
                    click_js(driver, btn_retry)
                    logger.info(f"✅ Adicionado (Retry): {nome_real}")
                except:
                    logger.warning(f"⚠️ Falha ao confirmar: {nome_real}")

        except Exception as e:
            logger.warning(f"Item não encontrado: {nome_real}")

def enviar_webhook(paciente_dados, dados_clinicos, link_app, status_msg):
    if not WEBHOOK_MAKE_URL: return
    try: 
        payload = {"status": status_msg, "link_app": link_app, "paciente": paciente_dados, "dados_clinicos": dados_clinicos}
        requests.post(WEBHOOK_MAKE_URL, json=payload, timeout=5)
        logger.info(f"Webhook enviado: {status_msg}")
    except: pass

# --- ROBÔ PRINCIPAL ---
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    logger.info("--- ⚡ Iniciando Robô V15 (Pausa de 3s Pós-Modal) ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--window-size=1366,768")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false") 
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-application-cache")
    chrome_options.page_load_strategy = 'eager'

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20)
    
    link_app_capturado = "Link não encontrado"

    try:
        driver.get("https://pt.webdiet.com.br/login/")
        
        # 1. LOGIN
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.switch_to.active_element.send_keys(Keys.TAB)
        driver.switch_to.active_element.send_keys(senha + Keys.ENTER)
        
        # 2. CADASTRO
        logger.info(">> Abrindo Novo Paciente...")
        btn_novo = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
        click_js(driver, btn_novo)
        
        time.sleep(1.5)
        
        # Preenchimento
        wait.until(EC.visibility_of_element_located((By.ID, "nomeAtalho"))).send_keys(paciente["nome"])
        try:
            sexo_val = paciente['sexo'].upper()[0]
            script_campos = f"""
                document.getElementById('generoAtalho').value = '{sexo_val}';
                document.getElementById('generoAtalho').dispatchEvent(new Event('change'));
                document.getElementById('nascimentoAtalho').value = '01/01/2000';
                document.getElementById('emailAtalho').value = '{paciente['email']}';
                document.getElementById('telefoneAtalho').value = '{paciente['telefone']}';
            """
            driver.execute_script(script_campos)
        except: pass

        # Salvar Paciente
        logger.info(">> Salvando Paciente...")
        btn_salvar = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_salvar)

        # ======================================================================
        # 3. TRANSIÇÃO: ESPERA 3S PRE-MODAL -> CLICA -> ESPERA 3S POS-MODAL
        # ======================================================================
        logger.info(">> ⏳ Aguardando 3 segundos para modal aparecer...")
        time.sleep(3) 

        logger.info(">> Clicando em 'Registrar Nova Consulta'...")
        try:
            # Seletor exato
            xpath_botao = "//div[contains(text(), 'registrar nova consulta')]"
            btn_confirmar = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath_botao)))
            click_js(driver, btn_confirmar)
            logger.info("✅ Botão clicado!")
            
        except TimeoutException:
            logger.warning("⚠️ Botão não apareceu ou timeout. Tentando JS direto...")
            driver.execute_script("swal.clickConfirm()")

        # AQUI ESTÁ A PAUSA QUE VOCÊ PEDIU
        logger.info(">> ⏳ Aguardando 3 segundos para carregar a tela do paciente...")
        time.sleep(3)

        # ======================================================================
        # 4. BUSCA TELA DE PLANEJAMENTO
        # ======================================================================
        logger.info(">> Buscando tela de Planejamento...")
        
        driver.execute_script("document.body.style.zoom='70%'")

        try:
            # Tenta achar o botão de planejamento
            btn_add = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            click_js(driver, btn_add)
            logger.info("✅ Planejamento iniciado!")
        except:
            logger.error("❌ Não foi possível encontrar o botão 'atalhoPlanejamento'. O redirecionamento falhou.")
            raise Exception("Falha na transição para o paciente.")

        # ======================================================================
        # FLUXO DE CRIAÇÃO DA DIETA
        # ======================================================================
        time.sleep(2)

        try:
            el_link = driver.find_element(By.ID, "linkRef")
            link_app_capturado = el_link.text.strip()
            logger.info(f"✅ Link Capturado: {link_app_capturado}")
        except: pass

        try:
            btn_av = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'avançar')]")))
            click_js(driver, btn_av)
            time.sleep(1)
            
            btn_criar = driver.find_element(By.ID, "criarPlanejamento")
            click_js(driver, btn_criar)
        except: pass
        
        time.sleep(3)

        # --- LIMPEZA ---
        logger.info(">> Limpando hábitos...")
        try:
            lixeiras = driver.find_elements(By.CSS_SELECTOR, "i.fi-sr-trash")
            for _ in range(15): 
                try:
                    lixeira = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "i.fi-sr-trash")))
                    click_js(driver, lixeira)
                    time.sleep(0.3)
                    driver.execute_script("swal.clickConfirm()")
                    time.sleep(0.5)
                except TimeoutException:
                    break 
                except: break
        except: pass

        # --- FAVORITOS ---
        logger.info(">> Favoritos...")
        driver.execute_script("window.scrollTo(0, 0);")
        
        btn_fav = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']")))
        click_js(driver, btn_fav)
        time.sleep(3)
        
        selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
        selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
        
        try:
            driver.execute_script("document.querySelector('button.close[data-dismiss=\"modal\"]').click()")
        except:
            driver.execute_script("document.querySelector('.modal-backdrop').click()")
        
        # Horários
        definir_horario(driver, "horarioRotinaTemp0", "08:00")
        definir_horario(driver, "horarioRotinaTemp1", "12:00")
        
        logger.info(">> Salvando Prescrição...")
        time.sleep(1)
        try:
            btn_final = driver.find_element(By.CSS_SELECTOR, "div[onclick*='salvarPrescricao']")
            click_js(driver, btn_final)
            logger.info("✅ Salvo!")
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Sucesso Total")
        except:
            logger.error("Erro ao salvar final.")

        return {"status": "sucesso", "link": link_app_capturado}

    except Exception as e:
        logger.error(f"❌ ERRO FATAL: {traceback.format_exc()}")
        enviar_webhook(paciente, dados_clinicos, link_app_capturado, f"Erro Fatal: {str(e)}")
        return {"status": "erro", "mensagem": str(e)}
    finally:
        try: driver.quit()
        except: pass

# ==============================================================================
# 🚀 API
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
    usuario, senha = ler_credenciais()
    if not usuario or not senha:
        raise HTTPException(status_code=500, detail="Credenciais não configuradas.")

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
