"""Genera la figura del informe, que muestra los aciertos, las respuestas «no sé» y los errores de cada modo, tanto
en la corrida base como en la corrida sin la instrucción de responder null.

    uv run graficar.py          # lee resultados_base.csv y resultados_sin_null.csv, y escribe grafico.png
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

AQUI = Path(__file__).parent
CORRIDAS = {"con null": "resultados_base.csv", "sin null": "resultados_sin_null.csv"}
RESULTADOS = {"acierta": "#0ca30c", "no sabe": "#a3a29b", "se equivoca": "#d03b3b"}
TINTA, TINTA_SUAVE, FONDO = "#0b0b0b", "#52514e", "#fcfcfb"

# se construye una fila por cada modo y corrida, con el número de preguntas en cada resultado
filas = []
for corrida, archivo in CORRIDAS.items():
    res = pd.read_csv(AQUI / archivo)
    for modo, grupo in res.groupby("modo"):
        conteo = grupo.resultado.value_counts()
        filas.append({"barra": f"{'MCP del BCRP' if modo == 'mcp' else 'Solo memoria'} · {corrida}",
                      **{r: conteo.get(r, 0) for r in RESULTADOS}})
orden = [f"{m} · {c}" for m in ["Solo memoria", "MCP del BCRP"] for c in CORRIDAS]
tabla = pd.DataFrame(filas).set_index("barra").loc[orden[::-1]]   # se invierte, ya que barh dibuja de abajo arriba
print(tabla)

fig, ax = plt.subplots(figsize=(8, 3.6), facecolor=FONDO)
ax.set_facecolor(FONDO)
izquierda = pd.Series(0, index=tabla.index)
for resultado, color in RESULTADOS.items():
    ancho = tabla[resultado]
    ax.barh(tabla.index, ancho, left=izquierda, color=color, height=0.55, label=resultado,
            edgecolor=FONDO, linewidth=2)
    for y, (n, x) in enumerate(zip(ancho, izquierda)):
        if n:
            ax.text(x + n / 2, y, str(n), ha="center", va="center", fontsize=10, fontweight="bold",
                    color="white" if resultado != "no sabe" else TINTA)
    izquierda += ancho

ax.set_xlim(0, 10)
ax.set_xlabel("preguntas (de 10)", color=TINTA_SUAVE)
ax.set_title("¿Acierta Claude (Haiku) las cifras del BCRP?", loc="left", color=TINTA, fontsize=12)
ax.tick_params(colors=TINTA_SUAVE, length=0)
for lado in ["top", "right", "left"]:
    ax.spines[lado].set_visible(False)
ax.spines["bottom"].set_color("#d9d8d3")
ax.legend(ncols=3, loc="upper left", bbox_to_anchor=(0, -0.22), frameon=False, labelcolor=TINTA_SUAVE)
fig.tight_layout()
fig.savefig(AQUI / "grafico.png", dpi=150)
