# OptiChek

Herramienta portable para técnicos de reparación de PC: escanea el estado completo de una computadora con Windows, genera un **informe PDF** listo para entregar al cliente y permite **comparar cualquier par de escaneos** para demostrar qué mejoró y qué empeoró después del mantenimiento.

[![Descargar](https://img.shields.io/badge/descargar-%C3%BAltima_versi%C3%B3n-blue)](../../releases/latest)
![Plataforma](https://img.shields.io/badge/windows-10%20%7C%2011-lightgrey)
![Python](https://img.shields.io/badge/python-3.12+-yellow)

## Descargar

1. Ir a la sección de [Releases](../../releases/latest)
2. Descargar `OptiChek.exe`
3. Ejecutarlo (no requiere instalación). Windows puede avisar que es de origen desconocido: elegir *Más información → Ejecutar de todos modos*

## Licencia de técnico

La versión gratuita genera todos los informes. Si sos **técnico de reparación**, activá el **modo técnico** (botón *Modo técnico*) y tus PDFs pasan a llevar tu **logo y tu WhatsApp** en cada página, con el nombre del técnico en la barra de título.

- Licencia de técnico (un solo pago): **$29.990**
- Pagás acá: [https://mpago.li/2w4jF47](https://mpago.li/2w4jF47)
- Después de pagar, recibís la clave de licencia junto con instrucciones para activarla.

## Qué hace

- **Escaneo completo**: CPU, RAM y swap, discos físicos con S.M.A.R.T., particiones y espacio libre, programas que arrancan con Windows, temperaturas (multi-fuente: LibreHardwareMonitor → ACPI), GPU, placa madre, batería (salud real según diseño vs capacidad actual) y tiempo de encendido.
- **Diagnóstico automático con semáforo**: cada aspecto se clasifica como 🟢 Correcto / 🟡 Atención / 🔴 Problema, con umbrales configurables en el código.
- **Informe PDF doble**: primera página simple para el cliente + páginas técnicas con todo el detalle. Se guarda automáticamente en la carpeta *Descargas*.
- **Historial por servicio**: cada cliente es un servicio (`SRV-FECHA-NNN`) con su propio historial numerado de escaneos. Podés nombrar cada escaneo (ej: "Limpieza inicial") o dejar el número automático.
- **Comparación antes/después**: elegís dos escaneos cualquiera del servicio y genera un PDF de diferencias que distingue *qué cambió* de *qué significa* (mejoró/empeoró), incluyendo evolución del diagnóstico (hallazgos resueltos, nuevos y persistentes).
- **100% local**: los datos nunca salen de la PC. Se guardan en una carpeta `servicios\` junto al ejecutable.

## Requisitos

- Windows 10 u 11
- Permisos de administrador (para leer S.M.A.R.T. detallado y temperaturas; sin ellos funciona igual con menos detalle)
- Microsoft Edge o Chrome instalado (para convertir el informe a PDF; si no hay navegador, descarga el informe en HTML)

## Uso recomendado

1. Copiá `OptiChek.exe` a un pendrive junto con una carpeta vacía llamada `servicios`
2. En casa del cliente: ejecutá el programa, creá el servicio con nombre del cliente y técnico
3. Hacé el **escaneo inicial** (queda como #001) y entregale al cliente su PDF
4. Realizá el mantenimiento
5. Hacé otro escaneo y usá **Comparar** → el PDF de diferencias le muestra al cliente exactamente qué cambió

## Compilar desde fuente

```bat
git clone https://github.com/ventiladortactico/Diagnostico-PC.git
cd Diagnostico-PC
pip install -r requirements.txt
compilar.bat
```

El ejecutable queda en `dist\OptiChek.exe`. Requiere Python 3.12+.

## Estructura

| Archivo | Descripción |
|---|---|
| `nucleo.py` | Motor: escaneo (WMI/psutil), diagnóstico, historial, informes HTML/PDF |
| `diagnostico.py` | Interfaz gráfica (CustomTkinter) |
| `compilar.bat` | Compila el ejecutable con PyInstaller |

Los umbrales del diagnóstico (batería mínima, % de RAM aceptable, etc.) son constantes al inicio de `nucleo.py`, fáciles de ajustar.

## Privacidad

Todo se procesa y almacena localmente. La carpeta `servicios\` contiene los datos de tus clientes: no la compartas ni la subas a ningún repositorio.
