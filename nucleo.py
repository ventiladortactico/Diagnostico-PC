import os
import re
import sys
import json
import glob
import html
import hmac
import base64
import shutil
import socket
import hashlib
import tempfile
import threading
import contextlib
import http.server
import socketserver
import subprocess
import unicodedata
from datetime import datetime

try:
    import psutil
    import wmi
except ImportError as e:
    raise RuntimeError(f"Falta una dependencia ({e.name}). Instala con: pip install psutil WMI")


@contextlib.contextmanager
def contexto_com():
    pythoncom = None
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pythoncom = None
    try:
        yield
    finally:
        if pythoncom:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


VERSION = "3.19"
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


def _guardar_json_atomico(ruta, datos):
    carpeta = os.path.dirname(ruta) or "."
    os.makedirs(carpeta, exist_ok=True)
    temporal = ruta + ".tmp"
    try:
        with open(temporal, "w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporal, ruta)
    finally:
        if os.path.exists(temporal):
            try:
                os.remove(temporal)
            except OSError:
                pass


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
    _guardar_json_atomico(ruta_config(), cfg)



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
    _guardar_json_atomico(os.path.join(carpeta, "servicio.json"), meta)
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
    except (IOError, json.JSONDecodeError, FileNotFoundError):
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
    _guardar_json_atomico(arch, meta)


def guardar_escaneo(datos, sid, nombre=""):
    nums = []
    for f in glob.glob(os.path.join(dir_escaneos(sid), "escaneo_*.json")):
        m = re.search(r"escaneo_(\d+)_", os.path.basename(f))
        if m:
            try:
                nums.append(int(m.group(1)))
            except ValueError:
                continue
    max_existente = max(nums) if nums else 0
    num = max_existente + 1
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo = os.path.join(dir_escaneos(sid), f"escaneo_{num:03d}_{stamp}.json")
    datos["Servicio"] = sid
    nombre = (nombre or "").strip()
    datos["Nombre"] = nombre if nombre else f"Escaneo #{num:03d}"
    _guardar_json_atomico(archivo, datos)
    meta = cargar_servicio(sid) or {}
    if isinstance(meta, dict):
        meta["Ultimo_Num"] = num
        _guardar_meta_servicio(sid, meta)
    return num, archivo


def eliminar_escaneo(sid, num):
    objetivo = None
    for f in glob.glob(os.path.join(dir_escaneos(sid), "escaneo_*.json")):
        m = re.search(r"escaneo_(\d+)_", os.path.basename(f))
        if m:
            try:
                if int(m.group(1)) == num:
                    objetivo = f
                    break
            except ValueError:
                continue
    if not objetivo:
        return False
    raiz = os.path.abspath(dir_raiz_servicios())
    try:
        objetivo_abs = os.path.abspath(objetivo)
        if not objetivo_abs.startswith(raiz):
            return False
        if not os.path.isfile(objetivo_abs):
            return False
        os.remove(objetivo_abs)
        return True
    except (OSError, IOError, ValueError):
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
        except (json.JSONDecodeError, IOError, ValueError) as e:
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
    return html.escape(str(s if s is not None else ""))


def fmt(v, dec=1):
    if v is None:
        return "-"
    if isinstance(v, (int, float)):
        if isinstance(v, int) or dec == 0:
            return str(round(v))
        return f"{v:.{dec}f}"
    return esc(v)


def _logo_base64(ruta):
    """Convierte la ruta de imagen del logo a un URI Base64 para incrustación directa en HTML."""
    if not ruta or not os.path.exists(ruta):
        return ""
    try:
        ext = os.path.splitext(ruta)[1].lower().lstrip(".")
        mime = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext or 'png'}"
        with open(ruta, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return ""


def _obtener_tipos_disco():
    """Consulta el namespace de Storage de Windows para detectar si las unidades son SSD, NVMe o HDD."""
    tipos = {}
    try:
        cs = wmi.WMI(namespace="root\\microsoft\\windows\\storage")
        for pd in getattr(cs, "MSFT_PhysicalDisk", lambda: [])():
            dev_id = getattr(pd, "DeviceId", None)
            media = getattr(pd, "MediaType", 0)  # 3: HDD, 4: SSD, 5: SCM
            bus = getattr(pd, "BusType", 0)     # 17: NVMe
            if media == 4:
                tipo = "SSD NVMe" if bus == 17 else "SSD"
            elif media == 3:
                tipo = "HDD"
            elif bus == 17:
                tipo = "SSD NVMe"
            else:
                tipo = ""
            nombre = (getattr(pd, "FriendlyName", "") or getattr(pd, "Model", "") or "").strip().lower()
            if dev_id is not None and tipo:
                tipos[str(dev_id)] = tipo
            if nombre and tipo:
                tipos[nombre] = tipo
    except Exception:
        pass
    return tipos


def _clasificar_tipo_disco(modelo, interfaz, tipos_storage, disk_index=None):
    """Clasifica el tipo de almacenamiento con fallback a heurísticas de modelo e interfaz."""
    if disk_index is not None and str(disk_index) in tipos_storage:
        return tipos_storage[str(disk_index)]
    mod_lower = (modelo or "").lower()
    for k, v in tipos_storage.items():
        if k and k in mod_lower and v:
            return v
    if "nvme" in mod_lower or "nvme" in (interfaz or "").lower():
        return "SSD NVMe"
    if any(k in mod_lower for k in ("ssd", "solid state", "kingston sa400", "crucial ct", "samsung 8", "samsung 9", "kioxia", "sandisk", "wd green", "wd blue sn", "wd black")):
        return "SSD"
    if any(k in mod_lower for k in ("wdc wd", "st1000", "st2000", "st500", "hitachi", "toshiba mq", "toshiba dt", "barracuda", "caviar")):
        return "HDD"
    return "Disco"


def obtener_sistema(c):
    so_list = c.Win32_OperatingSystem()
    cs_list = c.Win32_ComputerSystem()
    so = so_list[0] if so_list else None
    cs = cs_list[0] if cs_list else None
    return {
        "Equipo": ((cs.Name if cs else None) or socket.gethostname()).strip(),
        "Usuario": os.environ.get("USERNAME", ""),
        "Windows": (getattr(so, "Caption", "") or "Windows").strip(),
        "Arquitectura": (getattr(so, "OSArchitecture", "") or ""),
        "Build": (getattr(so, "BuildNumber", "") or ""),
        "Fabricante": (getattr(cs, "Manufacturer", "") or "").strip() if cs else "",
        "Modelo": (getattr(cs, "Model", "") or "").strip() if cs else "",
    }


def obtener_cpu(c):
    p_list = c.Win32_Processor()
    p = p_list[0] if p_list else None
    ghz = round(p.MaxClockSpeed / 1000.0, 2) if (p and getattr(p, "MaxClockSpeed", None)) else 0.0
    return {
        "Modelo": (getattr(p, "Name", "") or "Procesador").strip(),
        "Nucleos": getattr(p, "NumberOfCores", None) or os.cpu_count() or 1,
        "Hilos": getattr(p, "NumberOfLogicalProcessors", None) or os.cpu_count() or 1,
        "GHz": ghz,
        "Carga_Pct": psutil.cpu_percent(interval=0.8),
    }


def obtener_ram(c):
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    modulos = []
    try:
        for m in c.Win32_PhysicalMemory():
            try:
                gb = round(int(m.Capacity) / 1024 ** 3, 1)
            except Exception:
                gb = 0
            vel = getattr(m, "Speed", "") or ""
            vel_txt = f"{vel} MHz - " if vel else ""
            fab = (getattr(m, "Manufacturer", "") or "").strip()
            modulos.append(f"{gb} GB - {vel_txt}{fab}".rstrip(" -"))
    except Exception:
        pass
    return {
        "Total_GB": round(vm.total / 1024 ** 3, 2),
        "En_Uso_Pct": vm.percent,
        "Swap_Total_GB": round(sw.total / 1024 ** 3, 2),
        "Swap_En_Uso_Pct": sw.percent,
        "Modulos": modulos,
    }


def obtener_discos(c):
    discos = []
    tipos_storage = _obtener_tipos_disco()
    for d in c.Win32_DiskDrive():
        try:
            gb = round(int(d.Size) / 1024 ** 3)
        except Exception:
            gb = 0
        modelo = (getattr(d, "Model", "") or "").strip()
        interfaz = (getattr(d, "InterfaceType", "") or "").strip()
        idx = getattr(d, "Index", None)
        tipo = _clasificar_tipo_disco(modelo, interfaz, tipos_storage, idx)
        discos.append({
            "Modelo": modelo,
            "Tipo": tipo,
            "Interfaz": interfaz,
            "Tamano_GB": gb,
            "SMART": (getattr(d, "Status", "") or "").strip(),
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
        if not p.fstype or "cdrom" in p.opts.lower():
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


def _origen_inicio(ubicacion):
    limpio = (ubicacion or "").strip()
    if limpio in ("Inicio (global)", "Inicio (usuario)", "Registro (global)", "Registro (usuario)", "Otro", "Desconocido"):
        return limpio
    u = limpio.lower().replace("\\", "/")
    if "startup" in u:
        return "Inicio (global)" if ("/common" in u or "/programdata" in u) else "Inicio (usuario)"
    if u.startswith("hklm") or "hkey_local_machine" in u:
        return "Registro (global)"
    if u.startswith("hku") or u.startswith("hkcu") or "hkey_users" in u or "hkey_current_user" in u or "s-1-5-" in u:
        return "Registro (usuario)"
    return "Otro" if u else "Desconocido"


def _inicio_limpio(lista):
    unicos = {}
    for p in lista or []:
        nombre = (p.get("Nombre") or "").strip() or "(sin nombre)"
        if nombre.lower() not in unicos:
            unicos[nombre.lower()] = {"Nombre": nombre, "Comando": (p.get("Comando") or "").strip(), "Origenes": []}
        origen = _origen_inicio(p.get("Ubicacion"))
        if origen not in unicos[nombre.lower()]["Origenes"]:
            unicos[nombre.lower()]["Origenes"].append(origen)
    limpios = [{
        "Nombre": d["Nombre"],
        "Comando": d["Comando"],
        "Ubicacion": " | ".join(d["Origenes"]) or "Desconocido",
    } for d in unicos.values()]
    return sorted(limpios, key=lambda p: p["Nombre"].lower())


def obtener_programas_inicio(c):
    progs = []
    try:
        for item in c.Win32_StartupCommand():
            progs.append({
                "Nombre": (getattr(item, "Name", "") or "").strip(),
                "Comando": (getattr(item, "Command", "") or "").strip(),
                "Ubicacion": (getattr(item, "Location", "") or "").strip(),
            })
    except Exception:
        pass
    return _inicio_limpio(progs)


def temperaturas_lhm():
    temps = []
    try:
        cw = wmi.WMI(namespace="root\\LibreHardwareMonitor")
        for s in getattr(cw, "LHM_Sensor", lambda: [])():
            if (getattr(s, "SensorType", "") or "") != "Temperature":
                continue
            try:
                val = float(s.Value)
            except Exception:
                continue
            if -50 < val < 150:
                temps.append({"Zona": (getattr(s, "Name", "") or "Sensor"), "Celsius": round(val, 1), "Fuente": "LibreHardwareMonitor"})
    except Exception:
        pass
    return temps


def temperaturas_acpi():
    temps = []
    try:
        cw = wmi.WMI(namespace="root\\WMI")
        for s in getattr(cw, "MSAcpi_ThermalZoneTemperature", lambda: [])():
            try:
                cel = round(s.CurrentTemperature / 10.0 - 273.15, 1)
                if -50 < cel < 150:
                    zona = (getattr(s, "InstanceName", "") or "Zona termica").split("\\")[-1]
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
    try:
        for g in c.Win32_VideoController():
            nombre = (getattr(g, "Name", "") or "").strip()
            if nombre:
                gpus.append(nombre)
    except Exception:
        pass
    return gpus


def obtener_placa(c):
    b_list = c.Win32_BaseBoard()
    bios_list = c.Win32_BIOS()
    b = b_list[0] if b_list else None
    bios = bios_list[0] if bios_list else None
    fecha_bios = ""
    try:
        rel = getattr(bios, "ReleaseDate", None)
        if rel:
            fecha_bios = datetime.strptime(rel.split(".")[0], "%Y%m%d%H%M%S").strftime("%d/%m/%Y")
    except Exception:
        pass
    placa_txt = f"{getattr(b, 'Manufacturer', '') or ''} {getattr(b, 'Product', '') or ''}".strip() or "Generica"
    return {
        "Placa": placa_txt,
        "BIOS": (getattr(bios, "SMBIOSBIOSVersion", "") or "").strip(),
        "Fecha_BIOS": fecha_bios,
    }


def obtener_bateria():
    try:
        cw = wmi.WMI(namespace="root\\WMI")
        dis = getattr(cw, "BatteryStaticData", lambda: [])()
        full = getattr(cw, "BatteryFullChargedCapacity", lambda: [])()
        if dis and full:
            diseno = int(dis[0].DesignedCapacity)
            actual = int(full[0].FullChargedCapacity)
            if diseno > 0:
                salud = round(100 * actual / diseno, 1)
                return {"Diseno_mWh": diseno, "Actual_mWh": actual, "Salud_Pct": salud}
    except Exception:
        pass
    return None


def _ejecutar_ps_json(script, timeout=45):
    try:
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
            timeout=timeout, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        salida = (res.stdout or "").strip()
        if not salida:
            return None
        if salida.startswith("["):
            return json.loads(salida)
        ini, fin = salida.find("{"), salida.rfind("}")
        if ini == -1:
            return None
        return json.loads(salida[ini:fin + 1])
    except Exception:
        return None


def _dias_desde(fecha):
    if not fecha:
        return None
    m = re.match(r"/Date\((\d+)\)/", str(fecha))
    if m:
        f = datetime.fromtimestamp(int(m.group(1)) / 1000)
        return max(0, (datetime.now() - f).days)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            f = datetime.strptime(str(fecha).strip()[:19], fmt)
            return max(0, (datetime.now() - f).days)
        except Exception:
            continue
    return None


def salud_discos():
    script = r"""
$out = @()
try {
  Get-PhysicalDisk -ErrorAction Stop | ForEach-Object {
    $p = $_
    try { $rc = $p | Get-StorageReliabilityCounter -ErrorAction Stop } catch { return }
    $out += [pscustomobject]@{ Nombre=$p.FriendlyName; Vida=[math]::Round(100 - $rc.Wear); Horas=$rc.PowerOnHours; Ciclos=$rc.StartStopCycleCount }
  }
} catch {}
if ($out.Count) { $out | ConvertTo-Json -Compress } else { "{}" }
"""
    r = _ejecutar_ps_json(script)
    return r if isinstance(r, list) else ([r] if isinstance(r, dict) and r else [])


def slots_ram():
    script = r"""
try {
  $arr = Get-CimInstance Win32_PhysicalMemoryArray -ErrorAction Stop | Select-Object -First 1
  $chips = @(Get-CimInstance Win32_PhysicalMemory -ErrorAction Stop)
  [pscustomobject]@{ Slots=[int]$arr.MemoryDevices; Ocupados=$chips.Count; MaxGB=[math]::Round($arr.MaxCapacity/1MB); UsadoGB=[math]::Round(($chips | Measure-Object -Property Capacity -Sum).Sum/1GB, 0) } | ConvertTo-Json -Compress
} catch { "{}" }
"""
    return _ejecutar_ps_json(script)


def estado_bateria_ciclos():
    script = r"""
$r = [pscustomobject]@{ Ciclos=$null; Cargador=$null; Carga=$null }
try {
  $b = Get-CimInstance Win32_Battery -ErrorAction Stop | Select-Object -First 1
  if ($b) {
    switch ([int]$b.BatteryStatus) {
      1 { $r.Cargador = "Bateria en uso" }
      2 { $r.Cargador = "Cargador conectado" }
      3 { $r.Cargador = "Cargador conectado (carga completa)" }
      default { $r.Cargador = "Estado " + [string]$b.BatteryStatus }
    }
    $r.Carga = [int]$b.EstimatedChargeRemaining
  }
} catch {}
try {
  $cc = Get-CimInstance -Namespace root\WMI -ClassName BatteryCycleCount -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($cc -and $cc.CycleCount) { $r.Ciclos = [int]$cc.CycleCount }
} catch {}
if ($null -eq $r.Ciclos) {
  try {
    $arch = Join-Path $env:TEMP "optichek_batt_report.html"
    & powercfg /batteryreport /output $arch | Out-Null
    if (Test-Path $arch) {
      $txt = Get-Content $arch -Raw
      if ($txt -match "Cycle\s+Count\s*</span>\s*</td>\s*<td>\s*([^<>]+)") {
        $v = $Matches[1].Trim()
        if ($v -match '^\d+$') { $r.Ciclos = [int]$v }
      }
      Remove-Item $arch -Force -ErrorAction SilentlyContinue
    }
  } catch {}
}
$r | ConvertTo-Json -Compress
"""
    return _ejecutar_ps_json(script)


def bsod_30d():
    script = r"""
try {
  $desde = (Get-Date).AddDays(-30)
  $n = @(Get-WinEvent -FilterHashtable @{ LogName='System'; Id=41,1001; StartTime=$desde } -ErrorAction SilentlyContinue).Count
  [pscustomobject]@{ N=$n } | ConvertTo-Json -Compress
} catch { "{}" }
"""
    r = _ejecutar_ps_json(script)
    if isinstance(r, dict) and isinstance(r.get("N"), int):
        return r["N"]
    return None


def actualizaciones_windows():
    script = r"""
$r = [pscustomobject]@{ Busqueda=$null; Instalacion=$null }
try {
  $p = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\Results\Detect" -ErrorAction SilentlyContinue
  if ($p -and $p.LastSuccessTime) { $r.Busqueda = $p.LastSuccessTime }
} catch {}
try {
  $p = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\Results\Install" -ErrorAction SilentlyContinue
  if ($p -and $p.LastSuccessTime) { $r.Instalacion = $p.LastSuccessTime }
} catch {}
if ($null -eq $r.Busqueda -or $null -eq $r.Instalacion) {
  $log = Join-Path $env:WINDIR "SoftwareDistribution\ReportingEvents.log"
  if (Test-Path $log) {
    $lineas = Get-Content $log -ErrorAction SilentlyContinue
    for ($i = $lineas.Count - 1; $i -ge 0; $i--) {
      $la = $lineas[$i]
      if ($la -match "(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})") {
        $fecha = $Matches[1]
        if ($null -eq $r.Instalacion -and $la -match "AGENT_INSTALLING_SUCCEEDED") { $r.Instalacion = $fecha }
        if ($null -eq $r.Busqueda -and $la -match "AGENT_DETECTION_FINISHED") { $r.Busqueda = $fecha }
        if ($null -ne $r.Busqueda -and $null -ne $r.Instalacion) { break }
      }
    }
  }
}
$r | ConvertTo-Json -Compress
"""
    return _ejecutar_ps_json(script)


def antivirus_estado():
    script = r"""
$r = @()
try {
  $m = Get-MpComputerStatus -ErrorAction SilentlyContinue
  if ($m) {
    $r += [pscustomobject]@{ Nombre="Windows Defender"; Activo=[bool]$m.AntivirusEnabled; Firma=$m.AntivirusSignatureLastUpdated }
  }
} catch {}
if (-not $r.Count) {
  try {
    Get-CimInstance -Namespace root\SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction SilentlyContinue | ForEach-Object {
      $r += [pscustomobject]@{ Nombre=$_.displayName; Activo=(([int]$_.productState -band 0x10000) -ne 0); Firma=$null }
    }
  } catch {}
}
if ($r.Count) { $r | ConvertTo-Json -Compress } else { "{}" }
"""
    r = _ejecutar_ps_json(script)
    return r if isinstance(r, list) else ([r] if isinstance(r, dict) and r else [])


def navegadores_instalados():
    script = r"""
$out = @{}
$claves = @(
  "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
  "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
  "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
)
foreach ($clave in $claves) {
  try {
    Get-ItemProperty $clave -ErrorAction SilentlyContinue | ForEach-Object {
      $dn = $_.DisplayName
      if ($dn) {
        $base = $null
        if ($dn -match "Chrome") { $base = "Google Chrome" }
        elseif ($dn -match "Firefox") { $base = "Mozilla Firefox" }
        elseif ($dn -match "Edge") { if ($dn -notmatch "WebView|Update") { $base = "Microsoft Edge" } }
        elseif ($dn -match "Brave") { $base = "Brave" }
        elseif ($dn -match "Opera") { $base = "Opera" }
        elseif ($dn -match "Vivaldi") { $base = "Vivaldi" }
        if ($base -and -not $out.ContainsKey($base)) {
          $inst = $null
          if ($_.InstallDate -match "^(\d{4})(\d{2})(\d{2})") { $inst = "$($Matches[1])/$($Matches[2])/$($Matches[3])" }
          $out[$base] = [pscustomobject]@{ Nombre=$base; Version=$_.DisplayVersion; Instalacion=$inst }
        }
      }
    }
  } catch {}
}
if ($out.Values.Count) { @($out.Values) | ConvertTo-Json -Compress } else { "{}" }
"""
    r = _ejecutar_ps_json(script)
    return r if isinstance(r, list) else ([r] if isinstance(r, dict) and r else [])


def _ps_lista(r):
    return r if isinstance(r, list) else ([r] if isinstance(r, dict) and r else [])


def archivos_temporales():
    script = r"""
$out = [pscustomobject]@{ TempUsuario=$null; TempSistema=$null; WindowsUpdate=$null; Prefetch=$null; Minidump=$null }
function tam-mb($ruta) {
  if (-not (Test-Path -LiteralPath $ruta)) { return $null }
  $s = (Get-ChildItem -LiteralPath $ruta -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  if ($null -eq $s) { return 0 }
  return [math]::Round($s / 1MB, 1)
}
$out.TempUsuario   = tam-mb ([System.IO.Path]::GetTempPath())
$out.TempSistema   = tam-mb (Join-Path $env:WINDIR "Temp")
$out.WindowsUpdate = tam-mb (Join-Path $env:WINDIR "SoftwareDistribution\Download")
$out.Prefetch      = tam-mb (Join-Path $env:WINDIR "Prefetch")
$out.Minidump      = tam-mb (Join-Path $env:WINDIR "Minidump")
$out | ConvertTo-Json -Compress
"""
    return _ejecutar_ps_json(script)


def servicios_terceros():
    script = r"""
Get-CimInstance Win32_Service -ErrorAction SilentlyContinue -Filter "StartMode='Auto' AND State='Running'" |
  Where-Object { $_.PathName -and $_.PathName -notmatch '\\Windows\\' -and $_.PathName -notmatch 'WindowsApps' -and $_.PathName -notmatch 'ClickToRun' -and $_.PathName -notmatch 'GameInput' -and $_.PathName -notmatch 'Windows Defender' } |
  Select-Object -First 20 @{N='Nombre';E={$_.Name}}, @{N='Mostrar';E={$_.DisplayName}}, @{N='Ruta';E={$_.PathName}} |
  ConvertTo-Json -Compress
"""
    return _ps_lista(_ejecutar_ps_json(script))


def tareas_terceros():
    script = r"""
Get-ScheduledTask -ErrorAction SilentlyContinue |
  Where-Object { $_.TaskPath -notlike '\Microsoft\*' -and $_.State -ne 'Disabled' } |
  Select-Object -First 12 | ForEach-Object {
    $acc = $_.Actions | Select-Object -First 1
    [pscustomobject]@{
      Nombre = $_.TaskName
      Estado = [string]$_.State
      Ejecuta = $(if ($acc -and $acc.Execute) { $acc.Execute } else { $null })
      Origen = $_.TaskPath
    }
  } | ConvertTo-Json -Compress
"""
    return _ps_lista(_ejecutar_ps_json(script, timeout=90))


def limpiar_temporales():
    script = r"""
$res = [pscustomobject]@{ Archivos=0; MB=0.0; Errores=0 }
$destinos = @(
  [System.IO.Path]::GetTempPath(),
  (Join-Path $env:WINDIR "Temp"),
  (Join-Path $env:WINDIR "SoftwareDistribution\Download"),
  (Join-Path $env:WINDIR "Prefetch"),
  (Join-Path $env:WINDIR "Minidump")
)
foreach ($ruta in $destinos) {
  if (-not (Test-Path -LiteralPath $ruta)) { continue }
  Get-ChildItem -LiteralPath $ruta -Force -ErrorAction SilentlyContinue | ForEach-Object {
    $tam = 0.0
    if ($_.PSIsContainer) {
      $s = (Get-ChildItem -LiteralPath $_.FullName -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
      if ($s) { $tam = $s / 1MB }
    } else {
      try { $tam = $_.Length / 1MB } catch {}
    }
    try {
      Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
      $res.Archivos += 1
      $res.MB += $tam
    } catch { $res.Errores += 1 }
  }
}
$res.MB = [math]::Round($res.MB, 1)
$res | ConvertTo-Json -Compress
"""
    return _ejecutar_ps_json(script, timeout=240)


def _basura_total_mb(datos):
    basura = datos.get("Temporales") or {}
    return sum(float(v) for v in basura.values() if isinstance(v, (int, float)))


def formato_tamano_mb(mb):
    mb = float(mb or 0)
    if mb >= 1024:
        return f"{fmt(mb / 1024, 2)} GB"
    return f"{fmt(mb, 1)} MB"


def recomendaciones_comerciales(datos):
    rec = []
    for d in datos.get("Discos_Fisicos", []):
        modelo = (d.get("Modelo") or "disco").strip()
        vida = d.get("Vida_Pct")
        smart = smart_norm(d.get("SMART"))
        if smart.startswith("FAIL") or "FAIL" in smart:
            rec.append(("problema", f"El disco {modelo} reporta falla SMART. Se recomienda respaldo inmediato y reemplazo por un SSD."))
        elif isinstance(vida, (int, float)):
            if vida < 15:
                rec.append(("problema", f"El disco {modelo} tiene {fmt(vida, 0)}% de vida restante. Reemplazo preventivo por SSD antes de una falla."))
            elif vida < 50:
                rec.append(("atencion", f"El disco {modelo} esta desgastado ({fmt(vida, 0)}% de vida restante). Un cambio preventivo evita perdida de datos."))
    libre_c = libre_en("C:", datos.get("Particiones", []))
    total_c = total_en("C:", datos.get("Particiones", []))
    if libre_c is not None and total_c and 100 * libre_c / total_c < 15:
        rec.append(("atencion", "El disco principal esta casi lleno. Se sugiere migrar a un SSD de mayor capacidad para mantener el rendimiento."))
    bat = datos.get("Bateria") or {}
    salud = bat.get("Salud_Pct")
    if isinstance(salud, (int, float)):
        if salud < 50:
            rec.append(("problema", "La bateria conserva menos del 50% de su capacidad original. Se recomienda reemplazo de bateria por desgaste avanzado."))
        elif salud < UMBRAL_BATERIA_ATENCION:
            rec.append(("atencion", "La bateria muestra desgaste moderado. Un reemplazo oportuno evita reclamos del cliente."))
    ram_pct = (datos.get("RAM", {}) or {}).get("En_Uso_Pct", 0)
    if ram_pct >= UMBRAL_RAM_ATENCION:
        rec.append(("atencion", "El uso de memoria es elevado en reposo. Ampliar la memoria RAM es la mejora mas rentable para este equipo."))
    slots = datos.get("Slots_RAM") or {}
    if isinstance(slots.get("Ocupados"), int) and isinstance(slots.get("Slots"), int) and 0 <= slots["Ocupados"] < slots["Slots"]:
        libres = slots["Slots"] - slots["Ocupados"]
        if libres == 1:
            rec.append(("info", f"Queda 1 slot de RAM libre de {slots['Slots']}. Una ampliacion de memoria es simple y economica."))
        else:
            rec.append(("info", f"Quedan {libres} slots de RAM libres de {slots['Slots']}. Una ampliacion de memoria es simple y economica."))
    bsod = datos.get("BSOD_30d")
    if isinstance(bsod, int) and bsod >= 2:
        rec.append(("problema", f"Se registraron {bsod} pantallas azules en 30 dias. Se recomienda revisar drivers, memoria y registro del sistema."))
    temp = temp_maxima(datos)
    if temp is not None and temp > TEMP_MAX_ATENCION:
        rec.append(("atencion", "El equipo alcanza temperaturas altas. Un servicio de limpieza interna y pasta termica previene fallas mayores."))
    uptime = datos.get("Uptime_Horas")
    if isinstance(uptime, (int, float)) and uptime > 48:
        rec.append(("info", "El equipo lleva mas de 48 h encendido. Se sugiere reiniciar para liberar la memoria en cache y aplicar actualizaciones pendientes."))
    basura_mb = _basura_total_mb(datos)
    if basura_mb >= 1024:
        rec.append(("atencion", f"Hay {fmt(basura_mb / 1024, 1)} GB de archivos temporales. Una limpieza del sistema (1 clic) libera espacio y deja el equipo mas fluido."))
    if len(datos.get("Servicios_Terceros") or []) >= 3:
        rec.append(("info", "Se detectaron varios servicios de terceros iniciando con Windows. Revisar servicios y tareas programadas optimiza el arranque."))
    return rec


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
    saluda_discos = salud_discos() or []
    for d in discos:
        modelo = (d.get("Modelo") or "").lower()
        for s in saluda_discos:
            nom = (s.get("Nombre") or "").lower()
            if nom and (nom in modelo or modelo in nom):
                d["Vida_Pct"] = s.get("Vida")
                d["Horas_Encendidas"] = s.get("Horas")
                d["Ciclos_Arranque"] = s.get("Ciclos")
                break
        else:
            d.setdefault("Vida_Pct", None)
            d.setdefault("Horas_Encendidas", None)
            d.setdefault("Ciclos_Arranque", None)

    paso("Leyendo programas de inicio...")
    inicio = obtener_programas_inicio(c)

    paso("Midiendo temperaturas y bateria...")
    temps, fuente_temp = obtener_temperaturas()
    gpu = obtener_gpu(c)
    placa = obtener_placa(c)
    bateria = obtener_bateria()
    bat_ciclos = estado_bateria_ciclos() or {}
    if isinstance(bateria, dict):
        bateria["Ciclos"] = bat_ciclos.get("Ciclos")
        bateria["Cargador"] = bat_ciclos.get("Cargador")
        bateria["Carga_Pct"] = bat_ciclos.get("Carga")
    uptime = round((datetime.now().timestamp() - psutil.boot_time()) / 3600, 1)

    paso("Revisando seguridad y actualizaciones...")
    bsod = bsod_30d()
    upd = actualizaciones_windows()
    av = antivirus_estado() or []
    nav = navegadores_instalados() or []
    slots = slots_ram()

    paso("Analizando archivos temporales...")
    basura = archivos_temporales() or {}

    paso("Auditando servicios y tareas de terceros...")
    serv_ter = servicios_terceros()
    tareas_ter = tareas_terceros()

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
        "Slots_RAM": slots,
        "BSOD_30d": bsod,
        "WindowsUpdate": upd,
        "Antivirus": av,
        "Navegadores": sorted(nav, key=lambda n: (n.get("Nombre") or "").lower()),
        "Temporales": basura,
        "Servicios_Terceros": serv_ter,
        "Tareas_Terceros": tareas_ter,
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

    discos = datos.get("Discos_Fisicos", [])
    for d in discos:
        sm = smart_norm(d.get("SMART"))
        nombre = d.get("Modelo", "Disco")
        tipo = d.get("Tipo", "")
        et_disco = f"{nombre} ({tipo})" if tipo and tipo != "Disco" else nombre
        if sm.startswith("OK"):
            add("ok", "Almacenamiento", f"S.M.A.R.T. correcto: {et_disco}", "El disco no reporta fallas internas.")
        elif sm:
            add("problema", "Almacenamiento", f"S.M.A.R.T. en falla: {et_disco}", f"Estado reportado: {sm}. Se recomienda respaldar y reemplazar el disco inmediatamente.")
        vida = d.get("Vida_Pct")
        if isinstance(vida, (int, float)):
            if vida < 15:
                add("problema", "Almacenamiento", f"Vida util agotada del SSD: {fmt(vida, 0)}%", "El contador de desgaste (Wear) indica fin de vida util cercano. Reemplazo preventivo recomendado.")
            elif vida < 50:
                add("atencion", "Almacenamiento", f"SSD desgastado: {fmt(vida, 0)}% de vida restante", "El desgaste acumulado recomienda planificar un reemplazo del disco a mediano plazo.")

    discos_hdd = [d for d in discos if d.get("Tipo") == "HDD"]
    discos_ssd = [d for d in discos if "SSD" in d.get("Tipo", "")]
    if discos_hdd and not discos_ssd:
        add("atencion", "Almacenamiento", "Sistema operando en disco mecanico (HDD)", "Se detecto unicamente almacenamiento HDD. Actualizar a un disco SSD aumentara drasticamente la velocidad del equipo.")

    libre_c = libre_en("C:", datos.get("Particiones", []))
    total_c = total_en("C:", datos.get("Particiones", []))
    if libre_c is not None and total_c:
        pct = 100 * libre_c / total_c
        if libre_c < UMBRAL_LIBRE_GB_PROBLEMA or pct < 5:
            add("problema", "Almacenamiento", f"Espacio critico en C: ({fmt(libre_c)} GB libres)", "Quedan menos del 5% de espacio libre; esto degrada Windows y bloquea actualizaciones.")
        elif pct < UMBRAL_LIBRE_PCT_ATENCION:
            add("atencion", "Almacenamiento", f"Espacio bajo en C: ({fmt(libre_c)} GB libres)", f"Queda menos del {UMBRAL_LIBRE_PCT_ATENCION}% de espacio libre. Conviene liberar espacio.")
        else:
            add("ok", "Almacenamiento", f"Espacio suficiente en C: ({fmt(libre_c)} GB libres)", f"{fmt(pct, 0)}% del disco disponible.")

    ram = datos.get("RAM", {})
    ram_pct = ram.get("En_Uso_Pct", 0)
    if ram_pct >= UMBRAL_RAM_ATENCION:
        add("atencion", "Memoria", f"Uso elevado de memoria ({fmt(ram_pct, 0)}%)",
            "Medido en reposo relativo; puede ser normal si hay muchas aplicaciones abiertas. Si la PC esta lenta, evaluar ampliar RAM o revisar procesos.")
    else:
        add("ok", "Memoria", f"Uso de memoria dentro de lo normal ({fmt(ram_pct, 0)}%)", f"Total instalado: {ram.get('Total_GB', '-')} GB.")

    inicio = datos.get("Inicio", [])
    n_inicio = len(inicio)
    if n_inicio >= UMBRAL_INICIO_PROBLEMA:
        add("problema", "Arranque", f"{n_inicio} programas se inician con Windows", "Exceso de programas al inicio: alarga el arranque y consume recursos. Depurar prioritariamente.")
    elif n_inicio >= UMBRAL_INICIO_ATENCION:
        add("atencion", "Arranque", f"{n_inicio} programas se inician con Windows", "Conviene deshabilitar los que no sean imprescindibles.")
    else:
        add("ok", "Arranque", f"Inicio ordenado ({n_inicio} programas)", "Cantidad razonable de programas al arranque.")

    bat = datos.get("Bateria")
    if bat:
        salud = bat.get("Salud_Pct", 0)
        if salud < UMBRAL_BATERIA_PROBLEMA:
            add("problema", "Bateria", f"Bateria degradada: {fmt(salud)}% de capacidad original",
                f"Conserva {bat.get('Actual_mWh', 0)} mWh de los {bat.get('Diseno_mWh', 0)} mWh de fabrica. Autonomia muy reducida; considerar reemplazo.")
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

    bsod = datos.get("BSOD_30d")
    if isinstance(bsod, int) and bsod > 0:
        if bsod >= 2:
            add("problema", "Sistema", f"{bsod} pantallas azules en 30 dias", "El visor de eventos registra apagados inesperados o errores de pantalla azul. Revisar drivers, memoria y estabilidad del sistema.")
        else:
            add("atencion", "Sistema", f"1 evento de apagado inesperado en 30 dias", "Se registro una pantalla azul o apagon en el visor de eventos. Conviene monitorear.")

    bat = datos.get("Bateria") or {}
    ciclos = bat.get("Ciclos")
    if isinstance(ciclos, int) and ciclos >= 800:
        add("atencion", "Bateria", f"Bateria con {ciclos} ciclos de carga", "Un recuento elevado de ciclos indica desgaste acumulado; considerar reemplazo proactivo.")

    basura_mb = _basura_total_mb(datos)
    if basura_mb >= 1024:
        add("atencion", "Sistema", f"Archivos temporales acumulados: {fmt(basura_mb / 1024, 1)} GB",
            "Se acumularon temporales de usuario y del sistema. Una limpieza de 1 clic liberara espacio en disco.")
    elif basura_mb >= 512:
        add("info", "Sistema", f"Archivos temporales: {fmt(basura_mb / 1024, 1)} GB",
            "Hay archivos temporales acumulados que una limpieza puede liberar.")

    serv_ter = datos.get("Servicios_Terceros") or []
    tareas_ter = datos.get("Tareas_Terceros") or []
    if len(serv_ter) >= 3:
        add("atencion", "Sistema", f"{len(serv_ter)} servicios de terceros activos",
            "Varios servicios externos se inician automaticamente con Windows; conviene revisarlos para acelerar el arranque.")
    elif len(serv_ter) >= 1:
        add("info", "Sistema", f"{len(serv_ter)} servicio(s) de terceros activo(s)",
            "Se detectaron servicios externos iniciados con el sistema; verificar que todos sean necesarios.")
    if len(tareas_ter) >= 5:
        add("info", "Sistema", f"{len(tareas_ter)} tareas programadas de terceros",
            "Hay varias tareas programadas externas; conviene revisar que no sean innecesarias.")

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
        if unidad == "%" and dec == 0 and umbral < 10:
            umbral = 10
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
.meta { font-size: 12px; color: #555; line-height: 1.75; text-align: right; }
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
.tabla-lista td { padding: 6px 8px; line-height: 1.45; }
.tabla-lista td:nth-child(2) { overflow-wrap: anywhere; }
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
@page {
  size: A4;
  margin: 0mm;
  padding: 0mm;
}
@media print {
  @page {
    size: A4;
    margin: 0mm;
    padding: 0mm;
  }
  html, body {
    background: #fff;
    padding: 0;
    margin: 0;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .hoja {
    box-shadow: none;
    border-radius: 0;
    max-width: none;
    padding: 10mm 12mm 14mm;
    margin: 0 auto;
  }
  .marca {
    display: none !important;
  }
  .no-print { display: none !important; }
  th, .pill, tbody tr:nth-child(even) td, .hero, .dot {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
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
    logo_src = _logo_base64(lic.get("logo") or "")
    if logo_src:
        img = f"<img src='{logo_src}' alt='logo'>"
    texto = f"<b>{nombre}</b>" + (f" &middot; WhatsApp {wa}" if wa else "")
    return f"<div class='marca'>{img}<span>{texto}</span></div>"


def _pagina(titulo, contenido, para_pdf=False):
    marca = "" if para_pdf else _marca_tecnico_html()
    botones = "" if para_pdf else "<button class='btn no-print btn-flotante' onclick=\"window.print()\">Guardar como PDF</button><p class='no-print aviso-pdf'>Informe generado por OptiChek. Guarda la version PDF desde la aplicacion (boton PDF del historial).</p>"
    html = f"""<!DOCTYPE html>
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
{botones}
</body>
</html>
"""
    return re.sub(r"\.{2,}", ".", html)


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


def _celda_vida(d, clave):
    v = d.get(clave)
    if isinstance(v, (int, float)):
        return f"{fmt(v, 0)} %" if clave == "Vida_Pct" else f"{fmt(v, 0)} h"
    return "<span class='neutro'>N/D</span>"


def _hace_dias(n):
    if n is None:
        return "no disponible"
    if n <= 0:
        return "hoy"
    if n == 1:
        return "ayer"
    return f"hace {n} dia(s)"


def _html_seccion_seguridad(datos):
    filas = []
    av_lista = datos.get("Antivirus") or []
    if av_lista:
        partes = []
        for av in av_lista:
            nombre = esc(av.get("Nombre") or "Antivirus")
            act = "ACTIVO" if av.get("Activo") else "INACTIVO"
            partes.append(f"{nombre}: <b>{act}</b>")
            dias = _dias_desde(av.get("Firma"))
            if dias is not None:
                partes.append(f"<span class='neutro'>firmas actualizadas {_hace_dias(dias)}</span>")
        filas.append(f"<tr><td style='width:44%'><b>Antivirus</b></td><td>{'<br>'.join(partes)}</td></tr>")
    upd = datos.get("WindowsUpdate") or {}
    bus = _dias_desde(upd.get("Busqueda"))
    inst = _dias_desde(upd.get("Instalacion"))
    wu_txt = "Sin datos de busqueda" if bus is None else f"Ultima busqueda: {_hace_dias(bus)}"
    if inst is not None:
        wu_txt += f"<br>Ultima instalacion: {_hace_dias(inst)}"
    filas.append(f"<tr><td><b>Actualizaciones de Windows</b></td><td>{wu_txt}</td></tr>")
    bsod = datos.get("BSOD_30d")
    if isinstance(bsod, int):
        bsod_txt = f"{bsod} en los ultimos 30 dias" if bsod else "Ninguna en los ultimos 30 dias"
    else:
        bsod_txt = "<span class='neutro'>No disponible</span>"
    filas.append(f"<tr><td><b>Pantallas azules (BSOD)</b></td><td>{bsod_txt}</td></tr>")
    return "".join(filas)


def generar_html_escaneo(datos, num, servicio=None, para_pdf=False):
    datos = dict(datos)
    datos["Inicio"] = _inicio_limpio(datos.get("Inicio") or [])
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

    slots = datos.get("Slots_RAM") or {}
    if isinstance(slots.get("Slots"), int) and isinstance(slots.get("Ocupados"), int):
        slots_txt = f"{slots['Ocupados']} de {slots['Slots']} ocupados"
        if isinstance(slots.get("MaxGB"), int):
            slots_txt += f" (soporta hasta {slots['MaxGB']} GB)"
    else:
        slots_txt = "<span class='neutro'>No disponible</span>"

    filas_metricas = (
        fila_valor("Uso de memoria RAM", f"{fmt(datos['RAM']['En_Uso_Pct'], 0)} %")
        + fila_valor("Memoria virtual (swap) en uso", f"{fmt(datos['RAM']['Swap_En_Uso_Pct'], 0)} %")
        + fila_valor("Carga de CPU", f"{fmt(datos['CPU']['Carga_Pct'], 0)} %")
        + fila_valor("Programas al inicio", str(len(datos["Inicio"])))
        + fila_valor("Tiempo de encendido (uptime)", f"{fmt(datos['Uptime_Horas'], 1)} h")
        + fila_valor("Temperatura maxima", celda_temp)
        + fila_valor("Espacio libre en C:", f"{fmt(libre_en('C:', datos['Particiones']), 1)} GB")
        + fila_valor("Archivos temporales", formato_tamano_mb(_basura_total_mb(datos)))
        + fila_valor("Slots de memoria RAM", slots_txt)
    )
    if bater:
        filas_metricas += fila_valor("Salud de bateria", pill_bateria(bater["Salud_Pct"]) + (esc(f" &middot; {int(bater['Ciclos'])} ciclos") if isinstance(bater.get("Ciclos"), int) else ""))
        cargador = bater.get("Cargador")
        if cargador:
            txt_carga = esc(str(cargador))
            if isinstance(bater.get("Carga_Pct"), int):
                txt_carga += esc(f" ({bater['Carga_Pct']}%)")
            filas_metricas += fila_valor("Cargador", txt_carga)

    filas_diag = "".join(
        f"<tr><td style='width:110px'>{pill_severidad(h['severidad'])}</td>"
        f"<td style='width:150px'>{esc(h['categoria'])}</td>"
        f"<td><b>{esc(h['titulo'])}</b><br><span class='neutro'>{esc(h['detalle'])}</span></td></tr>"
        for h in hallazgos
    )

    filas_discos = "".join(
        f"<tr><td>{esc(d['Modelo'])}</td><td>{pill('pill-neutro', esc(d.get('Tipo', 'Disco')))}</td><td>{esc(d['Interfaz'])}</td>"
        f"<td>{d['Tamano_GB']} GB</td><td>{_celda_vida(d, 'Vida_Pct')}</td><td>{_celda_vida(d, 'Horas_Encendidas')}</td>"
        f"<td>{pill_smart(d['SMART'])}</td></tr>"
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
        tabla_inicio = ("<table class='tabla-lista'><thead><tr><th style='width:26%'>Programa</th><th>Comando</th><th style='width:28%'>Origen</th></tr></thead>"
                        f"<tbody>{filas_ini}</tbody></table>")
    else:
        tabla_inicio = "<p class='sin-cambios'>No se detectaron programas al inicio.</p>"

    nav = datos.get("Navegadores") or []
    if nav:
        filas_nav = "".join(
            f"<tr><td>{esc(n.get('Nombre', ''))}</td><td>{esc(n.get('Version') or 'N/D')}</td><td>{esc(n.get('Instalacion') or 'N/D')}</td></tr>"
            for n in nav
        )
        seccion_nav = ("<div class='seccion'><h2>Navegadores instalados</h2>"
                       "<table><thead><tr><th>Navegador</th><th>Version</th><th>Instalado</th></tr></thead>"
                       f"<tbody>{filas_nav}</tbody></table></div>")
    else:
        seccion_nav = ""

    seguro = _html_seccion_seguridad(datos)
    seccion_seg = f"<div class='seccion'><h2>Seguridad y actualizaciones</h2><table><tbody>{seguro}</tbody></table></div>" if seguro else ""

    basura = datos.get("Temporales") or {}
    serv_ter = datos.get("Servicios_Terceros") or []
    tareas_ter = datos.get("Tareas_Terceros") or []
    tabla_temp = ""
    if any(v is not None for v in basura.values()):
        filas_temp = "".join(
            f"<tr><td>{esc(t)}</td><td>{'-' if v is None else formato_tamano_mb(v)}</td></tr>"
            for t, v in (
                ("Temporales del usuario", basura.get("TempUsuario")),
                ("Temporales del sistema", basura.get("TempSistema")),
                ("Descargas de Windows Update", basura.get("WindowsUpdate")),
                ("Precarga (Prefetch)", basura.get("Prefetch")),
                ("Registros de minidump", basura.get("Minidump")),
            )
        )
        tabla_temp = ("<div class='sub-bloque'>Archivos temporales</div>"
                      "<table><thead><tr><th>Ubicacion</th><th style='width:30%'>Tamano actual</th></tr></thead>"
                      f"<tbody>{filas_temp}</tbody></table>")
    filas_ter = []
    for s in serv_ter:
        filas_ter.append(f"<tr><td>{esc(s.get('Nombre', '') or s.get('Mostrar', ''))}</td><td>{esc(s.get('Ruta') or 'N/D')}</td><td>Srv</td></tr>")
    for t in tareas_ter:
        filas_ter.append(f"<tr><td>{esc(t.get('Nombre', ''))}</td><td>{esc(t.get('Ejecuta') or 'N/D')}</td><td>Tarea</td></tr>")
    tabla_ter = ""
    if filas_ter:
        tabla_ter = ("<div class='sub-bloque'>Servicios y tareas iniciados fuera de Windows</div>"
                     "<table><thead><tr><th>Nombre</th><th>Ruta / Ejecutable</th><th style='width:15%'>Tipo</th></tr></thead>"
                     f"<tbody>{''.join(filas_ter)}</tbody></table>")
    if tabla_temp or tabla_ter:
        seccion_limpieza = f"<div class='seccion'><h2>Limpieza y servicios</h2>{tabla_temp}{tabla_ter}</div>"
    else:
        seccion_limpieza = ""

    recs = recomendaciones_comerciales(datos)
    if recs:
        items_rec = "".join(f"<li>{dot_severidad(sev)}{esc(texto)}</li>" for sev, texto in recs)
        seccion_rec = f"<div class='seccion'><h2>Recomendaciones del tecnico</h2><ul class='lista-cliente'>{items_rec}</ul></div>"
    else:
        seccion_rec = ""

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
        + f"<div class='seccion'><h2>Almacenamiento, vida util y SMART</h2>"
        + ("<table><thead><tr><th>Disco</th><th>Tipo</th><th>Interfaz</th><th>Capacidad</th><th>Vida restante</th><th>Encendido</th><th>SMART</th></tr></thead>"
           f"<tbody>{filas_discos}</tbody></table><br>"
           "<table><thead><tr><th>Unidad</th><th>Sistema de archivos</th><th>Total</th><th>Libre</th></tr></thead>"
           f"<tbody>{filas_part}</tbody></table></div>")
        + f"<div class='seccion'><h2>Programas al inicio ({len(datos['Inicio'])})</h2>{tabla_inicio}</div>"
        + seccion_limpieza
        + seccion_seg
        + seccion_nav
        + seccion_rec
        + "<div class='firma'><div>Firma del tecnico</div><div>Firma del cliente</div></div>"
        + f"<p class='pie'>Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} por OptiChek v{VERSION} &mdash; Los porcentajes son valores instantaneos tomados al momento del escaneo.</p>"
    )

    titulo = f"Diagnostico #{num:03d} - {equipo}"
    return _pagina(titulo, pagina_cliente + contenido_tecnico, para_pdf=para_pdf)


def _tabla_hallazgos(lista, vacio):
    if not lista:
        return f"<p class='sin-cambios'>{vacio}</p>"
    filas = "".join(
        f"<tr><td style='width:105px'>{pill_severidad(h['severidad'])}</td>"
        f"<td style='width:150px'>{esc(h['categoria'])}</td><td>{esc(h['titulo'])}</td></tr>"
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


def generar_html_diferencias(a, b, et_a, et_b, servicio=None, para_pdf=False):
    a = dict(a)
    a["Inicio"] = _inicio_limpio(a.get("Inicio") or [])
    b = dict(b)
    b["Inicio"] = _inicio_limpio(b.get("Inicio") or [])
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
        return _pagina(f"Diferencias {et_a} vs {et_b} - {equipo}", contenido, para_pdf=para_pdf)

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

    return _pagina(f"Diferencias {et_a} vs {et_b} - {equipo}", pagina_cliente + secciones, para_pdf=para_pdf)


_SERVIDOR_INFORMES = {"httpd": None, "puerto": None, "extra": {}}


def _servidor_informes():
    st = _SERVIDOR_INFORMES
    if st["httpd"]:
        return st["puerto"]

    class Maneja(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nombre = self.path.lstrip("/")
            if not nombre or "/" in nombre or "\\" in nombre:
                self.send_response(404)
                self.end_headers()
                return
            ruta = st["extra"].get(nombre)
            if not ruta:
                ruta = os.path.join(carpeta_descargas(), nombre)
            if not os.path.exists(ruta):
                self.send_response(404)
                self.end_headers()
                return
            try:
                with open(ruta, "rb") as fh:
                    datos = fh.read()
            except Exception:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            if ruta.lower().endswith(".pdf"):
                self.send_header("Content-Type", "application/pdf")
            else:
                self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def log_message(self, *args):
            pass

    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Maneja)
    hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
    hilo.start()
    st["httpd"] = httpd
    st["puerto"] = httpd.server_address[1]
    return st["puerto"]


def _servir_archivo(ruta):
    st = _SERVIDOR_INFORMES
    puerto = _servidor_informes()
    nombre = "informe" + str(len(st["extra"]) + 1) + os.path.splitext(ruta)[1]
    st["extra"][nombre] = ruta
    return f"http://127.0.0.1:{puerto}/{nombre}"


def url_reporte(ruta):
    try:
        puerto = _servidor_informes()
        return f"http://127.0.0.1:{puerto}/{os.path.basename(ruta)}"
    except Exception:
        return ruta


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


def _perfil_edge_tmp(sufijo):
    carpeta = os.path.join(tempfile.gettempdir(), "optichek_pdf_perfil_" + str(sufijo))
    try:
        shutil.rmtree(carpeta, ignore_errors=True)
    except Exception:
        pass
    try:
        os.makedirs(carpeta, exist_ok=True)
        prefs_dir = os.path.join(carpeta, "Default")
        os.makedirs(prefs_dir, exist_ok=True)
        prefs = {
            "printing": {
                "print_preview_sticky_settings": {
                    "headerFooterEnabled": False,
                    "isHeaderFooterEnabled": False,
                    "margins_type": 2,
                    "paper_type": 0,
                    "scaling": 100,
                    "should_print_backgrounds": False,
                    "should_print_selection_only": False
                },
                "print_header_footer": False
            },
            "plugins": {
                "always_open_pdf_externally": False
            }
        }
        with open(os.path.join(prefs_dir, "Preferences"), "w", encoding="utf-8") as f:
            json.dump(prefs, f)
    except Exception:
        pass
    return carpeta


def _es_pdf_valido(ruta):
    try:
        import time
        if not os.path.exists(ruta):
            time.sleep(0.5)
            if not os.path.exists(ruta):
                return False
        time.sleep(0.5)
        if os.path.getsize(ruta) < 1500:
            return False
        with open(ruta, "rb") as fh:
            cabecera = fh.read(5)
            return cabecera == b"%PDF-"
    except Exception:
        return False


def _firma_pdf(ruta):
    try:
        if not os.path.exists(ruta):
            return "no-existe"
        if os.path.getsize(ruta) == 0:
            return "0-bytes"
        with open(ruta, "rb") as fh:
            cabecera = fh.read(16)
        return str(cabecera[:5])
    except Exception as exc:
        return "error: " + str(exc)


def _esperar_pdf_valido(ruta, segundos=8):
    import time
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if _es_pdf_valido(ruta):
            return True
        time.sleep(0.4)
    return False


def _matar_edge_perfil(perfil):
    try:
        if not perfil:
            return
        viejo = os.environ.get("OPTICHEK_PERFIL")
        os.environ["OPTICHEK_PERFIL"] = perfil
        comando = (
            "$p = Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\"; "
            "foreach ($x in $p) { if ($x.CommandLine -and "
            "$x.CommandLine.Contains('--user-data-dir=' + $env:OPTICHEK_PERFIL)) { "
            "Stop-Process -Id $x.ProcessId -Force -ErrorAction SilentlyContinue } }"
        )
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", comando],
            timeout=30, capture_output=True, text=True,
        )
        if viejo is None:
            os.environ.pop("OPTICHEK_PERFIL", None)
        else:
            os.environ["OPTICHEK_PERFIL"] = viejo
    except Exception:
        pass


def generar_pdf_de_informe(ruta_html, ruta_pdf=None):
    import time
    if not ruta_pdf:
        ruta_pdf = os.path.join(os.path.dirname(ruta_html), os.path.splitext(os.path.basename(ruta_html))[0] + ".pdf")
    import http.server
    import threading
    servidor = None
    perfil = None
    pdf_temporal = None
    navegador = None
    detalles = []
    try:
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=os.path.dirname(ruta_html), **kwargs)
            def log_message(self, format, *args):
                pass

        servidor = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        puerto = servidor.server_address[1]
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        navegador = _encontrar_navegador()
        if not navegador:
            raise FileNotFoundError("No se encontró Microsoft Edge ni Google Chrome")
        file_url = "file:///" + os.path.abspath(ruta_html).replace("\\", "/")
        fuentes = [
            ("--headless=new", f"http://127.0.0.1:{puerto}/{os.path.basename(ruta_html)}"),
            ("--headless", file_url),
            ("--headless=new", file_url),
        ]
        idx = 0
        for pasada in range(2):
            for modo, fuente in fuentes:
                idx += 1
                perfil = _perfil_edge_tmp(f"{os.getpid()}_p{pasada}_{idx}")
                pdf_temporal = os.path.join(tempfile.gettempdir(), f"optichek_{os.getpid()}_{time.time_ns()}.pdf")
                args = [
                    navegador, modo, "--disable-gpu", "--no-sandbox",
                    "--disable-extensions", "--disable-background-networking",
                    "--no-first-run", "--no-default-browser-check",
                    "--disable-crash-reporter", "--disable-features=msEdgeSidebarV2",
                    "--allow-file-access-from-files", f"--user-data-dir={perfil}",
                    f"--print-to-pdf={pdf_temporal}", fuente,
                ]
                try:
                    resultado = subprocess.run(args, timeout=60, capture_output=True, text=True)
                    salida = (resultado.stderr or resultado.stdout or "sin salida").strip()[-200:]
                except Exception as exc:
                    resultado = None
                    salida = "excepcion: " + str(exc)
                if _esperar_pdf_valido(pdf_temporal):
                    try:
                        shutil.copy2(pdf_temporal, ruta_pdf)
                    except Exception:
                        pass
                    _matar_edge_perfil(perfil)
                    if _es_pdf_valido(ruta_pdf):
                        return ruta_pdf
                _matar_edge_perfil(perfil)
                rc = resultado.returncode if resultado is not None else "EXC"
                detalles.append(f"{modo} | {os.path.basename(fuente)[:40]} | rc={rc} | {salida}")
            time.sleep(1.0)
        raise RuntimeError("Edge no creó el PDF. " + " | ".join(detalles[-6:]))
    except Exception:
        return None
    finally:
        if servidor:
            servidor.shutdown()
            servidor.server_close()
        if perfil:
            shutil.rmtree(perfil, ignore_errors=True)
        if pdf_temporal:
            try:
                os.remove(pdf_temporal)
            except OSError:
                pass
        try:
            for d in glob.glob(os.path.join(tempfile.gettempdir(), "optichek_pdf_perfil_" + str(os.getpid()) + "_*")):
                _matar_edge_perfil(d)
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


def _generar_informe_con_pdf(contenido_html, nombre_base):
    descargas = carpeta_descargas()
    ruta_pdf_final = os.path.join(descargas, nombre_base + ".pdf")
    ruta_html_final = os.path.join(descargas, nombre_base + ".html")
    tmp_dir = tempfile.mkdtemp(prefix="diag_inf_")
    ruta_html_tmp = os.path.join(tmp_dir, "informe.html")
    ruta_pdf_tmp = os.path.join(tmp_dir, "informe.pdf")
    
    try:
        with open(ruta_html_tmp, "w", encoding="utf-8") as fh:
            fh.write(contenido_html)
        
        ruta_pdf = generar_pdf_de_informe(ruta_html_tmp, ruta_pdf_tmp)
        
        if ruta_pdf and os.path.exists(ruta_pdf_tmp) and _es_pdf_valido(ruta_pdf_tmp):
            try:
                shutil.copy2(ruta_pdf_tmp, ruta_pdf_final)
                return ruta_pdf_final, True
            except Exception as e:
                raise RuntimeError(f"Error copiando PDF a descargas: {e}")
        else:
            with open(ruta_html_final, "w", encoding="utf-8") as fh:
                fh.write(contenido_html)
            raise RuntimeError(f"Error generando PDF. Se guardó HTML en descargas para convertir manualmente. "
                             f"Verifica que Microsoft Edge o Google Chrome esté disponible.\nArchivo: {os.path.basename(ruta_html_final)}")
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def generar_informe_escaneo(datos, num, servicio=None):
    contenido = generar_html_escaneo(datos, num, servicio, para_pdf=True)
    sid = (servicio or {}).get("Id", "SRV")
    nombre_slug = slug_equipo(nombre_escaneo(datos, num))[:24].strip("_")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    return _generar_informe_con_pdf(contenido, f"{sid}_Escaneo{num:03d}_{nombre_slug}_{stamp}")


def generar_informe_comparacion(a, b, et_a, et_b, servicio=None):
    contenido = generar_html_diferencias(a, b, et_a, et_b, servicio, para_pdf=True)
    sid = (servicio or {}).get("Id", "SRV")
    na = et_a.replace("#", "")
    nb = et_b.replace("#", "")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    return _generar_informe_con_pdf(contenido, f"{sid}_Comparacion_{na}_vs_{nb}_{stamp}")
