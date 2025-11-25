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

# Filtros de Archivos (Lo que queremos descargar)
KEYWORDS = ["ampliación", "remodelación", "modificación", "obra nueva", "regularización", "edificación", "obra menor"]
MIN_METROS = 200.0

# Filtros de Carpetas (Donde buscar el año)
# Buscaremos carpetas que contengan estas palabras para hallar el año dentro
CARPETAS_PISTA = ["obras", "edificación", "urban", "permiso", "dom", "construc"]

# Lista Negra (Donde NO entrar jamás)
CARPETAS_IGNORAR = [
    "ley 20.898", "20.898", "cuentas", "loteo", "subdivisión", 
    "copropiedad", "recepción", "anteproyecto", 
    "paralización", "demolición", "convenio", "decreto", "nómina", 
    "contrato", "adjudicación", "sistema", "actas", "sumarios", "informe",
    "resolución", "plan regulador", "reglamento", "ordenanza", "catastro",
    "catastral", "patrimonial", "arbolado", "ambiental", "sanitario",
    "salud", "vialidad", "tránsito", "transito", "estadística", "estadistica"
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

def limpiar_texto(texto): return texto.lower().strip()

def extraer_metros(texto):
    match = re.search(r'(\d+[\.,]?\d*)\s*(?:m2|mts2|metros|mts)', texto, re.IGNORECASE)
    if match: 
        numero_limpio = match.group(1).replace(",", ".")
        try: return float(numero_limpio)
        except: return 0.0
    return 0.0

def mover_archivo(carpeta_destino):
    time.sleep(2) 
    lista = glob.glob(os.path.join(TEMP_DOWNLOAD_DIR, "*"))
    validos = [f for f in lista if not f.endswith(".crdownload") and not f.endswith(".tmp")]
    if not validos: return False
    
    nuevo = max(validos, key=os.path.getctime)
    if not os.path.exists(carpeta_destino): os.makedirs(carpeta_destino)
    
    nombre_base = os.path.basename(nuevo)
    destino = os.path.join(carpeta_destino, nombre_base)
    try:
        if os.path.exists(destino): os.remove(destino)
        shutil.move(nuevo, destino)
        print(f"      [DESCARGA OK] {nombre_base}")
        return True
    except: return False

def descargar_pdf_por_url(url, carpeta_destino, cookies_selenium, nombre_sugerido="documento.pdf"):
    print(f"         [PLAN B] Descarga directa URL...")
    try:
        if not os.path.exists(carpeta_destino): os.makedirs(carpeta_destino)
        session = requests.Session()
        for cookie in cookies_selenium:
            session.cookies.set(cookie['name'], cookie['value'])
        
        response = session.get(url, stream=True, verify=False)
        nombre_archivo = nombre_sugerido
        if "Content-Disposition" in response.headers:
            fname = re.findall("filename=(.+)", response.headers["Content-Disposition"])
            if fname: nombre_archivo = fname[0].strip('"')

        ruta_final = os.path.join(carpeta_destino, nombre_archivo)
        with open(ruta_final, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"      [DESCARGA OK - DIRECTO] {nombre_archivo}")
        return True
    except: return False

def click_js(driver, elemento):
    driver.execute_script("arguments[0].scrollIntoView();", elemento)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", elemento)

def volver_atras(driver):
    """Intenta volver atrás de forma inteligente."""
    try:
        # Intenta buscar migas de pan genéricas (cualquier enlace en el header azul)
        migas = driver.find_elements(By.CSS_SELECTOR, ".ui-breadcrumb a")
        if len(migas) > 1:
            # Clic en el penúltimo (el nivel anterior al actual)
            click_js(driver, migas[-2])
            time.sleep(4)
            return
    except: pass
    
    # Si falla, usa navegador
    driver.back()
    time.sleep(4)

# ==========================================
# NAVEGACIÓN "SABUESO" (BUSCADOR DE AÑO)
# ==========================================

def es_carpeta_valida(texto):
    texto = texto.lower()
    for ban in CARPETAS_IGNORAR:
        if ban in texto: return False
    return True

def buscar_ruta_hacia_anio(driver, anio_objetivo, profundidad=0):
    """
    Función RECURSIVA que busca el año.
    1. ¿Está el año aquí? -> Entra y retorna True.
    2. Si no, ¿Hay carpetas prometedoras (Obras, Permisos)? -> Entra, busca adentro, y si no está, vuelve y prueba la siguiente.
    """
    if profundidad > 2: return False # No bajar más de 2 niveles para no perderse

    # 1. Buscar AÑO directamente
    links = driver.find_elements(By.TAG_NAME, "a")
    for l in links:
        try:
            if l.is_displayed() and anio_objetivo in l.text:
                # Validar que no sea un Convenio falso
                if es_carpeta_valida(l.text) and len(l.text) < 25:
                    print(f"  🎯 ¡AÑO {anio_objetivo} ENCONTRADO!: {l.text}")
                    click_js(driver, l)
                    time.sleep(3)
                    return True
        except: pass

    # 2. Si no está el año, buscar CARPETAS PISTA
    # Recopilamos candidatos para no perder referencias al navegar
    candidatos = []
    links = driver.find_elements(By.TAG_NAME, "a")
    
    # Debug visual para saber qué ve el robot
    nombres_visibles = []
    
    for l in links:
        try:
            if l.is_displayed():
                txt = l.text.strip()
                if not txt: continue
                nombres_visibles.append(txt)
                
                # Chequeo: Contiene palabra pista Y NO está prohibida
                if any(pista in txt.lower() for pista in CARPETAS_PISTA) and es_carpeta_valida(txt):
                    candidatos.append(txt)
        except: pass
    
    # Deduplicar
    candidatos = sorted(list(set(candidatos)))
    
    if profundidad == 0:
        print(f"  👀 Veo estas carpetas posibles: {candidatos}")

    # 3. Explorar candidatos
    for carpeta in candidatos:
        print(f"  🔎 Explorando nivel {profundidad}: {carpeta}...")
        
        # Volver a encontrar el elemento (el DOM cambia al volver atrás)
        try:
            elem = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, carpeta)))
            click_js(driver, elem)
            time.sleep(3)
            
            # RECURSIÓN: Buscar el año aquí adentro
            if buscar_ruta_hacia_anio(driver, anio_objetivo, profundidad + 1):
                return True # ¡Lo encontramos adentro!
            
            # Si no estaba, volver atrás y probar siguiente candidato
            print(f"  ↩️ No estaba en {carpeta}, volviendo...")
            volver_atras(driver)
            
        except Exception as e:
            print(f"     Error entrando a {carpeta}: {e}")
            try: volver_atras(driver) 
            except: pass

    return False

# ==========================================
# PROCESAMIENTO DE ARCHIVOS (PDF/TABLAS)
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
            metros = extraer_metros(txt)
            if metros < MIN_METROS: continue
            if not any(k in txt for k in KEYWORDS): continue
            
            print(f"      ★ CANDIDATO: {metros} m2")
            ruta_destino = os.path.join(BASE_DIR, nombre_comuna, anio, mes)
            
            # Clic flexible
            try: link = fila.find_element(By.PARTIAL_LINK_TEXT, "Enlace")
            except:
                try: link = fila.find_element(By.PARTIAL_LINK_TEXT, "Ver")
                except: 
                    links_row = fila.find_elements(By.TAG_NAME, "a")
                    if links_row: link = links_row[-1]
                    else: continue

            click_js(driver, link)
            time.sleep(3)
            
            # Manejo Pestaña/PDF
            ventanas_ahora = driver.window_handles
            if len(ventanas_ahora) > len(ventanas_antes):
                new_win = [v for v in ventanas_ahora if v not in ventanas_antes][0]
                driver.switch_to.window(new_win)
                if descargar_pdf_por_url(driver.current_url, ruta_destino, driver.get_cookies()): descargas += 1
                driver.close(); driver.switch_to.window(ventana_principal)
            elif driver.current_url.endswith(".pdf"):
                descargar_pdf_por_url(driver.current_url, ruta_destino, driver.get_cookies())
                driver.back()
            else:
                for _ in range(5):
                    if mover_archivo(ruta_destino): descargas += 1; break
                    time.sleep(1)
        except: 
            if len(driver.window_handles) > len(ventanas_antes):
                driver.close(); driver.switch_to.window(ventana_principal)
            continue
    return descargas

def procesar_contenido_del_mes(driver, nombre_comuna, anio, mes):
    # 1. PDF Directo
    if driver.current_url.endswith(".pdf") or "drive.google" in driver.current_url:
        print("      ⚠️ PDF/Drive Directo detectado.")
        ruta = os.path.join(BASE_DIR, nombre_comuna, anio, mes)
        if "drive.google" not in driver.current_url:
            descargar_pdf_por_url(driver.current_url, ruta, driver.get_cookies(), f"Doc_{mes}.pdf")
        driver.back(); return 1

    # 2. Tabla o Subcarpetas
    filas = len(driver.find_elements(By.TAG_NAME, "tr"))
    total = 0
    
    if filas > 3:
        total += analizar_tabla_final(driver, nombre_comuna, anio, mes)
    else:
        # Subcarpetas
        sub_interes = ["edificación", "regularización", "obra menor", "permiso"]
        links = driver.find_elements(By.TAG_NAME, "a")
        candidatos = set()
        for l in links:
            try:
                if l.is_displayed() and es_carpeta_valida(l.text):
                    if any(k in l.text.lower() for k in sub_interes):
                        candidatos.add(l.text)
            except: pass
        
        for sub in sorted(list(candidatos)):
            print(f"      -> Subcarpeta: {sub}")
            try:
                elem = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, sub)))
                click_js(driver, elem)
                time.sleep(3)
                # Recursividad simple (solo 1 nivel más)
                if driver.current_url.endswith(".pdf"):
                    descargar_pdf_por_url(driver.current_url, os.path.join(BASE_DIR, nombre_comuna, anio, mes), driver.get_cookies(), f"{sub}.pdf")
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
        # 1. Inicio
        driver.get("https://www.portaltransparencia.cl/")
        time.sleep(2)
        try:
            s = wait.until(EC.element_to_be_clickable((By.ID, "cuadroBusqueda")))
            s.clear(); s.send_keys(f"Municipalidad de {nombre_comuna}"); time.sleep(1); s.send_keys(Keys.ENTER)
        except: input("⚠️ BUSCA MANUALMENTE Y ENTER...")

        # 2. Resultado
        time.sleep(3)
        try:
            xp = f"//p[contains(@class, 'entry-body__title') and contains(text(), '{nombre_comuna}')]"
            res = wait.until(EC.element_to_be_clickable((By.XPATH, xp))); click_js(driver, res)
        except: input("⚠️ CLIC EN LA MUNI Y ENTER...")

        # 3. Pestaña
        try:
            wait.until(EC.number_of_windows_to_be(2))
            driver.switch_to.window(driver.window_handles[-1])
            time.sleep(4)
        except: pass

        # 4. Punto 7
        try:
            xp7 = "//a[contains(text(), 'Efectos sobre Terceros') or contains(text(), 'efectos sobre terceros')]"
            l7 = wait.until(EC.presence_of_element_located((By.XPATH, xp7))); click_js(driver, l7)
        except: input("⚠️ ENTRA AL PUNTO 7 Y ENTER...")

        time.sleep(3)
        
        # 5. BUCLE DE AÑOS (Aquí está la magia V14)
        total_comuna = 0
        for anio in ["2024", "2025"]:
            print(f"--- Buscando Año {anio} ---")
            
            # Llamamos al sabueso
            encontrado = buscar_ruta_hacia_anio(driver, anio, profundidad=0)
            
            if encontrado:
                # Procesar Meses
                meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
                         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
                for mes in meses:
                    # Buscar mes
                    xp_mes = f"//a[contains(translate(text(), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{mes.upper()}')]"
                    elems = driver.find_elements(By.XPATH, xp_mes)
                    l_mes = None
                    for e in elems:
                        if e.is_displayed(): l_mes = e; break
                    
                    if l_mes:
                        print(f"    📂 {mes}...")
                        click_js(driver, l_mes); time.sleep(3)
                        total_comuna += procesar_contenido_del_mes(driver, nombre_comuna, anio, mes)
                        volver_atras(driver)
                
                # Volver al inicio de Punto 7 para buscar el siguiente año limpio
                # Es más seguro reiniciar la búsqueda desde la raíz de Point 7 que tratar de subir niveles exactos
                print("    🔄 Reiniciando a Punto 7 para siguiente año...")
                try:
                    xp7 = "//a[contains(text(), 'Efectos sobre Terceros')]"
                    driver.find_element(By.XPATH, xp7).click() # Si hay breadcrumb al root
                except:
                    # Si no hay link directo, back() varias veces hasta ver el menú principal
                    for _ in range(3):
                        try: 
                            if len(driver.find_elements(By.PARTIAL_LINK_TEXT, "Dirección de Obras")) > 0: break
                            driver.back(); time.sleep(2)
                        except: pass
                time.sleep(3)
            else:
                print(f"    ❌ No se encontró el Año {anio} tras búsqueda profunda.")

        print(f"✅ Fin {nombre_comuna}. Total: {total_comuna}")

    except Exception as e: print(f"❌ Error {nombre_comuna}: {e}")
    finally:
        try:
            if len(driver.window_handles) > 1: driver.close(); driver.switch_to.window(main_win)
        except: pass

def main():
    driver = configurar_driver()
    print("--- ROBOT V14 UNIVERSAL: BÚSQUEDA PROFUNDA ---")
    for c in COMUNAS: procesar_comuna(driver, c)
    driver.quit()

if __name__ == "__main__":
    main()