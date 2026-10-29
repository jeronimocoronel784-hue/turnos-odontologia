"""Hash y verificación de passwords con bcrypt (C-03, D1b).

Se usa `bcrypt` directo porque `passlib` 1.7.4 está roto con bcrypt 5.x.
bcrypt trunca a 72 bytes: el schema limita el password a 72 caracteres y acá se
rechaza cualquier valor que supere ese límite en bytes para no aceptar entradas
silenciosamente distintas.
"""

import bcrypt

LIMITE_BYTES = 72


class PasswordInvalido(ValueError):
    """El password excede lo que bcrypt puede hashear sin truncar."""


def hashear_password(password: str, rounds: int) -> str:
    """Devuelve el hash `$2b$` del password con las rondas indicadas."""
    crudo = password.encode("utf-8")
    if len(crudo) > LIMITE_BYTES:
        raise PasswordInvalido("La contraseña no puede superar los 72 bytes.")
    return bcrypt.hashpw(crudo, bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verificar_password(password: str, hash_guardado: str) -> bool:
    """Compara en tiempo constante; un hash corrupto cuenta como password incorrecto."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hash_guardado.encode("ascii"))
    except (ValueError, TypeError):
        return False
