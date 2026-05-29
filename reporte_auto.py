# ══════════════════════════════════════════════════════
#  reporte_auto.py — TODO EN UNO
#  1. Abre Power BI con Chrome
#  2. Exporta el reporte como PDF
#  3. Lo envía por Office 365
#  4. Se ejecuta automáticamente todos los días
#
#  pip install selenium webdriver-manager schedule
# ══════════════════════════════════════════════════════

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import smtplib, time, os, schedule
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

# ┌─────────────────────────────────────────────────────┐
# │  EDITA SOLO ESTA SECCIÓN                            │
# └─────────────────────────────────────────────────────┘
USUARIO       = "tu@empresa.com"
PASSWORD      = "TuContraseña"          # si tienes MFA usa contraseña de aplicación
URL_REPORTE   = "https://app.powerbi.com/groups/WORKSPACE_ID/reports/REPORT_ID"
DESCARGA_DIR  = r"C:\reportes"

DESTINATARIOS = ["destino1@empresa.com", "destino2@empresa.com"]
ASUNTO        = "Reporte Power BI — Exportación Automática"
CUERPO        = "Hola,\n\nAdjunto el reporte de Power BI generado automáticamente.\n\nSaludos."
HORA_ENVIO    = "08:00"                 # HH:MM — hora de envío diario
# ──────────────────────────────────────────────────────


def exportar_pdf():
    os.makedirs(DESCARGA_DIR, exist_ok=True)
    ops = webdriver.ChromeOptions()
    ops.add_experimental_option("prefs", {
        "download.default_directory": DESCARGA_DIR,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    })
    # ops.add_argument("--headless=new")  # descomentar para correr sin ventana

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=ops)
    wait   = WebDriverWait(driver, 40)

    try:
        print("  → Iniciando sesión en Power BI...")
        driver.get("https://app.powerbi.com")
        wait.until(EC.presence_of_element_located((By.NAME, "loginfmt")))
        driver.find_element(By.NAME, "loginfmt").send_keys(USUARIO)
        driver.find_element(By.ID, "idSIButton9").click()
        time.sleep(2)
        wait.until(EC.presence_of_element_located((By.NAME, "passwd")))
        driver.find_element(By.NAME, "passwd").send_keys(PASSWORD)
        driver.find_element(By.ID, "idSIButton9").click()
        time.sleep(3)
        try:
            driver.find_element(By.ID, "idBtn_Back").click()  # "¿Mantener sesión?" → No
        except Exception:
            pass

        print("  → Abriendo reporte...")
        driver.get(URL_REPORTE)
        time.sleep(7)

        print("  → Exportando PDF...")
        wait.until(EC.element_to_be_clickable((
            By.XPATH, "//button[contains(@aria-label,'Exportar') or contains(@aria-label,'Export')]"
        ))).click()
        time.sleep(1)
        wait.until(EC.element_to_be_clickable((
            By.XPATH, "//*[contains(text(),'PDF')]"
        ))).click()
        time.sleep(12)

    finally:
        driver.quit()

    pdfs = [f for f in os.listdir(DESCARGA_DIR) if f.endswith(".pdf")]
    if not pdfs:
        raise FileNotFoundError(f"No se encontró PDF en {DESCARGA_DIR}")
    ruta = max([os.path.join(DESCARGA_DIR, f) for f in pdfs], key=os.path.getctime)
    print(f"  → PDF listo: {ruta}")
    return ruta


def enviar_correo(ruta_pdf):
    nombre = f"Reporte_PowerBI_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    msg = MIMEMultipart()
    msg["From"]    = USUARIO
    msg["To"]      = ", ".join(DESTINATARIOS)
    msg["Subject"] = ASUNTO
    msg.attach(MIMEText(CUERPO, "plain", "utf-8"))

    with open(ruta_pdf, "rb") as f:
        adj = MIMEBase("application", "octet-stream")
        adj.set_payload(f.read())
    encoders.encode_base64(adj)
    adj.add_header("Content-Disposition", f"attachment; filename={nombre}")
    msg.attach(adj)

    print("  → Enviando correo...")
    with smtplib.SMTP("smtp.office365.com", 587, timeout=30) as srv:
        srv.ehlo()
        srv.starttls()
        srv.login(USUARIO, PASSWORD)
        srv.sendmail(USUARIO, DESTINATARIOS, msg.as_string())
    print(f"  → Correo enviado a: {', '.join(DESTINATARIOS)}")


def tarea():
    print(f"\n{'─'*50}")
    print(f"  Iniciando: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'─'*50}")
    try:
        pdf = exportar_pdf()
        enviar_correo(pdf)
        print("  ✓ Proceso completado.\n")
    except Exception as e:
        print(f"  ✗ Error: {e}\n")


# ── Arranque ───────────────────────────────────────────
if __name__ == "__main__":
    print(f"Automatización activa — envío diario a las {HORA_ENVIO}")
    print("Ctrl+C para detener.\n")

    schedule.every().day.at(HORA_ENVIO).do(tarea)

    # Descomenta para ejecutar ahora mismo (prueba):
    # tarea()

    while True:
        schedule.run_pending()
        time.sleep(30)
