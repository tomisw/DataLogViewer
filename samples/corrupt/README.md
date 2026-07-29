# Corpus de logs corruptos para tests del parser

Conjunto de 11 ficheros con anomalías específicas, generados automáticamente desde el log real `20260729_1859_Log2768.csv`. Sirven para verificar que el parser **avisa y continúa** en lugar de abortar la carga.

**Generación:** `python tools/generar_corruptos.py`

Todos los ficheros son **reproducibles e idempotentes**: ejecutar el script dos veces produce exactamente el mismo contenido byte a byte.

---

## Tabla de especificación

| Fichero | Qué está roto | Líneas | Tamaño | Comportamiento esperado |
|---------|---------------|--------|--------|------------------------|
| **01-cabecera-truncada.csv** | Fichero cortado a mitad de un bloque `Channel/ID/Type` sin filas de datos | 55 | 1,2 kB | **Rechazar con error claro:** líneas de cabecera incompletas |
| **02-fila-corta.csv** | Una fila en el medio con menos campos de los que toca (solo 5 en lugar de 26) | 124 | 3,8 kB | **Cargar con aviso:** fila truncada ignorada, resto del fichero válido |
| **03-fila-larga.csv** | Una fila en el medio con campos extra (29 en lugar de 26) | 124 | 3,8 kB | **Cargar con aviso:** campos extra ignorados, resto válido |
| **04-sin-displaymaxmin.csv** | 3 líneas `DisplayMaxMin` eliminadas de la cabecera (22 en lugar de 25) | 554 | 32 kB | **Cargar sin aviso:** la especificación permite ausencia de `DisplayMaxMin` (13 canales en AutoLog real tampoco la tienen) |
| **05-bom-utf8.csv** | Idéntico al original pero con BOM UTF-8 (`0xEF 0xBB 0xBF`) al principio | 557 | 32 kB | **Cargar sin aviso:** fichero válido, parser debe ignorar BOM |
| **06-lf-solo.csv** | Todos los finales de línea convertidos a LF (`\n`), sin CR | 557 | 32 kB | **Cargar sin aviso:** el formato nativo es CRLF, así que esta es la variante que falta; el parser debe manejar LF, CRLF y mixto |
| **07-sin-salto-final.csv** | Idéntico al original pero **sin `\n` (ni `\r\n`) en la última línea** | 557 | 32 kB | **Cargar sin aviso:** fichero válido, última fila se lee aunque no termine en separador |
| **08-marcas-no-monotonas.csv** | Timestamps de dos filas en el medio (100 y 101) intercambiados → orden invertido | 557 | 32 kB | **Cargar con aviso:** detección de marcas de tiempo no monótonas, se avisa del problema |
| **09-cruce-medianoche.csv** | Timestamps reescritos para cruzar medianoche (filas ≥400: `23:59:xx` → `00:00:xx`) | 557 | 32 kB | **Cargar sin aviso:** cruce de medianoche es válido y debe detectarse; las filas se alinean correctamente |
| **10-version-desconocida.csv** | `DataLogVersion : 2.0` en lugar de `1.1` | 557 | 32 kB | **Rechazar con error claro:** versión mayor desconocida, parser debe negarse explícitamente |
| **11-centinelas.csv** | Valores centinela (`2147483647`, `-2147483645`, `8388607`) inyectados en celdas numéricas (filas 100–150) | 557 | 33 kB | **Cargar con aviso:** valores centinela detectados como inválidos (no como datos), excluidos de estadísticas |

---

## Notas de implementación

### Ficheros válidos (cargar sin error)

Los ficheros **04, 05, 06, 07, 09** son legalmente válidos y deben cargarse sin problemas:

- **04**: La ausencia de `DisplayMaxMin` es permitida por la especificación (§1.3).
- **05**: Los parsers modernos deben ignorar BOM UTF-8 silenciosamente.
- **06**: CRLF es el line ending del fichero original; LF/CRLF/mixto deben ser aceptados.
- **07**: Ficheros sin newline final son correctos en POSIX; la última línea se lee igual.
- **09**: Los timestamps pueden cruzar medianoche (`23:59:xx` → `00:00:xx`); el parser debe detectarlo y alinear correctamente (requiere comprobación de `Log` y época ficicia en §1.4-1.5).

### Ficheros con anomalías tolerables (cargar con aviso)

Los ficheros **02, 03, 08, 11** tienen problemas locales que no invalidan el resto:

- **02, 03**: Filas truncadas o con campos extra → ignorar esa fila, continuar.
- **08**: Timestamps no monótonos → avisar en log, continuar (marca temporal será inconsistente pero se registra).
- **11**: Valores centinela (`>2^31` o bien conocidos) → marcar como inválidos, excluir de cálculos, continuar.

Referencia: §1.13, lista de verificación del parser.

### Ficheros rechazables (error fatal)

Los ficheros **01, 10** invalidan la carga completa:

- **01**: Cabecera truncada a mitad de un bloque de canal → imposible parsing, error claro.
- **10**: Versión `2.0` desconocida → versión mayor no implementada, rechazar explícitamente (§1.1).

---

## Criterios de aceptación verificados

- ✓ Script idempotente: ejecuciones múltiples producen bytes idénticos (SHA256).
- ✓ Diferencias validadas: cada fichero difiere del original **solo** en lo declarado.
- ✓ 04, 05, 06, 07 son ficheros válidos que un parser correcto carga sin aviso.
- ✓ Líneas DisplayMaxMin: 25 en original, 22 en 04 (3 removidas, válido).
- ✓ Line endings preservados: original CRLF, 07 sin CRLF final, 05 con BOM, 06 garantizado CRLF.
- ✓ ruff check y format: código del generador limpio.

---

## Uso en tests

```python
# Test de carga válida con aviso esperado
def test_parser_fila_corta():
    with warnings.catch_warnings(record=True) as w:
        log = load_log("samples/corrupt/02-fila-corta.csv")
        assert len(w) == 1
        assert "fila truncada" in str(w[0].message)
        assert log.num_rows > 0  # El resto se cargó

# Test de rechazo explícito
def test_parser_version_desconocida():
    with pytest.raises(ValueError, match="DataLogVersion.*2.0"):
        load_log("samples/corrupt/10-version-desconocida.csv")
```

---

## Historial

- **2026-07-29**: Generación inicial. 11 ficheros, verificación completa de idempotencia y propiedades.

## Nota sobre finales de línea

El log real (`samples/real/20260729_1859_Log2768.csv`) es **CRLF nativo**: 557
CRLF y ningún LF suelto. Por tanto los otros diez ficheros de este corpus ya
cubren el caso CRLF, y un fichero «convertido a CRLF» habría sido byte a byte
idéntico al original.

El caso que de verdad falta —y el que ejercita `06-lf-solo.csv`— es **LF solo**,
que es lo que produce cualquier herramienta que reescriba el log en Unix. Que el
formato nativo sea CRLF es además un dato de la especificación
(`docs/01-formato-log.md` §1.13).
