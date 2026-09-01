import os
import threading
import traceback
import webbrowser
from tkinter import BooleanVar, filedialog, messagebox

import customtkinter as ctk

import nucleo


ACENTO = "#3b82f6"
VERDE = "#10b981"
ROJO = "#ef4444"
AMBAR = "#f59e0b"
GRIS = "#94a3b8"
FONDO = "#0b0f17"
PANEL = "#111827"
CARD = "#1e293b"
BORDE = "#334155"
TEXTO = "#f8fafc"
TEXTO2 = "#94a3b8"
TEXTO3 = "#64748b"


def centrar_dialogo(dialogo, master, ancho=420, alto=360):
    dialogo.update_idletasks()
    mx = master.winfo_rootx()
    my = master.winfo_rooty()
    mw = master.winfo_width()
    mh = master.winfo_height()
    x = max(10, mx + (mw - ancho) // 2)
    y = max(10, my + (mh - alto) // 2)
    dialogo.geometry(f"{ancho}x{alto}+{x}+{y}")


class DialogoServicio(ctk.CTkToplevel):
    def __init__(self, master, al_crear):
        super().__init__(master)
        self.al_crear = al_crear
        self.title("Nuevo servicio")
        self.resizable(False, False)
        self.transient(master)
        self.configure(fg_color=FONDO)
        centrar_dialogo(self, master, 420, 360)
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
        self.resizable(False, False)
        self.transient(master)
        self.configure(fg_color=FONDO)
        centrar_dialogo(self, master, 520, 430)
        self.grab_set()

        ctk.CTkLabel(self, text="MODO TECNICO", font=("Segoe UI", 18, "bold"), text_color=ACENTO).pack(pady=(22, 2))
        ctk.CTkLabel(
            self,
            text="Con tu cuenta de tecnico generas PDFs con tu logo y WhatsApp.\nEl creador de OptiChek te da la clave de activacion al pagar.",
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
        estado = nucleo._estado_cuenta()
        if lic:
            self._vista_activa(lic)
        elif estado["email"]:
            self._vista_sin_suscripcion(estado)
        else:
            self._vista_login()

    def _vista_activa(self, lic):
        self._logo = lic["logo"]
        ctk.CTkLabel(
            self.cuerpo,
            text=f"Licencia activa para {lic['nombre']}",
            font=("Segoe UI", 14, "bold"),
            text_color=VERDE,
            anchor="w",
        ).pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(
            self.cuerpo,
            text="Suscripcion vigente — vence el " + (lic.get("vence") or "sin caducidad"),
            font=("Segoe UI", 11),
            text_color=TEXTO2,
            anchor="w",
        ).pack(fill="x")

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
        ctk.CTkButton(botones, text="Cerrar sesion", height=34, fg_color="transparent", text_color=ROJO, border_width=1, command=self._cerrar).pack(
            side="left", expand=True, fill="x", padx=(6, 0)
        )
        ctk.CTkButton(self.cuerpo, text="Renovar suscripcion (pagar)", height=28, fg_color="transparent",
                       text_color=ACENTO, border_width=1, border_color=BORDE, command=self._pagar).pack(fill="x", pady=(0, 4))
        ctk.CTkButton(self.cuerpo, text="Renovar por QR (escanear con celular)", height=28, fg_color="transparent",
                       text_color=VERDE, border_width=1, border_color=BORDE, command=self._pagar_qr).pack(fill="x", pady=(0, 6))

    def _vista_login(self):
        ctk.CTkLabel(self.cuerpo, text="Ingresa con tu cuenta de tecnico", font=("Segoe UI", 14, "bold"), anchor="w").pack(fill="x", pady=(6, 2))

        ctk.CTkLabel(self.cuerpo, text="Email", font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(8, 2))
        self.ent_email = ctk.CTkEntry(self.cuerpo, height=32, placeholder_text="tecnico@email.com")
        self.ent_email.pack(fill="x")

        ctk.CTkLabel(self.cuerpo, text="Contrasena", font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(8, 2))
        self.ent_pass = ctk.CTkEntry(self.cuerpo, height=32, placeholder_text="minimo 6 caracteres", show="*")
        self.ent_pass.pack(fill="x")

        ctk.CTkLabel(self.cuerpo, text="Nombre del tecnico (solo si creas cuenta)", font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(8, 2))
        self.ent_nombre = ctk.CTkEntry(self.cuerpo, height=32, placeholder_text="Ej: Juan Perez")
        self.ent_nombre.pack(fill="x")
        self.ent_nombre.bind("<FocusIn>", lambda e: self.ent_nombre.get())

        self.lbl_error = ctk.CTkLabel(self.cuerpo, text="", font=("Segoe UI", 12), text_color=ROJO, justify="left", wraplength=440)
        self.lbl_error.pack(pady=(8, 0))

        fila = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        fila.pack(fill="x", pady=(12, 4))
        ctk.CTkButton(fila, text="Ingresar", height=34, fg_color=ACENTO, hover_color="#1d4ed8", command=self._ingresar).pack(
            side="left", expand=True, fill="x", padx=(0, 6)
        )
        ctk.CTkButton(fila, text="Crear cuenta", height=34, fg_color="transparent", border_width=1, border_color=BORDE, command=self._registrar).pack(
            side="left", expand=True, fill="x", padx=(6, 0)
        )
        ctk.CTkButton(self.cuerpo, text="Reenviar email de verificacion", height=28,
                      fg_color="transparent", text_color=GRIS, command=self._reenviar).pack(fill="x", pady=(6, 0))
        self.bind("<Return>", lambda e: self._ingresar())

    def _vista_sin_suscripcion(self, estado):
        self.estado = estado
        vencido = nucleo.tecnico_vencido()
        ctk.CTkLabel(
            self.cuerpo,
            text=f"Hola {estado['nombre'] or estado['email']}",
            font=("Segoe UI", 14, "bold"),
            text_color=TEXTO,
            anchor="w",
        ).pack(fill="x", pady=(6, 2))
        if vencido:
            msj = f"Tu suscripcion vencio el {vencido['vence']}. Ingresa una clave de activacion nueva para renovarla."
        else:
            msj = "Tu cuenta esta registrada, pero todavia no tiene una suscripcion activa. Canjea la clave que te dio el creador de OptiChek."
        ctk.CTkLabel(self.cuerpo, text=msj, font=("Segoe UI", 12), text_color=ROJO if vencido else GRIS, justify="left", wraplength=440).pack(
            fill="x", pady=(6, 2)
        )

        ctk.CTkLabel(self.cuerpo, text="Clave de activacion", font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x", pady=(10, 2))
        self.ent_clave = ctk.CTkEntry(self.cuerpo, height=32, placeholder_text="XXXXXX-XXXX-XXXX")
        self.ent_clave.pack(fill="x")

        self.lbl_error = ctk.CTkLabel(self.cuerpo, text="", font=("Segoe UI", 12), text_color=ROJO, justify="left", wraplength=440)
        self.lbl_error.pack(pady=(8, 0))

        ctk.CTkButton(
            self.cuerpo,
            text="Canjear clave",
            height=38,
            font=("Segoe UI", 14, "bold"),
            command=self._canjear,
        ).pack(fill="x", pady=(10, 6))
        ctk.CTkButton(self.cuerpo, text="Pagar con tarjeta (Mercado Pago)", height=34,
                      fg_color="transparent", border_width=1, border_color=ACENTO,
                      text_color=ACENTO, command=self._pagar).pack(fill="x", pady=(0, 4))
        ctk.CTkButton(self.cuerpo, text="Pagar por QR (escanear con celular)", height=34,
                      fg_color="transparent", border_width=1, border_color=VERDE,
                      text_color=VERDE, command=self._pagar_qr).pack(fill="x", pady=(0, 4))
        botones_fin = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        botones_fin.pack(fill="x", pady=(0, 4))
        ctk.CTkButton(botones_fin, text="Ya pague, verificar", height=30,
                      fg_color="transparent", border_width=1, border_color=BORDE,
                      text_color=TEXTO, command=self._verificar_pago).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(botones_fin, text="Cerrar sesion", height=30,
                      fg_color="transparent", border_width=1, border_color=BORDE,
                      text_color=ROJO, command=self._cerrar).pack(side="left", expand=True, fill="x", padx=(6, 0))
        self.bind("<Return>", lambda e: self._canjear())

    def _elegir_logo(self):
        ruta = filedialog.askopenfilename(
            title="Logo del tecnico",
            filetypes=[("Imagen", "*.png *.jpg *.jpeg *.bmp"), ("Todos", "*.*")],
        )
        if ruta:
            self._logo = ruta
            self.lbl_logo.configure(text=os.path.basename(ruta))

    def _ingresar(self):
        email = self.ent_email.get().strip()
        passw = self.ent_pass.get()
        self.lbl_error.configure(text="Verificando...", text_color=TEXTO2)
        self.update_idletasks()
        try:
            perfil = nucleo.iniciar_cuenta(email, passw)
        except Exception as e:
            self.lbl_error.configure(text=str(e), text_color=ROJO)
            return
        self.lbl_error.configure(text="", text_color=VERDE)
        self._renovar()
        self.master._actualizar_titulo()
        if perfil.get("vence"):
            self.lbl_error.configure(text="Sesion iniciada. Tu suscripcion esta activa.")
        else:
            self.lbl_error.configure(text="Sesion iniciada. Ingresa tu clave de activacion.")

    def _registrar(self):
        email = self.ent_email.get().strip()
        passw = self.ent_pass.get()
        nombre = self.ent_nombre.get().strip()
        self.lbl_error.configure(text="Creando cuenta...", text_color=TEXTO2)
        self.update_idletasks()
        try:
            perfil = nucleo.registrar_cuenta(email, passw, nombre)
        except Exception as e:
            self.lbl_error.configure(text=str(e), text_color=ROJO)
            return
        if perfil:
            self._renovar()
            self.master._actualizar_titulo()
            self.lbl_error.configure(
                text="Cuenta creada. Paga o canjea tu clave de activacion para desbloquear el modo tecnico.",
                text_color=VERDE,
            )
        else:
            self.lbl_error.configure(text="", text_color=VERDE)
            self.lbl_error.configure(
                text="Cuenta creada. Te enviamos un email para verificar la cuenta. Confirmala y despues presiona Ingresar.",
                text_color=VERDE,
            )

    def _reenviar(self):
        email = self.ent_email.get().strip()
        try:
            nucleo.reenviar_verificacion(email)
        except Exception as e:
            self.lbl_error.configure(text=str(e), text_color=ROJO)
            return
        self.lbl_error.configure(
            text="Email de verificacion enviado. Revisa tu casilla (y el spam).", text_color=VERDE
        )

    def _canjear(self):
        clave = self.ent_clave.get().strip()
        self.lbl_error.configure(text="Activando suscripcion...", text_color=TEXTO2)
        self.update_idletasks()
        try:
            perfil = nucleo.canjear_clave(clave)
        except Exception as e:
            self.lbl_error.configure(text=str(e), text_color=ROJO)
            return
        self.lbl_error.configure(text="", text_color=VERDE)
        self._renovar()
        self.master._actualizar_titulo()
        self.lbl_error.configure(text=f"Licencia activa hasta {perfil.get('vence')}. Tus PDFs llevan tu marca.", text_color=VERDE)

    def _pagar(self):
        self.lbl_error.configure(text="Preparando el pago...", text_color=TEXTO2)
        self.update_idletasks()
        try:
            url = nucleo.url_pago()
        except Exception as e:
            self.lbl_error.configure(text=str(e), text_color=ROJO)
            return
        import webbrowser

        webbrowser.open(url)
        self.lbl_error.configure(
            text="Se abrio la pagina de Mercado Pago para pagar. Cuando termines, presiona 'Ya pague, verificar'.",
            text_color=VERDE,
        )

    def _pagar_qr(self):
        self.lbl_error.configure(text="Generando QR de pago...", text_color=TEXTO2)
        self.update_idletasks()
        try:
            qr_data = nucleo.url_pago_qr()
        except Exception as e:
            self.lbl_error.configure(text=str(e), text_color=ROJO)
            return
        import qrcode
        from PIL import ImageTk
        img = qrcode.make(qr_data, box_size=6, border=2)
        tk_img = ImageTk.PhotoImage(img)
        dlg = ctk.CTkToplevel(self)
        dlg.title("Pagar por QR")
        dlg.configure(fg_color=FONDO)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        dlg.update_idletasks()
        mx = self.winfo_rootx()
        my = self.winfo_rooty()
        mw = self.winfo_width()
        mh = self.winfo_height()
        w, h = 380, 440
        dlg.geometry(f"{w}x{h}+{max(10, mx + (mw - w) // 2)}+{max(10, my + (mh - h) // 2)}")
        ctk.CTkLabel(dlg, text="Escanea este QR con tu app de Mercado Pago", font=("Segoe UI", 15, "bold"), text_color=TEXTO).pack(pady=(18, 4))
        ctk.CTkLabel(dlg, text="Abri Mercado Pago en tu celular, tocá\n'Pagar' y escaneá el codigo.", font=("Segoe UI", 12), text_color=GRIS, justify="center").pack()
        lbl_img = ctk.CTkLabel(dlg, image=tk_img, text="")
        lbl_img._tk_img = tk_img
        lbl_img.pack(pady=10)
        ctk.CTkLabel(dlg, text="Monto: $" + str(nucleo.leer_config().get("cuenta_vence", "")) or "$25.000",
                      font=("Segoe UI", 13, "bold"), text_color=ACENTO).pack()
        ctk.CTkLabel(dlg, text="Valido 30 minutos", font=("Segoe UI", 11), text_color=TEXTO3).pack(pady=(2, 8))
        ctk.CTkButton(dlg, text="Cerrar", height=34, fg_color="transparent", border_width=1, border_color=BORDE,
                      text_color=TEXTO, command=dlg.destroy).pack(pady=(0, 14))
        self.lbl_error.configure(text="QR generado. El cliente escanea y paga con su app de Mercado Pago.", text_color=VERDE)

    def _verificar_pago(self):
        self.lbl_error.configure(text="Verificando el pago...", text_color=TEXTO2)
        self.update_idletasks()
        try:
            nucleo.estado_pago()
        except Exception as e:
            self.lbl_error.configure(text=str(e), text_color=ROJO)
            return
        if nucleo.tecnico_licenciado():
            self._renovar()
            self.master._actualizar_titulo()
            self.lbl_error.configure(text="Pago confirmado. Modo tecnico activo.", text_color=VERDE)
        else:
            self.lbl_error.configure(
                text="Todavia no se confirma el pago. Espera unos segundos y volve a intentar.", text_color=TEXTO2
            )

    def _cerrar(self):
        nucleo.cerrar_cuenta()
        self.master._actualizar_titulo()
        self._renovar()

    def _guardar(self):
        wa = self.ent_wa.get().strip()
        logo = getattr(self, "_logo", "")
        if not nucleo.tecnico_licenciado():
            self.lbl_error.configure(text="La cuenta ya no es valida.")
            return
        try:
            nucleo.guardar_tecnico(logo=logo or "", whatsapp=wa)
        except Exception as e:
            self.lbl_error.configure(text=str(e), text_color=ROJO)
            return
        self.lbl_error.configure(text="", text_color=VERDE)
        self.lbl_error.configure(text="Marca guardada. Los proximos PDFs la incluyen.", text_color=VERDE)
        self.master._actualizar_titulo()


class SelectorLista(ctk.CTkToplevel):
    def __init__(self, master, titulo, opciones, activo=None, vacio="", crear_cmd=None,
                 eliminar_cmd=None, obtener_opciones=None, activo_cmd=None):
        super().__init__(master)
        self.al_elegir = None
        self.eliminar_cmd = eliminar_cmd
        self.obtener_opciones = obtener_opciones
        self.activo_cmd = activo_cmd
        self.opciones = opciones
        self.activo = activo
        self.vacio = vacio
        self.crear_cmd = crear_cmd
        self.title(titulo)
        self.resizable(False, False)
        self.transient(master)
        self.configure(fg_color=FONDO)
        alto = min(500, max(240, 110 + len(opciones) * 46 + (48 if crear_cmd else 0)))
        ancho = 440
        centrar_dialogo(self, master, ancho, alto)

        ctk.CTkLabel(self, text=titulo, font=("Segoe UI", 15, "bold"), text_color=TEXTO).pack(padx=20, pady=(18, 10), anchor="w")

        self.cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        self.cuerpo.pack(fill="both", expand=True, padx=16)
        self._poblar()

        if crear_cmd:
            ctk.CTkButton(
                self,
                text="+ Nuevo servicio",
                height=36,
                corner_radius=10,
                fg_color="transparent",
                border_width=1,
                border_color=BORDE,
                text_color=TEXTO,
                command=lambda: self._crear(crear_cmd),
            ).pack(fill="x", padx=16, pady=(10, 4))

        ctk.CTkButton(
            self, text="Cerrar", width=110, height=32, corner_radius=10, fg_color="transparent", border_width=1,
            border_color=BORDE, text_color=TEXTO, command=self.destroy,
        ).pack(pady=(4, 16))

        self.lift()
        self.focus()
        self.after(150, self.grab_set)

    def _poblar(self):
        for w in self.cuerpo.winfo_children():
            w.destroy()
        if not self.opciones:
            ctk.CTkLabel(self.cuerpo, text=self.vacio, font=("Segoe UI", 13), text_color=TEXTO3, justify="left").pack(
                anchor="w", padx=6, pady=(2, 8)
            )
        for texto, valor in self.opciones:
            es_activo = valor == self.activo
            if self.eliminar_cmd:
                fila = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
                fila.grid_columnconfigure(0, weight=1)
                fila.pack(fill="x", pady=4)
                btn = ctk.CTkButton(
                    fila,
                    text=("\u2713 " if es_activo else "") + texto,
                    anchor="w",
                    height=40,
                    corner_radius=10,
                    font=("Segoe UI", 13, "bold" if es_activo else "normal"),
                    fg_color="#1d4ed8" if es_activo else CARD,
                    hover_color="#2563eb" if es_activo else BORDE,
                    text_color="#ffffff" if es_activo else TEXTO,
                    command=lambda v=valor: self._elegir(v),
                )
                btn.grid(row=0, column=0, sticky="ew")
                ctk.CTkButton(
                    fila,
                    text="\U0001F5D1",
                    width=40,
                    height=40,
                    corner_radius=10,
                    fg_color="transparent",
                    border_width=1,
                    border_color=BORDE,
                    hover_color=CARD,
                    text_color=ROJO,
                    font=("Segoe UI Emoji", 13),
                    command=lambda v=valor: self._eliminar(v),
                ).grid(row=0, column=1, padx=(6, 0))
            else:
                btn = ctk.CTkButton(
                    self.cuerpo,
                    text=("\u2713 " if es_activo else "") + texto,
                    anchor="w",
                    height=40,
                    corner_radius=10,
                    font=("Segoe UI", 13, "bold" if es_activo else "normal"),
                    fg_color="#1d4ed8" if es_activo else CARD,
                    hover_color="#2563eb" if es_activo else BORDE,
                    text_color="#ffffff" if es_activo else TEXTO,
                    command=lambda v=valor: self._elegir(v),
                )
                btn.pack(fill="x", pady=4)

    def _recargar(self):
        self.opciones = self.obtener_opciones() if self.obtener_opciones else self.opciones
        self.activo = self.activo_cmd() if self.activo_cmd else self.activo
        self._poblar()

    def _eliminar(self, valor):
        if not messagebox.askyesno(
            "Eliminar servicio",
            f"Se eliminara PERMANENTEMENTE el servicio:\n\n{valor}\n\n"
            "Incluye su historial de escaneos, revision fisica y reparaciones. Esta accion no se puede deshacer.\n\nEliminar?",
        ):
            return
        if self.eliminar_cmd and self.eliminar_cmd(valor):
            self._recargar()

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
        self.configure(fg_color=FONDO)

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
        self._refrescar_permisos()
        if getattr(self, "pie_lat", None) is None:
            return
        for w in self.pie_lat.winfo_children():
            w.destroy()
        if lic:
            ctk.CTkLabel(self.pie_lat, text="Tecnico", font=("Segoe UI", 10, "bold"), text_color=TEXTO3).pack(anchor="w")
            ctk.CTkLabel(self.pie_lat, text=lic["nombre"], font=("Segoe UI", 12, "bold"), text_color=VERDE).pack(anchor="w")
        else:
            ctk.CTkLabel(self.pie_lat, text="Version gratuita", font=("Segoe UI", 11), text_color=TEXTO3).pack(anchor="w")
            ctk.CTkLabel(
                self.pie_lat, text="Activa tu licencia desde\nModo tecnico", font=("Segoe UI", 11), text_color=TEXTO2, justify="left"
            ).pack(anchor="w", pady=(2, 0))

    def _refrescar_permisos(self):
        if getattr(self, "btn_revision_fisica", None) is None:
            return
        lic = nucleo.tecnico_licenciado() is not None
        for w in ([self.btn_revision_fisica, self.lbl_reparacion] + list(getattr(self, "btns_reparacion", []))):
            if w is None:
                continue
            if lic:
                w.pack(**w._pack_args)
            else:
                w.pack_forget()

    def _construir(self):
        barra_estado = ctk.CTkFrame(self, height=32, corner_radius=0, fg_color=PANEL)
        barra_estado.pack(fill="x", side="bottom")
        self.lbl_estado = ctk.CTkLabel(
            barra_estado, text="Listo.", font=("Segoe UI", 12), text_color=TEXTO2, anchor="w"
        )
        self.lbl_estado.pack(side="left", padx=16, pady=4)

        medio = ctk.CTkFrame(self, fg_color="transparent")
        medio.pack(fill="both", expand=True)
        medio.grid_columnconfigure(0, weight=0)
        medio.grid_columnconfigure(1, weight=1)
        medio.grid_rowconfigure(0, weight=1)

        barra_lat = ctk.CTkFrame(medio, width=220, corner_radius=0, fg_color=PANEL)
        barra_lat.grid(row=0, column=0, sticky="nsew")
        barra_lat.grid_propagate(False)

        marca = ctk.CTkFrame(barra_lat, fg_color="transparent")
        marca.pack(fill="x", padx=20, pady=(24, 18))
        ctk.CTkLabel(marca, text="OptiChek", font=("Segoe UI", 26, "bold"), text_color=TEXTO).pack(anchor="w")
        ctk.CTkLabel(
            marca, text=f"Diagnostico tecnico v{nucleo.VERSION}", font=("Segoe UI", 11), text_color=TEXTO3
        ).pack(anchor="w")

        sec_srv = ctk.CTkFrame(barra_lat, fg_color="transparent")
        sec_srv.pack(fill="x", padx=14, pady=(4, 12))
        ctk.CTkLabel(sec_srv, text="SERVICIO ACTIVO", font=("Segoe UI", 11, "bold"), text_color=TEXTO3).pack(
            anchor="w", padx=4, pady=(0, 6)
        )
        self.btn_servicio = ctk.CTkButton(
            sec_srv,
            text="-- Sin servicios --",
            height=38,
            corner_radius=10,
            anchor="w",
            font=("Segoe UI", 12, "bold"),
            fg_color=CARD,
            hover_color=ACENTO,
            text_color=TEXTO,
            command=self._abrir_selector_servicio,
        )
        self.btn_servicio.pack(fill="x")
        self.lbl_info_servicio = ctk.CTkLabel(sec_srv, text="", font=("Segoe UI", 11), text_color=TEXTO3)
        self.lbl_info_servicio.pack(anchor="w", padx=4, pady=(6, 0))
        ctk.CTkButton(
            sec_srv,
            text="+ Nuevo servicio",
            height=34,
            corner_radius=10,
            fg_color="transparent",
            border_width=1,
            border_color=BORDE,
            text_color=TEXTO,
            hover_color=CARD,
            font=("Segoe UI", 12),
            command=self._dialogo_nuevo_servicio,
        ).pack(fill="x", pady=(10, 0))

        sec_acc = ctk.CTkFrame(barra_lat, fg_color="transparent")
        sec_acc.pack(fill="x", padx=14, pady=(4, 0))
        ctk.CTkLabel(sec_acc, text="ACCIONES", font=("Segoe UI", 11, "bold"), text_color=TEXTO3).pack(
            anchor="w", padx=4, pady=(0, 6)
        )
        self.btn_escanear = ctk.CTkButton(
            sec_acc,
            text="Iniciar escaneo",
            height=40,
            corner_radius=10,
            font=("Segoe UI", 13, "bold"),
            fg_color=ACENTO,
            hover_color="#1d4ed8",
            text_color="#ffffff",
            command=self.iniciar_escaneo,
        )
        self.btn_escanear.pack(fill="x")
        ctk.CTkButton(
            sec_acc,
            text="Modo tecnico",
            height=34,
            corner_radius=10,
            fg_color="transparent",
            border_width=1,
            border_color=BORDE,
            text_color=TEXTO,
            hover_color=CARD,
            font=("Segoe UI", 12),
            command=self._abrir_modo_tecnico,
        ).pack(fill="x", pady=(10, 0))
        ctk.CTkButton(
            sec_acc,
            text="Abrir Descargas",
            height=34,
            corner_radius=10,
            fg_color="transparent",
            border_width=1,
            border_color=BORDE,
            text_color=TEXTO,
            hover_color=CARD,
            font=("Segoe UI", 12),
            command=self.abrir_descargas,
        ).pack(fill="x", pady=(8, 0))
        ctk.CTkButton(
            sec_acc,
            text="Limpieza de temporales",
            height=34,
            corner_radius=10,
            fg_color="transparent",
            border_width=1,
            border_color=AMBAR,
            text_color=AMBAR,
            hover_color=CARD,
            font=("Segoe UI", 12),
            command=self._iniciar_limpieza,
        ).pack(fill="x", pady=(8, 0))
        self.btn_revision_fisica = ctk.CTkButton(
            sec_acc,
            text="Revision fisica",
            height=34,
            corner_radius=10,
            fg_color="transparent",
            border_width=1,
            border_color=BORDE,
            text_color=TEXTO,
            hover_color=CARD,
            font=("Segoe UI", 12),
            command=self._abrir_revision_fisica,
        )
        self.btn_revision_fisica._pack_args = dict(fill="x", pady=(8, 0))
        self.btn_revision_fisica.pack(**self.btn_revision_fisica._pack_args)
        self.lbl_reparacion = ctk.CTkLabel(sec_acc, text="REPARACION", font=("Segoe UI", 11, "bold"), text_color=TEXTO3)
        self.lbl_reparacion._pack_args = dict(anchor="w", pady=(14, 0))
        self.lbl_reparacion.pack(**self.lbl_reparacion._pack_args)
        self.btns_reparacion = []
        for texto, accion, color in (
            ("SFC (integridad)", "sfc", TEXTO2),
            ("DISM (imagen del sistema)", "dism", TEXTO2),
            ("Reset de red", "red", TEXTO2),
        ):
            btn_rep = ctk.CTkButton(
                sec_acc,
                text=texto,
                height=30,
                corner_radius=10,
                fg_color="transparent",
                border_width=1,
                border_color=BORDE,
                text_color=color,
                hover_color=CARD,
                font=("Segoe UI", 11),
                command=lambda a=accion, t=texto: self._reparar(a, t),
            )
            btn_rep._pack_args = dict(fill="x", pady=(6, 0))
            btn_rep.pack(**btn_rep._pack_args)
            self.btns_reparacion.append(btn_rep)
        self._refrescar_permisos()

        lic = nucleo.tecnico_licenciado()
        self.pie_lat = ctk.CTkFrame(barra_lat, fg_color="transparent")
        self.pie_lat.pack(side="bottom", fill="x", padx=20, pady=(0, 16))
        if lic:
            ctk.CTkLabel(self.pie_lat, text="Tecnico", font=("Segoe UI", 10, "bold"), text_color=TEXTO3).pack(anchor="w")
            ctk.CTkLabel(self.pie_lat, text=lic["nombre"], font=("Segoe UI", 12, "bold"), text_color=VERDE).pack(anchor="w")
        else:
            ctk.CTkLabel(self.pie_lat, text="Version gratuita", font=("Segoe UI", 11), text_color=TEXTO3).pack(anchor="w")
            ctk.CTkLabel(
                self.pie_lat, text="Activa tu licencia desde\nModo tecnico", font=("Segoe UI", 11), text_color=TEXTO2, justify="left"
            ).pack(anchor="w", pady=(2, 0))

        principal = ctk.CTkFrame(medio, fg_color=FONDO)
        principal.grid(row=0, column=1, sticky="nsew")

        self.lbl_aviso = ctk.CTkLabel(
            principal, text="", font=("Segoe UI", 12, "bold"), text_color=AMBAR, anchor="w", justify="left", wraplength=780
        )
        self.lbl_aviso.pack(fill="x", padx=24, pady=(14, 0))

        cuerpo = ctk.CTkFrame(principal, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=24, pady=(12, 0))
        cuerpo.grid_columnconfigure(0, weight=0)
        cuerpo.grid_columnconfigure(1, weight=1)
        cuerpo.grid_rowconfigure(0, weight=1)

        card_scan = ctk.CTkFrame(cuerpo, width=330, corner_radius=14, fg_color=CARD)
        card_scan.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        card_scan.grid_propagate(False)

        ctk.CTkLabel(card_scan, text="NUEVO ESCANEO", font=("Segoe UI", 14, "bold"), text_color=ACENTO).pack(
            anchor="w", padx=22, pady=(20, 4)
        )
        ctk.CTkLabel(
            card_scan,
            text="Hardware, discos y SMART, RAM, CPU,\nprogramas de inicio, temperaturas y\nbateria del equipo.\n\nGenera el PDF directamente en Descargas.",
            font=("Segoe UI", 12),
            text_color=TEXTO2,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=22)

        ctk.CTkLabel(card_scan, text="Nombre del escaneo (opcional)", font=("Segoe UI", 12, "bold"), text_color=TEXTO).pack(
            fill="x", padx=22, pady=(16, 4)
        )
        self.ent_nombre = ctk.CTkEntry(
            card_scan, height=36, corner_radius=10, fg_color=FONDO, border_color=BORDE,
            placeholder_text="Ej: Limpieza inicial",
        )
        self.ent_nombre.pack(fill="x", padx=22)

        self.barra = ctk.CTkProgressBar(card_scan, height=8, progress_color=ACENTO)
        self.barra.set(0)
        self.barra.pack(fill="x", padx=22, pady=(18, 0))

        self.lbl_progreso = ctk.CTkLabel(
            card_scan, text="", font=("Segoe UI", 12), text_color=TEXTO2, wraplength=286, justify="left"
        )
        self.lbl_progreso.pack(anchor="w", padx=22, pady=(8, 20))

        card_hist = ctk.CTkFrame(cuerpo, corner_radius=14, fg_color=CARD)
        card_hist.grid(row=0, column=1, sticky="nsew")

        cab_hist = ctk.CTkFrame(card_hist, fg_color="transparent")
        cab_hist.pack(fill="x", padx=22, pady=(18, 6))
        ctk.CTkLabel(cab_hist, text="HISTORIAL DEL SERVICIO", font=("Segoe UI", 14, "bold"), text_color=ACENTO).pack(side="left")
        self.lbl_cantidad = ctk.CTkLabel(cab_hist, text="0 escaneos", font=("Segoe UI", 12), text_color=TEXTO2)
        self.lbl_cantidad.pack(side="right")

        self.frame_lista = ctk.CTkScrollableFrame(card_hist, fg_color="transparent")
        self.frame_lista.pack(fill="both", expand=True, padx=14, pady=(0, 16))

        card_comp = ctk.CTkFrame(principal, corner_radius=14, fg_color=CARD)
        card_comp.pack(fill="x", padx=24, pady=(14, 18))

        zona = ctk.CTkFrame(card_comp, fg_color="transparent")
        zona.pack(pady=(14, 12), padx=22)

        ctk.CTkLabel(zona, text="COMPARAR ESCANEOS DE ESTE SERVICIO", font=("Segoe UI", 14, "bold"), text_color=ACENTO).grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 10)
        )

        ctk.CTkLabel(zona, text="Comparar", font=("Segoe UI", 13), text_color=TEXTO2).grid(row=1, column=0, padx=(0, 8))
        self.btn_sel_a = ctk.CTkButton(
            zona,
            text="-- elegir escaneo --",
            width=250,
            height=34,
            corner_radius=10,
            anchor="w",
            font=("Segoe UI", 12),
            fg_color="transparent",
            border_width=1,
            border_color=BORDE,
            hover_color=BORDE,
            text_color=TEXTO,
            command=self._elegir_escaneo_a,
        )
        self.btn_sel_a.grid(row=1, column=1, padx=(0, 8))

        ctk.CTkLabel(zona, text="con", font=("Segoe UI", 13), text_color=TEXTO2).grid(row=1, column=2, padx=(0, 8))
        self.btn_sel_b = ctk.CTkButton(
            zona,
            text="-- elegir escaneo --",
            width=250,
            height=34,
            corner_radius=10,
            anchor="w",
            font=("Segoe UI", 12),
            fg_color="transparent",
            border_width=1,
            border_color=BORDE,
            hover_color=BORDE,
            text_color=TEXTO,
            command=self._elegir_escaneo_b,
        )
        self.btn_sel_b.grid(row=1, column=3, padx=(0, 16))

        self.btn_comparar = ctk.CTkButton(
            zona,
            text="Generar PDF de diferencias",
            height=38,
            corner_radius=10,
            font=("Segoe UI", 13, "bold"),
            fg_color=ACENTO,
            hover_color="#1d4ed8",
            text_color="#ffffff",
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
            crear_cmd=self._dialogo_nuevo_servicio,
            eliminar_cmd=self._eliminar_servicio_selector,
            obtener_opciones=lambda: [(f"{s['Id']}  ·  {s['Cliente']}", s["Id"]) for s in nucleo.listar_servicios()],
            activo_cmd=lambda: self.servicio_activo,
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
            nucleo.escribir_config(cfg)
        self._refrescar_historial()

    def _al_elegir_servicio(self, sid):
        if nucleo.cargar_servicio(sid):
            self._activar_servicio(sid)

    def _dialogo_nuevo_servicio(self):
        DialogoServicio(self, al_crear=self._servicio_creado)

    def _servicio_creado(self, sid):
        self._refrescar_servicios()
        self._activar_servicio(sid)

    def _eliminar_servicio_selector(self, sid):
        if nucleo.eliminar_servicio(sid):
            if self.servicio_activo == sid:
                self.servicio_activo = None
                cfg = nucleo.leer_config()
                if cfg.get("ultimo_servicio") == sid:
                    cfg["ultimo_servicio"] = ""
                    nucleo.escribir_config(cfg)
            self._estado(f"Servicio {sid} eliminado.", AMBAR)
            self._refrescar_servicios()
            return True
        return False

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
        fila = ctk.CTkFrame(self.frame_lista, corner_radius=10, fg_color=FONDO)
        fila.pack(fill="x", pady=4, padx=2)

        info = ctk.CTkFrame(fila, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=(14, 4), pady=9)

        datos = item["datos"]
        hallazgos = nucleo.diagnosticar(datos)
        estado, clase_estado = nucleo.estado_general(hallazgos)
        pil = {
            "pill-ok": (VERDE, "#052e23"),
            "pill-warn": (AMBAR, "#3a2a08"),
            "pill-mal": (ROJO, "#3f1212"),
        }.get(clase_estado, (TEXTO2, FONDO))
        color_estado, fondo_estado = pil

        resumen = f"#{item['num']:03d}  {nucleo.nombre_escaneo(datos, item['num'])}"
        ctk.CTkLabel(info, text=resumen, font=("Segoe UI", 13, "bold"), text_color=TEXTO, anchor="w").pack(anchor="w")

        linea2 = ctk.CTkFrame(info, fg_color="transparent")
        linea2.pack(fill="x", pady=(3, 0))
        ctk.CTkLabel(linea2, text=f"{datos['Fecha']}   ", font=("Segoe UI", 11), text_color=TEXTO2).pack(side="left")
        ctk.CTkLabel(
            linea2,
            text=estado.title(),
            font=("Segoe UI", 10, "bold"),
            text_color=color_estado,
            fg_color=fondo_estado,
            corner_radius=6,
            padx=8,
            pady=2,
        ).pack(side="left")

        ctk.CTkButton(
            fila,
            text="PDF",
            width=52,
            height=30,
            corner_radius=8,
            fg_color="transparent",
            border_width=1,
            border_color=BORDE,
            hover_color=ACENTO,
            text_color=TEXTO,
            font=("Segoe UI", 11, "bold"),
            command=lambda it=item: self._pdf_de_item(it),
        ).pack(side="right", padx=(0, 12), pady=9)

        ctk.CTkButton(
            fila,
            text="Eliminar",
            width=78,
            height=30,
            corner_radius=8,
            fg_color="transparent",
            border_width=1,
            border_color="#7f1d1d",
            hover_color="#7f1d1d",
            text_color="#f87171",
            font=("Segoe UI", 11),
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
        with nucleo.contexto_com():
            try:
                sid = self.servicio_activo
                servicio = nucleo.cargar_servicio(sid)
                datos = nucleo.escanear(progreso=self._progreso)
                self._progreso("Guardando en el historial del servicio...")
                num, _ruta = nucleo.guardar_escaneo(datos, sid, nombre)
                self._progreso("Generando PDF en Descargas...")
                salida, _ = nucleo.generar_informe_escaneo(datos, num, servicio)
                self._terminar(True, f"Escaneo #{num:03d} completado. PDF guardado en Descargas: {os.path.basename(salida)}")
            except Exception as e:
                self._terminar(False, f"Error durante el escaneo: {e}")

    def _iniciar_limpieza(self):
        if self.ocupado:
            return
        if not nucleo.es_admin():
            seguir = messagebox.askyesno(
                "Sin permisos de administrador",
                "La limpieza de temporales del sistema requiere administrador.\n"
                "Sin elevacion solo se limpiara la carpeta temporal del usuario.\n\nQuieres continuar de todos modos?",
            )
            if not seguir:
                return
        self._set_ocupado(True)
        self._estado("Limpiando archivos temporales...", GRIS)
        threading.Thread(target=self._hilo_limpieza, daemon=True).start()

    def _hilo_limpieza(self):
        try:
            res = nucleo.limpiar_temporales() or {}
            mb = res.get("MB") or 0
            arch = res.get("Archivos") or 0
            err = res.get("Errores") or 0
            msg = "Limpieza de temporales completada. Liberado: " + nucleo.formato_tamano_mb(mb)
            msg += f" ({arch} elementos eliminados"
            if err:
                msg += f"; {err} en uso o bloqueados"
            msg += ")."
            self._terminar(True, msg)
        except Exception as e:
            self._terminar(False, f"Error en la limpieza: {e}")

    def _abrir_revision_fisica(self):
        if self.ocupado:
            return
        if not nucleo.tecnico_licenciado():
            messagebox.showinfo("Modo tecnico", "La revision fisica es una opcion del modo tecnico licenciado.")
            return
        if not self.servicio_activo:
            messagebox.showinfo("Sin servicio", "Primero crea un servicio para asociar la revision.")
            self._dialogo_nuevo_servicio()
            return
        sid = self.servicio_activo
        prev = nucleo.cargar_checklist(sid) or {}
        prev_items = {item.get("Titulo"): bool(item.get("Ok")) for item in prev.get("Items", [])}

        dialogo = ctk.CTkToplevel(self)
        dialogo.title("Revision fisica del equipo")
        dialogo.geometry("560x680")
        dialogo.transient(self)
        dialogo.grab_set()
        ctk.CTkLabel(dialogo, text="Lista de revision fisica", font=("Segoe UI", 15, "bold"), text_color=TEXTO).pack(pady=(14, 2))
        ctk.CTkLabel(dialogo, text=sid, font=("Segoe UI", 11), text_color=TEXTO3).pack()

        panel = ctk.CTkScrollableFrame(dialogo, width=520, height=330, fg_color=CARD, corner_radius=10)
        panel.pack(padx=20, pady=(10, 6), fill="both", expand=True)
        vars_chk = {}
        for titulo in nucleo.CHECKLIST_FISICA:
            var = BooleanVar(value=prev_items.get(titulo, False))
            vars_chk[titulo] = var
            ctk.CTkCheckBox(panel, text=titulo, variable=var, font=("Segoe UI", 13)).pack(anchor="w", padx=12, pady=4)

        ctk.CTkLabel(dialogo, text="Observaciones del tecnico", font=("Segoe UI", 12, "bold"), text_color=TEXTO).pack(anchor="w", padx=20, pady=(10, 2))
        obs_txt = ctk.CTkTextbox(dialogo, height=90, font=("Segoe UI", 12))
        obs_txt.pack(fill="x", padx=20, pady=(0, 10))
        if prev.get("Observaciones"):
            obs_txt.insert("1.0", prev["Observaciones"])

        def _guardar():
            try:
                items = [(t, bool(v.get())) for t, v in vars_chk.items()]
                nucleo.guardar_checklist(sid, items, obs_txt.get("1.0", "end").strip())
            except Exception as e:
                messagebox.showerror("Error", str(e))
                return
            dialogo.destroy()
            self._estado("Revision fisica guardada y vinculada al servicio.", VERDE)

        ctk.CTkButton(
            dialogo, text="Guardar revision", height=36, fg_color=ACENTO, hover_color="#1d4ed8",
            text_color="#ffffff", font=("Segoe UI", 13, "bold"), command=_guardar,
        ).pack(fill="x", padx=20, pady=(0, 16))

    def _reparar(self, accion, titulo):
        if self.ocupado:
            return
        if not nucleo.tecnico_licenciado():
            messagebox.showinfo("Modo tecnico", "La seccion de reparacion es del modo tecnico licenciado.")
            return
        if not self.servicio_activo:
            messagebox.showinfo("Sin servicio", "Primero crea un servicio para registrar la reparacion.")
            self._dialogo_nuevo_servicio()
            return
        if not nucleo.es_admin():
            messagebox.showwarning("Permisos", f"{titulo} requiere permisos de administrador.")
            return
        if not messagebox.askyesno(
            titulo,
            f"Se ejecutara {titulo}.\nPuede tardar varios minutos y el equipo podria pedir un reinicio.\n\nContinuar?",
        ):
            return
        self._set_ocupado(True)
        self._estado(f"Ejecutando {titulo}...", AMBAR)
        self.barra.set(0)
        self.lbl_progreso.configure(text=f"{titulo}: iniciando...")

        def _cb_pct(pct):
            self._ui(lambda: (self.barra.set(pct / 100.0),
                              self.lbl_progreso.configure(text=f"{titulo}: {pct}%")))

        threading.Thread(target=self._hilo_reparar, args=(accion, titulo, _cb_pct), daemon=True).start()

    def _hilo_reparar(self, accion, titulo, cb_pct):
        try:
            res = nucleo.reparar(accion, progreso=cb_pct) or {}
            ok = bool(res.get("Ok"))
            detalle = (res.get("Detalle") or res.get("Salida") or "Finalizado.")
            lineas = [l for l in detalle.splitlines() if l.strip()][-4:]
            msg = f"{titulo}: " + ("OK" if ok else "FALLO")
            if lineas:
                msg += " :: " + " | ".join(lineas)[:400]
            try:
                if self.servicio_activo:
                    nucleo.registrar_reparacion(self.servicio_activo, titulo, ok, " | ".join(lineas)[:300])
            except Exception:
                pass
            self._terminar(ok, msg)
        except Exception as e:
            self._terminar(False, f"Error en {titulo}: {e}")
        finally:
            self._ui(lambda: (self.barra.set(0), self.lbl_progreso.configure(text="")))

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
        with nucleo.contexto_com():
            try:
                servicio = nucleo.cargar_servicio(self.servicio_activo)
                et_a = f"#{item_a['num']:03d}"
                et_b = f"#{item_b['num']:03d}"
                salida, _ = nucleo.generar_informe_comparacion(item_a["datos"], item_b["datos"], et_a, et_b, servicio)
                self._terminar(True, f"Comparacion {et_a} vs {et_b} lista. PDF guardado en Descargas: {os.path.basename(salida)}")
            except Exception as e:
                self._terminar(False, f"Error al generar la comparacion: {e}")

    def _pdf_de_item(self, item):
        if self.ocupado:
            return
        self._set_ocupado(True)
        self._estado(f"Generando PDF del escaneo #{item['num']:03d}...", GRIS)
        threading.Thread(target=self._hilo_pdf_item, args=(item,), daemon=True).start()

    def _hilo_pdf_item(self, item):
        with nucleo.contexto_com():
            try:
                servicio = nucleo.cargar_servicio(self.servicio_activo)
                salida, _ = nucleo.generar_informe_escaneo(item["datos"], item["num"], servicio)
                self._terminar(True, f"PDF del escaneo #{item['num']:03d} guardado en Descargas: {os.path.basename(salida)}")
            except Exception as e:
                self._terminar(False, f"Error al generar el PDF: {e}")

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
            if ok and len(self.historial) >= 2 and (self.sel_a is not None) and (self.sel_b is not None):
                if self.sel_a != self.sel_b:
                    texto += f" Comparacion habilitada: {self.sel_a} vs {self.sel_b}."
            self._estado(texto, VERDE if ok else ROJO)
            if abrir:
                try:
                    destino = nucleo.url_reporte(abrir)
                    if destino.startswith("http"):
                        webbrowser.open(destino)
                    else:
                        os.startfile(destino)
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
