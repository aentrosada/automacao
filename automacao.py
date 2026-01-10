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
            
            # Confirmação genérica
            driver.execute_script("swal.clickConfirm()")
            time.sleep(0.5)
        except: pass

# ==============================================================================
# 🤖 ROBÔ V46 - ADAPTAÇÃO TOTAL AOS NOVOS ELEMENTOS
# ==============================================================================
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    matar_zumbis()
    logger.info("--- ⚡ Iniciando Robô V46 (Elementos Atualizados) ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,720")
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(120)
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

        # 5. MODAL "NOVA CONSULTA" (Limpeza via JS direto)
        # Elemento 3: registrar nova consulta
        logger.info(">> Limpando modal de transição...")
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
            
            logger.info("   > Clicando no paciente...")
            linha_paciente = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".pacienteLinha")))
            click_js(driver, linha_paciente)
            
            logger.info("   > Aguardando perfil...")
            wait.until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            logger.info("✅ Perfil carregado.")

        except Exception as e:
            raise Exception(f"Falha ao entrar no perfil: {e}")

        # 7. PLANEJAMENTO (Elemento 4)
        logger.info(">> Iniciando Fluxo de Dieta...")
        driver.execute_script("document.body.style.zoom='70%'")
        time.sleep(2)
        
        try:
            # Elemento 4: atalhoPlanejamento
            btn_add = driver.find_element(By.ID, "atalhoPlanejamento")
            click_js(driver, btn_add)
            logger.info("   > Clicado em 'Adicionar Planejamento'")
            time.sleep(3)
            
            # Elemento 5 b1: Avançar
            logger.info("   > Avançar...")
            try:
                # Tenta achar botão com classe 'botao' e texto 'avançar'
                btn_avancar = driver.find_element(By.XPATH, "//div[contains(@class, 'botao') and contains(text(), 'avançar')]")
                click_js(driver, btn_avancar)
            except:
                driver.execute_script("swal.clickConfirm()") # Fallback
            time.sleep(3)
            
            # Elemento 5 b2: Confirmar (Criar)
            logger.info("   > Confirmar (Criar)...")
            try:
                # ID criarPlanejamento
                btn_criar = driver.find_element(By.ID, "criarPlanejamento")
                click_js(driver, btn_criar)
            except:
                driver.execute_script("swal.clickConfirm()") # Fallback
            
            # Aguarda tela de edição carregar
            time.sleep(5)
            
        except Exception as e:
            raise Exception(f"Erro na abertura da dieta: {e}")

        # 8. CAPTURA LINK (Elemento 13 na lógica antiga)
        try:
            link_elem = driver.find_element(By.XPATH, "//*[contains(text(), 'paciente.me/')]")
            link_app = link_elem.text.strip()
            logger.info(f"✅ LINK: {link_app}")
        except: pass

        # 9. LIMPEZA DE HÁBITOS (Elemento 6)
        logger.info(">> Limpando hábitos...")
        try:
            # Procura ícone lixeira (fi-sr-trash) dentro de onclick excluir(0) ou similar
            # Usando seletor mais genérico para garantir: qualquer i com a classe trash
            lixeiras = driver.find_elements(By.CSS_SELECTOR, "i.fi-sr-trash")
            
            # Limita a 5 tentativas de limpeza para não ficar loop infinito
            for _ in range(5):
                lixeiras = driver.find_elements(By.CSS_SELECTOR, "i.fi-sr-trash")
                if not lixeiras: break
                
                # Clica na primeira lixeira visível
                click_js(driver, lixeiras[0])
                time.sleep(0.5)
                
                # Confirma no botão vermelho (Elemento 6 confirmação)
                # Procura botão vermelho ou usa swal.clickConfirm()
                try:
                    btn_remove = driver.find_element(By.XPATH, "//div[contains(@style, 'var(--vermelho)')]")
                    click_js(driver, btn_remove)
                except:
                    driver.execute_script("swal.clickConfirm()")
                
                time.sleep(0.5)
        except Exception as e: 
            logger.warning(f"Erro menor na limpeza: {e}")

        # 10. FAVORITOS
        logger.info(">> Inserindo favoritos...")
        driver.execute_script("window.scrollTo(0, 0);")
        click_js(driver, WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']"))))
        time.sleep(3)
        
        selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
        selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
        
        try: driver.execute_script("document.querySelector('button.close[data-dismiss=\"modal\"]').click()")
        except: driver.execute_script("document.querySelector('.modal-backdrop').click()")
        
        # 11. FINALIZAÇÃO (Elemento 7)
        logger.info(">> Finalizando...")
        try:
            driver.execute_script("document.getElementById('horarioRotinaTemp0').value = '08:00';")
            driver.execute_script("document.getElementById('horarioRotinaTemp1').value = '12:00';")
        except: pass
        
        time.sleep(1)
        # Elemento 7: salvarPrescricao()
        try:
            btn_final = driver.find_element(By.XPATH, "//div[contains(@onclick, 'salvarPrescricao()')]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_final)
            time.sleep(1)
            click_js(driver, btn_final)
        except:
            # Fallback classe botao e texto salvar
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
