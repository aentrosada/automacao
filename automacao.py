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

WEBHOOK_MAKE_URL = os.getenv("WEBHOOK_MAKE_URL")

# ==============================================================================
# 🛠️ FUNÇÕES AUXILIARES
# ==============================================================================
def ler_credenciais():
    email = os.getenv("LOGIN_WEBDIET")
    senha = os.getenv("SENHA_WEBDIET")
    if not email or not senha:
        if os.path.exists("login-web-diet.env"):
            try:
                with open("login-web-diet.env") as f:
                    for line in f:
                        if "LOGIN_WEBDIET" in line: email = line.split("=")[1].strip()
                        if "SENHA_WEBDIET" in line: senha = line.split("=")[1].strip()
            except: pass
    return email, senha

def click_js(driver, elemento):
    driver.execute_script("arguments[0].click();", elemento)

def preencher_js(driver, id_elemento, valor):
    """Preenche campos forçando o valor via JS (evita erro de máscara/digitação)"""
    try:
        script = f"""
        var el = document.getElementById('{id_elemento}');
        if(el) {{
            el.value = '{valor}';
            el.dispatchEvent(new Event('input'));
            el.dispatchEvent(new Event('change'));
            el.dispatchEvent(new Event('blur'));
        }}
        """
        driver.execute_script(script)
    except: pass

def definir_horario(driver, element_id, horario):
    try:
        driver.execute_script(f"document.getElementById('{element_id}').value = '{horario}';")
    except: pass

def enviar_webhook(paciente_dados, dados_clinicos, link_app, status_msg, erro_detalhe=None):
    if not WEBHOOK_MAKE_URL: return
    try: 
        payload = {
            "status": status_msg, 
            "link_app": link_app, 
            "erro_detalhe": erro_detalhe,
            "paciente": paciente_dados, 
            "dados_clinicos": dados_clinicos
        }
        requests.post(WEBHOOK_MAKE_URL, json=payload, timeout=5)
        logger.info(f"Webhook enviado: {status_msg}")
    except: pass

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

def selecionar_itens(driver, wait, categoria, codigos_brutos):
    if not codigos_brutos: return
    logger.info(f">> Selecionando {categoria}: {codigos_brutos}")
    lista_codigos = str(codigos_brutos).split(",")
    
    for codigo in lista_codigos:
        nome_real = MAPA_REFEICOES.get(categoria, {}).get(codigo.strip().lower())
        if not nome_real: continue
        try:
            xpath_item = f"//span[contains(text(), '{nome_real}')]"
            elem = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath_item)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            click_js(driver, elem)
            
            # Confirmação do item
            time.sleep(0.5)
            click_js(driver, driver.find_element(By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']"))
            time.sleep(0.5)
            logger.info(f"✅ Item adicionado: {nome_real}")
        except: 
            logger.warning(f"⚠️ Falha ao adicionar: {nome_real}")

# ==============================================================================
# 🤖 ROBÔ PRINCIPAL (V18 - COMPLETO)
# ==============================================================================
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    logger.info("--- ⚡ Iniciando Robô V18 (Cadastro Blindado + Dieta Completa) ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1366,768")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false") 
    
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 15)
    link_app_capturado = "Link não capturado"

    try:
        # 1. LOGIN
        driver.get("https://pt.webdiet.com.br/login/")
        wait.until(EC.visibility_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.find_element(By.ID, "senhaLogin").send_keys(senha + Keys.ENTER)
        
        # 2. CADASTRO
        logger.info(">> Abrindo formulário...")
        try:
            # Espera carregar o painel
            WebDriverWait(driver, 20).until(EC.url_contains("painel"))
            btn_novo = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
            click_js(driver, btn_novo)
        except:
            raise Exception("Falha ao acessar botão 'Novo Paciente' no Painel.")
        
        time.sleep(1.5)
        
        # Preenchimento via JS (Mais seguro)
        logger.info(f">> Preenchendo: {paciente['nome']}")
        preencher_js(driver, "nomeAtalho", paciente['nome'])
        preencher_js(driver, "emailAtalho", paciente['email'])
        preencher_js(driver, "telefoneAtalho", paciente['telefone'])
        preencher_js(driver, "nascimentoAtalho", "01/01/1990")
        
        sexo = "M" if paciente['sexo'].lower().startswith('m') else "F"
        preencher_js(driver, "generoAtalho", sexo)

        # 3. SALVAR E VALIDAR
        logger.info(">> Clicando em Salvar...")
        click_js(driver, driver.find_element(By.ID, "novoPacienteBtnAtalho"))
        
        # GARANTIA DE CADASTRO: Verifica se o botão de salvar sumiu
        try:
            WebDriverWait(driver, 5).until(EC.invisibility_of_element_located((By.ID, "novoPacienteBtnAtalho")))
            logger.info("✅ Cadastro Validado! (Botão salvar sumiu)")
        except TimeoutException:
            # Se o botão não sumiu, tenta ler o erro na tela
            try:
                msg_erro = driver.find_element(By.CLASS_NAME, "swal2-validation-message").text
                raise Exception(f"Erro no formulário: {msg_erro}")
            except:
                raise Exception("O cadastro travou (Botão salvar não sumiu). Verifique dados duplicados.")

        # 4. TRANSIÇÃO (MODAL + ESPERA 3s)
        logger.info(">> Aguardando Modal de Consulta...")
        try:
            # Espera o modal aparecer visualmente
            WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'registrar nova consulta')]")))
            logger.info("✅ Modal detectado. Confirmando via JS...")
            
            # Clica via JS
            driver.execute_script("swal.clickConfirm()")
            
            # PAUSA SOLICITADA
            logger.info(">> ⏳ Aguardando 3 segundos...")
            time.sleep(3)
            
        except TimeoutException:
            logger.warning("⚠️ Modal não apareceu (pode ter sido rápido ou redirecionou direto).")

        # 5. ENTRANDO NO PLANEJAMENTO (COM RESGATE)
        logger.info(">> Buscando botão 'Planejamento'...")
        
        encontrou_paciente = False
        try:
            # Tenta acesso direto
            btn_add = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            click_js(driver, btn_add)
            encontrou_paciente = True
            logger.info("✅ Acesso direto ao planejamento!")
        except:
            logger.warning("⚠️ Botão sumiu. Iniciando RESGATE na lista...")
        
        # LÓGICA DE RESGATE (Se não entrou direto)
        if not encontrou_paciente:
            try:
                # Garante que não tem modal travando
                try: driver.execute_script("swal.close()")
                except: pass
                
                # Clica no nome do paciente na lista
                xpath_nome = f"//*[contains(text(), '{paciente['nome']}')]"
                elem_nome = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath_nome)))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem_nome)
                click_js(driver, elem_nome)
                logger.info("✅ Resgate: Clicado no nome.")
                
                # Agora espera carregar o perfil e clica no planejamento
                time.sleep(3)
                btn_add = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
                click_js(driver, btn_add)
                logger.info("✅ Planejamento acessado após resgate!")
                
            except Exception as e:
                raise Exception(f"Falha total ao acessar paciente. Nem redirect nem lista funcionaram. Erro: {e}")

        # ======================================================================
        # 6. EXECUÇÃO DO PLANO ALIMENTAR
        # ======================================================================
        logger.info(">> Iniciando criação da dieta...")
        time.sleep(2)

        # Tenta pegar o Link
        try:
            el_link = driver.find_element(By.ID, "linkRef")
            link_app_capturado = el_link.text.strip()
            logger.info(f"✅ Link Capturado: {link_app_capturado}")
        except: pass

        # Passa pelos modais iniciais (Avançar / Criar)
        try:
            click_js(driver, WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'avançar')]"))))
            time.sleep(1)
            click_js(driver, driver.find_element(By.ID, "criarPlanejamento"))
        except: pass
        
        time.sleep(3)

        # A. LIMPEZA DE HÁBITOS
        logger.info(">> Limpando hábitos...")
        try:
            # Tenta limpar até 15 itens
            for _ in range(15):
                try:
                    lixeira = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "i.fi-sr-trash")))
                    click_js(driver, lixeira)
                    time.sleep(0.3)
                    driver.execute_script("swal.clickConfirm()") # Confirma exclusão
                    time.sleep(0.5)
                except: break # Se não achar mais lixeiras, sai do loop
        except: pass

        # B. FAVORITOS
        logger.info(">> Inserindo refeições...")
        driver.execute_script("window.scrollTo(0, 0);")
        try:
            btn_fav = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']")))
            click_js(driver, btn_fav)
            time.sleep(3)
            
            selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
            selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
            
            # Fecha modal favoritos
            try: driver.execute_script("document.querySelector('button.close[data-dismiss=\"modal\"]').click()")
            except: driver.execute_script("document.querySelector('.modal-backdrop').click()")
            
        except Exception as e:
            logger.error(f"Erro nos favoritos: {e}")

        # C. HORÁRIOS
        logger.info(">> Ajustando horários...")
        definir_horario(driver, "horarioRotinaTemp0", "08:00")
        definir_horario(driver, "horarioRotinaTemp1", "12:00")

        # D. SALVAR FINAL
        logger.info(">> Salvando Prescrição...")
        time.sleep(1)
        try:
            btn_final = driver.find_element(By.CSS_SELECTOR, "div[onclick*='salvarPrescricao']")
            click_js(driver, btn_final)
            logger.info("✅ SUCESSO TOTAL! Dieta Criada.")
            
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Sucesso Total")
            return {"status": "sucesso", "link": link_app_capturado}
            
        except Exception as e:
            logger.error(f"Erro ao salvar final: {e}")
            raise Exception("Erro ao clicar em Salvar Prescrição")

    except Exception as e:
        logger.error(f"❌ ERRO GERAL: {traceback.format_exc()}")
        enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Erro Fatal", str(e))
        return {"status": "erro", "mensagem": str(e)}
    
    finally:
        try: driver.quit()
        except: pass

# ==============================================================================
# API SETUP
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
    if not usuario: return {"erro": "sem credenciais"}
    
    background_tasks.add_task(executar_cadastro, usuario, senha, pedido.paciente.dict(), pedido.dados_clinicos)
    return {"mensagem": "Processando...", "paciente": pedido.paciente.nome}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
