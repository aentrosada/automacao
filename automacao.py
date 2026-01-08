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
# 📝 CONFIGURAÇÃO DE LOGS (MODO DETETIVE 🕵️)
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
    if email and senha: return email, senha
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

# --- FUNÇÕES AUXILIARES COM LOG ---
def click_js(driver, elemento, desc="elemento"):
    logger.info(f"   [JS CLICK] Tentando clicar em: {desc}")
    driver.execute_script("arguments[0].click();", elemento)

def definir_horario(driver, element_id, horario):
    try:
        logger.info(f"   [HORÁRIO] Definindo {horario} para ID: {element_id}")
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
        logger.warning(f"   [ERRO] Falha ao definir horário: {e}")

def enviar_webhook(status_msg, detalhe=""):
    if not WEBHOOK_MAKE_URL: return
    try:
        payload = {"status": status_msg, "detalhe": detalhe}
        requests.post(WEBHOOK_MAKE_URL, json=payload, timeout=5)
        logger.info(f"Webhook enviado: {status_msg}")
    except: pass

# --- ROBÔ COM LOGS DETALHADOS ---
def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    logger.info("--- 🕵️ INICIANDO MODO DEBUG COMPLETO ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false") 
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.page_load_strategy = 'eager'

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 25)
    short = WebDriverWait(driver, 4)
    
    link_app_capturado = "Link não encontrado"

    try:
        # 1. LOGIN
        logger.info("1. Acessando Login...")
        driver.get("https://pt.webdiet.com.br/login/")
        
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.switch_to.active_element.send_keys(Keys.TAB)
        driver.switch_to.active_element.send_keys(senha + Keys.ENTER)
        
        # 2. CADASTRO
        time.sleep(2)
        logger.info("2. Procurando botão 'Novo Paciente'...")
        btn_novo = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[onclick*='novoPaciente']")))
        click_js(driver, btn_novo, "Botão Novo Paciente")
        
        time.sleep(1.5)
        logger.info("   > Modal aberto. Preenchendo campos...")
        wait.until(EC.visibility_of_element_located((By.ID, "nomeAtalho"))).send_keys(paciente["nome"])
        
        # Injeção JS
        driver.execute_script(f"""
            try {{ document.getElementById('generoAtalho').value = '{paciente['sexo'].upper()[0]}'; }} catch(e) {{}}
            try {{ document.getElementById('nascimentoAtalho').value = '01/01/2000'; }} catch(e) {{}}
            try {{ document.getElementById('emailAtalho').value = '{paciente['email']}'; }} catch(e) {{}}
            try {{ document.getElementById('telefoneAtalho').value = '{paciente['telefone']}'; }} catch(e) {{}}
        """)

        logger.info("   > Clicando Salvar...")
        btn_salvar = driver.find_element(By.ID, "novoPacienteBtnAtalho")
        click_js(driver, btn_salvar, "Salvar Paciente")

        # Espera modal sumir (Confirmação de que salvou)
        time.sleep(2)
        try:
            if btn_salvar.is_displayed():
                erro = driver.find_element(By.CSS_SELECTOR, ".toast-message").text
                raise Exception(f"Erro no cadastro: {erro}")
        except: pass
        logger.info("✅ Cadastro enviado (Modal fechou).")

        # --- PONTO CRÍTICO: TRANSIÇÃO PARA O DASHBOARD ---
        logger.info("3. Aguardando redirecionamento/popup pós-cadastro...")
        time.sleep(1)
        
        # Tenta clicar no botão "abrir menu" se aparecer (É OBRIGATÓRIO para mudar de tela)
        try:
            logger.info("   > Procurando popup 'abrir menu'...")
            # XPath genérico para pegar qualquer variação do texto
            btn_pos_cadastro = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'abrir menu')]")))
            click_js(driver, btn_pos_cadastro, "Botão Abrir Menu (Pós-Cadastro)")
            logger.info("   > Botão de redirecionamento clicado!")
            time.sleep(3) # Tempo para a página carregar
        except TimeoutException:
            logger.warning("   > Popup 'abrir menu' não apareceu. Verificando se já estamos no dashboard...")

        # Captura Link
        try:
            logger.info("   > Buscando Link...")
            el_link = wait.until(EC.visibility_of_element_located((By.ID, "linkRef")))
            link_app_capturado = el_link.text.strip()
            logger.info(f"✅ Link Capturado: {link_app_capturado}")
        except:
            logger.error(f"❌ Link não encontrado. URL Atual: {driver.current_url}")
            # Se não achou o link, provavelmente não estamos na tela certa

        # 4. PLANEJAMENTO
        if dados_clinicos:
            logger.info("4. Iniciando Bloco de Planejamento...")
            
            logger.info("   > 🔍 Procurando botão 'atalhoPlanejamento'...")
            try:
                # Agora usamos visibility para garantir que carregou
                btn_add = wait.until(EC.visibility_of_element_located((By.ID, "atalhoPlanejamento")))
                click_js(driver, btn_add, "Atalho Planejamento")
            except TimeoutException:
                logger.error(f"❌ ERRO FATAL: Botão de planejamento não encontrado na URL: {driver.current_url}")
                # Fallback: Tentar navegar direto para a URL se soubermos (difícil sem ID)
                raise Exception("Falha ao navegar para o Dashboard do paciente.")

            time.sleep(1.5)

            # Confirmações
            logger.info("   > Procurando botão 'Avançar'...")
            try:
                btn_av = short.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']")))
                click_js(driver, btn_av, "Confirmar Avançar")
                time.sleep(1)
            except: pass

            logger.info("   > Procurando botão 'Confirmar'...")
            try:
                btn_criar = wait.until(EC.presence_of_element_located((By.ID, "criarPlanejamento")))
                click_js(driver, btn_criar, "Criar Planejamento")
            except: pass
            
            time.sleep(3)

            # --- LIMPEZA OTIMIZADA ---
            logger.info("5. Limpando Hábitos...")
            for i in range(5):
                try:
                    btn_lixo = short.until(EC.presence_of_element_located((By.CSS_SELECTOR, "i.fi-sr-trash")))
                    click_js(driver, btn_lixo, "Lixeira")
                    
                    btn_conf = short.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']")))
                    click_js(driver, btn_conf, "Confirmar Exclusão")
                    time.sleep(1)
                except TimeoutException:
                    logger.info("✅ Limpeza concluída.")
                    break
                except Exception: break

            # --- FAVORITOS ---
            logger.info("6. Abrindo Favoritos...")
            try:
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)
                btn_fav = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='verRefeicoesProntas']")))
                click_js(driver, btn_fav, "Botão Favoritos")
                time.sleep(4)
            except Exception as e:
                logger.error(f"❌ Erro ao abrir favoritos: {e}")

            # --- SELEÇÃO ---
            def selecionar_com_log(categoria, codigos):
                if not codigos: return
                logger.info(f"   > Processando {categoria}: {codigos}")
                lista = str(codigos).split(",")
                for cod in lista:
                    nome = MAPA_REFEICOES.get(categoria, {}).get(cod.strip().lower())
                    if not nome: continue
                    
                    try:
                        xpath = f"//span[contains(text(), '{nome}')]"
                        el = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath)))
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                        click_js(driver, el, f"Item {nome}")
                        
                        try:
                            btn_conf = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[onclick*='swal.clickConfirm']")))
                            click_js(driver, btn_conf, "Confirmar Item")
                            time.sleep(1)
                        except: pass
                    except Exception:
                        logger.warning(f"       ❌ Item não encontrado: {nome}")

            selecionar_com_log("cafe", dados_clinicos.get("cafe"))
            selecionar_com_log("almoco", dados_clinicos.get("almoco"))

            # --- HORÁRIOS ---
            logger.info("7. Ajustando Horários...")
            definir_horario(driver, "horarioRotinaTemp0", "08:00")
            definir_horario(driver, "horarioRotinaTemp1", "12:00")

            # --- FECHAR E SALVAR ---
            logger.info("8. Finalizando...")
            try:
                driver.execute_script("document.querySelector('button.close[data-dismiss=\"modal\"]').click()")
            except: 
                try: driver.execute_script("document.querySelector('.modal-backdrop').click()")
                except: pass
            
            time.sleep(1)

            logger.info("   > Salvando Final...")
            try:
                btn_final = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[onclick*='salvarPrescricao']")))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_final)
                time.sleep(0.5)
                click_js(driver, btn_final, "SALVAR FINAL")
                logger.info("✅ CLIQUE FINAL REALIZADO!")
                enviar_webhook("Sucesso", f"Link: {link_app_capturado}")
            except Exception as e:
                logger.error(f"❌ Erro ao salvar final: {e}")
                raise e

        return {"status": "concluido", "link": link_app_capturado}

    except Exception as e:
        logger.error(f"❌ CRASH FATAL: {traceback.format_exc()}")
        enviar_webhook("Erro Fatal", str(e))
        return {"status": "erro", "msg": str(e)}
    finally:
        try: driver.quit()
        except: pass

# ==============================================================================
# API
# ==============================================================================
app = FastAPI()

class Payload(BaseModel):
    paciente: dict
    dados_clinicos: dict

@app.post("/cadastrar-paciente")
def run(p: Payload, bt: BackgroundTasks):
    creds = ler_credenciais()
    if not creds: raise HTTPException(status_code=500, detail="Credenciais não encontradas")
    
    bt.add_task(executar_cadastro, creds[0], creds[1], p.paciente, p.dados_clinicos)
    return {"msg": "Rodando com logs detalhados..."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
