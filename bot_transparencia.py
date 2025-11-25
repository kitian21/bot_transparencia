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
    #"Cerrillos", "Cerro Navia", "Conchalí", "El Bosque", "Estación Central", 
    "Huechuraba",
    #"Independencia", "La Cisterna", "La Florida", "La Granja", 
    #"La Pintana", "La Reina", "Las Condes", "Lo Barnechea", "Lo Espejo", 
    #"Lo Prado", "Macul", "Maipú", "Ñuñoa", "Pedro Aguirre Cerda", "Peñalolén", 
    #"Providencia", "Pudahuel", "Quilicura", "Quinta Normal", "Recoleta", 
    #"Renca", "San Joaquín", "San Miguel", "San Ramón", "Santiago", "Vitacura"
]

KEYWORDS = ["ampliación", "remodelación", "modificación", "obra nueva", "regularización", "edificación", "obra menor"]
MIN_METROS = 200.0

# Lista negra de carpetas
CARPETAS_IGNORAR = [
    "Urbanización", "Ley 20.898", "20.898", "Cuentas", "Loteo", 
    "Subdivisión", "Copropiedad", "Certificados", "Recepción", 
    "Anteproyecto", "Paralización", "Demolición",
    "Convenio", "Decreto", "Nómina", "Contrato", "Adjudicación", "Sistema"
]

TEMP_DOWNLOAD_DIR = os.path.join(BASE_DIR, "Temp_Descargas")

# ==========================================
# HERRAMIENTAS BÁSICAS
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
    print(f"         [PLAN B] Descargando URL directa...")
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
    except Exception as e:
        print(f"      [ERROR PLAN B] {e}")
        return False

def click_js(driver, elemento):
    try:
        driver.execute_script("arguments[0].scrollIntoView();", elemento)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", elemento)
    except: pass

def es_enlace_valido(texto_enlace):
    for prohibida in CARPETAS_IGNORAR:
        if prohibida.lower() in texto_enlace.lower():
            return False
    return True

# ==========================================
# LÓGICA DE RECUPERACIÓN (NUEVO)
# ==========================================

def restaurar_ruta_si_es_necesario(driver, anio_objetivo):
    """
    Verifica si estamos en la carpeta del año. Si no (porque el back nos sacó),
    vuelve a entrar desde el principio (DOM -> Permisos -> Año).
    """
    # 1. Verificar si vemos los meses (Señal de que estamos bien)
    try:
        # Buscamos si "Enero" o "Marzo" están visibles
        if len(driver.find_elements(By.PARTIAL_LINK_TEXT, "Enero")) > 0 or \
           len(driver.find_elements(By.PARTIAL_LINK_TEXT, "Marzo")) > 0:
            return True # Estamos bien
    except: pass

    print("    ⚠️ ¡ALERTA! Parece que me salí de la carpeta del año. RECONECTANDO...")
    time.sleep(2)

    # 2. Si estamos perdidos (en Point 7), reingresamos
    # Paso A: Dirección de Obras
    nombres_dom = ["Dirección de Obras", "Obras Municipales", "Urbanización"]
    encontrado_dom = False
    links = driver.find_elements(By.TAG_NAME, "a")
    for l in links:
        try:
            if l.is_displayed() and any(n in l.text for n in nombres_dom):
                click_js(driver, l)
                encontrado_dom = True
                time.sleep(3)
                break
        except: pass
    
    # Paso B: Permisos
    nombres_permisos = ["Permisos de Obras", "Permisos de Edificación", "Edificación"]
    links = driver.find_elements(By.TAG_NAME, "a")
    for l in links:
        try:
            if l.is_displayed():
                txt = l.text.strip()
                if any(n in txt for n in nombres_permisos) and es_enlace_valido(txt):
                    click_js(driver, l)
                    time.sleep(3)
                    break
        except: pass

    # Paso C: Año
    links = driver.find_elements(By.TAG_NAME, "a")
    for l in links:
        try:
            if l.is_displayed():
                txt = l.text.strip()
                if anio_objetivo in txt and es_enlace_valido(txt):
                    click_js(driver, l)
                    time.sleep(3)
                    print(f"    ✅ Ruta restaurada al año {anio_objetivo}.")
                    return True
        except: pass
    
    print("    ❌ No pude restaurar la ruta automáticamente.")
    return False

def volver_al_nivel_superior(driver, texto_nivel):
    """Intenta volver con migas, si no con back."""
    print(f"    << Intentando volver a: {texto_nivel}...")
    try:
        xpath_ruta = f"//a[contains(text(), '{texto_nivel}')]"
        link_retorno = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath_ruta)))
        click_js(driver, link_retorno)
        time.sleep(4) 
        return True
    except: 
        print("       (Usando navegador ATRÁS)")
        driver.back()
        time.sleep(4)
        return False

# ==========================================
# PROCESAMIENTO
# ==========================================

def analizar_tabla_final(driver, nombre_comuna, anio, mes):
    try:
        WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
    except: return 0 

    filas = driver.find_elements(By.TAG_NAME, "tr")
    descargas = 0
    
    # Guardar contexto de ventana
    ventana_principal = driver.current_window_handle
    ventanas_antes = driver.window_handles
    
    print(f"      -> Analizando {len(filas)} filas...")
    
    for fila in filas:
        try:
            txt = limpiar_texto(fila.text)
            metros = extraer_metros(txt)
            if metros < MIN_METROS: continue
            if not any(k in txt for k in KEYWORDS): continue
            
            print(f"      ★ CANDIDATO: {metros} m2")
            ruta_destino = os.path.join(BASE_DIR, nombre_comuna, anio, mes)
            
            # Intentar Clic
            try: link = fila.find_element(By.PARTIAL_LINK_TEXT, "Enlace")
            except:
                try: link = fila.find_element(By.PARTIAL_LINK_TEXT, "Ver")
                except: 
                    try:
                        links_fila = fila.find_elements(By.TAG_NAME, "a")
                        if links_fila: link = links_fila[-1]
                        else: continue
                    except: continue

            click_js(driver, link)
            time.sleep(3)
            
            # CHEQUEO: ¿Se abrió pestaña nueva?
            ventanas_ahora = driver.window_handles
            if len(ventanas_ahora) > len(ventanas_antes):
                nueva_ventana = [v for v in ventanas_ahora if v not in ventanas_antes][0]
                driver.switch_to.window(nueva_ventana)
                
                # Descargar PDF
                url_pdf = driver.current_url
                cookies = driver.get_cookies()
                if descargar_pdf_por_url(url_pdf, ruta_destino, cookies): descargas += 1
                
                # Cerrar y volver
                driver.close()
                driver.switch_to.window(ventana_principal)
            else:
                # CHEQUEO: ¿Cambió la URL en la misma ventana (PDF directo)?
                if driver.current_url.endswith(".pdf"):
                    descargar_pdf_por_url(driver.current_url, ruta_destino, driver.get_cookies())
                    driver.back() # Volver a la tabla
                else:
                    # Descarga normal
                    for _ in range(5):
                        if mover_archivo(ruta_destino):
                            descargas += 1
                            break
                        time.sleep(1)
        except Exception as e: 
            # Recuperación de emergencia
            if len(driver.window_handles) > len(ventanas_antes):
                driver.close(); driver.switch_to.window(ventana_principal)
            continue
    return descargas

def procesar_contenido_del_mes(driver, nombre_comuna, anio, mes):
    total_descargas = 0
    wait = WebDriverWait(driver, 5)
    
    # 1. Detectar PDF Directo (Caso Huechuraba)
    url_actual = driver.current_url.lower()
    if url_actual.endswith(".pdf") or "drive.google" in url_actual:
        print("      ⚠️ EL MES ES UN PDF DIRECTO.")
        ruta = os.path.join(BASE_DIR, nombre_comuna, anio, mes)
        nombre = f"Documento_{mes}_{anio}.pdf"
        
        if "drive.google" in url_actual:
            print("      [!] Drive detectado (saltando).")
        else:
            descargar_pdf_por_url(driver.current_url, ruta, driver.get_cookies(), nombre)
        
        driver.back() # Volver obligatorio
        return 1

    # 2. Detectar Tabla
    filas_tabla = len(driver.find_elements(By.TAG_NAME, "tr"))
    
    if filas_tabla > 3:
        total_descargas += analizar_tabla_final(driver, nombre_comuna, anio, mes)
    else:
        # 3. Detectar Subcarpetas
        print("      (Buscando subcarpetas...)")
        subcarpetas_interes = ["Permiso de Edificación", "Regularización", "Edificación", "Obra Menor"]
        links_potenciales = driver.find_elements(By.TAG_NAME, "a")
        nombres_validos = set() 
        for l in links_potenciales:
            try:
                if l.is_displayed():
                    texto = l.text.strip()
                    if es_enlace_valido(texto):
                        if any(k in texto for k in subcarpetas_interes):
                            nombres_validos.add(texto)
            except: pass
        
        lista_a_procesar = sorted(list(nombres_validos))
        for nombre_sub in lista_a_procesar:
            print(f"      -> Entrando a: {nombre_sub}")
            try:
                xpath_sub = f"//a[contains(text(), '{nombre_sub}')]"
                link_click = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_sub)))
                click_js(driver, link_click)
                time.sleep(3)
                
                total_descargas += analizar_tabla_final(driver, nombre_comuna, anio, mes)
                volver_al_nivel_superior(driver, mes.upper())
            except: volver_al_nivel_superior(driver, mes.upper())
            
    return total_descargas

def procesar_anios_y_meses(driver, nombre_comuna):
    total_comuna = 0
    anios_target = ["2024", "2025"]
    
    for anio in anios_target:
        print(f"  📂 Buscando carpeta Año {anio}...")
        
        # Búsqueda inteligente de año
        encontrado_anio = False
        links = driver.find_elements(By.TAG_NAME, "a")
        for l in links:
            try:
                if l.is_displayed() and anio in l.text and es_enlace_valido(l.text):
                    click_js(driver, l)
                    encontrado_anio = True
                    time.sleep(3)
                    break
            except: pass
        
        if not encontrado_anio:
            print(f"    (No encontré carpeta {anio})")
            continue

        meses_nombres = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
                         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        
        for mes in meses_nombres:
            # --- AUTO-RECUPERACIÓN ---
            # Antes de buscar el mes, verificamos si seguimos en el año. Si no, volvemos.
            restaurar_ruta_si_es_necesario(driver, anio)
            
            # Ahora sí, buscamos el mes
            xpath_mes = f"//a[contains(translate(text(), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{mes.upper()}')]"
            elems_mes = driver.find_elements(By.XPATH, xpath_mes)
            link_mes = None
            for e in elems_mes:
                if e.is_displayed(): link_mes = e; break
            
            if link_mes:
                print(f"    📂 Entrando a {mes}...")
                click_js(driver, link_mes)
                time.sleep(3)
                
                total_comuna += procesar_contenido_del_mes(driver, nombre_comuna, anio, mes)
                
                # Intentamos volver con migas, si falla usa back
                if not volver_al_nivel_superior(driver, anio):
                    # Si volver falló mucho, la siguiente iteración de 'mes' activará 'restaurar_ruta'
                    pass

        # Salir del año
        if not volver_al_nivel_superior(driver, "Permisos de Obras"):
             if not volver_al_nivel_superior(driver, "Edificación"):
                 volver_al_nivel_superior(driver, "Dirección de Obras")
        time.sleep(2)

    return total_comuna

# ==========================================
# FLUJO PRINCIPAL
# ==========================================
def procesar_comuna(driver, nombre_comuna):
    print(f"\n{'='*40}")
    print(f" PROCESANDO: {nombre_comuna}")
    print(f"{'='*40}")
    wait = WebDriverWait(driver, 15)
    ventana_main = driver.current_window_handle
    
    try:
        driver.get("https://www.portaltransparencia.cl/")
        time.sleep(2)
        try:
            s = wait.until(EC.element_to_be_clickable((By.ID, "cuadroBusqueda")))
            s.clear(); s.send_keys(f"Municipalidad de {nombre_comuna}"); time.sleep(1); s.send_keys(Keys.ENTER)
        except: input("⚠️ HAZ BÚSQUEDA MANUAL Y ENTER...")

        time.sleep(3)
        try:
            xpath = f"//p[contains(@class, 'entry-body__title') and contains(text(), '{nombre_comuna}')]"
            res = wait.until(EC.element_to_be_clickable((By.XPATH, xpath))); click_js(driver, res)
        except: input("⚠️ HAZ CLIC EN LA MUNI Y ENTER...")

        try:
            wait.until(EC.number_of_windows_to_be(2))
            driver.switch_to.window(driver.window_handles[-1])
            time.sleep(4)
        except: pass

        try:
            xpath7 = "//a[contains(text(), 'Efectos sobre Terceros') or contains(text(), 'efectos sobre terceros')]"
            l7 = wait.until(EC.presence_of_element_located((By.XPATH, xpath7))); click_js(driver, l7)
        except: input("⚠️ ENTRA AL PUNTO 7 Y ENTER...")

        time.sleep(3)
        # Nivel 1 y 2 (Simplificado con búsqueda en cascada)
        
        # Intento 1: Buscar DOM
        encontrado = False
        nombres_dom = ["Dirección de Obras", "Obras Municipales", "Urbanización"]
        links = driver.find_elements(By.TAG_NAME, "a")
        for l in links:
            try:
                if l.is_displayed() and any(n in l.text for n in nombres_dom):
                    click_js(driver, l); encontrado = True; time.sleep(3); break
            except: pass
            
        # Intento 2: Buscar Permisos (dentro de DOM o directo)
        nombres_permisos = ["Permisos de Obras", "Permisos de Edificación", "Edificación", "Urbanización"]
        links = driver.find_elements(By.TAG_NAME, "a")
        permiso_ok = False
        for l in links:
            try:
                txt = l.text.strip()
                if l.is_displayed() and any(n in txt for n in nombres_permisos) and es_enlace_valido(txt):
                    click_js(driver, l); permiso_ok = True; time.sleep(3); break
            except: pass
            
        if not permiso_ok:
            print("⚠️ No encontré carpeta 'Permisos'. Buscando Años directo...")

        total = procesar_anios_y_meses(driver, nombre_comuna)
        print(f"✅ Fin {nombre_comuna}. Total: {total}")

    except Exception as e:
        print(f"❌ Error en {nombre_comuna}: {e}")
    
    finally:
        try:
            if len(driver.window_handles) > 1:
                driver.close(); driver.switch_to.window(ventana_main)
        except: pass

def main():
    driver = configurar_driver()
    print("--- ROBOT V13: AUTO-RECUPERACIÓN DE RUTA ---")
    for c in COMUNAS:
        procesar_comuna(driver, c)
    driver.quit()

if __name__ == "__main__":
    main()