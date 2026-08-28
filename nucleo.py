import os
import re
import sys
import json
import glob
import html
import hmac
import shutil
import socket
import hashlib
import subprocess
import unicodedata
from datetime import datetime

try:
    import psutil
    import wmi
except ImportError as e:
    raise RuntimeError(f"Falta una dependencia ({e.name}). Instala con: pip install psutil WMI")


VERSION = "3.12"

TECNICO_SECRETO = "OptiChek-lic-2026#T3c"

UMBRAL_BATERIA_ATENCION = 60
UMBRAL_BATERIA_PROBLEMA = 35
UMBRAL_INICIO_ATENCION = 10
UMBRAL_INICIO_PROBLEMA = 20
UMBRAL_RAM_ATENCION = 90
UMBRAL_LIBRE_PCT_ATENCION = 15
UMBRAL_LIBRE_GB_PROBLEMA = 5
UMBRAL_UPTIME_HORAS = 168
TEMP_MAX_ATENCION = 85
TEMP_MAX_PROBLEMA = 95

SEV_ORDEN = {"problema": 0, "atencion": 1, "ok": 2, "info": 3}


def es_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def recurso(nombre):
    pkg = getattr(sys, "_MEIPASS", None)
    if pkg and os.path.exists(os.path.join(pkg, nombre)):
        return os.path.join(pkg, nombre)
    return os.path.join(base_dir(), nombre)


def ruta_config():
    return os.path.join(base_dir(), "config.json")


def leer_config():
    try:
        with open(ruta_config(), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _norm_tecnico(nombre):
    return "".join((nombre or "").upper().split())


def _clave_tecnico_esperada(nombre):
    d = hmac.new(TECNICO_SECRETO.encode(), _norm_tecnico(nombre).encode(), hashlib.sha256).hexdigest().upper()
    return d[:12]


def generar_clave_tecnico(nombre):
    k = _clave_tecnico_esperada(nombre)
    return f"{k[:4]}-{k[4:8]}-{k[8:12]}"


def clave_tecnico_valida(nombre, clave):
    k = (clave or "").replace("-", "").replace(" ", "").upper()
    return bool(_norm_tecnico(nombre)) and k == _clave_tecnico_esperada(nombre)


def activar_tecnico(nombre, clave):
    if not _norm_tecnico(nombre):
        raise ValueError("El nombre del tecnico es obligatorio.")
    if not clave_tecnico_valida(nombre, clave):
        raise ValueError("Clave de licencia invalida para ese nombre.")
    cfg = leer_config()
    cfg["tecnico_nombre"] = (nombre or "").strip()
    cfg["tecnico_clave"] = (clave or "").strip().upper()
    escribir_config(cfg)


def desactivar_tecnico():
    cfg = leer_config()
    for k in ("tecnico_nombre", "tecnico_clave", "tecnico_logo", "tecnico_whatsapp"):
        cfg.pop(k, None)
    escribir_config(cfg)


def guardar_tecnico(logo="", whatsapp=""):
    cfg = leer_config()
    cfg["tecnico_logo"] = (logo or "").strip()
    cfg["tecnico_whatsapp"] = (whatsapp or "").strip()
    escribir_config(cfg)


def tecnico_licenciado():
    cfg = leer_config()
    nombre = (cfg.get("tecnico_nombre") or "").strip()
    clave = (cfg.get("tecnico_clave") or "").strip()
    if not nombre or not clave or not clave_tecnico_valida(nombre, clave):
        return None
    return {
        "nombre": nombre,
        "logo": (cfg.get("tecnico_logo") or "").strip(),
        "whatsapp": (cfg.get("tecnico_whatsapp") or "").strip(),
    }


def escribir_config(cfg):
    try:
        with open(ruta_config(), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=4, ensure_ascii=False)
    except Exception:
        pass


def dir_raiz_servicios():
    carpeta = os.path.join(base_dir(), "servicios")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def crear_servicio(cliente, tecnico=""):
    cliente = (cliente or "").strip()
    if not cliente:
        raise ValueError("El nombre del cliente es obligatorio.")
    ahora = datetime.now()
    prefijo = ahora.strftime("SRV-%Y%m%d-")
    existentes = [d for d in os.listdir(dir_raiz_servicios()) if re.match(rf"^{prefijo}\d{{3}}$", d)]
    num = len(existentes) + 1
    sid = f"{prefijo}{num:03d}"
    carpeta = os.path.join(dir_raiz_servicios(), sid)
    os.makedirs(os.path.join(carpeta, "escaneos"), exist_ok=True)
    meta = {
        "Id": sid,
        "Cliente": cliente,
        "Tecnico": (tecnico or "").strip(),
        "Creado": ahora.strftime("%d/%m/%Y %H:%M"),
    }
    with open(os.path.join(carpeta, "servicio.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=4, ensure_ascii=False)
    cfg = leer_config()
    cfg["ultimo_servicio"] = sid
    cfg["ultimo_tecnico"] = meta["Tecnico"]
    escribir_config(cfg)
    return sid


def cargar_servicio(sid):
    if not sid or not re.match(r"^SRV-\d{8}-\d{3}$", sid):
        return None
    arch = os.path.join(dir_raiz_servicios(), sid, "servicio.json")
    try:
        with open(arch, "r", encoding="utf-8") as fh:
            meta = json.load(fh)
        return meta if isinstance(meta, dict) else None
    except Exception:
        return None


def listar_servicios():
    items = []
    for d in sorted(os.listdir(dir_raiz_servicios()), reverse=True):
        meta = cargar_servicio(d)
        if meta:
            meta["Num_Escaneos"] = len(glob.glob(os.path.join(dir_raiz_servicios(), d, "escaneos", "escaneo_*.json")))
            items.append(meta)
    return items


def dir_escaneos(sid):
    carpeta = os.path.join(dir_raiz_servicios(), sid, "escaneos")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def _guardar_meta_servicio(sid, meta):
    arch = os.path.join(dir_raiz_servicios(), sid, "servicio.json")
    try:
        with open(arch, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=4, ensure_ascii=False)
    except Exception:
        pass


def guardar_escaneo(datos, sid, nombre=""):
    nums = []
    for f in glob.glob(os.path.join(dir_escaneos(sid), "escaneo_*.json")):
        m = re.search(r"escaneo_(\d+)_", os.path.basename(f))
        if m:
            nums.append(int(m.group(1)))
    meta = cargar_servicio(sid) or {}
    ultimo_usado = int(meta.get("Ultimo_Num", 0)) if isinstance(meta, dict) else 0
    max_existente = max(nums) if nums else 0
    num = max(ultimo_usado, max_existente) + 1
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo = os.path.join(dir_escaneos(sid), f"escaneo_{num:03d}_{stamp}.json")
    datos["Servicio"] = sid
    nombre = (nombre or "").strip()
    datos["Nombre"] = nombre if nombre else f"Escaneo #{num:03d}"
    with open(archivo, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, indent=4, ensure_ascii=False)
    if isinstance(meta, dict):
        meta["Ultimo_Num"] = num
        _guardar_meta_servicio(sid, meta)
    return num, archivo


def eliminar_escaneo(sid, num):
    objetivo = None
    for f in glob.glob(os.path.join(dir_escaneos(sid), "escaneo_*.json")):
        m = re.search(r"escaneo_(\d+)_", os.path.basename(f))
        if m and int(m.group(1)) == num:
            objetivo = f
            break
    if not objetivo:
        return False
    raiz = os.path.abspath(dir_raiz_servicios())
    if not os.path.abspath(objetivo).startswith(raiz):
        return False
    try:
        os.remove(objetivo)
        return True
    except Exception:
        return False


def nombre_escaneo(datos, num=None):
    return (datos.get("Nombre") or "").strip() or (f"Escaneo #{num:03d}" if isinstance(num, int) else "Escaneo")


def cargar_historial(sid):
    items = []
    for f in glob.glob(os.path.join(dir_escaneos(sid), "escaneo_*.json")):
        m = re.search(r"escaneo_(\d+)_", os.path.basename(f))
        if not m:
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                datos = json.load(fh)
            if isinstance(datos, dict) and "Sistema" in datos:
                items.append({"num": int(m.group(1)), "archivo": f, "datos": datos})
        except Exception:
            continue
    items.sort(key=lambda x: x["num"])
    return items


def carpeta_descargas():
    try:
        import winreg
        clave = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        )
        val, _ = winreg.QueryValueEx(clave, "{374DE290-123F-4565-9164-39C4925E467B}")
        winreg.CloseKey(clave)
        ruta = os.path.expandvars(val)
        if os.path.isdir(ruta):
            return ruta
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


def slug_equipo(nombre):
    base = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^\w\-]+", "_", base).strip("_") or "PC"


def esc(s):
    return html.escape(str(s))


def fmt(v, dec=1):
    if v is None:
        return "-"
    if isinstance(v, (int, float)):
        if isinstance(v, int) or dec == 0:
            return str(v)
        return f"{v:.{dec}f}"
    return esc(v)


def obtener_sistema(c):
    so = c.Win32_OperatingSystem()[0]
    cs = c.Win32_ComputerSystem()[0]
    return {
        "Equipo": (cs.Name or socket.gethostname()).strip(),
        "Usuario": os.environ.get("USERNAME", ""),
        "Windows": so.Caption.strip(),
        "Arquitectura": so.OSArchitecture,
        "Build": so.BuildNumber,
        "Fabricante": (cs.Manufacturer or "").strip(),
        "Modelo": (cs.Model or "").strip(),
    }


def obtener_cpu(c):
    p = c.Win32_Processor()[0]
    return {
        "Modelo": p.Name.strip(),
        "Nucleos": p.NumberOfCores,
        "Hilos": p.NumberOfLogicalProcessors,
        "GHz": round(p.MaxClockSpeed / 1000.0, 2),
        "Carga_Pct": psutil.cpu_percent(interval=0.8),
    }


def obtener_ram(c):
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    modulos = []
    for m in c.Win32_PhysicalMemory():
        try:
            gb = round(int(m.Capacity) / 1024 ** 3, 1)
        except Exception:
            gb = 0
        modulos.append(f"{gb} GB - {m.Speed} MHz - {(m.Manufacturer or '').strip()}")
    return {
        "Total_GB": round(vm.total / 1024 ** 3, 2),
        "En_Uso_Pct": vm.percent,
        "Swap_Total_GB": round(sw.total / 1024 ** 3, 2),
        "Swap_En_Uso_Pct": sw.percent,
        "Modulos": modulos,
    }


def obtener_discos(c):
    discos = []
    for d in c.Win32_DiskDrive():
        try:
            gb = round(int(d.Size) / 1024 ** 3)
        except Exception:
            gb = 0
        discos.append({
            "Modelo": (d.Model or "").strip(),
            "Interfaz": d.InterfaceType or "",
            "Tamano_GB": gb,
            "SMART": (d.Status or "").strip(),
        })
    return discos


def smart_smartctl():
    exe = shutil.which("smartctl")
    if not exe:
        return {}
    res = {}
    try:
        out = subprocess.run([exe, "--scan-open"], capture_output=True, text=True, timeout=25).stdout
        for linea in out.splitlines():
            partes = linea.split()
            if not partes:
                continue
            dev = partes[0]
            try:
                r = subprocess.run([exe, "-H", dev], capture_output=True, text=True, timeout=45)
                txt = (r.stdout + r.stderr).upper()
                if "PASSED" in txt:
                    res[dev] = "OK"
                elif "FAILED" in txt:
                    res[dev] = "ERROR"
            except Exception:
                continue
    except Exception:
        pass
    return res


def agregar_smart_detallado(discos):
    det = smart_smartctl()
    if not det:
        return
    devs = sorted(det.keys())
    for i, disco in enumerate(discos):
        if i < len(devs) and disco.get("SMART") == "OK":
            disco["SMART"] = det[devs[i]] + " (smartctl)"


def obtener_particiones():
    parts = []
    for p in psutil.disk_partitions(all=False):
        if "cdrom" in p.opts.lower():
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except Exception:
            continue
        if u.total <= 0:
            continue
        parts.append({
            "Unidad": p.device.replace("\\", ""),
            "FS": p.fstype,
            "Total_GB": round(u.total / 1024 ** 3, 1),
            "Libre_GB": round(u.free / 1024 ** 3, 1),
        })
    return parts


def obtener_programas_inicio(c):
    progs = []
    for item in c.Win32_StartupCommand():
        progs.append({
            "Nombre": (item.Name or "").strip(),
            "Comando": (item.Command or "").strip(),
            "Ubicacion": (item.Location or "").strip(),
        })
    return sorted(progs, key=lambda p: p["Nombre"].lower())


def temperaturas_lhm():
    temps = []
    try:
        cw = wmi.WMI(namespace="root\\LibreHardwareMonitor")
        for s in cw.LHM_Sensor():
            if (s.SensorType or "") != "Temperature":
                continue
            try:
                val = float(s.Value)
            except Exception:
                continue
            if -50 < val < 150:
                temps.append({"Zona": (s.Name or "Sensor"), "Celsius": round(val, 1), "Fuente": "LibreHardwareMonitor"})
    except Exception:
        pass
    return temps


def temperaturas_acpi():
    temps = []
    try:
        cw = wmi.WMI(namespace="root\\WMI")
        for s in cw.MSAcpi_ThermalZoneTemperature():
            try:
                cel = round(s.CurrentTemperature / 10.0 - 273.15, 1)
                if -50 < cel < 150:
                    zona = (s.InstanceName or "Zona termica").split("\\")[-1]
                    temps.append({"Zona": zona, "Celsius": cel, "Fuente": "ACPI"})
            except Exception:
                continue
    except Exception:
        pass
    return temps


def obtener_temperaturas():
    temps = temperaturas_lhm()
    if temps:
        return temps, "LibreHardwareMonitor"
    temps = temperaturas_acpi()
    if temps:
        return temps, "ACPI"
    return [], None


def obtener_gpu(c):
    gpus = []
    for g in c.Win32_VideoController():
        gpus.append((g.Name or "").strip())
    return [g for g in gpus if g]


def obtener_placa(c):
    b = c.Win32_BaseBoard()[0]
    bios = c.Win32_BIOS()[0]
    fecha_bios = ""
    try:
        if bios.ReleaseDate:
            fecha_bios = datetime.strptime(bios.ReleaseDate.split(".")[0], "%Y%m%d%H%M%S").strftime("%d/%m/%Y")
    except Exception:
        pass
    return {
        "Placa": f"{(b.Manufacturer or '').strip()} {(b.Product or '').strip()}".strip(),
        "BIOS": (bios.SMBIOSBIOSVersion or "").strip(),
        "Fecha_BIOS": fecha_bios,
    }


def obtener_bateria():
    try:
        cw = wmi.WMI(namespace="root\\WMI")
        dis = cw.BatteryStaticData()
        full = cw.BatteryFullChargedCapacity()
        if dis and full:
            diseno = int(dis[0].DesignedCapacity)
            actual = int(full[0].FullChargedCapacity)
            if diseno > 0:
                salud = round(100 * actual / diseno, 1)
                return {"Diseno_mWh": diseno, "Actual_mWh": actual, "Salud_Pct": salud}
    except Exception:
        pass
    return None


def escanear(progreso=None):
    def paso(msg):
        if progreso:
            try:
                progreso(msg)
            except Exception:
                pass

    paso("Conectando con el sistema...")
    c = wmi.WMI()

    paso("Leyendo sistema y procesador...")
    sistema = obtener_sistema(c)
    cpu = obtener_cpu(c)

    paso("Analizando memoria RAM...")
    ram = obtener_ram(c)

    paso("Analizando discos y estado SMART...")
    discos = obtener_discos(c)
    agregar_smart_detallado(discos)
    particiones = obtener_particiones()

    paso("Leyendo programas de inicio...")
    inicio = obtener_programas_inicio(c)

    paso("Midiendo temperaturas y bateria...")
    temps, fuente_temp = obtener_temperaturas()
    gpu = obtener_gpu(c)
    placa = obtener_placa(c)
    bateria = obtener_bateria()
    uptime = round((datetime.now().timestamp() - psutil.boot_time()) / 3600, 1)

    paso("Escaneo completado")
    return {
        "Fecha": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "Sistema": sistema,
        "CPU": cpu,
        "RAM": ram,
        "Discos_Fisicos": discos,
        "Particiones": particiones,
        "Inicio": inicio,
        "Temperaturas": temps,
        "Temperatura_Fuente": fuente_temp,
        "GPU": gpu,
        "Placa": placa,
        "Bateria": bateria,
        "Uptime_Horas": uptime,
    }


def nombre_norm(s):
    s = (s or "").strip().lower()
    if s.endswith(".lnk"):
        s = s[:-4].strip()
    return s


def comando_norm(s):
    return " ".join((s or "").lower().replace('"', "").split())


def comparar_inicio(a, d):
    grupos_a, grupos_d = {}, {}
    for p in a:
        grupos_a.setdefault(nombre_norm(p.get("Nombre")), []).append(p)
    for p in d:
        grupos_d.setdefault(nombre_norm(p.get("Nombre")), []).append(p)
    eliminados, agregados, modificados = [], [], []
    for n in sorted(set(grupos_a) | set(grupos_d)):
        la = grupos_a.get(n, [])
        ld = grupos_d.get(n, [])
        m = min(len(la), len(ld))
        for i in range(m):
            if comando_norm(la[i].get("Comando")) != comando_norm(ld[i].get("Comando")):
                modificados.append((la[i], ld[i]))
        if len(la) > m:
            eliminados.extend(la[m:])
        if len(ld) > m:
            agregados.extend(ld[m:])
    return eliminados, agregados, modificados


clave_disco = lambda d: (d.get("Modelo", "").lower(), d.get("Tamano_GB"))
smart_norm = lambda s: (s or "").upper().strip()


def temp_maxima(datos):
    vals = [t["Celsius"] for t in datos["Temperaturas"] if isinstance(t.get("Celsius"), (int, float))]
    return round(max(vals), 1) if vals else None


def libre_en(letra, particiones):
    for p in particiones:
        if p["Unidad"].upper().startswith(letra.upper()):
            return p["Libre_GB"]
    return None


def total_en(letra, particiones):
    for p in particiones:
        if p["Unidad"].upper().startswith(letra.upper()):
            return p["Total_GB"]
    return None


def diagnosticar(datos):
    hallazgos = []

    def add(sev, cat, titulo, detalle):
        hallazgos.append({"severidad": sev, "categoria": cat, "titulo": titulo, "detalle": detalle})

    for d in datos["Discos_Fisicos"]:
        sm = smart_norm(d.get("SMART"))
        nombre = d["Modelo"]
        if sm.startswith("OK"):
            add("ok", "Almacenamiento", f"S.M.A.R.T. correcto: {nombre}", "El disco no reporta fallas internas.")
        elif sm:
            add("problema", "Almacenamiento", f"S.M.A.R.T. en falla: {nombre}", f"Estado reportado: {sm}. Se recomienda respaldar y reemplazar el disco.")

    libre_c = libre_en("C:", datos["Particiones"])
    total_c = total_en("C:", datos["Particiones"])
    if libre_c is not None and total_c:
        pct = 100 * libre_c / total_c
        if libre_c < UMBRAL_LIBRE_GB_PROBLEMA or pct < 5:
            add("problema", "Almacenamiento", f"Espacio critico en C: ({fmt(libre_c)} GB libres)", "Quedan menos del 5% de espacio libre; esto degrada Windows y evita actualizaciones.")
        elif pct < UMBRAL_LIBRE_PCT_ATENCION:
            add("atencion", "Almacenamiento", f"Espacio bajo en C: ({fmt(libre_c)} GB libres)", f"Queda menos del {UMBRAL_LIBRE_PCT_ATENCION}% de espacio libre. Conviene liberar espacio.")
        else:
            add("ok", "Almacenamiento", f"Espacio suficiente en C: ({fmt(libre_c)} GB libres)", f"{fmt(pct, 0)}% del disco disponible.")

    ram_pct = datos["RAM"]["En_Uso_Pct"]
    if ram_pct >= UMBRAL_RAM_ATENCION:
        add("atencion", "Memoria", f"Uso elevado de memoria ({fmt(ram_pct, 0)}%)",
            "Medido en reposo relativo; puede ser normal si hay muchas aplicaciones abiertas. Si la PC esta lenta, evaluar ampliar RAM o revisar procesos.")
    else:
        add("ok", "Memoria", f"Uso de memoria dentro de lo normal ({fmt(ram_pct, 0)}%)", f"Total instalado: {datos['RAM']['Total_GB']} GB.")

    n_inicio = len(datos["Inicio"])
    if n_inicio >= UMBRAL_INICIO_PROBLEMA:
        add("problema", "Arranque", f"{n_inicio} programas se inician con Windows", "Exceso de programas al inicio: alarga el arranque y consume recursos. Depurar prioritariamente.")
    elif n_inicio >= UMBRAL_INICIO_ATENCION:
        add("atencion", "Arranque", f"{n_inicio} programas se inician con Windows", "Conviene deshabilitar los que no sean imprescindibles.")
    else:
        add("ok", "Arranque", f"Inicio ordenado ({n_inicio} programas)", "Cantidad razonable de programas al arranque.")

    bat = datos.get("Bateria")
    if bat:
        salud = bat["Salud_Pct"]
        if salud < UMBRAL_BATERIA_PROBLEMA:
            add("problema", "Bateria", f"Bateria degradada: {fmt(salud)}% de capacidad original",
                f"Conserva {bat['Actual_mWh']} mWh de los {bat['Diseno_mWh']} mWh de fabrica. Autonomia muy reducida; considerar reemplazo.")
        elif salud < UMBRAL_BATERIA_ATENCION:
            add("atencion", "Bateria", f"Bateria con desgaste: {fmt(salud)}% de capacidad original",
                "La autonomia esta notablemente reducida respecto a la fabrica.")
        else:
            add("ok", "Bateria", f"Bateria en buen estado ({fmt(salud)}%)", "Desgaste dentro de lo esperado.")
    else:
        add("info", "Bateria", "Sin bateria detectada", "Equipo de escritorio o sin sensor compatible.")

    temp_max = temp_maxima(datos)
    fuente = datos.get("Temperatura_Fuente")
    if temp_max is not None:
        etiqueta_fuente = f" (fuente: {fuente})" if fuente else ""
        if temp_max >= TEMP_MAX_PROBLEMA:
            add("problema", "Termico", f"Temperatura critica: max {fmt(temp_max)} °C{etiqueta_fuente}", "Revisar refrigeracion, disipacion y pasta termica.")
        elif temp_max >= TEMP_MAX_ATENCION:
            add("atencion", "Termico", f"Temperatura elevada: max {fmt(temp_max)} °C{etiqueta_fuente}", "Conviene revisar limpieza de ventiladores y disipacion.")
        else:
            add("ok", "Termico", f"Temperaturas normales (max {fmt(temp_max)} °C){etiqueta_fuente}", "Dentro del rango seguro de operacion.")
    else:
        add("info", "Termico", "Temperatura no disponible", "El hardware no expuso sensores compatibles (se intento LibreHardwareMonitor y ACPI). No se inventan valores.")

    uptime = datos.get("Uptime_Horas")
    if uptime is not None and uptime >= UMBRAL_UPTIME_HORAS:
        add("atencion", "Sistema", f"Sin reiniciar hace {fmt(uptime / 24, 0)} dias", "Un reinicio libera memoria y aplica actualizaciones pendientes.")

    hallazgos.sort(key=lambda x: SEV_ORDEN.get(x["severidad"], 9))
    return hallazgos


def estado_general(hallazgos):
    tiene_problema = any(h["severidad"] == "problema" for h in hallazgos)
    tiene_atencion = any(h["severidad"] == "atencion" for h in hallazgos)
    if tiene_problema:
        return "REQUIERE ATENCION URGENTE", "pill-mal"
    if tiene_atencion:
        return "FUNCIONA CON OBSERVACIONES", "pill-warn"
    return "SIN HALLAZGOS CRITICOS", "pill-ok"


def score_gravedad(hallazgos):
    return (
        sum(1 for h in hallazgos if h["severidad"] == "problema"),
        sum(1 for h in hallazgos if h["severidad"] == "atencion"),
    )


clave_hallazgo = lambda h: (h["categoria"], h["titulo"].lower())


def comparar_diagnosticos(ha, hb):
    mapa_b = {clave_hallazgo(h): h for h in hb}
    resueltos, persistentes = [], []
    for h in ha:
        clave = clave_hallazgo(h)
        if clave in mapa_b:
            persistentes.append(h)
            mapa_b.pop(clave)
        elif h["severidad"] in ("problema", "atencion"):
            resueltos.append(h)
    nuevos = [h for h in mapa_b.values() if h["severidad"] in ("problema", "atencion")]
    return resueltos, persistentes, nuevos


def pill(clase, texto):
    return f"<span class='pill {clase}'>{texto}</span>"


PILL_SEVERIDAD = {
    "ok": ("pill-ok", "CORRECTO"),
    "atencion": ("pill-warn", "ATENCION"),
    "problema": ("pill-mal", "PROBLEMA"),
    "info": ("pill-neutro", "INFO"),
}


def pill_severidad(sev):
    clase, texto = PILL_SEVERIDAD.get(sev, ("pill-neutro", sev.upper()))
    return pill(clase, texto)


def dot_severidad(sev):
    return f"<span class='dot dot-{sev}'></span>"


def pill_smart(valor):
    v = (valor or "").upper()
    if v.startswith("OK"):
        return pill("pill-ok", esc(valor))
    if "FAIL" in v or "ERROR" in v:
        return pill("pill-mal", esc(valor))
    return pill("pill-neutro", esc(valor) if valor else "N/D")


def pill_bateria(salud):
    clase = "pill-ok" if salud >= UMBRAL_BATERIA_ATENCION else ("pill-warn" if salud >= UMBRAL_BATERIA_PROBLEMA else "pill-mal")
    return pill(clase, f"{salud}% de salud")


def fila_metrica(nombre, a, d, unidad="", mejor="bajo", dec=1):
    num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
    if num(a) and num(d):
        dif = round(d - a, 2)
        umbral = 0.05 if dec > 0 else 1
        if abs(dif) < umbral:
            cls, etiqueta_txt, delta_txt = "neutro", "SIN CAMBIO", ""
        else:
            mejora = (dif < 0) if mejor == "bajo" else (dif > 0)
            cls = "mejora" if mejora else "empeora"
            etiqueta_txt = "MEJOR&Oacute;" if mejora else "EMPEOR&Oacute;"
            signo = "+" if dif > 0 else ""
            sufijo = " pp" if unidad == "%" else ((f" {unidad}") if unidad else "")
            delta_txt = f"{signo}{fmt(dif, dec)}{sufijo}"
        clase_pill = {"mejora": "pill-ok", "empeora": "pill-mal", "neutro": "pill-neutro"}[cls]
        unidad_celda = " %" if unidad == "%" else ((f" {unidad}") if unidad else "")
        tr = (f"<tr><td>{esc(nombre)}</td>"
              f"<td>{fmt(a, dec)}{unidad_celda}</td>"
              f"<td>{fmt(d, dec)}{unidad_celda}</td>"
              f"<td class='{cls}'>{delta_txt}</td>"
              f"<td style='text-align:center'>{pill(clase_pill, etiqueta_txt)}</td></tr>")
        return {"estado": cls, "cambio": abs(dif) >= umbral, "tr": tr}
    tr = (f"<tr><td>{esc(nombre)}</td>"
          f"<td colspan='2' class='neutro'>No disponible</td>"
          f"<td colspan='2' class='neutro'>-</td></tr>")
    return {"estado": "neutro", "cambio": False, "tr": tr}


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #eef1f5; color: #222; padding: 24px; }
.hoja { max-width: 920px; margin: 0 auto; background: #fff; border-radius: 10px; padding: 32px 40px; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
h1 { font-size: 21px; color: #14345c; letter-spacing: .3px; }
.subtitulo { color: #66707d; font-size: 13px; margin-top: 3px; }
.cabecera { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; border-bottom: 3px solid #2b6cb0; padding-bottom: 16px; }
.meta { font-size: 12px; color: #555; line-height: 1.75; text-align: right; white-space: nowrap; }
.btn { background: #2b6cb0; color: #fff; border: none; border-radius: 6px; padding: 8px 14px; font-size: 13px; cursor: pointer; margin-top: 8px; }
.btn:hover { background: #1e4e8c; }
.btn-flotante { position: fixed; bottom: 22px; right: 26px; margin-top: 0; z-index: 99; font-size: 14px; padding: 10px 18px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3); }
.aviso-pdf { position: fixed; bottom: 4px; left: 10px; font-size: 9px; color: #98a2b3; z-index: 99; max-width: 55%; }
.chips { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
.hero { background: #f0f6ff; border: 1px solid #dbeafe; border-radius: 10px; padding: 18px 22px; margin-top: 18px; }
.hero .etiqueta { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #66707d; font-weight: 700; }
.estado-grande { font-size: 17px; font-weight: 800; margin-top: 6px; }
.lista-cliente { list-style: none; margin-top: 14px; font-size: 13.5px; line-height: 2.1; }
.lista-cliente li small { display: block; color: #7a8494; font-size: 11.5px; line-height: 1.4; margin-left: 18px; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 9px; vertical-align: middle; }
.dot-ok { background: #22c55e; } .dot-atencion { background: #f59e0b; } .dot-problema { background: #ef4444; } .dot-info { background: #9ca3af; }
.salto-pagina { page-break-before: always; height: 1px; }
.seccion { margin-top: 28px; }
.seccion h2 { font-size: 15px; color: #14345c; text-transform: uppercase; letter-spacing: .5px; border-bottom: 2px solid #2b6cb0; padding-bottom: 6px; margin-bottom: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { background: #2b6cb0; color: #fff; text-align: left; padding: 8px 10px; font-weight: 600; }
td { padding: 7px 10px; border-bottom: 1px solid #e3e8ef; vertical-align: top; word-break: break-word; }
tbody tr:nth-child(even) td { background: #f7f9fc; }
.ok { color: #15803d; font-weight: 600; }
.mal { color: #dc2626; font-weight: 600; }
.mejora { color: #15803d; font-weight: 700; }
.empeora { color: #dc2626; font-weight: 700; }
.neutro { color: #8a94a3; }
.pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; white-space: nowrap; }
.pill-ok { background: #dcfce7; color: #166534; }
.pill-warn { background: #fef3c7; color: #92400e; }
.pill-mal { background: #fee2e2; color: #991b1b; }
.pill-neutro { background: #e5e7eb; color: #374151; }
.aviso { margin-top: 8px; font-size: 12px; color: #92400e; background: #fef3c7; border-radius: 6px; padding: 8px 12px; }
.sin-cambios { font-size: 13px; color: #555; font-style: italic; }
.sub-bloque { font-size: 13px; margin: 14px 0 8px; font-weight: 600; }
.firma { margin-top: 44px; display: flex; justify-content: space-between; font-size: 13px; page-break-inside: avoid; }
.firma div { width: 44%; border-top: 1px solid #333; padding-top: 6px; text-align: center; color: #444; }
.pie { margin-top: 26px; font-size: 11px; color: #98a2b3; text-align: center; }
.marca { position: fixed; bottom: 0; left: 0; right: 0; display: flex; align-items: center; gap: 10px; padding: 3px 18px; font-size: 10px; color: #475569; background: #f1f5f9; border-top: 1px solid #e2e8f0; z-index: 5; }
.marca img { height: 20px; }
@media print {
  body { background: #fff; padding: 0; }
  .hoja { box-shadow: none; border-radius: 0; max-width: none; padding: 8mm 10mm 14mm; }
  .no-print { display: none !important; }
  th, .pill, tbody tr:nth-child(even) td, .hero, .dot { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .salto-pagina { page-break-before: always; }
  .seccion { page-break-inside: avoid; }
}
"""


def _metas_servicio(servicio):
    lineas = []
    if servicio:
        tecnico = servicio.get("Tecnico", "")
        lineas.append(f"<b>Servicio:</b> {esc(servicio.get('Id', ''))}")
        lineas.append(f"<b>Cliente:</b> {esc(servicio.get('Cliente', ''))}")
    return lineas


def _cabecera(titulo, subtitulo, equipo, lineas_meta, chips_html="", tecnico=None):
    meta = "<br>".join(lineas_meta)
    chips = f"\n    {chips_html}" if chips_html else ""
    quien = esc(tecnico) if tecnico else "______________________"
    return f"""
<div class="cabecera">
  <div>
    <h1>{titulo}</h1>
    <p class="subtitulo">{subtitulo}</p>{chips}
  </div>
  <div class="meta">
    <b>Equipo:</b> {esc(equipo)}<br>
    {meta}<br>
    <b>Tecnico:</b> {quien}
  </div>
</div>
"""


def _marca_tecnico_html():
    lic = tecnico_licenciado()
    if not lic:
        return ""
    nombre = esc(lic.get("nombre") or "")
    wa = esc(lic.get("whatsapp") or "")
    img = ""
    logo = lic.get("logo") or ""
    if logo and os.path.exists(logo):
        img = f"<img src='file:///{logo.replace(chr(92), '/')}' alt='logo'>"
    texto = f"<b>{nombre}</b>" + (f" &middot; WhatsApp {wa}" if wa else "")
    return f"<div class='marca'>{img}<span>{texto}</span></div>"


def _pagina(titulo, contenido):
    marca = _marca_tecnico_html()
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>{esc(titulo)}</title>
<style>{CSS}</style>
</head>
<body>
{marca}
<div class="hoja">
{contenido}
</div>
<button class="btn no-print btn-flotante" onclick="window.print()">Guardar como PDF</button>
<p class="no-print aviso-pdf">Ya tenes el informe en pantalla. En OptiChek podes guardarlo como PDF con un clic (sale sin la direccion del archivo). Si imprimis desde el navegador: Ctrl+P y desactiva &quot;Cabecera y pie de pagina&quot;.</p>
</body>
</html>
"""


def _html_resumen_hardware(datos):
    sis = datos["Sistema"]
    modulos_ram = "<br>".join(esc(m) for m in datos["RAM"]["Modulos"]) or "No detectado"
    gpus = "<br>".join(esc(g) for g in datos["GPU"]) or "No detectada"
    bater = datos.get("Bateria")
    if bater:
        detalle = f" ({bater['Actual_mWh']} / {bater['Diseno_mWh']} mWh)"
        bateria_html = pill_bateria(bater["Salud_Pct"]) + esc(detalle)
    else:
        bateria_html = "<span class='neutro'>No detectada (equipo de escritorio o sin datos)</span>"

    return f"""
<table>
<tr><td style='width:34%'><b>Equipo</b></td><td>{esc(sis['Equipo'])} &mdash; {esc(sis['Fabricante'])} {esc(sis['Modelo'])}</td></tr>
<tr><td><b>Usuario</b></td><td>{esc(sis['Usuario'])}</td></tr>
<tr><td><b>Sistema Operativo</b></td><td>{esc(sis['Windows'])} ({esc(sis['Arquitectura'])}, Build {esc(sis['Build'])})</td></tr>
<tr><td><b>Procesador</b></td><td>{esc(datos['CPU']['Modelo'])}<br><span class='neutro'>{datos['CPU']['Nucleos']} nucleos / {datos['CPU']['Hilos']} hilos @ {datos['CPU']['GHz']} GHz</span></td></tr>
<tr><td><b>Memoria RAM</b></td><td>{datos['RAM']['Total_GB']} GB<br><span class='neutro'>{modulos_ram}</span></td></tr>
<tr><td><b>Graficos</b></td><td>{gpus}</td></tr>
<tr><td><b>Placa madre / BIOS</b></td><td>{esc(datos['Placa']['Placa'])} &mdash; BIOS {esc(datos['Placa']['BIOS'])} ({esc(datos['Placa']['Fecha_BIOS'] or 's/f')})</td></tr>
<tr><td><b>Bateria</b></td><td>{bateria_html}</td></tr>
</table>
"""


def _html_pagina_cliente_escaneo(datos, hallazgos, servicio, num, tecnico):
    estado, clase_estado = estado_general(hallazgos)
    equipo = datos["Sistema"].get("Equipo", "Equipo")

    orden = sorted(hallazgos, key=lambda h: SEV_ORDEN.get(h["severidad"], 9))
    items = "".join(
        f"<li>{dot_severidad(h['severidad'])}{esc(h['titulo'])}<small>{esc(h['detalle'])}</small></li>"
        for h in orden
    )

    lineas_meta = _metas_servicio(servicio)
    lineas_meta.append(f"<b>Fecha:</b> {esc(datos['Fecha'])}")

    cabecera = _cabecera(
        "RESULTADO DEL SERVICIO",
        f"Hoja de resumen para el cliente &mdash; {esc(nombre_escaneo(datos, num))}",
        equipo,
        lineas_meta,
        tecnico=tecnico,
    )

    hero = f"""
<div class="hero">
  <div class="etiqueta">Estado general del equipo</div>
  <div class="estado-grande">{pill(clase_estado, estado)}</div>
  <ul class="lista-cliente">{items}</ul>
</div>
"""

    nota = ("<p style='margin-top:14px;font-size:12px;color:#7a8494'>Las observaciones se basan en mediciones automaticas "
            "del hardware y del sistema al momento del escaneo. El detalle tecnico completo se encuentra en las paginas siguientes.</p>")

    return cabecera + hero + nota


def generar_html_escaneo(datos, num, servicio=None):
    sis = datos["Sistema"]
    equipo = sis.get("Equipo", "Equipo")
    tecnico = (servicio or {}).get("Tecnico") or None
    hallazgos = diagnosticar(datos)

    pagina_cliente = _html_pagina_cliente_escaneo(datos, hallazgos, servicio, num, tecnico)

    bater = datos.get("Bateria")

    def fila_valor(nombre, valor):
        return f"<tr><td style='width:44%'>{esc(nombre)}</td><td>{valor}</td></tr>"

    temp_val = temp_maxima(datos)
    fuente_temp = datos.get("Temperatura_Fuente")
    if temp_val is not None:
        celda_temp = f"{fmt(temp_val)} &deg;C<span class='neutro'> (via {fuente_temp})</span>" if fuente_temp else f"{fmt(temp_val)} &deg;C"
    else:
        celda_temp = "<span class='neutro'>No disponible: el hardware no expuso sensores compatibles</span>"

    filas_metricas = (
        fila_valor("Uso de memoria RAM", f"{fmt(datos['RAM']['En_Uso_Pct'], 0)} %")
        + fila_valor("Memoria virtual (swap) en uso", f"{fmt(datos['RAM']['Swap_En_Uso_Pct'], 0)} %")
        + fila_valor("Carga de CPU", f"{fmt(datos['CPU']['Carga_Pct'], 0)} %")
        + fila_valor("Programas al inicio", str(len(datos["Inicio"])))
        + fila_valor("Tiempo de encendido (uptime)", f"{fmt(datos['Uptime_Horas'], 1)} h")
        + fila_valor("Temperatura maxima", celda_temp)
        + fila_valor("Espacio libre en C:", f"{fmt(libre_en('C:', datos['Particiones']), 1)} GB")
        + (fila_valor("Salud de bateria", pill_bateria(bater["Salud_Pct"])) if bater else "")
    )

    filas_diag = "".join(
        f"<tr><td style='width:110px'>{pill_severidad(h['severidad'])}</td>"
        f"<td style='width:120px'>{esc(h['categoria'])}</td>"
        f"<td><b>{esc(h['titulo'])}</b><br><span class='neutro'>{esc(h['detalle'])}</span></td></tr>"
        for h in hallazgos
    )

    filas_discos = "".join(
        f"<tr><td>{esc(d['Modelo'])}</td><td>{esc(d['Interfaz'])}</td>"
        f"<td>{d['Tamano_GB']} GB</td><td>{pill_smart(d['SMART'])}</td></tr>"
        for d in datos["Discos_Fisicos"]
    )

    filas_part = "".join(
        f"<tr><td>{esc(p['Unidad'])}</td><td>{esc(p['FS'])}</td><td>{p['Total_GB']} GB</td>"
        f"<td>{p['Libre_GB']} GB</td></tr>"
        for p in datos["Particiones"]
    )

    if datos["Inicio"]:
        filas_ini = "".join(
            f"<tr><td>{esc(p['Nombre'])}</td><td>{esc(p['Comando'])}</td><td>{esc(p['Ubicacion'])}</td></tr>"
            for p in datos["Inicio"]
        )
        tabla_inicio = ("<table><thead><tr><th style='width:26%'>Programa</th><th>Comando</th><th style='width:28%'>Origen</th></tr></thead>"
                        f"<tbody>{filas_ini}</tbody></table>")
    else:
        tabla_inicio = "<p class='sin-cambios'>No se detectaron programas al inicio.</p>"

    cabecera_tecnica = _cabecera(
        "INFORME TECNICO DE REVISION",
        f"Diagnostico completo del equipo &mdash; {esc(nombre_escaneo(datos, num))}",
        equipo,
        _metas_servicio(servicio) + [f"<b>Fecha del escaneo:</b> {esc(datos['Fecha'])}"],
        tecnico=tecnico,
    )

    contenido_tecnico = (
        f"<div class='salto-pagina'></div>"
        + cabecera_tecnica
        + f"<div class='seccion'><h2>Diagnostico automatico</h2>"
        + f"<table><thead><tr><th>Severidad</th><th>Categoria</th><th>Hallazgo</th></tr></thead><tbody>{filas_diag}</tbody></table></div>"
        + f"<div class='seccion'><h2>Metricas del sistema al momento del escaneo</h2>"
        + f"<table><tbody>{filas_metricas}</tbody></table></div>"
        + f"<div class='seccion'><h2>Resumen del hardware</h2>{_html_resumen_hardware(datos)}</div>"
        + f"<div class='seccion'><h2>Almacenamiento y estado SMART</h2>"
        + ("<table><thead><tr><th>Disco</th><th>Interfaz</th><th>Capacidad</th><th>SMART</th></tr></thead>"
           f"<tbody>{filas_discos}</tbody></table><br>"
           "<table><thead><tr><th>Unidad</th><th>Sistema de archivos</th><th>Total</th><th>Libre</th></tr></thead>"
           f"<tbody>{filas_part}</tbody></table></div>")
        + f"<div class='seccion'><h2>Programas al inicio ({len(datos['Inicio'])})</h2>{tabla_inicio}</div>"
        + "<div class='firma'><div>Firma del tecnico</div><div>Firma del cliente</div></div>"
        + f"<p class='pie'>Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} por OptiChek v{VERSION} &mdash; Los porcentajes son valores instantaneos tomados al momento del escaneo.</p>"
    )

    titulo = f"Diagnostico #{num:03d} - {equipo}"
    return _pagina(titulo, pagina_cliente + contenido_tecnico)


def _tabla_hallazgos(lista, vacio):
    if not lista:
        return f"<p class='sin-cambios'>{vacio}</p>"
    filas = "".join(
        f"<tr><td style='width:105px'>{pill_severidad(h['severidad'])}</td>"
        f"<td style='width:115px'>{esc(h['categoria'])}</td><td>{esc(h['titulo'])}</td></tr>"
        for h in lista
    )
    return ("<table><thead><tr><th>Severidad</th><th>Categoria</th><th>Hallazgo</th></tr></thead>"
            f"<tbody>{filas}</tbody></table>")


def _html_pagina_cliente_diferencias(a, b, hallazgos_a, hallazgos_b, et_a, et_b, bullets, estado_final, clase_estado):
    sis = a["Sistema"]
    equipo = sis.get("Equipo", "Equipo")

    chips = (f"<div class='chips'>{pill(clase_estado, estado_final)}</div>")
    cabecera = _cabecera(
        "RESULTADO DEL MANTENIMIENTO",
        f"Comparativa entre escaneo {esc(et_a)} y escaneo {esc(et_b)}",
        equipo,
        [
            f"<b>Escaneo inicial ({esc(et_a)}):</b> {esc(a['Fecha'])}",
            f"<b>Escaneo final ({esc(et_b)}):</b> {esc(b['Fecha'])}",
        ],
        chips_html=chips,
    )

    if bullets:
        lista = "".join(f"<li>{dot_severidad(clase)}{esc(texto)}</li>" for clase, texto in bullets)
        cuerpo = f"<ul class='lista-cliente'>{lista}</ul>"
    else:
        cuerpo = "<p class='sin-cambios' style='margin-top:16px'>No se detectaron cambios relevantes entre ambos escaneos.</p>"

    hero = f"""
<div class="hero">
  <div class="etiqueta">Que cambio en el equipo</div>
  {cuerpo}
</div>
"""

    nota = ("<p style='margin-top:14px;font-size:12px;color:#7a8494'>Este resumen muestra unicamente los cambios detectados entre ambos escaneos. "
            "El detalle tecnico completo se encuentra en las paginas siguientes.</p>")

    return cabecera + hero + nota


def generar_html_diferencias(a, b, et_a, et_b, servicio=None):
    sis = a["Sistema"]
    equipo = sis.get("Equipo", "Equipo")
    tecnico = (servicio or {}).get("Tecnico") or None
    hallazgos_a = diagnosticar(a)
    hallazgos_b = diagnosticar(b)
    resueltos, persistentes, nuevos = comparar_diagnosticos(hallazgos_a, hallazgos_b)

    nom_a = (a.get("Nombre") or "").strip()
    nom_b = (b.get("Nombre") or "").strip()
    et_a_full = f"{et_a} · {nom_a}" if nom_a else et_a
    et_b_full = f"{et_b} · {nom_b}" if nom_b else et_b

    metricas_defs = [
        ("Uso de memoria RAM", a["RAM"]["En_Uso_Pct"], b["RAM"]["En_Uso_Pct"], "%", "bajo", 0),
        ("Memoria virtual (swap) en uso", a["RAM"]["Swap_En_Uso_Pct"], b["RAM"]["Swap_En_Uso_Pct"], "%", "bajo", 0),
        ("Carga de CPU", a["CPU"]["Carga_Pct"], b["CPU"]["Carga_Pct"], "%", "bajo", 0),
        ("Programas al inicio", len(a["Inicio"]), len(b["Inicio"]), "", "bajo", 0),
        ("Tiempo de encendido (uptime)", a["Uptime_Horas"], b["Uptime_Horas"], "h", "bajo", 1),
        ("Temperatura maxima", temp_maxima(a), temp_maxima(b), "&deg;C", "bajo", 1),
        ("Espacio libre en C:", libre_en("C:", a["Particiones"]), libre_en("C:", b["Particiones"]), "GB", "alto", 1),
    ]
    if a.get("Bateria") and b.get("Bateria"):
        metricas_defs.append(("Salud de bateria", a["Bateria"]["Salud_Pct"], b["Bateria"]["Salud_Pct"], "%", "alto", 1))

    resultados = []
    metricas_cambio = {}
    filas_metricas = ""
    for nombre, va, vb, unidad, mejor, dec in metricas_defs:
        r = fila_metrica(nombre, va, vb, unidad, mejor, dec)
        metricas_cambio[nombre] = r
        if r["cambio"]:
            resultados.append(r["estado"])
            filas_metricas += r["tr"]

    eliminados, agregados, modificados = comparar_inicio(a["Inicio"], b["Inicio"])

    mapa_b = {clave_disco(d): d for d in b["Discos_Fisicos"]}
    filas_discos = ""
    smart_mejoro = smart_empeoro = False
    for da in a["Discos_Fisicos"]:
        db = mapa_b.pop(clave_disco(da), None)
        if db is None:
            filas_discos += (f"<tr><td>{esc(da['Modelo'])}</td><td>{esc(da['Interfaz'])}</td><td>{da['Tamano_GB']} GB</td>"
                             f"<td>{pill_smart(da['SMART'])}</td><td>{pill('pill-mal', 'RETIRADO')}</td></tr>")
        elif smart_norm(da["SMART"]) != smart_norm(db["SMART"]):
            antes_ok = smart_norm(da["SMART"]).startswith("OK")
            despues_ok = smart_norm(db["SMART"]).startswith("OK")
            if antes_ok and not despues_ok:
                smart_empeoro = True
            elif not antes_ok and despues_ok:
                smart_mejoro = True
            filas_discos += (f"<tr><td>{esc(da['Modelo'])}</td><td>{esc(da['Interfaz'])}</td><td>{da['Tamano_GB']} GB</td>"
                             f"<td>{pill_smart(da['SMART'])}</td><td>{pill_smart(db['SMART'])}</td></tr>")
    for db in mapa_b.values():
        filas_discos += (f"<tr><td>{esc(db['Modelo'])}</td><td>{esc(db['Interfaz'])}</td><td>{db['Tamano_GB']} GB</td>"
                         f"<td>{pill('pill-neutro', 'NO ESTABA')}</td><td>{pill_smart(db['SMART'])}</td></tr>")

    letras = sorted({p["Unidad"] for p in a["Particiones"]} | {p["Unidad"] for p in b["Particiones"]})
    filas_part = ""
    gb_libre_delta = None
    for letra in letras:
        pa = next((p for p in a["Particiones"] if p["Unidad"] == letra), None)
        pb = next((p for p in b["Particiones"] if p["Unidad"] == letra), None)
        if pa is None:
            filas_part += (f"<tr><td>{esc(letra)}</td><td colspan='3' class='neutro'>No existia</td>"
                           f"<td>{pb['Libre_GB']} GB</td><td>{pill('pill-neutro', 'NUEVA')}</td></tr>")
            continue
        if pb is None:
            filas_part += (f"<tr><td>{esc(letra)}</td><td colspan='3'>{pa['Libre_GB']} GB</td>"
                           f"<td colspan='2' class='neutro'>Eliminada / no visible</td></tr>")
            continue
        la, lb = pa["Libre_GB"], pb["Libre_GB"]
        if abs(lb - la) >= 0.1:
            dif = round(lb - la, 1)
            cls_delta = "mejora" if dif > 0 else "empeora"
            delta = f"<span class='{cls_delta}'>{'+' if dif > 0 else ''}{dif} GB</span>"
            filas_part += (f"<tr><td>{esc(letra)}</td><td>{pa['Total_GB']} GB</td><td>{la} GB</td>"
                           f"<td>{lb} GB</td><td>{delta}</td></tr>")
            if letra.upper().startswith("C:"):
                gb_libre_delta = dif

    total_cambios = len(resultados) + len(eliminados) + len(agregados) + len(modificados) + len(filas_discos) + len(filas_part) + len(resueltos) + len(nuevos)

    sa = score_gravedad(hallazgos_a)
    sb = score_gravedad(hallazgos_b)
    n_mejora = resultados.count("mejora")
    n_empeora = resultados.count("empeora")
    if sb < sa or (sb == sa and smart_mejoro):
        estado_final, clase_estado = "MEJORADO", "pill-ok"
    elif sb > sa or smart_empeoro:
        estado_final, clase_estado = "EMPEORO", "pill-mal"
    elif n_mejora > n_empeora:
        estado_final, clase_estado = "MEJORA LEVE", "pill-ok"
    elif n_empeora > n_mejora:
        estado_final, clase_estado = "EMPEORA LEVE", "pill-warn"
    else:
        estado_final, clase_estado = "SIN CAMBIOS SIGNIFICATIVOS", "pill-neutro"

    bullets = []
    if eliminados:
        bullets.append(("ok", f"{len(eliminados)} aplicaciones de inicio eliminadas"))
    if agregados:
        bullets.append(("problema", f"{len(agregados)} aplicaciones de inicio agregadas"))
    if modificados:
        bullets.append(("info", f"{len(modificados)} aplicaciones de inicio cambiaron su ruta"))
    if gb_libre_delta is not None and abs(gb_libre_delta) >= 0.5:
        if gb_libre_delta > 0:
            bullets.append(("ok", f"{fmt(gb_libre_delta)} GB de almacenamiento liberados en el disco principal"))
        else:
            bullets.append(("problema", f"{fmt(abs(gb_libre_delta))} GB menos de espacio libre en el disco principal"))
    temp_a, temp_b = temp_maxima(a), temp_maxima(b)
    if temp_a is not None and temp_b is not None:
        dif_t = round(temp_a - temp_b, 1)
        if dif_t >= 3:
            bullets.append(("ok", f"Temperatura maxima reducida {fmt(dif_t)} °C"))
        elif dif_t <= -3:
            bullets.append(("problema", f"Temperatura maxima aumento {fmt(abs(dif_t))} °C"))
    for h in resueltos:
        bullets.append(("ok", f"Corregido: {h['titulo']}"))
    for h in nuevos:
        bullets.append((h["severidad"], f"Nueva observacion: {h['titulo']}"))
    n_pers_graves = sum(1 for h in persistentes if h["severidad"] == "problema")
    if n_pers_graves:
        bullets.append(("problema", f"{n_pers_graves} problema(s) que persisten y requieren intervencion"))

    pagina_cliente = _html_pagina_cliente_diferencias(
        a, b, hallazgos_a, hallazgos_b, et_a_full, et_b_full, bullets, estado_final, clase_estado
    )

    chips_tecnicos = (f"<div class='chips'>"
                      f"{pill('pill-ok', f'{n_mejora} metricas mejoraron')} "
                      f"{pill('pill-mal', f'{n_empeora} metricas empeoraron')} "
                      f"{pill('pill-neutro', f'{total_cambios} cambios detectados')}</div>")

    cabecera_tec = _cabecera(
        "INFORME COMPARATIVO DE DIFERENCIAS",
        f"Escaneo {esc(et_a_full)} vs. Escaneo {esc(et_b_full)} &mdash; solo cambios detectados",
        equipo,
        _metas_servicio(servicio) + [
            f"<b>Escaneo A ({esc(et_a_full)}):</b> {esc(a['Fecha'])}",
            f"<b>Escaneo B ({esc(et_b_full)}):</b> {esc(b['Fecha'])}",
        ],
        chips_html=chips_tecnicos,
        tecnico=tecnico,
    )

    if total_cambios == 0:
        contenido = (
            pagina_cliente
            + "<div class='salto-pagina'></div>" + cabecera_tec
            + "<div class='seccion vacio'><h2>Sin diferencias tecnicas</h2>"
            + "<p>Los dos escaneos son identicos en las metricas monitoreadas: rendimiento, programas de inicio,<br>"
            + "almacenamiento, estado SMART y diagnostico automatico no presentan cambios.</p></div>"
            + f"<p class='pie'>OptiChek v{VERSION}</p>"
        )
        return _pagina(f"Diferencias {et_a} vs {et_b} - {equipo}", contenido)

    secciones = f"<div class='salto-pagina'></div>" + cabecera_tec

    if resueltos or persistentes or nuevos:
        secciones += ("<div class='seccion'><h2>Evolucion del diagnostico automatico</h2>"
                      f"<p class='sub-bloque' style='color:#15803d'>Resueltos ({len(resueltos)})</p>"
                      + _tabla_hallazgos(resueltos, "Ninguno.")
                      + f"<p class='sub-bloque' style='color:#dc2626'>Nuevos ({len(nuevos)})</p>"
                      + _tabla_hallazgos(nuevos, "Ninguno.")
                      + f"<p class='sub-bloque' style='color:#92400e'>Persistentes ({len(persistentes)})</p>"
                      + _tabla_hallazgos(persistentes, "Ninguno.") + "</div>")

    if filas_metricas:
        secciones += ("<div class='seccion'><h2>Cambios en metricas de rendimiento</h2>"
                      "<table><thead><tr><th>Metrica</th><th>Antes</th><th>Despues</th><th>Cambio</th><th>Interpretacion</th></tr></thead>"
                      f"<tbody>{filas_metricas}</tbody></table></div>")

    if eliminados or agregados or modificados:

        def tabla_lista(lista):
            if not lista:
                return "<p class='sin-cambios'>Sin cambios.</p>"
            filas = "".join(
                f"<tr><td>{esc(p['Nombre'])}</td><td>{esc(p['Comando'])}</td><td>{esc(p['Ubicacion'])}</td></tr>"
                for p in lista
            )
            return ("<table><thead><tr><th style='width:26%'>Programa</th><th>Comando</th><th style='width:28%'>Origen</th></tr></thead>"
                    f"<tbody>{filas}</tbody></table>")

        def tabla_modificados(lista):
            if not lista:
                return "<p class='sin-cambios'>Sin cambios.</p>"
            filas = "".join(
                f"<tr><td>{esc(pa['Nombre'])}</td><td>{esc(pa['Comando'])}</td><td>{esc(pd['Comando'])}</td></tr>"
                for pa, pd in lista
            )
            return ("<table><thead><tr><th style='width:26%'>Programa</th><th>Comando antes</th><th>Comando ahora</th></tr></thead>"
                    f"<tbody>{filas}</tbody></table>")

        secciones += ("<div class='seccion'><h2>Cambios en programas de inicio</h2>"
                      f"<p class='sub-bloque' style='color:#15803d'>Eliminados del inicio ({len(eliminados)})</p>{tabla_lista(eliminados)}"
                      f"<p class='sub-bloque' style='color:#991b1b'>Agregados al inicio ({len(agregados)})</p>{tabla_lista(agregados)}"
                      f"<p class='sub-bloque' style='color:#92400e'>Cambiaron de ruta ({len(modificados)})</p>{tabla_modificados(modificados)}</div>")

    if filas_discos:
        secciones += ("<div class='seccion'><h2>Cambios en almacenamiento y SMART</h2>"
                      "<table><thead><tr><th>Disco</th><th>Interfaz</th><th>Capacidad</th><th>SMART Antes</th><th>SMART Despues</th></tr></thead>"
                      f"<tbody>{filas_discos}</tbody></table></div>")

    if filas_part:
        secciones += ("<div class='seccion'><h2>Cambios en espacio libre por unidad</h2>"
                      "<table><thead><tr><th>Unidad</th><th>Total</th><th>Libre Antes</th><th>Libre Despues</th><th>Diferencia</th></tr></thead>"
                      f"<tbody>{filas_part}</tbody></table></div>")

    secciones += "<div class='firma'><div>Firma del tecnico</div><div>Firma del cliente</div></div>"
    secciones += f"<p class='pie'>Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} por OptiChek v{VERSION}.</p>"

    return _pagina(f"Diferencias {et_a} vs {et_b} - {equipo}", pagina_cliente + secciones)


def _encontrar_navegador():
    bases = [
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("ProgramFiles", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    pares = [
        ("msedge.exe", "Microsoft\\Edge\\Application\\msedge.exe"),
        ("chrome.exe", "Google\\Chrome\\Application\\chrome.exe"),
        ("brave.exe", "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
        ("vivaldi.exe", "Vivaldi\\Application\\vivaldi.exe"),
        ("opera.exe", "Opera\\Application\\opera.exe"),
    ]
    for base in bases:
        if not base:
            continue
        for nombre, rel in pares:
            cand = os.path.join(base, rel)
            if os.path.exists(cand):
                return cand
    for nombre in ("msedge", "chrome", "brave", "vivaldi", "opera"):
        cand = shutil.which(nombre)
        if cand:
            return cand
    return None


def generar_pdf_de_informe(ruta_html):
    descargas_dir = os.path.dirname(ruta_html)
    base = os.path.splitext(os.path.basename(ruta_html))[0]
    ruta_pdf = os.path.join(descargas_dir, base + ".pdf")
    navegador = _encontrar_navegador()
    if not navegador:
        return None
    url = "file:///" + ruta_html.replace("\\", "/")
    for _ in range(2):
        try:
            subprocess.run(
                [
                    navegador,
                    "--headless",
                    "--disable-gpu",
                    "--no-pdf-header-footer",
                    "--print-to-pdf-no-header",
                    "--no-first-run",
                    "--no-default-browser-check",
                    f"--print-to-pdf={ruta_pdf}",
                    url,
                ],
                timeout=90,
                capture_output=True,
            )
        except Exception:
            pass
        if os.path.exists(ruta_pdf) and os.path.getsize(ruta_pdf) > 500:
            return ruta_pdf
    return None


def _guardar_informe_html(contenido_html, nombre_base):
    descargas = carpeta_descargas()
    ruta_html = os.path.join(descargas, nombre_base + ".html")
    with open(ruta_html, "w", encoding="utf-8") as fh:
        fh.write(contenido_html)
    return ruta_html


def generar_informe_escaneo(datos, num, servicio=None):
    contenido = generar_html_escaneo(datos, num, servicio)
    sid = (servicio or {}).get("Id", "SRV")
    nombre_slug = slug_equipo(nombre_escaneo(datos, num))[:24].strip("_")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    return _guardar_informe_html(contenido, f"{sid}_Escaneo{num:03d}_{nombre_slug}_{stamp}")


def generar_informe_comparacion(a, b, et_a, et_b, servicio=None):
    contenido = generar_html_diferencias(a, b, et_a, et_b, servicio)
    sid = (servicio or {}).get("Id", "SRV")
    na = et_a.replace("#", "")
    nb = et_b.replace("#", "")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    return _guardar_informe_html(contenido, f"{sid}_Comparacion_{na}_vs_{nb}_{stamp}")
