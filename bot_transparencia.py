import os
import time
import re
import shutil
import glob
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- LIBRERÍA NUEVA PARA LEER PDFS ---
try:
    from pypdf import PdfReader
except ImportError:
    print("FALTA INSTALAR pypdf. Ejecuta: python -m pip install pypdf")
    exit()

# ==========================================
# CONFIGURACIÓN
# ==========================================
BASE_DIR = r"C:\Users\In Data\OneDrive\Escritorio\christian\200mts o mas"

COMUNAS = [
    "Cerrillos", "Cerro Navia", "Conchalí", "El Bosque", "Estación Central", 
    "Huechuraba", "Independencia", "La Cisterna", "La Florida", "La Granja", 
    "La Pintana", "La Reina", "Las Condes", "Lo Barnechea", "Lo Espejo", 
    "Lo Prado", "Macul", "Maipú", "Ñuñoa", "Pedro Aguirre Cerda", "Peñalolén", 
    "Providencia", "Pudahuel", "Quilicura", "Quinta Normal", "Recoleta", 
    "Renca", "San Joaquín", "San Miguel", "San Ramón", "Santiago", "Vitacura"
]

KEYWORDS = ["ampliación", "remodelación", "modificación", "obra nueva", "regularización", "edificación", "obra menor"]

# --- LÓGICA DE FILTRO ---
MIN_METROS_SEGURO = 200.0  # Si dice esto en la web, pasa directo.
MIN_METROS_DUDOSO = 100.0  # Si dice esto, lo descargamos para leerlo por dentro.

CARPETAS_PISTA = ["obras", "edificación", "urban", "permiso", "dom", "construc", "trámites"]

CARPETAS_IGNORAR = [
    "ley 20.898", "20.898", "cuentas", "loteo", "subdivisión", 
    "copropiedad", "certificados", "recepción", "anteproyecto", 
    "paralización", "demolición", "convenio", "decreto", "nómina", 
    "contrato", "adjudicación", "sistema", "actas", "sumarios",
    "07.", "actos y resoluciones", "concesiones"
]

TEMP_DOWNLOAD_DIR = os.path.join(BASE_DIR, "Temp_Descargas")

# ==========================================
# HERRAMIENTAS DE PDF
# ==========================================

def escanear_pdf_en_busca_de_metros(ruta_archivo):
    """
    Abre el PDF, extrae todo el texto y busca el número más alto asociado a 'm2'.
    Retorna el máximo encontrado.
    """
    print("         [🔍] Escaneando contenido del PDF...")
    try:
        reader = PdfReader(ruta_archivo)
        texto_completo = ""
        
        # Leer todas las páginas (o las primeras 5 para ser rápido)
        paginas_a_leer = min(len(reader.pages), 5)
        for i in range(paginas_a_leer):
            texto_completo += reader.pages[i].extract_text() + "\n"
            
        # Buscar patrones de metros: "120,5 m2", "Total: 300 mts"
        # Regex busca números seguidos de m2/mts/metros
        matches = re.findall(r'(\d+[\.,]?\d*)\s*(?:m2|mts2|metros|mts)', texto_completo, re.IGNORECASE)
        
        if not matches:
            return 0.0
            
        # Convertir a floats y buscar el máximo
        numeros = []
        for m in matches:
            try:
                val = float(m.replace(",", "."))
                numeros.append(val)
            except: pass
            
        maximo = max(numeros) if numeros else 0.0
        print(f"         [🔍] Máximo encontrado en PDF: {maximo} m2")
        return maximo

    except Exception as e:
        print(f"         [!] No se pudo leer el PDF (¿Encriptado/Imagen?): {e}")
        return 0.0

# ==========================================
# HERRAMIENTAS GENERALES
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

def limpiar_texto(texto): return texto.lower().strip()

def extraer_metros(texto):
    match = re.search(r'(\d+[\.,]?\d*)\s*(?:m2|mts2|metros|mts)', texto, re.IGNORECASE)
    if match: 
        numero_limpio = match.group(1).replace(",", ".")
        try: return float(numero_limpio)
        except: return 0.0
    return 0.0

def procesar_archivo_descargado(carpeta_destino, metros_web):
    """
    Decide si guarda o borra el archivo basándose en la lógica de doble capa.
    """
    time.sleep(2) 
    lista = glob.glob(os.path.join(TEMP_DOWNLOAD_DIR, "*"))
    validos = [f for f in lista if not f.endswith(".crdownload") and not f.endswith(".tmp")]
    
    if not validos: return False
    
    nuevo = max(validos, key=os.path.getctime)
    nombre_base = os.path.basename(nuevo)
    
    decision_final = False
    
    # --- LÓGICA DE DECISIÓN ---
    if metros_web >= MIN_METROS_SEGURO:
        print(f"      [OK] Web dice {metros_web}m2. Guardando directo.")
        decision_final = True
    else:
        # Caso Dudoso (100 - 199): Leemos el PDF
        metros_pdf = escanear_pdf_en_busca_de_metros(nuevo)
        
        if metros_pdf >= MIN_METROS_SEGURO:
            print(f"      [OK] PDF confirma {metros_pdf}m2. Guardando.")
            decision_final = True
        else:
            print(f"      [X] ELIMINADO. PDF dice {metros_pdf}m2 (Insuficiente).")
            try: os.remove(nuevo) # Borramos el archivo temporal
            except: pass
            return False # No se guardó

    if decision_final:
        if not os.path.exists(carpeta_destino): os.makedirs(carpeta_destino)
        destino = os.path.join(carpeta_destino, nombre_base)
        try:
            if os.path.exists(destino): os.remove(destino)
            shutil.move(nuevo, destino)
            return True
        except: return False
        
    return False

def arreglar_url_drive(url):
    match_id = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if match_id:
        return f"https://drive.google.com/uc?export=download&id={match_id.group(1)}"
    return url

def descargar_pdf_por_url(url, carpeta_destino, cookies_selenium, metros_web=0.0):
    print(f"         [PLAN B] Descargando URL directa...")
    url_final = url
    if "drive.google.com" in url: url_final = arreglar_url_drive(url)

    try:
        session = requests.Session()
        if "drive.google" not in url_final:
            for cookie in cookies_selenium: session.cookies.set(cookie['name'], cookie['value'])
        
        response = session.get(url_final, stream=True, verify=False)
        
        # Guardamos temporalmente para analizar
        nombre_temp = "temp_analisis.pdf"
        if "Content-Disposition" in response.headers:
            fname = re.findall("filename=(.+)", response.headers["Content-Disposition"])
            if fname: nombre_temp = fname[0].strip('"')
        if not nombre_temp.lower().endswith(".pdf"): nombre_temp += ".pdf"

        ruta_temp = os.path.join(TEMP_DOWNLOAD_DIR, nombre_temp)
        
        with open(ruta_temp, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
            
        # Llamamos a la lógica de decisión pasando la ruta temporal
        return procesar_archivo_descargado(carpeta_destino, metros_web)

    except: return False

def click_js(driver, elemento):
    driver.execute_script("arguments[0].scrollIntoView();", elemento)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", elemento)

def volver_atras(driver):
    try:
        migas = driver.find_elements(By.CSS_SELECTOR, ".ui-breadcrumb a")
        if len(migas) >= 2:
            click_js(driver, migas[-2]); time.sleep(4); return
    except: pass
    driver.back(); time.sleep(4)

def volver_seguro_al_anio(driver, anio_texto):
    print(f"    << Volviendo a carpeta '{anio_texto}'...")
    try:
        xpath_anio = f"//a[contains(text(), '{anio_texto}')]"
        link_anio = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath_anio)))
        click_js(driver, link_anio); time.sleep(5); return True
    except:
        driver.back(); time.sleep(5); return True

# ==========================================
# NAVEGACIÓN INTELIGENTE
# ==========================================

def analizar_carpeta(texto_link):
    texto = texto_link.lower()
    if len(texto) > 100: return False, "Muy largo"
    for ban in CARPETAS_IGNORAR:
        if ban in texto: return False, f"Palabra prohibida: {ban}"
    return True, "OK"

def obtener_puntaje_carpeta(nombre_carpeta):
    nombre = nombre_carpeta.lower()
    if "2024" in nombre or "2025" in nombre: return 200 
    if "permisos de obras" in nombre: return 100
    if "permisos de edificación" in nombre: return 90
    if "edificación" in nombre: return 80
    if "dirección de obras" in nombre: return 70
    if "obras municipales" in nombre: return 60
    return 10

def buscar_ruta_hacia_anio(driver, anio_objetivo, profundidad=0, visitados=None):
    if profundidad > 3: return False 
    if visitados is None: visitados = set()

    links = driver.find_elements(By.TAG_NAME, "a")
    candidatos = []
    
    for l in links:
        try:
            if not l.is_displayed(): continue
            txt = l.text.strip()
            if not txt or txt in visitados: continue
            
            es_valida, razon = analizar_carpeta(txt)
            if not es_valida: continue

            txt_lower = txt.lower()
            
            if anio_objetivo in txt:
                if len(txt) < 10 or any(p in txt_lower for p in CARPETAS_PISTA):
                    print(f"  🎯 ¡AÑO DETECTADO!: {txt}")
                    click_js(driver, l)
                    time.sleep(3)
                    return True

            if any(pista in txt_lower for pista in CARPETAS_PISTA):
                candidatos.append(txt)
        except: pass
    
    candidatos = sorted(list(set(candidatos)), key=obtener_puntaje_carpeta, reverse=True)
    
    if profundidad == 0:
        print(f"  👀 Rutas posibles: {candidatos}")

    for carpeta in candidatos:
        print(f"  🔎 (Nivel {profundidad}) Probando: {carpeta}...")
        visitados.add(carpeta)
        
        try:
            elem = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, carpeta)))
            click_js(driver, elem)
            time.sleep(3)
            if buscar_ruta_hacia_anio(driver, anio_objetivo, profundidad + 1, visitados):
                return True 
            print(f"  ↩️ Volviendo de {carpeta}...")
            volver_atras(driver)
        except Exception as e:
            try: 
                if "no such element" not in str(e): volver_atras(driver) 
            except: pass

    return False

# ==========================================
# PROCESAMIENTO
# ==========================================

def analizar_tabla_final(driver, nombre_comuna, anio, mes):
    try: WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
    except: return 0 

    filas = driver.find_elements(By.TAG_NAME, "tr")
    descargas = 0
    ventana_principal = driver.current_window_handle
    ventanas_antes = driver.window_handles
    
    print(f"      -> Escaneando {len(filas)} filas...")
    
    for fila in filas:
        try:
            txt = limpiar_texto(fila.text)
            metros_web = extraer_metros(txt)
            
            # --- FILTRO NIVEL 1: WEB ---
            # Si dice menos de 100, ignoramos.
            if metros_web < MIN_METROS_DUDOSO: 
                continue
            
            # Si pasa, revisamos palabras clave
            if not any(k in txt for k in KEYWORDS): 
                continue
            
            print(f"      ★ CANDIDATO: {metros_web} m2 (En descripción)")
            ruta_destino = os.path.join(BASE_DIR, nombre_comuna, anio, mes)
            
            try: link = fila.find_element(By.PARTIAL_LINK_TEXT, "Enlace")
            except:
                try: link = fila.find_element(By.PARTIAL_LINK_TEXT, "Ver")
                except: 
                    links_row = fila.find_elements(By.TAG_NAME, "a")
                    if links_row: link = links_row[-1]
                    else: continue

            click_js(driver, link)
            time.sleep(3)
            
            ventanas_ahora = driver.window_handles
            if len(ventanas_ahora) > len(ventanas_antes):
                new_win = [v for v in ventanas_ahora if v not in ventanas_antes][0]
                driver.switch_to.window(new_win)
                # PLAN B + ESCANEO PDF
                if descargar_pdf_por_url(driver.current_url, ruta_destino, driver.get_cookies(), metros_web): 
                    descargas += 1
                driver.close(); driver.switch_to.window(ventana_principal)
            elif driver.current_url.endswith(".pdf"):
                descargar_pdf_por_url(driver.current_url, ruta_destino, driver.get_cookies(), metros_web)
                driver.back()
            else:
                # DESCARGA NORMAL + ESCANEO PDF
                for _ in range(5):
                    # Pasamos metros_web para que la función sepa si debe escanear o no
                    if procesar_archivo_descargado(ruta_destino, metros_web): 
                        descargas += 1; break
                    time.sleep(1)
        except: 
            if len(driver.window_handles) > len(ventanas_antes):
                driver.close(); driver.switch_to.window(ventana_principal)
            continue
    return descargas

def procesar_contenido_del_mes(driver, nombre_comuna, anio, mes):
    if driver.current_url.endswith(".pdf") or "drive.google" in driver.current_url:
        print("      ⚠️ PDF/Drive Directo detectado.")
        ruta = os.path.join(BASE_DIR, nombre_comuna, anio, mes)
        # Asumimos 100m2 para forzar el escaneo interno
        descargar_pdf_por_url(driver.current_url, ruta, driver.get_cookies(), 100.0)
        driver.back(); return 1

    filas = len(driver.find_elements(By.TAG_NAME, "tr"))
    total = 0
    
    if filas > 3:
        total += analizar_tabla_final(driver, nombre_comuna, anio, mes)
    else:
        sub_interes = ["edificación", "regularización", "obra menor", "permiso"]
        links = driver.find_elements(By.TAG_NAME, "a")
        candidatos = set()
        for l in links:
            try:
                if l.is_displayed():
                    txt = l.text.strip()
                    es_val, _ = analizar_carpeta(txt)
                    if es_val and any(k in txt.lower() for k in sub_interes):
                        candidatos.add(txt)
            except: pass
        
        for sub in sorted(list(candidatos)):
            print(f"      -> Subcarpeta: {sub}")
            try:
                elem = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, sub)))
                click_js(driver, elem)
                time.sleep(3)
                if driver.current_url.endswith(".pdf"):
                    descargar_pdf_por_url(driver.current_url, os.path.join(BASE_DIR, nombre_comuna, anio, mes), driver.get_cookies(), 100.0)
                    driver.back()
                else:
                    total += analizar_tabla_final(driver, nombre_comuna, anio, mes)
                    volver_atras(driver)
            except: volver_atras(driver)
            
    return total

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
                        if not volver_seguro_al_anio(driver, anio): volver_atras(driver)
                
                print("    🔄 Reiniciando a Punto 7...")
                try:
                    xp7 = "//a[contains(text(), 'Efectos sobre Terceros')]"
                    driver.find_element(By.XPATH, xp7).click()
                except:
                    for _ in range(3):
                        try: 
                            if len(driver.find_elements(By.PARTIAL_LINK_TEXT, "Dirección de Obras")) > 0: break
                            driver.back(); time.sleep(2)
                        except: pass
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
    print("--- ROBOT V21: EL ANALISTA DE PDF ---")
    for c in COMUNAS: procesar_comuna(driver, c)
    driver.quit()

if __name__ == "__main__":
    main()