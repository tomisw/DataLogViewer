# Hoja de revisión — F0-08 (`data/units.toml`)

> Generada por el orquestador. Cada fila toma un **valor crudo real** del
> log `samples/real/AutoLog_20260729_1830.csv` y lo pasa por el catálogo. Si la columna de la derecha es
> físicamente plausible para tu motor, el factor está bien.

## Lo único que hay que revisar: 14 filas

| Canal del log | Crudo | Canónica | Convertido | ¿Plausible? | Nota |
|---|---|---|---|---|---|
| Coolant Temperature | `3663` | 366,300 K | **366,3 K · 93,2 °C · 199,7 °F** |  ☐  | deciKelvin: el offset -273,15 |
| Intake Air Temperature | `3228` | 322,800 K | **49,7 °C · 121,4 °F** |  ☐  |  |
| Manifold Pressure | `326` | 32,600 kPa | **33 kPa · 0,33 bar · 4,7 psi** |  ☐  | kPa ABSOLUTOS, no relativos |
| Oil Pressure | `2463` | 246,300 kPa | **246 kPa · 2,46 bar · 35,7 psi** |  ☐  |  |
| Wideband O2 1 | `995` | 0,995 lambda | **0,995 λ · 14,63 AFR · 1,005 φ** |  ☐  | el tipo se llama AFR pero es lambda |
| Target Lambda | `1000` | 1,000 lambda | **1,000 λ · 14,70 AFR** |  ☐  |  |
| RPM | `961` | 961,000 rpm | **961 rpm · 16,02 Hz** |  ☐  |  |
| Vehicle Speed Drive Train Sensor | `0` | 0,000 km/h | **0,0 km/h · 0,0 mph** |  ☐  |  |
| Throttle Position | `0` | 0,000 fraccion | **0,0 %** |  ☐  |  |
| Ignition Angle | `206` | 20,600 deg | **20,6 ° · 0,360 rad** |  ☐  |  |
| Battery Voltage | `12531` | 12,531 V | **12,53 V** |  ☐  | milivoltios en origen |
| Injector 1 On Time | `1748` | 0,002 s | **1 748 µs · 1,75 ms** |  ☐  |  |
| Knock Threshold | `3400` | 34,000 dB | **34,0 dB** |  ☐  | logaritmica: sin conversion |
| Fuel - Primary Fuel Density | `7372` | 737,200 kg/m3 | **737,2 kg/m³ · 0,7372 g/cm³** |  ☐  |  |

Estequiometría leída del propio log: **14,7** (por eso λ→AFR es parametrizada).
## Cómo aprobar o rechazar

Si las 14 filas son plausibles:

```bash
python tools/estado.py aprobar F0-08 --nota "14 filas verificadas contra el log real"
```

Si alguna no lo es, dime **qué fila y qué valor esperabas**. Un solo dato basta:
con «la presión de aceite en ralentí debería ser ~1,5 bar, no 2,46» ya sé que el
factor de `Pressure` está mal y en qué sentido.

## Lo que NO tienes que revisar

- Las otras 13 dimensiones del catálogo (par, potencia, consumo, masa, caudal…):
  son conversiones de libro y hay 31 pruebas automáticas que las verifican, pero
  **ninguna aparece en tus logs de muestra**. Si mañana aparece un canal de par,
  se revisará entonces.
- Las conversiones entre unidades de la misma dimensión (bar↔psi, °C↔°F): están
  cubiertas por casos conocidos en `tests/test_units_catalogo.py`
  (0 °C = 273,15 K = 32 °F, 1 bar = 100 kPa = 14,5038 psi).
- El código. Esta puerta es sobre **números**, no sobre implementación.

## Detalle que sí merece un segundo de atención

`Manifold Pressure` en ralentí sale **0,33 bar absolutos**. Es correcto —es
vacío de admisión— pero es la cifra que un tuner espera ver como **−0,68 bar
relativos**. Esa diferencia es el modo `pressure_referencia` de `units.toml`, y
el preset «Métrico» lo trae en `auto`. La conversión de origen es la que estás
revisando aquí; el modo relativo se implementa en F1-15.
