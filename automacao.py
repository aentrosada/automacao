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
        logger.error(f"Erro ao ler arquivo de credenciais: {e}")
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
        logger.info(f"Tentando definir horário {horario} para {element_id}")
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
    logger.info(f">> Processando categoria: {categoria} com códigos: {codigos_brutos}")
    lista_codigos = str(codigos_brutos).split(",")
    
    for codigo in lista_codigos:
        codigo_limpo = codigo.strip().lower()
        nome_real = MAPA_REFEICOES.get(categoria, {}).get(codigo_limpo)
        
        if not nome_real: continue
            
        try:
            logger.info(f"Procurando item: {nome_real}")
            xpath_item = f"//div[contains(text(), '{nome_real}')] | //span[contains(text(), '{nome_real}')] | //label[contains(text(), '{nome_real}')]"
            elem = driver.find_element(By.XPATH, xpath_item)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(0.5)
            click_js(driver, elem)
            
            time.sleep(1) 
            # Confirma seleção (Popup do SweetAlert)
            try:
                btn_confirmar = WebDriverWait(driver, 3).until(EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'confirmar')]")
                ))
                click_js(driver, btn_confirmar)
                time.sleep(1) 
            except: pass 
            
        except Exception as e:
            logger.error(f"Erro ao selecionar item {nome_real}: {e}")

def enviar_webhook(paciente_dados, dados_clinicos, link_app, status_msg):
    logger.info(f"\n📡 TENTANDO ENVIAR WEBHOOK: {status_msg}")
    if not WEBHOOK_MAKE_URL: 
        logger.warning("URL do Webhook não definida.")
        return
    payload = {"status": status_msg, "link_app": link_app, "paciente": paciente_dados, "dados_clinicos": dados_clinicos}
    try: 
        requests.post(WEBHOOK_MAKE_URL, json=payload)
        logger.info("Webhook enviado com sucesso.")
    except Exception as e: 
        logger.error(f"Erro ao enviar webhook: {e}")

# --- ROBÔ PRINCIPAL ---
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    logger.info("--- 🔧 Configurando Chrome Ultra-Leve ---")
    chrome_options = Options()
    
    # Configurações para Render
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions") 
    chrome_options.add_argument("--window-size=1920,1080") 

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 30)
    
    link_app_capturado = "Link não encontrado"

    try:
        logger.info(f"--- 🚀 Iniciando fluxo para: {paciente.get('nome', 'Sem Nome')} ---")
        driver.get("https://pt.webdiet.com.br/login/")
        
        # 1. LOGIN
        logger.info("Preenchendo login...")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.switch_to.active_element.send_keys(Keys.TAB)
        driver.switch_to.active_element.send_keys(senha + Keys.ENTER)
        
        # 2. CADASTRO
        time.sleep(3)
        logger.info(">> Navegando para Novo Paciente...")
        btn_novo_paciente = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
        click_js(driver, btn_novo_paciente)
        
        time.sleep(2)
        logger.info("Preenchendo formulário básico...")
        
        # Nome
        wait.until(EC.visibility_of_element_located((By.ID, "nomeAtalho"))).send_keys(paciente["nome"])
        
        # Gênero
        try:
            sexo_formatado = paciente['sexo'].upper()[0]
            genero_select = driver.find_element(By.ID, "generoAtalho")
            driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change'));", genero_select, sexo_formatado)
        except Exception as e: logger.warning(f"Aviso Gênero: {e}")

        # Data Nascimento
        try:
            campo_nasc = driver.find_element(By.ID, "nascimentoAtalho")
            driver.execute_script("arguments[0].value = '01/01/2000';", campo_nasc)
        except Exception as e: logger.warning(f"Aviso Data: {e}")

        # Contatos
        driver.find_element(By.ID, "emailAtalho").send_keys(paciente["email"])
        driver.find_element(By.ID, "telefoneAtalho").send_keys(paciente["telefone"])
        
        # Salvar e Verificar Erro
        logger.info("Clicando em Salvar...")
        btn_salvar = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        driver.execute_script("arguments[0].click();", btn_salvar)

        time.sleep(3)
        
        # --- VERIFICAÇÃO DE SUCESSO (CORREÇÃO AQUI) ---
        try:
            # Se tentar acessar o botão e der 'StaleElementReferenceException', é SUCESSO (botão morreu, modal fechou)
            if btn_salvar.is_displayed():
                 # Se o botão ainda existe E está visível, algo deu errado
                 try:
                    erro_msg = driver.find_element(By.CSS_SELECTOR, ".toast-message").text
                    raise Exception(f"Site recusou cadastro: {erro_msg}")
                 except NoSuchElementException:
                    # Botão está lá mas sem mensagem? Pode ser lag, vamos tentar seguir
                    logger.warning("Modal parece aberto, mas sem erro. Tentando seguir...")
        except StaleElementReferenceException:
            logger.info("✅ Botão salvar desapareceu (Sucesso!), modal fechou.")
        except NoSuchElementException:
            logger.info("✅ Botão salvar não encontrado (Sucesso!), modal fechou.")
        # -----------------------------------------------

        # 3. CAPTURA LINK
        time.sleep(3)
        try:
            # Tenta fechar menu lateral se aparecer
            try:
                btn_abrir_menu = driver.find_element(By.XPATH, "//div[contains(text(), 'não registrar e abrir menu')]")
                click_js(driver, btn_abrir_menu)
                time.sleep(2)
            except: pass

            elemento_link = wait.until(EC.visibility_of_element_located((By.ID, "linkRef")))
            link_app_capturado = elemento_link.text.strip()
            logger.info(f"✅ LINK CAPTURADO: {link_app_capturado}")
        except:
            logger.info("Link não apareceu de imediato.")

        # 4. PLANEJAMENTO ALIMENTAR
        if dados_clinicos and (dados_clinicos.get("cafe") or dados_clinicos.get("almoco")):
            logger.info(">> Iniciando Fluxo de Planejamento...")
            
            # Clica no botão de atalho
            btn_add_planejamento = wait.until(EC.element_to_be_clickable((By.ID, "atalhoPlanejamento")))
            click_js(driver, btn_add_planejamento)
            time.sleep(2)

            # Avançar (SweetAlert)
            try:
                btn_avancar = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'avançar')]")))
                click_js(driver, btn_avancar)
                time.sleep(2)
            except: pass

            # Criar Planejamento
            btn_confirmar = wait.until(EC.presence_of_element_located((By.ID, "criarPlanejamento")))
            click_js(driver, btn_confirmar)
            time.sleep(5) 

            # Limpeza dos itens padrão
            logger.info(">> Limpando hábitos padrão...")
            for i in range(1, 4):
                try:
                    btn_lixeira = driver.find_elements(By.XPATH, "//div[contains(@onclick, 'excluir(0)')]")
                    if btn_lixeira:
                        click_js(driver, btn_lixeira[0])
                        time.sleep(1)
                        btn_remover_habito = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'remover hábito')]")))
                        click_js(driver, btn_remover_habito)
                        time.sleep(2)
                except: pass 

            # ABRIR FAVORITOS
            logger.info(">> Abrindo Favoritos/Refeições Prontas...")
            try:
                btn_favoritas = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(@onclick, \"verRefeicoesProntas('')\")]")
                ))
                click_js(driver, btn_favoritas)
                time.sleep(3) 
            except Exception as e:
                logger.warning(f"Não consegui clicar em favoritos: {e}")

            # Seleção dos itens
            selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
            selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
            
            # Horários
            logger.info(">> Ajustando horários...")
            definir_horario(driver, "horarioRotinaTemp0", "08:00")
            definir_horario(driver, "horarioRotinaTemp1", "12:00")
            
            # Salvar Final
            logger.info(">> Salvando Prescrição...")
            try:
                btn_fechar_modal = driver.find_element(By.XPATH, "//button[@class='close' and @data-dismiss='modal']")
                click_js(driver, btn_fechar_modal)
            except: pass
            
            time.sleep(1)
            btn_salvar_final = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@onclick, 'salvarPrescricao()')]")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_salvar_final)
            click_js(driver, btn_salvar_final)
            logger.info("✅ Planejamento Salvo!")
            
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Cadastro + Planejamento Finalizado")
        else:
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Cadastro Realizado (Sem Planejamento)")

        return {"status": "sucesso", "link": link_app_capturado}

    except Exception as e:
        logger.error("❌ ERRO FATAL NA AUTOMAÇÃO!")
        logger.error(traceback.format_exc())
        
        enviar_webhook(paciente, dados_clinicos, link_app_capturado, f"Erro Fatal: {str(e)}")
        return {"status": "erro", "mensagem": str(e)}
    finally:
        try: driver.quit()
        except: pass

# ==============================================================================
# 🚀 API UNIFICADA
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
