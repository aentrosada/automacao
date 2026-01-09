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
# 📝 LOGS
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)
WEBHOOK_MAKE_URL = os.getenv("WEBHOOK_MAKE_URL")

# ==============================================================================
# 🛠️ FUNÇÕES AUXILIARES
# ==============================================================================
def ler_credenciais():
    email = os.getenv("LOGIN_WEBDIET")
    senha = os.getenv("SENHA_WEBDIET")
    if not email: return None, None
    return email, senha

def click_js(driver, elemento):
    try:
        driver.execute_script("arguments[0].click();", elemento)
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
        logger.error(f"Erro ao digitar em {id_elemento}: {e}")

def verificar_erro_formulario(driver):
    try:
        div_erro = driver.find_element(By.ID, "erroPacienteAtalho")
        if div_erro.is_displayed() and div_erro.text.strip():
            msg = div_erro.text.strip()
            logger.error(f"❌ O SITE RECUSOU O CADASTRO: '{msg}'")
            return msg
    except: pass
    return None

def encontrar_botao_planejamento(driver, wait):
    """Tenta encontrar o botão de planejamento por ID, Texto ou Classe"""
    seletores = [
        (By.ID, "atalhoPlanejamento"),
        (By.XPATH, "//div[contains(text(), 'adicionar') and contains(text(), 'planejamento')]"),
        (By.XPATH, "//div[contains(text(), 'planejamento')]"),
        (By.CSS_SELECTOR, ".cardMenuPaciente")
    ]
    
    for by, valor in seletores:
        try:
            btn = wait.until(EC.element_to_be_clickable((by, valor)))
            return btn
        except: continue
    return None

# CORREÇÃO DO WEBHOOK PARA ACEITAR 5 ARGUMENTOS
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

# --- MAPAS ---
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
            elem = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, f"//span[contains(text(), '{nome}')]")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            click_js(driver, elem)
            time.sleep(0.5)
            click_js(driver, driver.find_element(By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']"))
            time.sleep(0.5)
        except: pass

# ==============================================================================
# 🤖 ROBÔ PRINCIPAL (V23 - RESGATE PAI & FIX WEBHOOK)
# ==============================================================================
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    logger.info("--- ⚡ Iniciando Robô V23 (Resgate Estrutural) ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1366,768")
    
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 15)
    link_app = "Não gerado"

    try:
        # 1. LOGIN
        driver.get("https://pt.webdiet.com.br/login/")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.find_element(By.ID, "senhaLogin").send_keys(senha + Keys.ENTER)
        
        # 2. CADASTRO
        logger.info(">> Abrindo formulário...")
        try:
            WebDriverWait(driver, 30).until(EC.url_contains("painel"))
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
            click_js(driver, btn)
        except:
            raise Exception("Falha ao abrir modal de cadastro.")
        
        time.sleep(2)

        # 3. PREENCHIMENTO
        logger.info(f">> Digitando dados de: {paciente['nome']}")
        digitar_humano(driver, "nomeAtalho", paciente['nome'])
        try:
            sexo_letra = "M" if paciente['sexo'].lower().startswith('m') else "F"
            driver.find_element(By.ID, "generoAtalho").send_keys(sexo_letra)
        except: pass
        digitar_humano(driver, "nascimentoAtalho", "01011990")
        digitar_humano(driver, "telefoneAtalho", "11999999999")
        digitar_humano(driver, "emailAtalho", paciente['email'])

        # 4. SALVAR
        logger.info(">> Clicando em CADASTRAR...")
        btn_salvar = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_salvar)
        
        logger.info(">> Validando envio...")
        try:
            WebDriverWait(driver, 5).until(EC.invisibility_of_element_located((By.ID, "novoPacienteBtnAtalho")))
            logger.info("✅ Botão sumiu/mudou (Sucesso).")
        except StaleElementReferenceException:
            logger.info("✅ Botão ficou obsoleto (Sucesso).")
        except TimeoutException:
            msg_erro = verificar_erro_formulario(driver)
            if msg_erro: raise Exception(f"Erro no formulário: {msg_erro}")
            else: logger.warning("⚠️ Botão continua na tela. Tentando seguir...")

        # 5. TRANSIÇÃO (MODAL)
        logger.info(">> Aguardando Modal de Consulta (3s)...")
        time.sleep(3)
        
        try:
            xpath_modal = "//div[contains(text(), 'registrar nova consulta')]"
            btn_modal = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath_modal)))
            click_js(driver, btn_modal)
            logger.info("✅ Modal confirmado!")
        except:
            logger.warning("⚠️ Modal não clicado (tentando JS ou seguindo)...")
            driver.execute_script("swal.clickConfirm()")

        # 6. ENTRAR NO PLANEJAMENTO (COM RESGATE ESTRUTURAL)
        logger.info(">> Buscando Planejamento...")
        time.sleep(3)
        driver.execute_script("document.body.style.zoom='70%'")

        # Tenta achar o botão de várias formas
        btn_planejamento = encontrar_botao_planejamento(driver, WebDriverWait(driver, 5))
        
        if btn_planejamento:
            click_js(driver, btn_planejamento)
            logger.info("✅ Entrou no planejamento (Direto)!")
        else:
            logger.warning("⚠️ Iniciando RESGATE NOVO...")
            
            # --- RESGATE ESTRUTURAL ---
            try:
                try: driver.execute_script("swal.close()")
                except: pass
                
                # Procura o texto do nome
                logger.info(f"   > Procurando nome '{paciente['nome']}'...")
                xpath_text = f"//*[contains(text(), '{paciente['nome']}')]"
                
                # TENTA CLICAR NO ELEMENTO PAI (CONTAINER)
                # Muitas vezes o texto é só um span, o clique está na div/tr em volta
                xpath_pai = f"{xpath_text}/.."
                
                try:
                    elem_pai = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath_pai)))
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem_pai)
                    click_js(driver, elem_pai)
                    logger.info("✅ Resgate: Clicado no container do nome!")
                except:
                    # Se falhar o pai, clica no texto mesmo
                    elem_text = driver.find_element(By.XPATH, xpath_text)
                    click_js(driver, elem_text)
                    logger.info("✅ Resgate: Clicado no texto do nome.")

                logger.info("   > Aguardando 10s para carregamento...")
                time.sleep(10)
                
                # Verifica sucesso
                btn_resgate = encontrar_botao_planejamento(driver, WebDriverWait(driver, 20))
                if btn_resgate:
                    click_js(driver, btn_resgate)
                    logger.info("✅ Planejamento acessado via Resgate!")
                else:
                    # Refresh e tenta de novo
                    logger.warning("⚠️ Refreshing...")
                    driver.refresh()
                    time.sleep(5)
                    btn_final = encontrar_botao_planejamento(driver, WebDriverWait(driver, 20))
                    if btn_final:
                        click_js(driver, btn_final)
                        logger.info("✅ Acessado pós-refresh!")
                    else:
                        raise Exception("Falha: Botão de planejamento inalcançável.")

            except Exception as e:
                logger.error(f"❌ URL FINAL: {driver.current_url}")
                raise Exception(f"Falha no acesso ao paciente: {e}")

        # 7. EXECUÇÃO DA DIETA
        time.sleep(3)
        try:
            el_link = driver.find_element(By.ID, "linkRef")
            link_app = el_link.text.strip()
            logger.info(f"✅ Link: {link_app}")
        except: pass

        try:
            click_js(driver, WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'avançar')]"))))
            time.sleep(1)
            click_js(driver, driver.find_element(By.ID, "criarPlanejamento"))
        except: pass
        
        time.sleep(3)

        # Limpeza
        try:
            for _ in range(10):
                lixeira = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "i.fi-sr-trash")))
                click_js(driver, lixeira)
                time.sleep(0.3)
                driver.execute_script("swal.clickConfirm()")
                time.sleep(0.5)
        except: pass

        # Favoritos
        driver.execute_script("window.scrollTo(0, 0);")
        click_js(driver, WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']"))))
        time.sleep(3)
        
        selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
        selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
        
        try: driver.execute_script("document.querySelector('button.close[data-dismiss=\"modal\"]').click()")
        except: driver.execute_script("document.querySelector('.modal-backdrop').click()")
        
        # Horários e Salvar
        try:
            driver.execute_script("document.getElementById('horarioRotinaTemp0').value = '08:00';")
            driver.execute_script("document.getElementById('horarioRotinaTemp1').value = '12:00';")
        except: pass
        
        logger.info(">> Salvando final...")
        time.sleep(1)
        click_js(driver, driver.find_element(By.CSS_SELECTOR, "div[onclick*='salvarPrescricao']"))
        
        logger.info("✅ SUCESSO TOTAL!")
        enviar_webhook(paciente, dados_clinicos, link_app, "Sucesso Total")
        return {"status": "sucesso", "link": link_app}

    except Exception as e:
        logger.error(f"❌ ERRO: {e}")
        enviar_webhook(paciente, dados_clinicos, link_app, "Erro", str(e))
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
    return {"mensagem": "Processando...", "paciente": pedido.paciente.nome}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
