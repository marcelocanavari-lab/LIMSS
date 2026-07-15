"""
Generador de hash de PIN para LIMSS
Uso: python generar_pin_hash.py
"""
import bcrypt

print("=" * 50)
print("  Generador de hash de PIN - LIMSS")
print("=" * 50)

while True:
    pin = input("\nIngresa el PIN (4-6 digitos, Enter para salir): ").strip()
    if not pin:
        break
    if not pin.isdigit() or not (4 <= len(pin) <= 6):
        print("  ERROR: el PIN debe tener entre 4 y 6 digitos numericos")
        continue

    hashed = bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    print(f"\n  Hash generado ({len(hashed)} caracteres):")
    print(f"  {hashed}")
    print(f"\n  Ejecuta esto en SSMS:")
    print(f"  UPDATE [LIMSS].[dbo].[lims_usuarios]")
    print(f"  SET pin_hash = '{hashed}'")
    print(f"  WHERE codigo = 'ADMIN';")

print("\nListo.")
