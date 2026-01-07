import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# ==============================================================================
# 🔐 CONFIGURAÇÃO DE AMBIENTE (RENDER)
# O link deve estar nas "Environment Variables" do Render com a chave: WEBHOOK_MAKE_URL
# ==============================================================================
WEBHOOK_MAKE_URL = os.getenv("WEBHOOK_MAKE_URL")

# Mapa de refeições (Mantido igual)
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

# --- Funções Auxiliares ---
def click_js(driver, elemento):
    driver.execute_script("arguments[0].click();", elemento)

def definir_horario(driver, element_id, horario):
    try:
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
    except: pass

def selecionar_itens(driver, wait, categoria, codigos_brutos):
    if not codigos_brutos: return
    print(f">> Processando {categoria}...")
    lista_codigos = str(codigos_brutos).split(",")
    for codigo in lista_codigos:
        codigo_limpo = codigo.strip().lower()
        nome_real = MAPA_REFEICOES.get(categoria, {}).get(codigo_limpo)
        if not nome_real: continue

        try:
            xpath_item = f"//div[contains(text(), '{nome_real}')] | //span[contains(text(), '{nome_real}')] | //label[contains(text(), '{nome_real}')]"
            elem = driver.find_element(By.XPATH, xpath_item)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(0.5)
            click_js(driver, elem)
            
            time.sleep(1) 
            btn_confirmar = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'confirmar')]")
            ))
            click_js(driver, btn_confirmar)
            time.sleep(1.5) 
        except: pass

def enviar_webhook(paciente_dados, dados_clinicos, link_app, status_msg):
    print(f"\n📡 TENTANDO ENVIAR WEBHOOK COMPLETO...")
    
    if not WEBHOOK_MAKE_URL:
        print("❌ ERRO: Variável WEBHOOK_MAKE_URL não configurada no Render!")
        return

    payload = {
        "status": status_msg,
        "link_app": link_app,
        "paciente": paciente_dados,
        "dados_clinicos": dados_clinicos
    }

    try:
        response = requests.post(WEBHOOK_MAKE_URL, json=payload)
        if response.status_code == 200:
            print("✅ WEBHOOK ENVIADO COM SUCESSO!")
        else:
            print(f"⚠️ Make respondeu com erro: {response.status_code}")
    except Exception as e:
        print(f"❌ Erro de conexão ao enviar webhook: {e}")

def executar_cadastro(usuario, senha, paciente, dados_clinicos):
    chrome_options = Options()
    
    # --- CONFIGURAÇÕES CRÍTICAS PARA O RENDER ---
    chrome_options.add_argument("--headless") # Obrigatório: não abre janela visual
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # --------------------------------------------

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20)
    
    link_app_capturado = "Link não encontrado"

    try:
        print(f"--- 🚀 Iniciando: {paciente.get('nome', 'Sem Nome')} ---")
        
        # 1. LOGIN
        driver.get("https://pt.webdiet.com.br/login/")
        wait.until(EC.presence_of_element_located((By.ID, "emailLogin"))).send_keys(usuario)
        driver.switch_to.active_element.send_keys(Keys.TAB)
        driver.switch_to.active_element.send_keys(senha + Keys.ENTER)
        
        # 2. CADASTRO
        time.sleep(3)
        print(">> Criando ficha...")
        btn_novo_paciente = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@onclick, \"novoPaciente('index')\")]")))
        click_js(driver, btn_novo_paciente)
        
        time.sleep(1.5)
        wait.until(EC.visibility_of_element_located((By.ID, "nomeAtalho"))).send_keys(paciente["nome"])
        try:
            opcao_genero = driver.find_element(By.XPATH, f"//option[@value='{paciente['sexo']}']")
            driver.execute_script("arguments[0].selected = true; arguments[0].parentElement.dispatchEvent(new Event('change'));", opcao_genero)
        except: pass

        driver.find_element(By.ID, "nascimentoAtalho").send_keys(paciente["nascimento"])
        driver.find_element(By.ID, "emailAtalho").send_keys(paciente["email"])
        driver.find_element(By.ID, "telefoneAtalho").send_keys(paciente["telefone"])
        time.sleep(0.5)
        driver.find_element(By.ID, "novoPacienteBtnAtalho").click()

        # 3. PERFIL
        time.sleep(2)
        print(">> Acessando perfil...")
        btn_abrir_menu = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//div[contains(text(), 'não registrar e abrir menu')]")
        ))
        click_js(driver, btn_abrir_menu)
        
        time.sleep(3)

        # --- CAPTURA LINK ---
        try:
            print(">> Buscando Link...")
            elemento_link = wait.until(EC.visibility_of_element_located((By.ID, "linkRef")))
            link_app_capturado = elemento_link.text.strip()
            print(f"✅ LINK CAPTURADO: {link_app_capturado}")
        except:
            print("⚠️ Aviso: Não consegui pegar o link nesta etapa.")

        # 4. PLANEJAMENTO
        if dados_clinicos:
            print(">> Iniciando Planejamento...")

            # Criação
            btn_add_planejamento = wait.until(EC.presence_of_element_located((By.ID, "atalhoPlanejamento")))
            click_js(driver, btn_add_planejamento)
            time.sleep(1.5)

            btn_avancar = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'avançar')]")
            ))
            click_js(driver, btn_avancar)
            time.sleep(1.5)

            btn_confirmar = wait.until(EC.presence_of_element_located((By.ID, "criarPlanejamento")))
            click_js(driver, btn_confirmar)

            print(">> Limpando padrão...")
            time.sleep(4) 

            # Limpeza (3x)
            for i in range(1, 4):
                try:
                    btn_lixeira = wait.until(EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(@onclick, 'excluir(0)')]")
                    ))
                    click_js(driver, btn_lixeira)
                    time.sleep(1)
                    btn_remover_habito = wait.until(EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(@onclick, 'swal.clickConfirm()') and contains(text(), 'remover hábito')]")
                    ))
                    click_js(driver, btn_remover_habito)
                    time.sleep(2)
                except: pass 

            # Favoritos
            btn_favoritas = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@onclick, \"verRefeicoesProntas('')\")]")
            ))
            click_js(driver, btn_favoritas)
            time.sleep(2.5) 

            # Seleção
            selecionar_itens(driver, wait, "cafe", dados_clinicos.get("cafe"))
            selecionar_itens(driver, wait, "almoco", dados_clinicos.get("almoco"))

            # Horários
            print(">> Ajustando horários...")
            time.sleep(1)
            definir_horario(driver, "horarioRotinaTemp0", "08:00")
            definir_horario(driver, "horarioRotinaTemp1", "08:00")
            time.sleep(1)

            # Finalizar
            print(">> Salvando...")
            btn_fechar_modal = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//button[@class='close' and @data-dismiss='modal']")
            ))
            click_js(driver, btn_fechar_modal)
            time.sleep(2)

            btn_salvar_final = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@onclick, 'salvarPrescricao()')]")
            ))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_salvar_final)
            time.sleep(0.5)
            click_js(driver, btn_salvar_final)
            print("✅ Salvo!")

            # --- ENVIO FINAL (SUCESSO) ---
            enviar_webhook(paciente, dados_clinicos, link_app_capturado, "Finalizado com Sucesso")

        return {"status": "sucesso", "link": link_app_capturado}

    except Exception as e:
        print(f"❌ Erro Fatal no Robô: {e}")
        # driver.save_screenshot("erro_final.png") # Comentado pois no Render não dá pra ver
        enviar_webhook(paciente, dados_clinicos, link_app_capturado, f"Erro: {str(e)}")
        return {"status": "erro", "mensagem": str(e)}

    finally:
        time.sleep(3)
        driver.quit()

# ==============================================================================
# 🚀 SERVIDOR API (FASTAPI) - Para rodar no Render
# ==============================================================================
app = FastAPI()

class DadosRequest(BaseModel):
    usuario: str
    senha: str
    paciente: dict
    dados_clinicos: dict

@app.post("/executar")
async def api_executar(dados: DadosRequest):
    return executar_cadastro(dados.usuario, dados.senha, dados.paciente, dados.dados_clinicos)

# Permite rodar localmente também se der play no arquivo
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
