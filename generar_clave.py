import nucleo

while True:
    nombre = input("Nombre del tecnico: ").strip()
    if not nucleo._norm_tecnico(nombre):
        print("El nombre no puede estar vacio.")
        continue
    print("-------------------------------------------------")
    print("Clave de licencia:", nucleo.generar_clave_tecnico(nombre))
    print("Entregala junto con el nombre exacto del tecnico.")
    print("-------------------------------------------------")