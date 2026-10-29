# Informe · ¿Acierta Claude las cifras del BCRP con y sin un MCP propio?

Frank Pinares · 28 de octubre de 2026 · Diplomatura de Ciencia de Datos (Q-LAB PUCP), Python Intermedio

Construí un servidor MCP (`server.py`, FastMCP 4.1.4) con las 17,167 series del BCRP y medí con `evaluar.py` cuántas
de 10 cifras oficiales acierta Claude **Haiku** respondiendo solo de memoria y cuántas con el MCP. Las 8 pruebas de
`test_server.py` pasan (`uv run pytest -q` → `8 passed`).

## 1. Resultados

![Aciertos por modo](grafico.png)

| Corrida | Modo | Acierta | No sabe | Se equivoca | Segundos por pregunta |
|---|---|---|---|---|---|
| Base (con la instrucción de responder `null`) | Solo memoria | 0 | 10 | 0 | 6.7 |
| Base (con la instrucción de responder `null`) | MCP del BCRP | **10** | 0 | 0 | 17.3 |
| Experimento (sin la instrucción de responder `null`) | Solo memoria | 0 | 9 | **1** | 7.4 |
| Experimento (sin la instrucción de responder `null`) | MCP del BCRP | **10** | 0 | 0 | 17.4 |

Archivos: `resultados.csv` y `resultados_base.csv` (corrida base, idénticos) y `resultados_sin_null.csv` (experimento).

Valor de cada pregunta en la corrida base:

| id | Serie | Verdad | MCP | Memoria |
|---|---|---|---|---|
| ipc_set26 | PN01273PM | 4.5487 | 4.5487 | no sabe |
| ipc_dic25 | PN01273PM | 1.5088 | 1.5088 | no sabe |
| ipc_mar25 | PN01271PM | 0.8102 | 0.8102 | no sabe |
| referencia_set26 | PD04722MM | 4.25 | 4.25 | no sabe |
| tc_15oct26 | PD04638PD | 3.4282 | 3.4282 | no sabe |
| rin_ago26 | PN00027MM | 96517.9 | 96517.9058 | no sabe |
| cobre_ago26 | PN38784BM | 689.70 | 689.6988 | no sabe |
| pbi_2025 | PM04923AA | 3.4306 | 3.4306 | no sabe |
| **desempleo_set26** (mía) | PN38063GM | 4.4 | 4.3717 | no sabe |
| **expectativa_set26** (mía) | PD12912AM | 3.09 | 3.0875 | no sabe |

## 2. Qué acertó y qué no, y por qué

**MCP del BCRP: 10 de 10 en ambas corridas.** Cada respuesta tomó de 4 a 6 turnos, es decir, varias llamadas a
herramientas: `resultados.csv` no guarda cuáles, pero en mi prueba interactiva en Claude Code la secuencia fue
`buscar_series` y luego `resumen` o `serie`. En la columna `fuente` cita el código de la serie, el periodo y la URL de
la API, por ejemplo
`https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PN01271PM/json/2025-3/2025-3`. Acertó porque la cifra no sale
del modelo: sale de una llamada a la API que cualquiera puede repetir, y las cuentas las hace Python. A cambio, tarda
más (unos 17 s frente a 7 s), porque cada pregunta necesita varias llamadas a herramientas.

**Solo memoria, corrida base: 0 aciertos y 10 «no sé».** La instrucción decía «si no puedes saberlo con certeza, pon
valor null: no estimes», y Haiku la cumplió en las 10 preguntas. Sus explicaciones dicen que no tenía herramientas
para consultar al BCRP ni al INEI y que su conocimiento llega hasta junio de 2026. Llama la atención que también se
abstuvo en cifras anteriores a esa fecha, como la inflación de marzo de 2025 o el PBI de 2025: no las recordaba con
la precisión que pide la tolerancia y prefirió no estimar.

**Experimento: sin la instrucción de `null`, la memoria se equivocó una vez.** Ejecuté
`uv run evaluar.py --sin-null --salida resultados_sin_null.csv`, que borra esa frase de la instrucción. En 9 de las 10
preguntas Claude siguió respondiendo `null`: el esquema JSON todavía lo permite, y el modelo explicó que no tenía
acceso a datos. En la pregunta del **PBI de 2025** sí dio una cifra, **3.0 %** contra los **3.43 %** oficiales, y
explicó que «proviene de mi conocimiento de las proyecciones publicadas por el BCRP a finales de 2025, no del dato
oficial de cierre». Es el caso típico de una cifra inventada: plausible y con justificación, pero no es el dato
oficial. Sin la salida fácil, el modelo pasó de «no sé» a estimar justo en la pregunta donde tenía algo parecido en
memoria. El MCP no cambió: sigue en 10 de 10, porque con la herramienta no necesita estimar.

## 3. Dos cifras comprobadas a mano en la web del BCRP

Comparé las respuestas del MCP en mis dos preguntas con las tablas de la web del BCRP. Las revisé yo mismo en el
navegador:

| Serie | Periodo | Web del BCRP | Mi MCP | Diferencia |
|---|---|---|---|---|
| PN38063GM · Tasa de desempleo de Lima Metropolitana, promedio móvil tres meses (%) | setiembre de 2026 (`Sep26`) | **4.4** | 4.3717 | 0.03: la web redondea a un decimal |
| PD12912AM · Expectativa de inflación a 12 meses (%) | setiembre de 2026 (`Sep26`) | **3.09** | 3.0875 | 0.003: la web redondea a dos decimales |

Tablas consultadas:
[PN38063GM](https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PN38063GM/html/2026-1/2026-10/) y
[PD12912AM](https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PD12912AM/html/2026-1/2026-10/).

## 4. Conclusión

Con las mismas 10 preguntas y el mismo modelo, el MCP pasó de 0 a 10 aciertos, y cada cifra trae su serie, su periodo
y su URL. Sin la instrucción de abstenerse, la memoria empezó a inventar: el PBI de 2025 salió 0.43 puntos por debajo
del dato oficial. Construir un MCP vale la pena cuando las preguntas se repiten sobre una misma fuente oficial con API,
cuando se necesitan cifras exactas y verificables o cuando hay que hacer cuentas sobre los datos. La búsqueda web
puede bastar para consultas ocasionales y variadas. No la corrí; en la demo del profesor acertó 7 de 8, tardó unos
26 s por pregunta y falló en el cobre.

## Cómo repetir la medición

```bash
uv run pytest -q                                              # 8 passed
uv run evaluar.py                                             # corrida base → resultados.csv
uv run evaluar.py --sin-null --salida resultados_sin_null.csv # experimento
uv run graficar.py                                            # grafico.png
```

Hice dos cambios a `evaluar.py`. Agregué las opciones `--sin-null` y `--salida`, para repetir el experimento sin editar
el archivo. También agregué `encoding="utf-8"` a la llamada de `subprocess.run`, porque en Windows leía la salida de
`claude -p` con la codificación del sistema y fallaba con las tildes.
