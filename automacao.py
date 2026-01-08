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
    """Clica usando JS puro (Mais rápido e ignora sobreposições)"""
    driver.execute_script("arguments[0].click();", elemento)

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
            # Busca OTIMIZADA: Procura o span com o texto específico
            xpath_item = f"//span[contains(text(), '{nome_real}')]"
            
            # Wait curto: se não achar em 5s, pula (evita travar o robô)
            elem = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath_item)))
            
            # Scroll e Click imediato
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            click_js(driver, elem)
            
            # Espera botão confirmar (Timeout curto de 2s para ser ágil)
            try:
                btn_confirmar = WebDriverWait(driver, 2).until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']")
                ))
                click_js(driver, btn_confirmar)
                time.sleep(0.8) # Pequena pausa para o modal fechar
                logger.info(f"✅ Adicionado: {nome_real}")
            except TimeoutException:
                # Tenta clicar de novo se o modal não abriu na primeira
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

# --- ROBÔ PRINCIPAL OTIMIZADO ---
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    logger.info("--- ⚡ Iniciando Robô Otimizado ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # --- OTIMIZAÇÃO MASTER: DESATIVAR IMAGENS ---
    # Isso reduz o uso de memória em ~60% e acelera o carregamento
    chrome_options.add_argument("--blink-settings=imagesEnabled=false") 
    chrome_options.add_argument("--disable-extensions")
    chrome_options.page_load_strategy = 'eager' # Não espera carregar tudo para liberar o código

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20) # Wait padrão reduzido
    short_wait = WebDriverWait(driver, 2) # Wait para loops rápidos
    
    link_app_capturado = "Link não encontrado"

    try:
        driver.get("https://pt.webdiet.com.br/login/")
        
        # 1. LOGIN RÁPIDO
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.switch_to.active_element.send_keys(Keys.TAB)
        driver.switch_to.active_element.send_keys(senha + Keys.ENTER)
        
        # 2. CADASTRO
        logger.info(">> Novo Paciente...")
        # Usa CSS Selector (mais rápido que XPath)
        btn_novo = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[onclick*='novoPaciente']")))
        click_js(driver, btn_novo)
        
        time.sleep(1.5) # Tempo mínimo para modal abrir
        
        # Preenchimento
        wait.until(EC.visibility_of_element_located((By.ID, "nomeAtalho"))).send_keys(paciente["nome"])
        
        # Injeção JS direta para campos (Mais rápido que send_keys)
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
        except: pass # Se falhar JS, os campos já devem estar preenchidos ou vazios, seguimos.

        # Salvar
        btn_salvar = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_salvar)

        # Espera o modal fechar (StaleElement = Sucesso)
        time.sleep(2)
        
        # 3. CAPTURA LINK
        try:
            # Tenta fechar menu lateral se existir
            try:
                btn_menu = driver.find_element(By.CSS_SELECTOR, "div[onclick*='não registrar']")
                click_js(driver, btn_menu)
            except: pass

            el_link = wait.until(EC.visibility_of_element_located((By.ID, "linkRef")))
            link_app_capturado = el_link.text.strip()
            logger.info(f"✅ Link: {link_app_capturado}")
        except: pass

        # 4. PLANEJAMENTO
        if dados_clinicos:
            logger.info(">> Planejamento...")
            
            # Atalho Planejamento
            btn_add = wait.until(EC.element_to_be_clickable((By.ID, "atalhoPlanejamento")))
            click_js(driver, btn_add)
            time.sleep(1.5)

            # Confirmações iniciais (Avançar/Criar)
            try:
                # Tenta clicar em todos os botões de confirmação que aparecerem em sequência
                # Botão Avançar
                btn_av = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']")))
                click_js(driver, btn_av)
                time.sleep(1)
                
                # Botão Criar (ID criarPlanejamento)
                btn_criar = wait.until(EC.presence_of_element_located((By.ID, "criarPlanejamento")))
                click_js(driver, btn_criar)
            except: pass
            
            time.sleep(3) # Tempo para carregar a tela de planejamento

            # --- LIMPEZA TURBO (SEQUENCIAL) ---
            logger.info(">> Limpando...")
            # Tenta até 5 vezes. Se não achar lixeira em 2s, para (economiza tempo).
            for _ in range(5):
                try:
                    # Busca Ícone Lixeira
                    lixeira = short_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "i.fi-sr-trash")))
                    click_js(driver, lixeira)
                    
                    # Busca Confirmar Remoção
                    confirmar = short_wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']")))
                    click_js(driver, confirmar)
                    
                    time.sleep(1) # Espera sumir
                except TimeoutException:
                    break # Acabaram as lixeiras
                except: break

            # --- FAVORITOS ---
            logger.info(">> Favoritos...")
            try:
                driver.execute_script("window.scrollTo(0, 0);") # Garante topo da página
                
                # Botão Favoritos (busca por texto ou classe)
                btn_fav = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']")))
                click_js(driver, btn_fav)
                
                # Espera lista carregar (Importante)
                time.sleep(3)
                
                # Seleção
                selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
                selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
                
                # Fechar modal favoritos (Botão X ou backdrop)
                try:
                    driver.execute_script("document.querySelector('button.close[data-dismiss=\"modal\"]').click()")
                except:
                    driver.execute_script("document.querySelector('.modal-backdrop').click()")
                
            except Exception as e:
                logger.warning(f"Erro Favoritos: {e}")

            # Horários
            definir_horario(driver, "horarioRotinaTemp0", "08:00")
            definir_horario(driver, "horarioRotinaTemp1", "12:00")
            
            # --- SALVAR FINAL ---
            logger.info(">> Salvando Final...")
            time.sleep(1)
            try:
                # Busca e clica direto via JS
                btn_final = driver.find_element(By.CSS_SELECTOR, "div[onclick*='salvarPrescricao']")
                click_js(driver, btn_final)
                logger.info("✅ Salvo!")
                enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Sucesso")
            except Exception as e:
                logger.error(f"Erro ao salvar: {e}")
                enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Erro no Salvamento Final")

        else:
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Cadastro Básico Sucesso")

        return {"status": "sucesso", "link": link_app_capturado}

    except Exception as e:
        logger.error(f"❌ ERRO GERAL: {e}")
        # Tenta enviar webhook de erro
        enviar_webhook(paciente, dados_clinicos, link_app_capturado, f"Erro Fatal: {str(e)}")
        return {"status": "erro", "mensagem": str(e)}
    finally:
        # Garante que o Chrome feche para liberar memória
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
