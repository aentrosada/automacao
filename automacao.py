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
                btn_confirmar = WebDriverWait(driver, 4).until(EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()')]")
                ))
                click_js(driver, btn_confirmar)
                time.sleep(1)
            except TimeoutException:
                pass 
        except Exception as e:
            logger.warning(f"Item não encontrado: {nome_real}")

def enviar_webhook(paciente_dados, dados_clinicos, link_app, status_msg):
    logger.info(f"\n📡 STATUS: {status_msg}")
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
    chrome_options.add_argument("--blink-settings=imagesEnabled=false") # Otimização de memória
    chrome_options.add_argument("--window-size=1920,1080") 

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 30)
    
    link_app_capturado = "Link não encontrado"

    try:
        logger.info(f"--- 🚀 Iniciando fluxo para: {paciente.get('nome')} ---")
        driver.get("https://pt.webdiet.com.br/login/")
        
        # 1. LOGIN
        logger.info("Preenchendo login...")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.switch_to.active_element.send_keys(Keys.TAB)
        driver.switch_to.active_element.send_keys(senha + Keys.ENTER)
        
        # --- FIX CRÍTICO: FORÇAR NAVEGAÇÃO ---
        logger.info("Aguardando processamento do login...")
        time.sleep(5) # Espera o cookie de sessão ser gravado
        
        logger.info(">> Forçando ida ao Painel...")
        driver.get("https://pt.webdiet.com.br/painel/")
        
        # Validação se logou
        if "login" in driver.current_url:
            raise Exception("Falha no login: O robô ainda está na página de login. Verifique senha.")

        # --- FIX POPUPS ---
        logger.info(">> Verificando popups bloqueadores...")
        try:
            # Tenta fechar qualquer modal genérico que esteja na frente
            popup_close = driver.find_elements(By.CSS_SELECTOR, "button.close, .modal-backdrop")
            if popup_close:
                logger.info("Fechando popup inicial...")
                driver.execute_script("document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());")
                driver.execute_script("document.querySelectorAll('.modal').forEach(el => el.style.display='none');")
        except: pass

        # 2. CADASTRO DE PACIENTE
        logger.info(">> Procurando botão Novo Paciente...")
        # Tenta seletor genérico por texto ou onclick
        btn_novo_paciente = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@onclick, 'novoPaciente')]")))
        click_js(driver, btn_novo_paciente)
        
        logger.info("Preenchendo formulário básico...")
        wait.until(EC.visibility_of_element_located((By.ID, "nomeAtalho"))).send_keys(paciente["nome"])
        
        # Gênero e Data (JS)
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

        # Espera modal fechar
        time.sleep(3)
        try:
            if btn_salvar.is_displayed():
                 click_js(driver, btn_salvar)
                 time.sleep(2)
        except: pass
        
        # 3. CAPTURA LINK
        time.sleep(2)
        try:
            # Fecha menu lateral se aparecer
            try:
                driver.find_element(By.XPATH, "//div[contains(text(), 'não registrar')]").click()
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
            btn_add_planejamento = wait.until(EC.element_to_be_clickable((By.ID, "atalhoPlanejamento")))
            click_js(driver, btn_add_planejamento)
            time.sleep(2)

            # Avançar/Confirmar
            try:
                # Clica em todos os botões de confirmação que aparecerem
                botoes_confirm = driver.find_elements(By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()')]")
                for btn in botoes_confirm:
                    if btn.is_displayed():
                        click_js(driver, btn)
                        time.sleep(1)
            except: pass

            # Botão Criar Final
            try:
                btn_criar = driver.find_element(By.ID, "criarPlanejamento")
                click_js(driver, btn_criar)
            except: pass
            
            time.sleep(4)

            # Limpeza
            logger.info(">> Limpando hábitos...")
            driver.execute_script("""
                var lixeiras = document.querySelectorAll('.fi-sr-trash');
                if(lixeiras.length > 0) { lixeiras[0].click(); }
            """)
            time.sleep(1)
            try:
                driver.find_element(By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()')]").click()
                time.sleep(1)
                # Tenta mais uma vez
                driver.execute_script("var l = document.querySelectorAll('.fi-sr-trash'); if(l.length > 0) l[0].click();")
                time.sleep(1)
                driver.find_element(By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()')]").click()
            except: pass

            # Favoritos
            logger.info(">> Favoritos...")
            try:
                driver.execute_script("window.scrollTo(0, 0);")
                btn_fav = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(., 'refeições favoritas')]")))
                click_js(driver, btn_fav)
                time.sleep(4)
            except:
                raise Exception("Menu Favoritos não abriu")

            selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
            selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
            
            logger.info(">> Horários e Salvar...")
            definir_horario(driver, "horarioRotinaTemp0", "08:00")
            definir_horario(driver, "horarioRotinaTemp1", "12:00")
            
            # Fecha modal favoritos
            try:
                driver.execute_script("document.querySelector('button.close[data-dismiss=\"modal\"]').click()")
                time.sleep(1)
            except: 
                driver.execute_script("document.body.click()") # Clica fora

            # Salvar Final
            btn_final = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'salvarPrescricao')]")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_final)
            click_js(driver, btn_final)
            
            logger.info("✅ Planejamento Salvo!")
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Sucesso Completo")
        else:
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Sucesso (Sem Dieta)")

        return {"status": "sucesso", "link": link_app_capturado}

    except Exception as e:
        logger.error(f"❌ ERRO: {traceback.format_exc()}")
        logger.error(f"URL no erro: {driver.current_url}") # LOG IMPORTANTE
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
