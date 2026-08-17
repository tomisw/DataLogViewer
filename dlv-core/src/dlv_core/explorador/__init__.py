"""Explorador de logs: triaje de una carpeta (épica E15, fase FE).

Convierte una carpeta con decenas de logs en una tabla ordenable y filtrable,
para poder elegir cuáles merecen análisis sin abrirlos uno a uno. La
especificación está en `docs/02-alcance-y-plan.md` §2.5, épica E15.

`indice.py` (FE-01) es el catálogo de la carpeta y su revalidación; el resumen
de cada log —los agregados por rol que llenan las columnas— es FE-02.
`escaneo.py` (FE-08) recorre el plan de FE-01 emitiendo una fila a la vez, de
forma cancelable, para que la tabla se pueble a medida que se calcula en vez
de esperar a que termine toda la carpeta.
"""
