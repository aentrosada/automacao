import os
import logging
import traceback
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
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
# 🛠️ FUNÇÕES DE LIMPEZA E AUXILIARES
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
            time.sleep(0.01)
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
    seletores = [
        (By.ID, "atalhoPlanejamento"),
        (By.XPATH, "//div[contains(text(), 'adicionar') and contains(text(), 'planejamento')]"),
        (By.XPATH, "//div[contains(text(), 'planejamento')]")
    ]
    for by, valor in seletores:
        try: return wait.until(EC.element_to_be_clickable((by, valor)))
        except: continue
    return None

def enviar_webhook(msg, status, link=None):
    if not WEBHOOK_MAKE_URL: return
    try: requests.post(WEBHOOK_MAKE_URL, json={"msg": msg, "status": status, "link": link}, timeout=5)
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
# 🤖 ROBÔ PRINCIPAL (V32 - MODAL INSISTENTE)
# ==============================================================================
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    matar_zumbis()
    logger.info("--- ⚡ Iniciando Robô V32 (Foco no Modal) ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,720")
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(60)
    wait = WebDriverWait(driver, 20)
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
            raise Exception("Falha ao abrir modal. O servidor pode estar lento.")
        
        time.sleep(2)

        # 3. PREENCHIMENTO
        logger.info(f">> Digitando: {paciente['nome']}")
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
        
        try:
            WebDriverWait(driver, 8).until(EC.invisibility_of_element_located((By.ID, "novoPacienteBtnAtalho")))
            logger.info("✅ Cadastro enviado.")
        except:
            msg = verificar_erro_formulario(driver)
            if msg: raise Exception(f"Erro no formulário: {msg}")
            logger.warning("⚠️ Botão persistiu.")

        # 5. TRANSIÇÃO (MODAL DE NOVA CONSULTA)
        logger.info(">> Aguardando Modal 'Registrar Nova Consulta'...")
        
        url_antes = driver.current_url
        redirecionou = False
        
        try:
            # Espera o texto aparecer para garantir que o modal carregou
            WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'registrar nova consulta')]")))
            
            # TENTA CLICAR VIA JS (Mais garantido que clicar no elemento)
            logger.info(">> Modal detectado. Executando swal.clickConfirm()...")
            driver.execute_script("swal.clickConfirm()")
            
            # Monitora mudança de URL
            for i in range(15):
                time.sleep(1)
                if driver.current_url != url_antes:
                    logger.info("✅ URL Mudou! Redirecionamento funcionou.")
                    redirecionou = True
                    break
            
            # Se não mudou, tenta clicar no elemento físico
            if not redirecionou:
                logger.warning("⚠️ URL não mudou. Tentando clicar no botão físico...")
                btn_modal = driver.find_element(By.XPATH, "//div[contains(text(), 'registrar nova consulta')]")
                click_js(driver, btn_modal)
                time.sleep(5)

        except TimeoutException:
            logger.warning("⚠️ Modal não apareceu a tempo (ou site já redirecionou).")

        # 6. ENTRAR NO PLANEJAMENTO
        logger.info(">> Buscando Planejamento...")
        driver.execute_script("document.body.style.zoom='70%'")

        # Verifica se estamos na tela certa
        btn_planejamento = encontrar_botao_planejamento(driver, WebDriverWait(driver, 5))
        
        if btn_planejamento:
            click_js(driver, btn_planejamento)
            logger.info("✅ Entrou no planejamento (Direto)!")
        else:
            # ==================================================================
            # 🚨 RESGATE SEM REFRESH (CLIQUE NO NOME NA LISTA)
            # ==================================================================
            logger.warning("⚠️ Ainda no Painel. Clicando no PRIMEIRO paciente da lista...")
            try:
                # Garante que modal fechou
                try: driver.execute_script("swal.close()")
                except: pass
                
                # Clica no texto do nome
                xpath_nome = f"//*[contains(text(), '{paciente['nome']}')]"
                elem_nome = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.XPATH, xpath_nome)))
                
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem_nome)
                click_js(driver, elem_nome)
                
                logger.info("✅ Clique de resgate enviado.")
                time.sleep(8) # Espera carregar perfil
                
                btn_final = encontrar_botao_planejamento(driver, WebDriverWait(driver, 15))
                if btn_final:
                    click_js(driver, btn_final)
                    logger.info("✅ Planejamento acessado!")
                else:
                    raise Exception("Não entrou no perfil (Botão de planejamento não achado).")

            except Exception as e:
                raise Exception(f"Falha crítica no resgate: {e}")

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
        logger.info(">> Limpando...")
        try:
            for _ in range(10):
                lixeira = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "i.fi-sr-trash")))
                click_js(driver, lixeira)
                time.sleep(0.3)
                driver.execute_script("swal.clickConfirm()")
                time.sleep(0.5)
        except: pass

        # Favoritos
        logger.info(">> Inserindo...")
        driver.execute_script("window.scrollTo(0, 0);")
        click_js(driver, WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']"))))
        time.sleep(3)
        
        selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
        selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
        
        try: driver.execute_script("document.querySelector('button.close[data-dismiss=\"modal\"]').click()")
        except: driver.execute_script("document.querySelector('.modal-backdrop').click()")
        
        # Salvar
        logger.info(">> Salvando final...")
        try:
            driver.execute_script("document.getElementById('horarioRotinaTemp0').value = '08:00';")
            driver.execute_script("document.getElementById('horarioRotinaTemp1').value = '12:00';")
        except: pass
        
        time.sleep(1)
        click_js(driver, driver.find_element(By.CSS_SELECTOR, "div[onclick*='salvarPrescricao']"))
        
        logger.info("✅ SUCESSO TOTAL!")
        enviar_webhook("Sucesso Total", "Concluido", link_app)
        return {"status": "sucesso", "link": link_app}

    except Exception as e:
        logger.error(f"❌ ERRO: {e}")
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
    if os.system("pgrep chrome > /dev/null") == 0:
        matar_zumbis()
    
    usuario, senha = ler_credenciais()
    background_tasks.add_task(executar_cadastro, usuario, senha, pedido.paciente.dict(), pedido.dados_clinicos)
    return {"mensagem": "Processando...", "paciente": pedido.paciente.nome}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
