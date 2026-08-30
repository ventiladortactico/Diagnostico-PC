import os
import sys
import uuid
import hashlib
import datetime
import requests

URL = os.environ.get("SUPABASE_URL", "https://zvalnpvidqxrcqdpdmfh.supabase.co")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def nueva_clave():
    d = hashlib.sha256(os.urandom(16)).hexdigest().upper()
    return f"{d[:6]}-{d[6:10]}-{d[10:14]}"


def insertar(clave, para, dias):
    if not SERVICE_KEY:
        print("ERROR: falta la variable SUPABASE_SERVICE_ROLE_KEY")
        sys.exit(1)
    r = requests.post(
        URL + "/rest/v1/claves_activacion",
        headers={"apikey": SERVICE_KEY, "Authorization": "Bearer " + SERVICE_KEY, "Content-Type": "application/json"},
        json={"clave": clave, "creada_para": para, "dias": dias},
        timeout=20,
    )
    if r.status_code >= 400:
        print("ERROR insertando en Supabase:", r.status_code, r.text[:300])
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Uso:  python generar_clave.py \"Nombre del tecnico\" [dias]")
        print("      La clave queda insertada en Supabase y ya se puede canjear.")
        sys.exit(1)
    para = sys.argv[1]
    dias = int(sys.argv[2]) if len(sys.argv) > 2 else 365
    clave = nueva_clave()
    insertar(clave, para, dias)
    print("Clave creada para:", para)
    print("Clave:", clave)
    print("Dias:", dias)
    print("Vence aprox:", datetime.date.today() + datetime.timedelta(days=dias))


if __name__ == "__main__":
    main()