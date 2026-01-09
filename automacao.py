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
    driver.execute_script("arguments[0].click();", elemento)

def digitar_humano(driver, id_elemento, texto):
    """Clica, limpa e digita caractere por caractere para ativar máscaras"""
    try:
        elem = driver.find_element(By.ID, id_elemento)
        elem.click()
        elem.clear()
        # Digita devagar para a máscara pegar
        for char in texto:
            elem.send_keys(char)
            time.sleep(0.05) # Pequeno delay humano
        elem.send_keys(Keys.TAB) # Sai do campo para validar
    except Exception as e:
        logger.error(f"Erro ao digitar em {id_elemento}: {e}")

def verificar_erro_formulario(driver):
    """Verifica se apareceu o erro específico que você mandou"""
    try:
        # Procura a div de erro
        div_erro = driver.find_element(By.ID, "erroPacienteAtalho")
        
        # Se ela estiver visível e tiver texto, é falha
        if div_erro.is_displayed() and div_erro.text.strip():
            msg = div_erro.text.strip()
            logger.error(f"❌ O SITE RECUSOU O CADASTRO: '{msg}'")
            return msg
    except NoSuchElementException:
        pass # Se não achar a div, ótimo
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
# 🤖 ROBÔ PRINCIPAL (V20 - DIGITAÇÃO HUMANA)
# ==============================================================================
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    logger.info("--- ⚡ Iniciando Robô V20 (Correção de Validação) ---")
    
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
        
        # 2. ABRIR NOVO PACIENTE
        logger.info(">> Abrindo formulário...")
        try:
            WebDriverWait(driver, 20).until(EC.url_contains("painel"))
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
            click_js(driver, btn)
        except:
            raise Exception("Falha ao abrir modal de cadastro.")
        
        time.sleep(2) # Espera modal abrir

        # 3. PREENCHIMENTO HUMANO (DIGITAÇÃO)
        logger.info(f">> Digitando dados de: {paciente['nome']}")
        
        # Nome
        digitar_humano(driver, "nomeAtalho", paciente['nome'])
        
        # Gênero (Select é chato, usa send_keys para selecionar pela primeira letra)
        try:
            sexo_letra = "M" if paciente['sexo'].lower().startswith('m') else "F"
            sel_sexo = driver.find_element(By.ID, "generoAtalho")
            sel_sexo.send_keys(sexo_letra)
        except: pass

        # Data de Nascimento (O PONTO CRÍTICO)
        # Digita apenas os números, a máscara do site deve colocar as barras
        # Se nascer em 01/01/1990, digita 01011990
        logger.info(">> Digitando Data de Nascimento...")
        digitar_humano(driver, "nascimentoAtalho", "01011990")
        
        # Telefone (Apenas números)
        digitar_humano(driver, "telefoneAtalho", "11999999999")
        
        # Email
        digitar_humano(driver, "emailAtalho", paciente['email'])

        # 4. TENTATIVA DE SALVAR COM VERIFICAÇÃO DE ERRO
        logger.info(">> Clicando em CADASTRAR...")
        btn_salvar = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_salvar)
        
        time.sleep(2) # Tempo para o site validar

        # --- VERIFICAÇÃO DE ERRO ---
        msg_erro = verificar_erro_formulario(driver)
        if msg_erro:
            # Se achou erro, tenta corrigir ou aborta
            raise Exception(f"Erro no formulário detectado: {msg_erro}")

        # Se o botão de salvar ainda estiver lá e visível, algo deu errado
        if btn_salvar.is_displayed():
            # Tenta verificar erro de novo
            msg_erro = verificar_erro_formulario(driver)
            if msg_erro: raise Exception(f"Erro: {msg_erro}")
            # Se não tem msg de erro mas o botão continua, pode ser timeout
            logger.warning("⚠️ Botão de salvar continua na tela, mas sem mensagem de erro visível. Continuando...")

        # 5. TRANSIÇÃO (MODAL DE CONSULTA)
        logger.info(">> Aguardando Modal de Consulta (3s)...")
        time.sleep(3)
        
        try:
            # Procura e clica no botão do modal
            xpath_modal = "//div[contains(text(), 'registrar nova consulta')]"
            btn_modal = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath_modal)))
            click_js(driver, btn_modal)
            logger.info("✅ Modal confirmado!")
        except:
            # Se falhar, tenta JS direto
            logger.warning("⚠️ Modal não clicado (tentando JS ou seguindo)...")
            driver.execute_script("swal.clickConfirm()")

        # 6. ENTRAR NO PLANEJAMENTO (COM RESGATE)
        logger.info(">> Buscando Planejamento...")
        time.sleep(3)
        driver.execute_script("document.body.style.zoom='70%'") # Zoom out para ver tudo

        try:
            btn_add = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            click_js(driver, btn_add)
            logger.info("✅ Entrou no planejamento!")
        except:
            logger.warning("⚠️ Iniciando RESGATE pelo nome...")
            # Resgate
            try:
                try: driver.execute_script("swal.close()")
                except: pass
                
                xpath_nome = f"//*[contains(text(), '{paciente['nome']}')]"
                elem_nome = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath_nome)))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem_nome)
                click_js(driver, elem_nome)
                logger.info("✅ Resgate clicado.")
                
                time.sleep(4)
                btn_add = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
                click_js(driver, btn_add)
                logger.info("✅ Planejamento acessado!")
            except Exception as e:
                raise Exception(f"Falha no cadastro/redirecionamento. Verifique se o paciente foi criado. Erro: {e}")

        # 7. EXECUÇÃO DA DIETA
        time.sleep(2)
        try:
            el_link = driver.find_element(By.ID, "linkRef")
            link_app = el_link.text.strip()
            logger.info(f"✅ Link: {link_app}")
        except: pass

        # Confirmações iniciais
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
        # Verifica erro de formulário uma última vez
        try:
            erro_final = verificar_erro_formulario(driver)
            if erro_final: logger.error(f"ERRO VISÍVEL NA TELA: {erro_final}")
        except: pass
        
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
