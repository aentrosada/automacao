import os
import logging
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
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
    handlers=[
        logging.StreamHandler()
    ]
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
        }} else {{
            console.error('Elemento {element_id} não encontrado no JS');
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
        
        if not nome_real: 
            logger.warning(f"Código {codigo_limpo} não encontrado no mapa.")
            continue
            
        try:
            logger.info(f"Procurando item: {nome_real}")
            xpath_item = f"//div[contains(text(), '{nome_real}')] | //span[contains(text(), '{nome_real}')] | //label[contains(text(), '{nome_real}')]"
            elem = driver.find_element(By.XPATH, xpath_item)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(0.5)
            click_js(driver, elem)
            logger.info(f"Clicado em: {nome_real}")
            
            time.sleep(1) 
            logger.info("Aguardando botão confirmar seleção...")
            btn_confirmar = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'confirmar')]")
            ))
            click_js(driver, btn_confirmar)
            time.sleep(1.5) 
        except Exception as e:
            logger.error(f"Erro ao selecionar item {nome_real}: {e}")

def preencher_antropometria(driver, dados):
    logger.info(">> Tentando preencher dados antropométricos...")
    campos_para_preencher = ["idade", "altura", "peso", "cintura", "pescoco", "quadril"]
    for campo in campos_para_preencher:
        valor = dados.get(campo)
        if valor and str(valor).strip() != "" and str(valor) != "0":
            try:
                # Procura elemento, se não achar segue o fluxo sem quebrar
                input_elem = driver.find_element(By.ID, campo)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_elem)
                input_elem.clear()
                input_elem.send_keys(str(valor))
                logger.info(f"   > Preenchido {campo}: {valor}")
                time.sleep(0.5)
            except Exception as e:
                # Apenas loga warning, pois pode ser que a página não carregou esses campos ainda
                logger.warning(f"Não foi possível preencher {campo} (pode não existir nesta tela): {e}")

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

# --- ROBÔ PRINCIPAL (OTIMIZADO PARA MEMÓRIA) ---
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    logger.info("--- 🔧 Configurando Chrome Ultra-Leve ---")
    chrome_options = Options()
    
    # --- CONFIGURAÇÕES ANTI-ESTOURO DE MEMÓRIA ---
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions") 
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--window-size=1280,720") 
    # --------------------------------------------

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 30)
    
    link_app_capturado = "Link não encontrado"

    try:
        logger.info(f"--- 🚀 Iniciando fluxo para: {paciente.get('nome', 'Sem Nome')} ---")
        driver.get("https://pt.webdiet.com.br/login/")
        
        # Login
        logger.info("Preenchendo login...")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.switch_to.active_element.send_keys(Keys.TAB)
        driver.switch_to.active_element.send_keys(senha + Keys.ENTER)
        
        # Cadastro
        time.sleep(3)
        logger.info(">> Navegando para Novo Paciente...")
        btn_novo_paciente = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
        click_js(driver, btn_novo_paciente)
        
        time.sleep(2)
        logger.info("Preenchendo formulário básico do Modal...")
        
        # 1. NOME
        logger.info("Preenchendo Nome...")
        wait.until(EC.visibility_of_element_located((By.ID, "nomeAtalho"))).send_keys(paciente["nome"])
        
        # 2. GÊNERO - CORREÇÃO CRÍTICA AQUI
        # Usa injeção de JS para burlar o erro "element not interactable"
        try:
            logger.info("Definindo Gênero via JS...")
            sexo_formatado = paciente['sexo'].upper()[0] # Pega 'M' ou 'F'
            genero_select = driver.find_element(By.ID, "generoAtalho")
            
            driver.execute_script("""
                var select = arguments[0];
                select.value = arguments[1];
                select.dispatchEvent(new Event('change'));
            """, genero_select, sexo_formatado)
            
            logger.info(f"✅ Gênero '{sexo_formatado}' definido com sucesso.")
        except Exception as e:
            logger.error(f"❌ Erro ao definir gênero: {e}")
            raise e # Se falhar o gênero, melhor parar ou o cadastro falha

        # 3. EMAIl e TELEFONE
        logger.info("Preenchendo Contatos...")
        driver.find_element(By.ID, "emailAtalho").send_keys(paciente["email"])
        driver.find_element(By.ID, "telefoneAtalho").send_keys(paciente["telefone"])
        
        time.sleep(1)
        
        # 4. SALVAR DO MODAL
        logger.info("Clicando em Salvar Paciente (Modal)...")
        btn_salvar_modal = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_salvar_modal)

        # Dados Clínicos (Só tenta preencher se saiu do modal e carregou a pág do paciente)
        time.sleep(5) 
        if dados_clinicos: 
            preencher_antropometria(driver, dados_clinicos)

        # Captura Link
        try:
            logger.info(">> Tentando fechar menu lateral se existir...")
            btn_abrir_menu = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'não registrar e abrir menu')]")))
            click_js(driver, btn_abrir_menu)
            time.sleep(3)
        except: 
            logger.info("Botão de fechar menu não apareceu, seguindo...")

        try:
            logger.info(">> Buscando Link do App...")
            elemento_link = wait.until(EC.visibility_of_element_located((By.ID, "linkRef")))
            link_app_capturado = elemento_link.text.strip()
            logger.info(f"✅ LINK CAPTURADO: {link_app_capturado}")
        except Exception as e:
            logger.warning(f"Não consegui capturar o link: {e}")

        # Planejamento Alimentar
        if dados_clinicos and (dados_clinicos.get("cafe") or dados_clinicos.get("almoco")):
            logger.info(">> Iniciando Fluxo de Planejamento Alimentar...")
            
            logger.info("Clicando em atalhoPlanejamento...")
            btn_add_planejamento = wait.until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            click_js(driver, btn_add_planejamento)
            time.sleep(2)

            logger.info("Confirmando 'avançar'...")
            btn_avancar = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'avançar')]")))
            click_js(driver, btn_avancar)
            time.sleep(2)

            logger.info("Confirmando criação do planejamento...")
            btn_confirmar = wait.until(EC.presence_of_element_located((By.ID, "criarPlanejamento")))
            click_js(driver, btn_confirmar)
            time.sleep(5) 

            # Limpeza
            logger.info(">> Limpando hábitos padrão...")
            for i in range(1, 4):
                try:
                    btn_lixeira = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'excluir(0)')]")))
                    click_js(driver, btn_lixeira)
                    time.sleep(1)
                    btn_remover_habito = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'remover hábito')]")))
                    click_js(driver, btn_remover_habito)
                    time.sleep(2)
                except: pass 

            # Seleção
            selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
            selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))
            
            # Horários
            logger.info(">> Ajustando horários...")
            time.sleep(1)
            definir_horario(driver, "horarioRotinaTemp0", "08:00")
            definir_horario(driver, "horarioRotinaTemp1", "08:00")
            time.sleep(1)

            # Salvar
            logger.info(">> Tentando salvar final...")
            try:
                btn_fechar_modal = wait.until(EC.presence_of_element_located((By.XPATH, "//button[@class='close' and @data-dismiss='modal']")))
                click_js(driver, btn_fechar_modal)
            except: pass
            
            time.sleep(2)
            btn_salvar_final = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, 'salvarPrescricao()')]")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_salvar_final)
            time.sleep(1)
            click_js(driver, btn_salvar_final)
            logger.info("✅ Planejamento Salvo!")
            
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Finalizado com Sucesso")

        return {"status": "sucesso", "link": link_app_capturado}

    except Exception as e:
        logger.error("❌ ERRO FATAL NA AUTOMAÇÃO!")
        logger.error(traceback.format_exc())
        
        try:
            driver.save_screenshot("erro_debug.png")
            with open("erro_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logger.info("📸 Screenshot e HTML de erro salvos localmente.")
        except:
            logger.warning("Não foi possível salvar screenshot de erro.")

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
        logger.error("Credenciais não encontradas.")
        raise HTTPException(status_code=500, detail="Credenciais do WebDiet não configuradas.")

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
