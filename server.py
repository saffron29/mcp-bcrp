"""Servidor MCP del BCRP. Empiecen aquí: buscar_series ya funciona; completen los TODO hasta que pasen las pruebas.

    uv run pytest                                           # el contrato: las 8 pruebas deben pasar
    uv run server.py                                        # el servidor, por stdio
    claude mcp add --scope project bcrp -- uv run server.py # conectarlo a Claude Code

Las cuentas las hace Python, no el modelo: así cada cifra sale de una llamada que se puede repetir.
"""
import json
import re
import time
import unicodedata
from functools import cache
from pathlib import Path

import httpx
import pandas as pd
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

AQUI = Path(__file__).parent
CATALOGO = AQUI / "datos" / "catalogo_bcrp.csv"
URL_CATALOGO = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": True}

mcp = FastMCP("bcrp", instructions=(
    "Series oficiales del Banco Central de Reserva del Perú (BCRP). Primero busca el código con buscar_series; "
    "luego usa resumen para variaciones, promedios y extremos, y serie para los datos. No calcules a mano: "
    "cita siempre el código de la serie y el periodo."))


def _sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


@cache
def catalogo():
    """El catálogo oficial: 17 mil series en unos 7 MB. Se baja una vez y queda en datos/."""
    if not CATALOGO.exists():
        CATALOGO.parent.mkdir(exist_ok=True)
        r = httpx.get(URL_CATALOGO, timeout=120)
        r.raise_for_status()
        CATALOGO.write_text(r.content.decode("latin-1"), encoding="utf-8")
    df = pd.read_csv(CATALOGO, sep=";", dtype=str).fillna("")
    df = df.rename(columns={"Código de serie": "codigo", "Categoría de serie": "categoria", "Grupo de serie": "grupo",
                            "Nombre de serie": "nombre", "Frecuencia": "frecuencia",
                            "Fecha de actualización": "actualizada", "Fecha de inicio": "inicio"})
    df["texto"] = (df.categoria + " " + df.grupo + " " + df.nombre).map(_sin_tildes)
    return df


def _ficha(codigo):
    fila = catalogo().query("codigo == @codigo")
    if fila.empty:
        raise ToolError(f"No existe el código de serie {codigo!r}. Búsquenlo con buscar_series.")
    f = fila.iloc[0]
    return {"codigo": f.codigo, "nombre": f"{f.grupo} - {f.nombre}", "categoria": f.categoria,
            "frecuencia": f.frecuencia, "inicio": f.inicio, "actualizada": f.actualizada}


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_series(texto: str, frecuencia: str | None = None, limite: int = 10) -> list[dict]:
    """Busca series del BCRP por palabras: todas deben aparecer en la categoría, el grupo o el nombre.

    Ejemplos: "ipc 12 meses", "tipo de cambio interbancario venta", "reservas internacionales netas",
    "tasa de referencia", "cobre precio". frecuencia: "Diaria", "Mensual", "Trimestral" o "Anual".
    Devuelve el código, el nombre completo, la frecuencia y desde cuándo hay datos. Si no hay resultados,
    prueben con menos palabras.
    """
    df = catalogo()
    m = pd.Series(True, index=df.index)
    for palabra in _sin_tildes(texto).split():
        m &= df.texto.str.contains(re.escape(palabra))
    if frecuencia:
        m &= df.frecuencia.str.lower() == frecuencia.lower()
    # primero las series vigentes y, entre ellas, las de nombre más corto (las más generales)
    sel = df[m]
    orden = sel.assign(vieja=sel.actualizada < "2025", largo=(sel.grupo + sel.nombre).str.len())
    return [_ficha(c) for c in orden.sort_values(["vieja", "largo"]).head(limite).codigo]


# TODO 1 · serie: debe considerarse que la API pide "2025-1" (mensual y trimestral), "2025-01-15" (diaria) o "2025"
# (anual), pero responde "Ene.2025", "01.Oct.26", "T1.25" o "2025". Por ello, las dos funciones siguientes realizan
# la traducción en cada sentido.
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12}


def _fecha_api(fecha, frecuencia, final=False):
    """Convierte "2025-01", "2025-T1" o "2025-01-15" al formato que pide la API, según la frecuencia de la serie."""
    partes = str(fecha).strip().upper().replace("T", "").split("-")
    anio = partes[0]
    if frecuencia == "Anual" or len(partes) == 1:
        if frecuencia == "Diaria":       # si se pide "2025" en una serie diaria, se toma todo el año
            return f"{anio}-12-31" if final else f"{anio}-01-01"
        if frecuencia in ("Mensual", "Trimestral"):
            return f"{anio}-{(4 if frecuencia == 'Trimestral' else 12) if final else 1}"
        return anio
    if frecuencia == "Diaria":
        if len(partes) == 2:             # si se pide "2026-10" en una serie diaria, se toma todo el mes
            dia = pd.Period(f"{anio}-{partes[1]}", "M").days_in_month if final else 1
            return f"{anio}-{int(partes[1]):02d}-{dia:02d}"
        return f"{anio}-{int(partes[1]):02d}-{int(partes[2]):02d}"
    return f"{anio}-{int(partes[1])}"   # en mensual y trimestral, la API pide el número sin cero adelante


def _periodo(nombre, frecuencia):
    """Convierte el nombre que devuelve la API ("Ene.2025", "01.Oct.26", "T1.25", "2025") al formato "2025-01",
    "2026-10-01", "2025-T1" o "2025"."""
    if frecuencia == "Mensual":
        mes, anio = nombre.split(".")
        return f"{anio}-{MESES[mes[:3].lower()]:02d}"
    if frecuencia == "Diaria":
        dia, mes, anio = nombre.split(".")
        return f"20{anio}-{MESES[mes[:3].lower()]:02d}-{int(dia):02d}"
    if frecuencia == "Trimestral":
        trimestre, anio = nombre.split(".")
        return f"20{anio}-{trimestre}"
    return nombre


@cache
def _pedir(url):
    """Descarga el JSON de la API. Ahora bien, si la API responde con la página HTML que envía cuando recibe
    demasiados pedidos seguidos, se espera unos segundos y se vuelve a intentar."""
    for intento in range(4):
        try:
            r = httpx.get(url, timeout=60)
            return json.loads(r.content.decode("latin-1"))
        except (httpx.HTTPError, json.JSONDecodeError):
            time.sleep(2 * (intento + 1))
    raise ToolError(f"El BCRP no respondió con datos para {url}. Se recomienda esperar unos segundos y volver a "
                    "intentarlo.")


@mcp.tool(annotations=SOLO_LECTURA)
def serie(codigo: str, desde: str, hasta: str) -> dict:
    """Datos de una serie del BCRP entre dos fechas, ambas incluidas, con la URL de la fuente.

    Las fechas dependen de la frecuencia de la serie: "2025-01" (mensual), "2025-01-15" (diaria), "2025-T1"
    (trimestral) o "2025" (anual). Por ejemplo: serie("PN01273PM", "2025-01", "2025-12"). En caso de no conocer el
    código, se debe usar antes buscar_series. Asimismo, para variaciones, promedios o valores extremos se debe usar
    resumen en lugar de calcularlos a mano.
    """
    ficha = _ficha(codigo)               # lanza un ToolError si el código no existe
    frecuencia = ficha["frecuencia"]
    url = f"{API}/{codigo}/json/{_fecha_api(desde, frecuencia)}/{_fecha_api(hasta, frecuencia, final=True)}"
    datos = [{"periodo": _periodo(p["name"], frecuencia), "valor": round(float(p["values"][0]), 4)}
             for p in _pedir(url).get("periods", []) if p["values"][0] != "n.d."]
    if not datos:
        raise ToolError(f"La serie {codigo} no tiene datos entre {desde} y {hasta}; "
                        f"hay datos desde {ficha['inicio']}.")
    return {"codigo": codigo, "nombre": ficha["nombre"], "frecuencia": frecuencia, "datos": datos, "fuente": url}


# TODO 2 · resumen: reutiliza serie, de modo que las operaciones las realiza Python y no el modelo.
@mcp.tool(annotations=SOLO_LECTURA)
def resumen(codigo: str, desde: str, hasta: str) -> dict:
    """Resume una serie del BCRP en un periodo: primer y último dato, cambio, variación %, promedio, máximo y mínimo.

    Se debe usar para preguntas como «cuánto subió», «cuál fue el promedio» o «cuándo fue el máximo», así como para
    leer un solo dato (desde = hasta). Las fechas siguen el formato de serie: "2025-01", "2025-01-15", "2025-T1" o
    "2025". Debe tenerse en cuenta que, si la serie ya es una tasa en % (por ejemplo, la inflación), el cambio está
    expresado en puntos porcentuales, mientras que variacion_pct es la variación relativa de dicha tasa, que casi
    nunca es lo que se pregunta.
    """
    s = serie(codigo, desde, hasta)
    df = pd.DataFrame(s["datos"])
    primero, ultimo = df.iloc[0], df.iloc[-1]
    maximo, minimo = df.loc[df.valor.idxmax()], df.loc[df.valor.idxmin()]
    dato = lambda fila: {"periodo": fila.periodo, "valor": float(fila.valor)}
    return {"codigo": codigo, "nombre": s["nombre"], "frecuencia": s["frecuencia"], "n": len(df),
            "primero": dato(primero), "ultimo": dato(ultimo),
            "cambio": round(ultimo.valor - primero.valor, 4),
            "variacion_pct": round((ultimo.valor / primero.valor - 1) * 100, 2) if primero.valor else None,
            "promedio": round(df.valor.mean(), 4), "maximo": dato(maximo), "minimo": dato(minimo),
            "fuente": s["fuente"]}


# TODO 3 · Herramienta propia: calcula la correlación entre dos series en los periodos que tienen en común.
@mcp.tool(annotations=SOLO_LECTURA)
def correlacion(codigo_a: str, codigo_b: str, desde: str, hasta: str) -> dict:
    """Correlación de Pearson entre dos series del BCRP de la misma frecuencia, en los periodos que tienen en común.

    Se debe usar cuando se pregunte si dos indicadores se mueven juntos o en sentido contrario, como por ejemplo la
    inflación (PN01273PM) y la tasa de referencia (PD04722MM) entre "2022-01" y "2026-09". El resultado va de -1 a
    1: un valor cercano a 1 indica que ambas series suben juntas, uno cercano a -1 indica que una sube cuando la
    otra baja, y uno cercano a 0 indica que no hay relación lineal. Sin embargo, debe considerarse que correlación
    no implica causalidad. Las fechas siguen el formato de serie, y la respuesta incluye las URL de ambas fuentes.
    """
    a, b = serie(codigo_a, desde, hasta), serie(codigo_b, desde, hasta)
    if a["frecuencia"] != b["frecuencia"]:
        raise ToolError(f"{codigo_a} es {a['frecuencia'].lower()} y {codigo_b} es {b['frecuencia'].lower()}: "
                        "se deben elegir dos series de la misma frecuencia (buscar_series permite filtrar por "
                        "frecuencia).")
    df = pd.DataFrame(a["datos"]).merge(pd.DataFrame(b["datos"]), on="periodo", suffixes=("_a", "_b"))
    if len(df) < 3:
        raise ToolError(f"{codigo_a} y {codigo_b} solo comparten {len(df)} periodos entre {desde} y {hasta}; "
                        "se requieren 3 o más.")
    r = round(df.valor_a.corr(df.valor_b), 3)
    fuerza = "fuerte" if abs(r) >= 0.7 else "moderada" if abs(r) >= 0.4 else "débil"
    return {"serie_a": {"codigo": codigo_a, "nombre": a["nombre"]},
            "serie_b": {"codigo": codigo_b, "nombre": b["nombre"]},
            "periodos": len(df), "desde": df.periodo.iloc[0], "hasta": df.periodo.iloc[-1],
            "correlacion": r, "lectura": f"correlación {fuerza} {'positiva' if r >= 0 else 'negativa'}",
            "fuentes": [a["fuente"], b["fuente"]]}


# TODO 4 · Recurso: al tratarse de una plantilla, se obtiene un recurso por cada una de las 17,167 series.
@mcp.resource("bcrp://serie/{codigo}")
def ficha(codigo: str) -> dict:
    """Ficha de una serie del BCRP: nombre, categoría, frecuencia, desde cuándo hay datos y última actualización."""
    return {**_ficha(codigo), "fuente": URL_CATALOGO}


# TODO 5 · Prompt: una plantilla de instrucciones reutilizable, que se lanza con /mcp__bcrp__informe.
@mcp.prompt
def informe(tema: str) -> str:
    """Informe de cinco viñetas sobre un tema económico, con cifras verificables del BCRP."""
    return (f"Escribe 5 viñetas sobre «{tema}» con datos oficiales del BCRP. Busca las series con buscar_series "
            "y saca cada cifra con resumen o serie, sin hacer cuentas a mano. En cada viñeta cita el código de la "
            "serie, el periodo y la URL de la fuente.")


if __name__ == "__main__":
    mcp.run()
