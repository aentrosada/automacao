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
    "cafe": {"op1": "PENDENTE", "op2": "OPÇÃO CAFÉ 2- Pão com requeijão", "op3": "CAFÉ OPÇÃO 3 - Pão com ovos", "op4": "CAFÉ OPÇÃO 4", "op5": "CAFÉ OPÇÃO 5"},
    "almoco": {"op1": "ALMOÇO/ JANTAR 1", "op2": "ALMOÇO/ JANTAR 2"}
}

# --- FUNÇÃO DE SELEÇÃO (BASEADA NO VÍDEO + HTML CORRETO) ---
def selecionar_itens(driver, wait, categoria, codigos_brutos):
    if not codigos_brutos: return
    logger.info(f">> Selecionando {categoria}: {codigos_brutos}")
    
    lista = str(codigos_brutos).split(",")
    for codigo in lista:
        nome = MAPA_REFEICOES.get(categoria, {}).get(codigo.strip().lower())
        if not nome: continue
        
        logger.info(f"   > Item: {nome}")
        try:
            # 1. Encontrar o elemento pelo Texto
            xpath = f"//span[contains(text(), '{nome}')]"
            
            # Rola o modal
            driver.execute_script("document.querySelectorAll('.modal-body').forEach(e => e.scrollTop = e.scrollHeight)")
            time.sleep(0.5)

            elem = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            
            # 2. Clicar no CARD (Pai)
            parent = elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'itemLista') or contains(@class, 'card')]")
            click_js(driver, parent)
            time.sleep(1.5) # Espera modal de confirmação
            
            # 3. Confirmar (HTML 1 que você mandou)
            try:
                btn_confirmar = WebDriverWait(driver, 3).until(EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'confirmar')]")
                ))
                click_js(driver, btn_confirmar)
            except:
                driver.execute_script("swal.clickConfirm()")
            
            time.sleep(1)
            
        except Exception as e:
            logger.warning(f"   ⚠️ Falha ao selecionar item '{nome}': {e}")

# ==============================================================================
# 🤖 ROBÔ V54 - ESTABILIDADE V46 + CORREÇÃO FAVORITOS
# ==============================================================================
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    matar_zumbis()
    logger.info("--- ⚡ Iniciando Robô V54 (Base V46 + Favoritos Corrigidos) ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,720")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    # AUMENTO CRÍTICO DE TIMEOUT PARA O RENDER
    driver.set_page_load_timeout(180)
    
    wait = WebDriverWait(driver, 25)
    link_app = "Não capturado"

    try:
        # 1. LOGIN
        driver.get("https://pt.webdiet.com.br/login/")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.find_element(By.ID, "senhaLogin").send_keys(senha + Keys.ENTER)
        
        # 2. CADASTRO
        logger.info(">> Abrindo formulário...")
        try:
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

        # 5. TRANSIÇÃO (HTML 3)
        time.sleep(2)
        driver.execute_script("if(typeof swal !== 'undefined') { swal.clickConfirm(); }")
        time.sleep(2)

        # 6. BUSCA POR TELEFONE
        logger.info(">> Buscando por Telefone...")
        try:
            driver.execute_script("swal.close(); $('.modal').modal('hide');")
            time.sleep(1)
            
            search_input = wait.until(EC.element_to_be_clickable((By.ID, "barraBuscaPaciente")))
            search_input.clear()
            search_input.send_keys(paciente['telefone'])
            time.sleep(1)
            search_input.send_keys(Keys.ENTER)
            
            linha_paciente = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".pacienteLinha")))
            click_js(driver, linha_paciente)
            
            wait.until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            logger.info("✅ Perfil carregado.")

        except Exception as e:
            raise Exception(f"Falha ao entrar no perfil: {e}")

        # 7. PLANEJAMENTO
        logger.info(">> Iniciando Fluxo de Dieta...")
        driver.execute_script("document.body.style.zoom='70%'")
        time.sleep(2)
        
        try:
            # HTML 4
            btn_add = driver.find_element(By.ID, "atalhoPlanejamento")
            click_js(driver, btn_add)
            time.sleep(3)
            
            # HTML 5 b1
            try:
                btn_avancar = driver.find_element(By.XPATH, "//div[contains(@class, 'botao') and contains(text(), 'avançar')]")
                click_js(driver, btn_avancar)
            except:
                driver.execute_script("swal.clickConfirm()") 
            time.sleep(3)
            
            # HTML 5 b2
            try:
                btn_criar = driver.find_element(By.ID, "criarPlanejamento")
                click_js(driver, btn_criar)
            except:
                driver.execute_script("swal.clickConfirm()") 
            
            time.sleep(5)
            
        except Exception as e:
            raise Exception(f"Erro na abertura da dieta: {e}")

        # 8. CAPTURA LINK
        try:
            link_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'paciente.me/')]")
            link_app = link_elem.text.strip()
            logger.info(f"✅ LINK: {link_app}")
        except: pass

        # 9. LIMPEZA DE HÁBITOS (Protegida)
        logger.info(">> Limpando hábitos...")
        try:
            inicio = time.time()
            for _ in range(5):
                if time.time() - inicio > 60: break # Trava de segurança
                
                lixeiras = driver.find_elements(By.CSS_SELECTOR, "i.fi-sr-trash")
                if not lixeiras: break
                
                click_js(driver, lixeiras[0])
                time.sleep(0.8)
                
                try:
                    # HTML 6
                    btn_remove = driver.find_element(By.XPATH, "//div[contains(@style, 'var(--vermelho)')]")
                    click_js(driver, btn_remove)
                except:
                    driver.execute_script("swal.clickConfirm()")
                
                time.sleep(1)
        except: pass

        # 10. FAVORITOS (CORRIGIDO COM HTML EXATO)
        logger.info(">> Inserindo favoritos...")
        driver.execute_script("window.scrollTo(0, 0);")
        driver.execute_script("document.body.click();") # Acorda o browser
        time.sleep(1)

        try:
            # HTML DO BOTÃO: <div class="botao botoesPrincipais col" onclick="verRefeicoesProntas('')">
            logger.info("   > Buscando botão 'Refeições Favoritas'...")
            
            # Seletor exato das classes e texto
            xpath_fav = "//div[contains(@class, 'botoesPrincipais') and contains(., 'refeições favoritas')]"
            btn_fav = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath_fav)))
            click_js(driver, btn_fav)
        except Exception as e:
            logger.warning(f"   ⚠️ Erro ao clicar no botão favoritos: {e}")
            # Tenta fallback via JS direto se falhar
            driver.execute_script("verRefeicoesProntas('')")

        logger.info("   > Aguardando lista...")
        time.sleep(4)
        
        selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
        selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
        
        logger.info("   > Fechando favoritos...")
        try: 
            # HTML 3
            btn_close = driver.find_element(By.CSS_SELECTOR, "button.close[data-dismiss='modal']")
            click_js(driver, btn_close)
        except: 
            driver.execute_script("document.querySelector('.modal-backdrop').click()")
        
        # 11. FINALIZAÇÃO
        logger.info(">> Finalizando...")
        try:
            driver.execute_script("document.getElementById('horarioRotinaTemp0').value = '08:00';")
            driver.execute_script("document.getElementById('horarioRotinaTemp1').value = '12:00';")
        except: pass
        
        time.sleep(1)
        try:
            btn_final = driver.find_element(By.XPATH, "//div[contains(@onclick, 'salvarPrescricao()')]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_final)
            time.sleep(1)
            click_js(driver, btn_final)
        except:
            btn_final_alt = driver.find_element(By.XPATH, "//div[contains(text(), 'salvar alterações')]")
            click_js(driver, btn_final_alt)
        
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
