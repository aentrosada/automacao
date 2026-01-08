import os
import logging
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException, TimeoutException
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
        logger.info("✅ Achei nas Variáveis de Ambiente!")
        return email, senha
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
    except Exception as e:
        logger.warning(f"Erro ao definir horário: {e}")

def selecionar_itens(driver, wait, categoria, codigos_brutos):
    if not codigos_brutos: return
    logger.info(f">> Processando categoria: {categoria}")
    lista_codigos = str(codigos_brutos).split(",")
    
    for codigo in lista_codigos:
        codigo_limpo = codigo.strip().lower()
        nome_real = MAPA_REFEICOES.get(categoria, {}).get(codigo_limpo)
        if not nome_real: continue
            
        try:
            logger.info(f"Procurando item: {nome_real}")
            xpath_item = f"//span[contains(text(), '{nome_real}')]"
            elem = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpath_item)))
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(0.5)
            click_js(driver, elem)
            
            time.sleep(1) 
            try:
                btn_confirmar = WebDriverWait(driver, 3).until(EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()')]")
                ))
                click_js(driver, btn_confirmar)
                time.sleep(0.5)
            except: pass 
        except:
            logger.warning(f"Item não encontrado: {nome_real}")

def enviar_webhook(paciente_dados, dados_clinicos, link_app, status_msg):
    logger.info(f"\n📡 STATUS WEBHOOK: {status_msg}")
    if not WEBHOOK_MAKE_URL: return
    payload = {"status": status_msg, "link_app": link_app, "paciente": paciente_dados, "dados_clinicos": dados_clinicos}
    try: requests.post(WEBHOOK_MAKE_URL, json=payload, timeout=10)
    except: pass

# --- ROBÔ PRINCIPAL ---
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    logger.info("--- 🔧 Configurando Chrome ---")
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--window-size=1920,1080") 

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 25)
    
    link_app_capturado = "Link não encontrado"

    try:
        logger.info(f"--- 🚀 Iniciando fluxo para: {paciente.get('nome')} ---")
        driver.get("https://pt.webdiet.com.br/login/")
        
        # 1. LOGIN
        logger.info("Preenchendo login...")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.switch_to.active_element.send_keys(Keys.TAB)
        driver.switch_to.active_element.send_keys(senha + Keys.ENTER)
        
        logger.info("Aguardando login...")
        time.sleep(5) 
        
        logger.info(">> Forçando ida ao Painel...")
        driver.get("https://pt.webdiet.com.br/painel/v4/")
        
        # --- FIX POPUPS ---
        logger.info(">> Limpando Backdrops/Modais...")
        driver.execute_script("""
            var backdrops = document.querySelectorAll('.modal-backdrop');
            backdrops.forEach(function(el) { el.parentNode.removeChild(el); });
            var modals = document.querySelectorAll('.modal');
            modals.forEach(function(el) { el.style.display = 'none'; });
            document.body.classList.remove('modal-open');
        """)
        time.sleep(1)

        # 2. CADASTRO DE PACIENTE (CORRIGIDO COM SEU SNIPPET)
        logger.info(">> Procurando botão 'adicionar paciente'...")
        
        # Lista de tentativas baseada no seu HTML: <div class="botao" ... onclick="novoPaciente('index')">adicionar paciente</div>
        seletores = [
            "//div[contains(text(), 'adicionar paciente')]",    # Texto exato minúsculo
            "//div[@onclick=\"novoPaciente('index')\"]",        # Onclick exato
            "//div[contains(@class, 'botao') and contains(text(), 'adicionar')]" # Classe + Texto parcial
        ]
        
        btn_encontrado = False
        for xpath in seletores:
            try:
                btn = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, xpath)))
                logger.info(f"Botão encontrado via: {xpath}")
                click_js(driver, btn)
                btn_encontrado = True
                break
            except: continue
            
        if not btn_encontrado:
            logger.warning("Botão visual falhou. Tentando Injeção JS Direta...")
            # Chama a função JS diretamente como último recurso
            driver.execute_script("novoPaciente('index');")

        # Preenchimento do Form
        logger.info("Preenchendo formulário...")
        wait.until(EC.visibility_of_element_located((By.ID, "nomeAtalho"))).send_keys(paciente["nome"])
        
        try:
            sexo = paciente['sexo'].upper()[0]
            driver.execute_script(f"document.getElementById('generoAtalho').value = '{sexo}';")
            driver.execute_script("document.getElementById('nascimentoAtalho').value = '01/01/2000';")
        except: pass

        driver.find_element(By.ID, "emailAtalho").send_keys(paciente["email"])
        driver.find_element(By.ID, "telefoneAtalho").send_keys(paciente["telefone"])
        
        logger.info("Clicando em Salvar...")
        btn_salvar = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_salvar)
        time.sleep(3)
        
        # Garante que salvou
        try:
             if btn_salvar.is_displayed(): click_js(driver, btn_salvar)
        except: pass
        
        # 3. CAPTURA LINK
        time.sleep(3)
        try:
            # Tenta clicar no botão "não registrar" se aparecer
            try: 
                driver.execute_script("document.querySelector(\"div[onclick*='não registrar']\").click()")
            except: pass

            elemento_link = wait.until(EC.visibility_of_element_located((By.ID, "linkRef")))
            link_app_capturado = elemento_link.text.strip()
            logger.info(f"✅ LINK: {link_app_capturado}")
        except: 
            logger.warning("Link não capturado.")

        # 4. PLANEJAMENTO
        if dados_clinicos and (dados_clinicos.get("cafe") or dados_clinicos.get("almoco")):
            logger.info(">> Iniciando Planejamento...")
            
            # Botão Adicionar Planejamento
            try:
                btn_add_planejamento = wait.until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
                click_js(driver, btn_add_planejamento)
            except:
                btn_alt = driver.find_element(By.XPATH, "//i[contains(@class, 'fa-utensils')]/..")
                click_js(driver, btn_alt)

            time.sleep(2)

            # Confirmações iniciais
            logger.info(">> Confirmando modais iniciais...")
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll("div[onclick*='swal.clickConfirm']");
                    for(var i=0; i<btns.length; i++) { btns[i].click(); }
                """)
                time.sleep(1)
                try: driver.execute_script("document.getElementById('criarPlanejamento').click();")
                except: pass
            except: pass
            
            time.sleep(4) 

            # Limpeza Turbo
            logger.info(">> Limpando hábitos...")
            for _ in range(3):
                try:
                    driver.execute_script("var trash = document.querySelector('.fi-sr-trash'); if(trash) trash.click();")
                    time.sleep(0.5)
                    driver.execute_script("swal.clickConfirm();")
                    time.sleep(1)
                except: break

            # Favoritos
            logger.info(">> Favoritos...")
            try:
                driver.execute_script("window.scrollTo(0, 0);")
                # Seletor robusto para o botão de favoritos
                btn_fav = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'refeições favoritas')]")))
                click_js(driver, btn_fav)
                time.sleep(3)
            except:
                raise Exception("Menu Favoritos não abriu")

            selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
            selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
            
            logger.info(">> Horários e Salvar...")
            definir_horario(driver, "horarioRotinaTemp0", "08:00")
            definir_horario(driver, "horarioRotinaTemp1", "12:00")
            
            # Fecha modal favoritos
            try: driver.execute_script("document.querySelector('button.close[data-dismiss=\"modal\"]').click()")
            except: driver.execute_script("document.body.click()")

            # Salvar Final
            logger.info(">> Salvando Final...")
            try:
                btn_final = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'salvarPrescricao')]")))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_final)
                click_js(driver, btn_final)
            except:
                driver.execute_script("salvarPrescricao();")
            
            logger.info("✅ Planejamento Salvo!")
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Sucesso Completo")
        else:
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Sucesso (Sem Dieta)")

        return {"status": "sucesso", "link": link_app_capturado}

    except Exception as e:
        logger.error(f"❌ ERRO: {traceback.format_exc()}")
        logger.error(f"URL no erro: {driver.current_url}")
        enviar_webhook(paciente, dados_clinicos, link_app_capturado, f"Erro: {str(e)}")
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
def api_cadastrar(pedido: PedidoCadastro, background_tasks: BackgroundTasks):
    user, pwd = ler_credenciais()
    if not user: raise HTTPException(status_code=500, detail="Sem credenciais")
    
    background_tasks.add_task(executar_cadastro, user, pwd, pedido.paciente.dict(), pedido.dados_clinicos)
    return {"msg": "Iniciado", "paciente": pedido.paciente.nome}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
