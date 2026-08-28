import os
import threading
import traceback
from tkinter import filedialog

import customtkinter as ctk
from tkinter import messagebox

import nucleo


ACENTO = "#3b82f6"
VERDE = "#22c55e"
ROJO = "#ef4444"
AMBAR = "#f59e0b"
GRIS = "#9ca3af"


class DialogoServicio(ctk.CTkToplevel):
    def __init__(self, master, al_crear):
        super().__init__(master)
        self.al_crear = al_crear
        self.title("Nuevo servicio")
        self.geometry("420x360")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        cfg = nucleo.leer_config()

        ctk.CTkLabel(self, text="NUEVO SERVICIO", font=("Segoe UI", 18, "bold"), text_color=ACENTO).pack(pady=(24, 2))
        ctk.CTkLabel(
            self,
            text="Los escaneos de este equipo quedaran agrupados bajo\nun ID unico, junto a los demas servicios del historial.",
            font=("Segoe UI", 12),
            text_color=GRIS,
            justify="center",
        ).pack()

        cont = ctk.CTkFrame(self, fg_color="transparent")
        cont.pack(fill="both", expand=True, padx=36, pady=14)

        ctk.CTkLabel(cont, text="Cliente", font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(6, 2))
        self.ent_cliente = ctk.CTkEntry(cont, height=34, placeholder_text="Nombre del cliente")
        self.ent_cliente.pack(fill="x")
        self.ent_cliente.focus()

        ctk.CTkLabel(cont, text="Tecnico asignado (opcional)", font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(12, 2))
        self.ent_tecnico = ctk.CTkEntry(cont, height=34, placeholder_text="Tu nombre")
        if cfg.get("ultimo_tecnico"):
            self.ent_tecnico.insert(0, cfg["ultimo_tecnico"])
        self.ent_tecnico.pack(fill="x")

        self.lbl_error = ctk.CTkLabel(cont, text="", font=("Segoe UI", 12), text_color=ROJO)
        self.lbl_error.pack(pady=(8, 0))

        ctk.CTkButton(self, text="Crear servicio", height=40, font=("Segoe UI", 14, "bold"), command=self._crear).pack(
            fill="x", padx=36, pady=(0, 10)
        )
        self.bind("<Return>", lambda e: self._crear())

    def _crear(self):
        cliente = self.ent_cliente.get().strip()
        if not cliente:
            self.lbl_error.configure(text="El nombre del cliente es obligatorio.")
            return
        try:
            sid = nucleo.crear_servicio(cliente, self.ent_tecnico.get())
        except Exception as e:
            self.lbl_error.configure(text=str(e))
            return
        self.grab_release()
        self.destroy()
        self.al_crear(sid)


class DialogoModoTecnico(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Modo tecnico")
        self.geometry("520x360")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(self, text="MODO TECNICO", font=("Segoe UI", 18, "bold"), text_color=ACENTO).pack(pady=(22, 2))
        ctk.CTkLabel(
            self,
            text="El tecnico certificado genera sus PDFs con su logo y WhatsApp.\nLa clave de licencia la entrega el creador de OptiChek.",
            font=("Segoe UI", 12),
            text_color=GRIS,
            justify="center",
        ).pack()

        self.cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        self.cuerpo.pack(fill="both", expand=True, padx=36)
        self._vista_licencia()

    def _renovar(self):
        for w in self.cuerpo.winfo_children():
            w.destroy()
        self._vista_licencia()

    def _vista_licencia(self):
        lic = nucleo.tecnico_licenciado()
        self.lic = lic
        if lic:
            self._logo = lic["logo"]
            self.lbl_titulo_lic = ctk.CTkLabel(
                self.cuerpo,
                text=f"Licencia activa para {lic['nombre']}",
                font=("Segoe UI", 14, "bold"),
                text_color=VERDE,
                anchor="w",
            )
            self.lbl_titulo_lic.pack(fill="x", pady=(6, 2))

            ctk.CTkLabel(self.cuerpo, text="Logo (PNG o JPG)", font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(8, 2))
            fila = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
            fila.pack(fill="x")
            self.lbl_logo = ctk.CTkLabel(
                fila,
                text=os.path.basename(lic["logo"]) if lic["logo"] else "Sin logo",
                font=("Segoe UI", 11),
                text_color=GRIS,
            )
            self.lbl_logo.pack(side="left", fill="x", expand=True)
            ctk.CTkButton(fila, text="Elegir...", width=90, height=28, command=self._elegir_logo).pack(side="right")

            ctk.CTkLabel(self.cuerpo, text="WhatsApp (ej: 11 5555 4444)", font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(8, 2))
            self.ent_wa = ctk.CTkEntry(self.cuerpo, height=32)
            self.ent_wa.insert(0, lic["whatsapp"])
            self.ent_wa.pack(fill="x")

            self.lbl_error = ctk.CTkLabel(self.cuerpo, text="", font=("Segoe UI", 12), text_color=ROJO)
            self.lbl_error.pack(pady=(6, 0))

            botones = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
            botones.pack(fill="x", pady=(12, 8))
            ctk.CTkButton(botones, text="Guardar", height=34, fg_color=VERDE, hover_color="#16a34a", command=self._guardar).pack(
                side="left", expand=True, fill="x", padx=(0, 6)
            )
            ctk.CTkButton(botones, text="Quitar licencia", height=34, fg_color="transparent", text_color=ROJO, border_width=1, command=self._quitar).pack(
                side="left", expand=True, fill="x", padx=(6, 0)
            )
        else:
            ctk.CTkLabel(self.cuerpo, text="Nombre del tecnico", font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(10, 2))
            self.ent_nombre = ctk.CTkEntry(self.cuerpo, height=32, placeholder_text="Ej: Juan Perez")
            self.ent_nombre.pack(fill="x")

            ctk.CTkLabel(self.cuerpo, text="Clave de licencia", font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(10, 2))
            self.ent_clave = ctk.CTkEntry(self.cuerpo, height=32, placeholder_text="XXXX-XXXX-XXXX")
            self.ent_clave.pack(fill="x")

            self.lbl_error = ctk.CTkLabel(self.cuerpo, text="", font=("Segoe UI", 12), text_color=ROJO)
            self.lbl_error.pack(pady=(8, 0))

            ctk.CTkButton(
                self.cuerpo,
                text="Activar licencia",
                height=38,
                font=("Segoe UI", 14, "bold"),
                command=self._activar,
            ).pack(fill="x", pady=(10, 8))
            self.bind("<Return>", lambda e: self._activar())

    def _elegir_logo(self):
        ruta = filedialog.askopenfilename(
            title="Logo del tecnico",
            filetypes=[("Imagen", "*.png *.jpg *.jpeg *.bmp"), ("Todos", "*.*")],
        )
        if ruta:
            self._logo = ruta
            self.lbl_logo.configure(text=os.path.basename(ruta))

    def _activar(self):
        nombre = self.ent_nombre.get().strip()
        clave = self.ent_clave.get().strip()
        try:
            nucleo.activar_tecnico(nombre, clave)
        except Exception as e:
            self.lbl_error.configure(text=str(e))
            return
        self.lbl_error.configure(text="", text_color=VERDE)
        self._renovar()
        self.master._actualizar_titulo()
        self.lbl_error.configure(text="Licencia activada. Tus PDFs llevan tu marca.")

    def _quitar(self):
        nucleo.desactivar_tecnico()
        self.master._actualizar_titulo()
        self._renovar()

    def _guardar(self):
        wa = self.ent_wa.get().strip()
        logo = getattr(self, "_logo", "")
        if not nucleo.tecnico_licenciado():
            self.lbl_error.configure(text="La licencia ya no es valida.")
            return
        nucleo.guardar_tecnico(logo=logo or "", whatsapp=wa)
        self.lbl_error.configure(text="", text_color=VERDE)
        self.lbl_error.configure(text="Marca guardada. Los proximos PDFs la incluyen.")
        self.master._actualizar_titulo()


class SelectorLista(ctk.CTkToplevel):
    def __init__(self, master, titulo, opciones, activo=None, vacio="", crear_cmd=None):
        super().__init__(master)
        self.al_elegir = None
        self.title(titulo)
        self.resizable(False, False)
        self.transient(master)
        self.configure(fg_color=("gray92", "gray12"))
        x = master.winfo_rootx() + 140
        y = master.winfo_rooty() + 120
        self.geometry(f"+{x}+{y}")

        ctk.CTkLabel(self, text=titulo, font=("Segoe UI", 15, "bold")).pack(padx=20, pady=(18, 10), anchor="w")

        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=16)

        if not opciones:
            ctk.CTkLabel(cuerpo, text=vacio, font=("Segoe UI", 13), text_color=("#666666", "#aaaaaa"), justify="left").pack(
                anchor="w", padx=6, pady=(2, 8)
            )
        for texto, valor in opciones:
            es_activo = valor == activo
            btn = ctk.CTkButton(
                cuerpo,
                text=("\u2713 " if es_activo else "") + texto,
                anchor="w",
                height=40,
                font=("Segoe UI", 13, "bold" if es_activo else "normal"),
                fg_color="#2b6cb0" if es_activo else ("gray80", "gray25"),
                hover_color="#1e4e8c" if es_activo else ("gray70", "gray35"),
                command=lambda v=valor: self._elegir(v),
            )
            btn.pack(fill="x", pady=4)

        if crear_cmd:
            ctk.CTkButton(
                cuerpo,
                text="+ Nuevo servicio",
                height=36,
                fg_color="transparent",
                border_width=1,
                border_color=("gray60", "gray45"),
                text_color=ACENTO,
                command=lambda: self._crear(crear_cmd),
            ).pack(fill="x", pady=(10, 4))

        ctk.CTkButton(
            self, text="Cerrar", width=110, height=32, fg_color="transparent", border_width=1,
            border_color=("gray60", "gray45"), command=self.destroy,
        ).pack(pady=(4, 16))

        self.lift()
        self.focus()
        self.after(150, self.grab_set)

    def _elegir(self, valor):
        cb = self.al_elegir
        self.grab_release()
        self.destroy()
        if cb:
            cb(valor)

    def _crear(self, cmd):
        self.grab_release()
        self.destroy()
        cmd()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"OptiChek v{nucleo.VERSION}")
        self._actualizar_titulo()
        try:
            self.iconbitmap(nucleo.recurso("optichek_logo.ico"))
        except Exception:
            pass
        self.geometry("1080x760")
        self.minsize(980, 640)

        self.servicios = []
        self.servicio_activo = None
        self.historial = []
        self.opciones = {}
        self.sel_a = None
        self.sel_b = None
        self.ocupado = False

        self._construir()
        self.after(200, self._iniciar_contexto)

    def _actualizar_titulo(self):
        lic = nucleo.tecnico_licenciado()
        sufijo = f" · Tecnico: {lic['nombre']}" if lic else ""
        self.title(f"OptiChek v{nucleo.VERSION}{sufijo}")

    def _construir(self):
        franja = ctk.CTkFrame(self, fg_color="transparent")
        franja.pack(fill="x", padx=26, pady=(8, 8))

        self.lbl_estado = ctk.CTkLabel(
            franja, text="Listo.", font=("Segoe UI", 13), text_color=GRIS, wraplength=760, justify="left"
        )
        self.lbl_estado.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(franja, text="Abrir Descargas", width=130, height=30, command=self.abrir_descargas).pack(
            side="right", padx=(12, 0)
        )

        ctk.CTkButton(
            franja, text="Modo tecnico", width=120, height=30, command=self._abrir_modo_tecnico
        ).pack(side="right", padx=(8, 0))

        self.lbl_aviso = ctk.CTkLabel(self, text="", font=("Segoe UI", 13, "bold"), text_color=AMBAR, justify="left", anchor="w")
        self.lbl_aviso.pack(fill="x", padx=28)

        barra_srv = ctk.CTkFrame(self, corner_radius=14)
        barra_srv.pack(fill="x", padx=26, pady=(6, 10))

        zona_srv = ctk.CTkFrame(barra_srv, fg_color="transparent")
        zona_srv.pack(fill="x", padx=18, pady=12)

        ctk.CTkLabel(zona_srv, text="SERVICIO ACTIVO", font=("Segoe UI", 12, "bold"), text_color=ACENTO).pack(side="left", padx=(2, 12))

        self.btn_servicio = ctk.CTkButton(
            zona_srv,
            text="-- Sin servicios --",
            width=380,
            height=32,
            anchor="w",
            font=("Segoe UI", 13),
            command=self._abrir_selector_servicio,
        )
        self.btn_servicio.pack(side="left")

        self.lbl_info_servicio = ctk.CTkLabel(zona_srv, text="", font=("Segoe UI", 12), text_color=GRIS)
        self.lbl_info_servicio.pack(side="left", padx=14)

        ctk.CTkButton(
            zona_srv,
            text="+ Nuevo servicio",
            width=150,
            height=30,
            command=self._dialogo_nuevo_servicio,
        ).pack(side="right")

        medio = ctk.CTkFrame(self, fg_color="transparent")
        medio.pack(fill="both", expand=True, padx=26, pady=4)
        medio.grid_columnconfigure(0, weight=0)
        medio.grid_columnconfigure(1, weight=1)
        medio.grid_rowconfigure(0, weight=1)

        card_scan = ctk.CTkFrame(medio, corner_radius=16)
        card_scan.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        ctk.CTkLabel(card_scan, text="NUEVO ESCANEO", font=("Segoe UI", 15, "bold"), text_color=ACENTO).pack(anchor="w", padx=22, pady=(20, 4))
        ctk.CTkLabel(
            card_scan,
            text="Analiza hardware, discos y SMART,\nRAM, CPU, programas de inicio,\ntemperaturas y bateria del equipo.\n\nGenera un PDF con:\n- Resumen simple para el cliente\n- Informe tecnico completo",
            font=("Segoe UI", 13),
            justify="left",
        ).pack(anchor="w", padx=22)

        ctk.CTkLabel(card_scan, text="Nombre del escaneo (opcional)", font=("Segoe UI", 12, "bold"), anchor="w").pack(
            fill="x", padx=22, pady=(14, 2)
        )
        self.ent_nombre = ctk.CTkEntry(card_scan, height=32, placeholder_text="Ej: Limpieza inicial")
        self.ent_nombre.pack(fill="x", padx=22)

        self.btn_escanear = ctk.CTkButton(
            card_scan,
            text="Iniciar escaneo",
            height=46,
            font=("Segoe UI", 16, "bold"),
            command=self.iniciar_escaneo,
        )
        self.btn_escanear.pack(fill="x", padx=22, pady=(10, 10))

        self.barra = ctk.CTkProgressBar(card_scan, height=10)
        self.barra.set(0)
        self.barra.pack(fill="x", padx=22)

        self.lbl_progreso = ctk.CTkLabel(card_scan, text="", font=("Segoe UI", 12), text_color=GRIS, wraplength=280, justify="left")
        self.lbl_progreso.pack(anchor="w", padx=22, pady=(8, 20))

        card_hist = ctk.CTkFrame(medio, corner_radius=16)
        card_hist.grid(row=0, column=1, sticky="nsew")

        cab_hist = ctk.CTkFrame(card_hist, fg_color="transparent")
        cab_hist.pack(fill="x", padx=22, pady=(20, 6))
        ctk.CTkLabel(cab_hist, text="HISTORIAL DEL SERVICIO", font=("Segoe UI", 15, "bold"), text_color=ACENTO).pack(side="left")
        self.lbl_cantidad = ctk.CTkLabel(cab_hist, text="0 escaneos", font=("Segoe UI", 12), text_color=GRIS)
        self.lbl_cantidad.pack(side="right")

        self.frame_lista = ctk.CTkScrollableFrame(card_hist, fg_color="transparent")
        self.frame_lista.pack(fill="both", expand=True, padx=12, pady=(0, 16))

        card_comp = ctk.CTkFrame(self, corner_radius=16)
        card_comp.pack(fill="x", padx=26, pady=(2, 12))

        zona = ctk.CTkFrame(card_comp, fg_color="transparent")
        zona.pack(pady=(12, 8), padx=22)

        ctk.CTkLabel(zona, text="COMPARAR ESCANEOS DE ESTE SERVICIO", font=("Segoe UI", 15, "bold"), text_color=ACENTO).grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 8)
        )

        ctk.CTkLabel(zona, text="Comparar", font=("Segoe UI", 13)).grid(row=1, column=0, padx=(0, 8))
        self.btn_sel_a = ctk.CTkButton(
            zona,
            text="-- elegir escaneo --",
            width=250,
            height=32,
            anchor="w",
            font=("Segoe UI", 12),
            fg_color=("gray80", "gray25"),
            hover_color=("gray70", "gray35"),
            command=self._elegir_escaneo_a,
        )
        self.btn_sel_a.grid(row=1, column=1, padx=(0, 8))

        ctk.CTkLabel(zona, text="con", font=("Segoe UI", 13)).grid(row=1, column=2, padx=(0, 8))
        self.btn_sel_b = ctk.CTkButton(
            zona,
            text="-- elegir escaneo --",
            width=250,
            height=32,
            anchor="w",
            font=("Segoe UI", 12),
            fg_color=("gray80", "gray25"),
            hover_color=("gray70", "gray35"),
            command=self._elegir_escaneo_b,
        )
        self.btn_sel_b.grid(row=1, column=3, padx=(0, 16))

        self.btn_comparar = ctk.CTkButton(
            zona,
            text="Generar PDF de diferencias",
            height=34,
            font=("Segoe UI", 14, "bold"),
            command=self.comparar,
        )
        self.btn_comparar.grid(row=1, column=4)

    def _iniciar_contexto(self):
        self._refrescar_servicios()
        if not self.servicio_activo:
            self.after(300, self._dialogo_nuevo_servicio)

    def _refrescar_servicios(self):
        self.servicios = nucleo.listar_servicios()
        cfg = nucleo.leer_config()
        ultimo = cfg.get("ultimo_servicio")

        if not self.servicios:
            self.servicio_activo = None
            self.btn_servicio.configure(text="-- Sin servicios --", state="disabled")
            self.lbl_info_servicio.configure(text="")
            self._refrescar_historial()
            return

        ids = [s["Id"] for s in self.servicios]
        if ultimo in ids:
            activo = ultimo
        else:
            activo = ids[0]
        self._activar_servicio(activo, guardar=False)

    def _abrir_selector_servicio(self):
        sel = SelectorLista(
            self,
            "Elegir servicio",
            [(f"{s['Id']}  ·  {s['Cliente']}", s["Id"]) for s in self.servicios],
            activo=self.servicio_activo,
            vacio="Todavia no hay servicios creados.",
        )
        sel.al_elegir = self._al_elegir_servicio

    def _activar_servicio(self, sid, guardar=True):
        self.servicio_activo = sid
        meta = nucleo.cargar_servicio(sid) or {}
        etiqueta = f"{sid}  ·  {meta.get('Cliente', '')}"
        self.btn_servicio.configure(text=etiqueta, state="normal")

        tec = meta.get("Tecnico", "")
        creado = meta.get("Creado", "")
        extra = f" | Tecnico: {tec}" if tec else ""
        self.lbl_info_servicio.configure(text=f"Creado: {creado}{extra}")

        if guardar:
            cfg = nucleo.leer_config()
            cfg["ultimo_servicio"] = sid
            escribir = cfg
            nucleo.escribir_config(escribir)
        self._refrescar_historial()

    def _al_elegir_servicio(self, sid):
        if nucleo.cargar_servicio(sid):
            self._activar_servicio(sid)

    def _dialogo_nuevo_servicio(self):
        DialogoServicio(self, al_crear=self._servicio_creado)

    def _servicio_creado(self, sid):
        self._refrescar_servicios()
        self._activar_servicio(sid)

    def _ui(self, fn):
        try:
            self.after(0, fn)
        except Exception:
            pass

    def _progreso(self, texto):
        self._ui(lambda: self.lbl_progreso.configure(text=texto))

    def _set_ocupado(self, ocupado):
        self.ocupado = ocupado

        def upd():
            puede = (not self.ocupado) and len(getattr(self, "historial", [])) >= 2
            estado_acciones = "disabled" if self.ocupado else "normal"
            self.btn_escanear.configure(state=estado_acciones)
            self.btn_comparar.configure(state="normal" if puede else "disabled")

        self._ui(upd)

    def _valor_alternativo(self, etiqueta):
        etiquetas = list(self.opciones.keys())
        try:
            idx = etiquetas.index(etiqueta)
        except ValueError:
            return None
        if idx > 0:
            return etiquetas[idx - 1]
        if idx < len(etiquetas) - 1:
            return etiquetas[idx + 1]
        return None

    def _elegir_escaneo_a(self):
        self._abrir_selector_escaneo("a")

    def _elegir_escaneo_b(self):
        self._abrir_selector_escaneo("b")

    def _abrir_selector_escaneo(self, lado):
        if len(self.historial) < 2 or self.ocupado:
            return
        actual = self.sel_a if lado == "a" else self.sel_b
        sel = SelectorLista(
            self,
            f"Elegir escaneo ({'primero' if lado == 'a' else 'segundo'})",
            [(e, e) for e in self.opciones.keys()],
            activo=actual,
        )
        sel.al_elegir = lambda v, ld=lado: self._fijar_seleccion(ld, v)

    def _fijar_seleccion(self, lado, valor):
        if lado == "a":
            self.sel_a = valor
            if len(self.historial) > 1 and valor == self.sel_b:
                otro = self._valor_alternativo(valor)
                if otro:
                    self.sel_b = otro
        else:
            self.sel_b = valor
            if len(self.historial) > 1 and valor == self.sel_a:
                otro = self._valor_alternativo(valor)
                if otro:
                    self.sel_a = otro
        self.btn_sel_a.configure(text=self.sel_a or "-- elegir escaneo --")
        self.btn_sel_b.configure(text=self.sel_b or "-- elegir escaneo --")

    def _refrescar_historial(self):
        for w in self.frame_lista.winfo_children():
            w.destroy()

        if not self.servicio_activo:
            self.historial = []
        else:
            self.historial = nucleo.cargar_historial(self.servicio_activo)

        self.lbl_cantidad.configure(text=f"{len(self.historial)} escaneo(s)")

        if not self.historial:
            mensaje = "Sin servicio activo." if not self.servicio_activo else (
                "Este servicio aun no tiene escaneos.\nRealiza el primero para comenzar el historial."
            )
            ctk.CTkLabel(
                self.frame_lista,
                text=mensaje,
                font=("Segoe UI", 14),
                text_color=GRIS,
                justify="center",
            ).pack(pady=40)
            self.lbl_aviso.configure(text="")
            self.sel_a = None
            self.sel_b = None
            self.btn_sel_a.configure(text="-- elegir escaneo --", state="disabled")
            self.btn_sel_b.configure(text="-- elegir escaneo --", state="disabled")
            self.btn_comparar.configure(state="disabled")
            return

        etiquetas = []
        self.opciones = {}
        for item in self.historial:
            etiqueta = f"#{item['num']:03d} · {nucleo.nombre_escaneo(item['datos'], item['num'])}"
            etiquetas.append(etiqueta)
            self.opciones[etiqueta] = item

        for item in self.historial:
            self._fila_historial(item)

        if len(self.historial) == 1:
            self.lbl_aviso.configure(
                text=f"Solo existe el escaneo {etiquetas[0]}. Realiza otro escaneo para habilitar la comparacion."
            )
            self.sel_a = None
            self.sel_b = None
            self.btn_sel_a.configure(text=etiquetas[0], state="disabled")
            self.btn_sel_b.configure(text=etiquetas[0], state="disabled")
            self.btn_comparar.configure(state="disabled")
            return

        if self.sel_a not in self.opciones or self.sel_b not in self.opciones or self.sel_a == self.sel_b:
            self.sel_a = etiquetas[0]
            self.sel_b = etiquetas[-1]
        self.btn_sel_a.configure(text=self.sel_a, state="normal")
        self.btn_sel_b.configure(text=self.sel_b, state="normal")
        self.lbl_aviso.configure(text="")

        if not self.ocupado:
            self.btn_comparar.configure(state="normal")
        else:
            self.btn_comparar.configure(state="disabled")

    def _fila_historial(self, item):
        fila = ctk.CTkFrame(self.frame_lista, corner_radius=10, fg_color=("gray88", "gray17"))
        fila.pack(fill="x", pady=4, padx=2)

        info = ctk.CTkFrame(fila, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=(14, 4), pady=9)

        datos = item["datos"]
        hallazgos = nucleo.diagnosticar(datos)
        estado, clase_estado = nucleo.estado_general(hallazgos)
        color_estado = {"pill-ok": VERDE, "pill-warn": AMBAR, "pill-mal": ROJO}.get(clase_estado, GRIS)

        resumen = f"#{item['num']:03d}  {nucleo.nombre_escaneo(datos, item['num'])}"
        ctk.CTkLabel(info, text=resumen, font=("Segoe UI", 13, "bold"), anchor="w").pack(anchor="w")

        linea2 = ctk.CTkFrame(info, fg_color="transparent")
        linea2.pack(fill="x")
        ctk.CTkLabel(linea2, text=f"{datos['Fecha']}   ", font=("Segoe UI", 11), text_color=GRIS).pack(side="left")
        ctk.CTkLabel(linea2, text=estado.title(), font=("Segoe UI", 11, "bold"), text_color=color_estado).pack(side="left")

        ctk.CTkButton(
            fila,
            text="PDF",
            width=56,
            height=30,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            font=("Segoe UI", 12),
            command=lambda it=item: self._pdf_de_item(it),
        ).pack(side="right", padx=(0, 14), pady=9)

        ctk.CTkButton(
            fila,
            text="Eliminar",
            width=76,
            height=30,
            fg_color="#b91c1c",
            hover_color="#7f1d1d",
            font=("Segoe UI", 12),
            command=lambda it=item: self._eliminar_item(it),
        ).pack(side="right", pady=9)

    def _eliminar_item(self, item):
        if self.ocupado:
            return
        nombre = nucleo.nombre_escaneo(item["datos"], item["num"])
        if not messagebox.askyesno(
            "Eliminar escaneo",
            f"Se eliminara el escaneo #{item['num']:03d} ({nombre}) del servicio {self.servicio_activo}.\n\n"
            "Esta accion no se puede deshacer. Continuar?",
        ):
            return
        if nucleo.eliminar_escaneo(self.servicio_activo, item["num"]):
            self._estado(f"Escaneo #{item['num']:03d} ({nombre}) eliminado del historial.", AMBAR)
        else:
            self._estado(f"No se pudo eliminar el escaneo #{item['num']:03d}.", ROJO)
        self._refrescar_historial()

    def iniciar_escaneo(self):
        if self.ocupado:
            return
        if not self.servicio_activo:
            messagebox.showinfo("Sin servicio", "Primero crea un servicio para asociar los escaneos.")
            self._dialogo_nuevo_servicio()
            return
        if not nucleo.es_admin():
            seguir = messagebox.askyesno(
                "Sin permisos de administrador",
                "No se estan ejecutando permisos de administrador:\n"
                "no se podran leer temperaturas ni SMART detallado.\n\nQuieres continuar de todos modos?",
            )
            if not seguir:
                return
        self._set_ocupado(True)
        self._estado("Iniciando escaneo...", GRIS)
        nombre = self.ent_nombre.get().strip()
        threading.Thread(target=self._hilo_escaneo, args=(nombre,), daemon=True).start()

    def _hilo_escaneo(self, nombre):
        co_inicializado = False
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
                co_inicializado = True
            except Exception:
                pass

            sid = self.servicio_activo
            servicio = nucleo.cargar_servicio(sid)
            datos = nucleo.escanear(progreso=self._progreso)
            self._progreso("Guardando en el historial del servicio...")
            num, _ruta = nucleo.guardar_escaneo(datos, sid, nombre)
            self._progreso("Generando PDF en Descargas...")
            salida = nucleo.generar_informe_escaneo(datos, num, servicio)
            nombre = os.path.basename(salida)
            self._terminar(True, f"Escaneo #{num:03d} completado. Informe abierto en el navegador. Para el PDF: Ctrl+P.", salida)
        except Exception as e:
            self._terminar(False, f"Error durante el escaneo: {e}")
        finally:
            if co_inicializado:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def comparar(self):
        if self.ocupado or len(self.historial) < 2:
            return
        et_a = self.sel_a
        et_b = self.sel_b
        if not et_a or not et_b or et_a == et_b:
            self._estado("Selecciona dos escaneos distintos para comparar.", AMBAR)
            return
        item_a = self.opciones.get(et_a)
        item_b = self.opciones.get(et_b)
        if not item_a or not item_b:
            return

        self._set_ocupado(True)
        self._estado("Generando comparacion...", GRIS)
        threading.Thread(target=self._hilo_comparar, args=(item_a, item_b), daemon=True).start()

    def _hilo_comparar(self, item_a, item_b):
        co_inicializado = False
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
                co_inicializado = True
            except Exception:
                pass

            servicio = nucleo.cargar_servicio(self.servicio_activo)
            et_a = f"#{item_a['num']:03d}"
            et_b = f"#{item_b['num']:03d}"
            salida = nucleo.generar_informe_comparacion(item_a["datos"], item_b["datos"], et_a, et_b, servicio)
            nombre = os.path.basename(salida)
            self._terminar(True, f"Comparacion {et_a} vs {et_b} lista. Informe abierto en el navegador. Para el PDF: Ctrl+P.", salida)
        except Exception as e:
            self._terminar(False, f"Error al generar la comparacion: {e}")
        finally:
            if co_inicializado:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def _pdf_de_item(self, item):
        if self.ocupado:
            return
        self._set_ocupado(True)
        self._estado(f"Abriendo informe del escaneo #{item['num']:03d}...", GRIS)
        threading.Thread(target=self._hilo_pdf_item, args=(item,), daemon=True).start()

    def _hilo_pdf_item(self, item):
        co_inicializado = False
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
                co_inicializado = True
            except Exception:
                pass
            servicio = nucleo.cargar_servicio(self.servicio_activo)
            salida = nucleo.generar_informe_escaneo(item["datos"], item["num"], servicio)
            nombre = os.path.basename(salida)
            self._terminar(True, f"Informe del escaneo #{item['num']:03d} abierto en el navegador. Para el PDF: Ctrl+P.", salida)
        except Exception as e:
            self._terminar(False, f"Error al generar el PDF: {e}")
        finally:
            if co_inicializado:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def _terminar(self, ok, mensaje, abrir=None):
        def ap():
            self.barra.stop()
            self.barra.set(0)
            self.lbl_progreso.configure(text="")
            try:
                self.ent_nombre.delete(0, "end")
            except Exception:
                pass
            self._refrescar_historial()
            self._set_ocupado(False)
            texto = mensaje
            if ok and len(self.historial) >= 2 and self.sel_a and self.sel_b:
                texto += f" Comparacion habilitada: {self.sel_a} vs {self.sel_b}."
            self._estado(texto, VERDE if ok else ROJO)
            if abrir:
                try:
                    os.startfile(abrir)
                except Exception:
                    pass
        self._ui(ap)

    def _estado(self, texto, color_txt=GRIS):
        self._ui(lambda: self.lbl_estado.configure(text=texto, text_color=color_txt))

    def _abrir_modo_tecnico(self):
        DialogoModoTecnico(self)

    def abrir_descargas(self):
        try:
            os.startfile(nucleo.carpeta_descargas())
        except Exception as e:
            self._estado(f"No se pudo abrir la carpeta: {e}", ROJO)


def main():
    try:
        App().mainloop()
    except Exception:
        detalle = traceback.format_exc()
        try:
            messagebox.showerror("Error inesperado", detalle[-1500:])
        except Exception:
            pass


if __name__ == "__main__":
    main()
