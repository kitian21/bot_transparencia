import os
import time
import re
import shutil
import glob
import requests
import urllib3 # Para silenciar advertencias
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# SILENCIAR ADVERTENCIAS ROJAS DE SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- LIBRERÍA PDF ---
try:
    from pypdf import PdfReader
except ImportError:
    print("⚠️ FALTA INSTALAR pypdf. Ejecuta: python -m pip install pypdf")

# ==========================================
# CONFIGURACIÓN
# ==========================================
BASE_DIR = r"C:\Users\In Data\OneDrive\Escritorio\christian\200mts o mas"

COMUNAS = [
    #"Cerrillos", "Cerro Navia", "Conchalí", "El Bosque", "Estación Central", 
    "Huechuraba", "Independencia", "La Cisterna", "La Florida", "La Granja", 
    "La Pintana", "La Reina", "Las Condes", "Lo Barnechea", "Lo Espejo", 
    "Lo Prado", "Macul", "Maipú", "Ñuñoa", "Pedro Aguirre Cerda", "Peñalolén", 
    "Providencia", "Pudahuel", "Quilicura", "Quinta Normal", "Recoleta", 
    "Renca", "San Joaquín", "San Miguel", "San Ramón", "Santiago", "Vitacura"
]

KEYWORDS = ["ampliación", "remodelación", "modificación", "obra nueva", "regularización", "edificación", "obra menor"]

# --- FILTRO DOBLE CAPA (100 web -> Escaneo PDF) ---
MIN_METROS_SEGURO = 200.0  
MIN_METROS_DUDOSO = 100.0  

CARPETAS_PISTA = ["obras", "edificación", "urban", "permiso", "dom", "construc", "trámites", "acuerdos"]

CARPETAS_IGNORAR = [
    "ley 20.898", "20.898", "cuentas", "loteo", "subdivisión", 
    "copropiedad", "certificados", "recepción", "anteproyecto", 
    "paralización", "demolición", "convenio", "decreto", "nómina", 
    "contrato", "adjudicación", "sistema", "actas", "sumarios",
    "07.", "actos y resoluciones", "concesiones", "mera tenencia", "ocupación"
]

TEMP_DOWNLOAD_DIR = os.path.join(BASE_DIR, "Temp_Descargas")

# ==========================================
# HERRAMIENTAS
# ==========================================
def configurar_driver():
    if not os.path.exists(TEMP_DOWNLOAD_DIR): os.makedirs(TEMP_DOWNLOAD_DIR)
    opts = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": TEMP_DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "pdfjs.disabled": True,
        "profile.default_content_setting_values.automatic_downloads": 1,
        "profile.default_content_settings.popups": 0
    }
    opts.add_experimental_option("prefs", prefs)
    opts.add_argument("--start-maximized")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def limpiar_texto(texto): 
    if not texto: return ""
    return texto.lower().strip()

def extraer_metros(texto):
    match = re.search(r'(\d+[\.,]?\d*)\s*(?:m2|mts2|metros|mts)', texto, re.IGNORECASE)
    if match: 
        val_str = match.group(1)
        if ',' in val_str and '.' in val_str:
            val_str = val_str.replace('.', '').replace(',', '.')
        elif ',' in val_str:
            val_str = val_str.replace(',', '.')
        try: return float(val_str)
        except: return 0.0
    return 0.0

# ==========================================
# ANALISTA DE PDF
# ==========================================
def escanear_pdf_en_busca_de_metros(ruta):
    print("         [🔍] Escaneando PDF interno...")
    try:
        reader = PdfReader(ruta)
        text = ""
        for i in range(min(len(reader.pages), 10)): 
            try: text += reader.pages[i].extract_text() + " "
            except: pass
            
        if len(text) < 50: 
            print("         [⚠️] PDF es imagen (Ilegible). Guardando por seguridad.")
            return 9999.0 

        text = text.replace('\n', ' ')
        matches = re.findall(r'(\d+[\.,]?\d*)\s*(?:m2|mts|sup\.|superficie)', text, re.IGNORECASE)
        nums = []
        for m in matches:
            val_str = m
            if ',' in val_str and '.' in val_str:
                val_str = val_str.replace('.', '').replace(',', '.')
            elif ',' in val_str:
                val_str = val_str.replace(',', '.')
            try: 
                val = float(val_str)
                if 10 < val < 50000: nums.append(val)
            except: pass
            
        if not nums: return 0.0
        maximo = max(nums)
        print(f"         [🔍] Máximo encontrado: {maximo} m2")
        return maximo
    except Exception as e: 
        print(f"         [!] Error leyendo PDF: {e}")
        return 9999.0 

# ==========================================
# GESTIÓN DE ARCHIVOS
# ==========================================
def procesar_archivo_descargado(carpeta_destino, metros_web):
    time.sleep(2) 
    lista = glob.glob(os.path.join(TEMP_DOWNLOAD_DIR, "*"))
    validos = [f for f in lista if not f.endswith(".crdownload") and not f.endswith(".tmp")]
    
    if not validos: return False
    nuevo = max(validos, key=os.path.getctime)
    
    decision = False
    if metros_web >= MIN_METROS_SEGURO: 
        print(f"      [OK] Web dice {metros_web}m2. Guardando.")
        decision = True
    else:
        m_pdf = escanear_pdf_en_busca_de_metros(nuevo)
        if m_pdf >= MIN_METROS_SEGURO: 
            print(f"      [OK] PDF confirma {m_pdf}m2. Guardando.")
            decision = True
        else: 
            print(f"      [X] Eliminado (PDF dice {m_pdf}m2)")
            try: os.remove(nuevo)
            except: pass
            return False

    if decision:
        if not os.path.exists(carpeta_destino): os.makedirs(carpeta_destino)
        shutil.move(nuevo, os.path.join(carpeta_destino, os.path.basename(nuevo)))
        return True
    return False

def arreglar_url_drive(url):
    match_id = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if match_id:
        return f"https://drive.google.com/uc?export=download&id={match_id.group(1)}"
    return url

def descargar_pdf_por_url(url, carpeta, cookies, m_web=0.0):
    print(f"         [PLAN B] Descargando URL directa...")
    url_final = url
    if "drive.google.com" in url: url_final = arreglar_url_drive(url)

    try:
        s = requests.Session()
        if "drive.google" not in url_final:
            for c in cookies: s.cookies.set(c['name'], c['value'])
        
        r = s.get(url_final, stream=True, verify=False)
        
        # Check content type
        content_type = r.headers.get('Content-Type', '').lower()
        if 'text/html' in content_type and "drive.google" not in url_final:
            return False

        name = "doc.pdf"
        if "filename=" in r.headers.get("Content-Disposition", ""):
            name = re.findall("filename=(.+)", r.headers["Content-Disposition"])[0].strip('"')
        if not name.lower().endswith(".pdf"): name += ".pdf"
        
        with open(os.path.join(TEMP_DOWNLOAD_DIR, name), 'wb') as f:
            for c in r.iter_content(8192): f.write(c)
            
        return procesar_archivo_descargado(carpeta, m_web)
    except: return False

def mover_archivo(carpeta_destino):
    return procesar_archivo_descargado(carpeta_destino, 200.0) 

# ==========================================
# NAVEGACIÓN
# ==========================================
def click_js(driver, elemento):
    driver.execute_script("arguments[0].scrollIntoView();", elemento)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", elemento)

def obtener_texto_seguro(elemento):
    try: return elemento.get_attribute("textContent").strip()
    except: return ""

def es_carpeta_valida(texto):
    texto = texto.lower()
    if len(texto) > 100: return False
    for ban in CARPETAS_IGNORAR:
        if ban in texto: return False
    return True

def obtener_puntaje_carpeta(nombre_carpeta):
    nombre = nombre_carpeta.lower()
    if "2024" in nombre or "2025" in nombre: return 200
    if "permisos de obras" in nombre: return 100
    if "dirección de obras" in nombre: return 90 
    if "obras municipales" in nombre: return 80
    if "edificación" in nombre: return 70
    return 10

def buscar_ruta_hacia_anio(driver, anio_objetivo, profundidad=0, visitados=None):
    if profundidad > 3: return False 
    if visitados is None: visitados = set()

    # 1. Buscar AÑO
    try:
        xpath_anio = f"//a[contains(text(), '{anio_objetivo}')]"
        links_anio = driver.find_elements(By.XPATH, xpath_anio)
        for l in links_anio:
            if l.is_displayed() and es_carpeta_valida(obtener_texto_seguro(l)):
                txt = obtener_texto_seguro(l)
                if len(txt) < 25 or "año" in txt.lower() or "permiso" in txt.lower():
                    print(f"  🎯 ¡AÑO {anio_objetivo} ENCONTRADO!: {txt}")
                    click_js(driver, l); time.sleep(3); return True
    except: pass

    # 2. Buscar Carpetas Pista
    links = driver.find_elements(By.TAG_NAME, "a")
    candidatos = []
    
    for l in links:
        try:
            if not l.is_displayed(): continue
            txt = obtener_texto_seguro(l)
            if not txt or txt in visitados: continue
            if not es_carpeta_valida(txt): continue
            txt_lower = txt.lower()
            if any(p in txt_lower for p in CARPETAS_PISTA):
                candidatos.append(txt)
        except: pass
    
    candidatos = sorted(list(set(candidatos)), key=obtener_puntaje_carpeta, reverse=True)
    
    if profundidad == 0:
        print(f"  👀 Rutas posibles: {candidatos}")

    for carpeta in candidatos:
        print(f"  🔎 (Nivel {profundidad}) Probando: {carpeta}...")
        visitados.add(carpeta)
        try:
            xpath_carpeta = f"//a[contains(text(), '{carpeta}')]"
            elems = driver.find_elements(By.XPATH, xpath_carpeta)
            clickeado = False
            for e in elems:
                if e.is_displayed():
                    click_js(driver, e); clickeado = True; break
            if not clickeado: continue

            time.sleep(3)
            if buscar_ruta_hacia_anio(driver, anio_objetivo, profundidad + 1, visitados): return True 
            
            print(f"  ↩️ Volviendo de {carpeta}...")
            driver.back(); time.sleep(4)
        except:
            try: driver.back(); time.sleep(4)
            except: pass
    return False

def volver_seguro_al_anio(driver, anio_texto):
    print(f"    << Volviendo a carpeta '{anio_texto}'...")
    try:
        xpath_anio = f"//a[contains(text(), '{anio_texto}')]"
        link_anio = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath_anio)))
        click_js(driver, link_anio); time.sleep(5); return True
    except:
        driver.back(); time.sleep(5); return True

# ==========================================
# ANÁLISIS CONTENIDO
# ==========================================
def analizar_tabla_final(driver, nombre_comuna, anio, mes):
    try: WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
    except: return 0 
    filas = driver.find_elements(By.TAG_NAME, "tr")
    descargas = 0
    print(f"      -> Escaneando {len(filas)} filas...")
    for fila in filas:
        try:
            txt = limpiar_texto(fila.text)
            m_web = extraer_metros(txt)
            if m_web < MIN_METROS_DUDOSO: continue 
            if not any(k in txt for k in KEYWORDS): continue
            
            print(f"      ★ CANDIDATO: {m_web} m2 (Web)")
            ruta = os.path.join(BASE_DIR, nombre_comuna, anio, mes)
            try: 
                l = fila.find_element(By.PARTIAL_LINK_TEXT, "Enlace")
                click_js(driver, l); time.sleep(3)
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])
                    descargar_pdf_por_url(driver.current_url, ruta, driver.get_cookies(), m_web)
                    driver.close(); driver.switch_to.window(driver.window_handles[0])
                else:
                    if driver.current_url.endswith(".pdf"):
                        descargar_pdf_por_url(driver.current_url, ruta, driver.get_cookies(), m_web)
                        driver.back()
                    else:
                        for _ in range(5):
                            if procesar_archivo_descargado(ruta, m_web): descargas+=1; break
                            time.sleep(1)
            except: pass
        except: pass
    return descargas

def procesar_contenido_del_mes(driver, nombre_comuna, anio, mes):
    if driver.current_url.endswith(".pdf") or "drive.google" in driver.current_url:
        ruta = os.path.join(BASE_DIR, nombre_comuna, anio, mes)
        descargar_pdf_por_url(driver.current_url, ruta, driver.get_cookies(), 100.0)
        driver.back(); return 1
        
    if len(driver.find_elements(By.TAG_NAME, "tr")) > 3:
        return analizar_tabla_final(driver, nombre_comuna, anio, mes)
    
    print("      (Buscando subcarpetas...)")
    subs = ["edificación", "regularización", "obra menor", "permiso"]
    links = driver.find_elements(By.TAG_NAME, "a")
    candidatos = set()
    for l in links:
        if l.is_displayed() and es_carpeta_valida(obtener_texto_seguro(l)):
            if any(k in obtener_texto_seguro(l).lower() for k in subs): candidatos.add(obtener_texto_seguro(l))
            
    for sub in sorted(list(candidatos)):
        print(f"      -> Subcarpeta: {sub}")
        try:
            xp = f"//a[contains(text(), '{sub}')]"
            clk = driver.find_element(By.XPATH, xp)
            click_js(driver, clk); time.sleep(3)
            if driver.current_url.endswith(".pdf"):
                descargar_pdf_por_url(driver.current_url, os.path.join(BASE_DIR, nombre_comuna, anio, mes), driver.get_cookies(), 100.0)
                driver.back()
            else:
                analizar_tabla_final(driver, nombre_comuna, anio, mes)
                driver.back(); time.sleep(3)
        except: driver.back(); time.sleep(3)
    return 0

# ==========================================
# FLUJO PRINCIPAL
# ==========================================
def procesar_comuna(driver, nombre_comuna):
    print(f"\n{'='*40}\n PROCESANDO: {nombre_comuna}\n{'='*40}")
    wait = WebDriverWait(driver, 15)
    main_win = driver.current_window_handle
    
    try:
        driver.get("https://www.portaltransparencia.cl/")
        time.sleep(2)
        try:
            s = wait.until(EC.element_to_be_clickable((By.ID, "cuadroBusqueda")))
            s.clear(); s.send_keys(f"Municipalidad de {nombre_comuna}"); time.sleep(1); s.send_keys(Keys.ENTER)
        except: input("⚠️ BUSCA MANUALMENTE Y ENTER...")

        time.sleep(3)
        try:
            xp = f"//p[contains(@class, 'entry-body__title') and contains(text(), '{nombre_comuna}')]"
            res = wait.until(EC.element_to_be_clickable((By.XPATH, xp))); click_js(driver, res)
        except: input("⚠️ CLIC EN LA MUNI Y ENTER...")

        try:
            wait.until(EC.number_of_windows_to_be(2))
            driver.switch_to.window(driver.window_handles[-1])
            time.sleep(4)
        except: pass

        try:
            xp7 = "//a[contains(text(), 'Efectos sobre Terceros') or contains(text(), 'efectos sobre terceros')]"
            l7 = wait.until(EC.presence_of_element_located((By.XPATH, xp7))); click_js(driver, l7)
        except: input("⚠️ ENTRA AL PUNTO 7 Y ENTER...")

        time.sleep(3)
        
        total_comuna = 0
        for anio in ["2024", "2025"]:
            print(f"--- Buscando Año {anio} ---")
            encontrado = buscar_ruta_hacia_anio(driver, anio, profundidad=0, visitados=set())
            
            if encontrado:
                meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
                         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
                for mes in meses:
                    xp_mes = f"//a[contains(translate(text(), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{mes.upper()}')]"
                    elems = driver.find_elements(By.XPATH, xp_mes)
                    l_mes = None
                    for e in elems:
                        if e.is_displayed(): l_mes = e; break
                    
                    if l_mes:
                        print(f"    📂 {mes}...")
                        click_js(driver, l_mes); time.sleep(3)
                        total_comuna += procesar_contenido_del_mes(driver, nombre_comuna, anio, mes)
                        try: 
                            xp_back_anio = f"//a[contains(text(), '{anio}')]"
                            clk_back = driver.find_element(By.XPATH, xp_back_anio)
                            click_js(driver, clk_back); time.sleep(4)
                        except: driver.back(); time.sleep(4)
                
                print("    🔄 Reiniciando...")
                try:
                    xp7 = "//a[contains(text(), 'Efectos sobre Terceros')]"
                    driver.find_element(By.XPATH, xp7).click()
                except: driver.get(driver.current_url)
                time.sleep(3)
            else:
                print(f"    ❌ No se encontró el Año {anio}.")

        print(f"✅ Fin {nombre_comuna}. Total: {total_comuna}")

    except Exception as e: print(f"❌ Error {nombre_comuna}: {e}")
    finally:
        try:
            if len(driver.window_handles) > 1: driver.close(); driver.switch_to.window(main_win)
        except: pass

def main():
    driver = configurar_driver()
    print("--- ROBOT V27: HUECHURABA OK + SILENCIO ---")
    for c in COMUNAS: procesar_comuna(driver, c)
    driver.quit()

if __name__ == "__main__":
    main()