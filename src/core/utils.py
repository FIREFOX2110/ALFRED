"""
utils.py -- funciones pequeñas de apoyo, sin dependencias de otros
módulos del proyecto. Separado aparte justamente para que cualquier
otro módulo (memory, llm_engine, commands, etc.) la pueda usar sin
crear un import circular.
"""
from datetime import datetime


def get_current_date_str() -> str:
    days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
              "septiembre", "octubre", "noviembre", "diciembre"]
    now = datetime.now()
    return f"{days[now.weekday()]}, {now.day} de {months[now.month - 1]} de {now.year}"
