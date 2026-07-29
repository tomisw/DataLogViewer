# 06 — Sistema de unidades intercambiables

## 6.1 Requisito

Cada tipo de campo debe poder mostrarse en **unidades alternativas** elegidas por
el usuario: Kelvin / Celsius / Fahrenheit, kPa / bar / psi, λ / AFR, km/h / mph,
etc. La elección debe ser posible a tres niveles (global, por dimensión, por
canal) y no debe alterar los datos almacenados.

## 6.2 El error que hay que evitar

Un sistema de unidades ingenuo guarda un `factor` por canal y multiplica. Eso
**no puede representar la temperatura**: K → °C es una resta, no un producto.
Tampoco puede representar λ → φ ni L/100 km → mpg, que son recíprocos.

Y hay un fallo peor, silencioso: si la conversión se aplica con el desplazamiento
también a las **diferencias**, un Δ de temperatura de 10 K se muestra como
−263,15 °C. Eso rompe el doble cursor, las derivadas, las desviaciones típicas y
cualquier estadística de dispersión — todo lo que el producto usa para detectar
problemas.

El diseño de este capítulo existe para que esos dos fallos sean imposibles por
construcción.

## 6.3 Modelo de tres capas

```
   entero crudo del fichero
        │  escala de origen (declarada por el formato o el importador)
        ▼
   valor CANÓNICO  (f64, unidad base fija por dimensión)   ← lo que se almacena
        │  conversión de presentación (elegida por el usuario)
        ▼
   valor MOSTRADO  (+ formato numérico y locale)
```

Reglas duras:

1. **La unidad canónica es fija por dimensión** y no configurable. Es el único
   idioma común entre logs de fabricantes distintos.
2. **Todo lo persistido está en canónica**: caché, umbrales de alerta, límites de
   perfil, definiciones de canales matemáticos, mallas RPM×MAP, anotaciones.
3. **La conversión de presentación no toca nada persistido.** Cambiar de °C a °F
   es un repintado, no una recarga: coste O(píxeles visibles), no O(muestras).
4. Cambiar de unidad **nunca** invalida la caché ni reescribe un umbral.

Sin la regla 2, cambiar la unidad global rompería todos los límites de todos los
perfiles del usuario. Es el motivo por el que los umbrales no se guardan «en psi».

## 6.4 Tipos de conversión soportados

| Tipo | Forma | Casos |
|---|---|---|
| **Afín** | `y = a·x + b` | la mayoría; temperatura es el caso con `b ≠ 0` |
| **Recíproca** | `y = a / x` | λ ↔ φ (relación de equivalencia), periodo ↔ frecuencia, L/100 km ↔ mpg |
| **Parametrizada** | `y = a(p)·x` con `p` de un canal del log | λ → AFR, donde `a` es la estequiometría del combustible |
| **Ninguna** | — | enums, máscaras de bits, contadores, y **decibelios** (escala logarítmica: no admite cambio de unidad, solo de referencia) |

Que las conversiones parametrizadas existan en el modelo es lo que permite que
λ → AFR sea correcto con E85 o metanol: el factor sale del canal
`Fuel Tuning Current Stoichiometry` del propio log (14,7 en las muestras de
gasolina), no de una constante cableada. Si el log no trae ese canal, se usa el
valor del perfil del vehículo y se marca como asumido.

## 6.5 Semántica de valor absoluto frente a diferencia

Cada magnitud que el sistema calcula declara si es un **punto** o un **intervalo**:

| Clase | Conversión aplicada | Ejemplos |
|---|---|---|
| **Punto** | afín completa `a·x + b` | valor bajo el cursor, media, mínimo, máximo, percentiles, umbrales |
| **Intervalo** | solo parte lineal `a·x` | Δ del doble cursor, rango, desviación típica, RMS, amplitud de pico a pico |
| **Tasa** | parte lineal del numerador ÷ unidad del denominador | derivadas (°C/s, psi/s), pendientes |
| **Varianza** | `a²·x` | varianza |

Así, un Δ de 10 K se muestra como 10 °C o 18 °F, que es lo correcto. Y una
desviación típica de 2 K nunca se convierte en −271 °C.

Esta clasificación es un campo obligatorio en la definición de cada métrica y
cada canal matemático. Una métrica nueva sin clase declarada **no compila**: es
más barato que una puerta de revisión.

## 6.6 Presión absoluta y relativa

En los logs analizados todas las presiones son **absolutas** y no hay canal
barométrico (`01-formato-log.md` §1.9). Un tuner, en cambio, piensa en bar o psi
**relativos** (de boost).

Absoluto vs relativo **no es un cambio de unidad, es un cambio de origen**, y se
modela aparte para que se pueda combinar con cualquier unidad de presión:

```
referencia = ninguna | constante(kPa) | canal(id) | auto
```

`auto` toma la mediana de la presión de colector con el motor parado al inicio
del log. La UI etiqueta el resultado sin ambigüedad —`bar (rel)`, `psi (abs)`—
porque «2 bar» sin más es la fuente de error más común al comparar logs de dos
herramientas distintas.

Al pasar a relativo, la conversión de un **punto** resta la referencia; la de un
**intervalo** no. La clasificación de §6.5 vuelve a ser la que lo resuelve.

## 6.7 Catálogo de dimensiones y unidades

Unidad canónica en **negrita**. Las conversiones se declaran en `units.toml`, no
en código.

| Dimensión | Canónica | Unidades alternativas |
|---|---|---|
| Temperatura | **K** | °C (`x−273,15`), °F (`1,8x−459,67`), °R (`1,8x`) |
| Presión | **kPa** | hPa/mbar, bar, psi, atm, inHg, mmHg — × modo abs/rel |
| Relación de mezcla | **λ** | AFR (`λ·stq`, parametrizada), φ/EQR (`1/λ`, recíproca), AFR-gasolina (`λ·14,7`) |
| Régimen | **rpm** | rad/s, Hz |
| Velocidad | **km/h** | mph, m/s, kn |
| Ángulo | **°** | rad, ° de árbol de levas (`x/2`), % de recorrido |
| Adimensional / relación | **fracción** | %, ‰, ppm |
| Tensión | **V** | mV |
| Tiempo | **s** | ms, µs, min; ↔ frecuencia por recíproca |
| Frecuencia | **Hz** | kHz, rpm, ↔ periodo |
| Resistencia | **Ω** | kΩ, mΩ |
| Nivel de sonido | **dB** | sin conversión (logarítmica) |
| Caudal másico | **kg/h** | g/s, lb/h, lb/min |
| Caudal volumétrico | **L/h** | cc/min, gal/h |
| Volumen | **L** | cc, mL, in³, gal |
| Masa | **kg** | g, mg, lb, oz |
| Masa por cilindro | **mg** | g, grano |
| Densidad | **kg/m³** | g/cm³, lb/ft³ |
| Distancia | **m** | km, mi, ft, in |
| Consumo | **L/100 km** | km/L (`100/x`), mpg-US (`235,215/x`), mpg-UK |
| Par | **N·m** | lb·ft, kgf·m |
| Potencia | **kW** | hp, PS/CV |
| Aceleración | **m/s²** | g |
| Contador / enum / máscara | **—** | sin conversión |

### Dimensiones compuestas

Los tipos `PercentPerRpm`, `PercentPerKPa` y `PercentPerLambda` del formato
Haltech son **cocientes de dimensiones**. Su unidad mostrada se **deriva** de las
unidades activas de numerador y denominador: si el usuario pone la presión en
psi, `%/kPa` pasa a mostrarse como `%/psi` con el factor recalculado. Fijar estas
unidades a mano produciría incoherencias dentro del mismo panel.

## 6.8 Mapeo del formato de origen a la dimensión

El registro de unidades deja de ser «tipo → factor» y pasa a ser
«tipo de origen → dimensión + escala a canónica»:

```toml
[source.haltech_nsp.types.Temperature]
dimension  = "temperature"
to_canonical = { a = 0.1, b = 0.0 }   # deciKelvin → K
confidence = "confirmed"
evidence   = "coolant 3663 -> 366,3 K = 93,2 C con motor caliente"

[source.haltech_nsp.types.AFR]
dimension  = "mixture_ratio"
to_canonical = { a = 0.001, b = 0.0 } # el tipo se llama AFR pero es lambda
confidence = "confirmed"

[source.haltech_nsp.types.MassOverTime]
dimension  = "mass_flow"
to_canonical = { a = 1.0, b = 0.0 }
confidence = "unknown"                # se muestra en crudo y marcado
```

El campo `confidence` sigue gobernando el riesgo R1: con `unknown`, la app
**muestra el valor crudo con una marca visual y desactiva el selector de unidad
para ese canal**. No hay unidad inventada, y por tanto no hay decisión de tuning
tomada sobre un número falso.

## 6.9 Selección de unidades: precedencia

De mayor a menor prioridad:

1. **Anulación por canal** — «este canal en psi aunque el resto esté en bar».
2. **Dimensión en el perfil activo** — el perfil «Boost» puede fijar psi.
3. **Preset global del usuario**.
4. **Unidad canónica** como último recurso.

La regla 1 es necesaria en la práctica: en el mismo panel se quiere presión de
aceite en bar y presión de boost en psi.

### Presets

| Preset | Temp. | Presión | Velocidad | Mezcla | Volumen |
|---|---|---|---|---|---|
| SI puro | K | kPa abs | m/s | λ | L |
| **Métrico (por defecto)** | °C | bar rel | km/h | λ | L |
| Imperial | °F | psi rel | mph | AFR | gal |
| Motorsport EU | °C | bar rel | km/h | λ | L |
| Motorsport US | °F | psi rel | mph | AFR | gal |

Un preset es un fichero de datos y el usuario puede crear el suyo. Cubrir el
caso «tuner estadounidense que quiere psi, °F y AFR de un clic» con un preset, en
lugar de con 20 selectores, es la diferencia entre una función usada y una
función ignorada.

## 6.10 Formato numérico y locale

Cada unidad declara sus **decimales significativos**, porque mostrar `λ 0,995`
con un decimal (`1,0`) destruye la información:

| Unidad | Dec. | | Unidad | Dec. |
|---|---|---|---|---|
| λ | 3 | | psi | 1 |
| AFR | 2 | | bar | 2 |
| °C / K / °F | 1 | | kPa | 0 |
| % | 1 | | rpm | 0 |
| V | 2 | | ° | 1 |
| ms | 2 | | µs | 0 |

Separador decimal y agrupación de miles siguen el locale de la app (coma decimal
en español). Esto se comparte con el importador genérico, que debe **leer** CSV
con coma decimal (`07-formatos-y-csv-generico.md` §7.3).

## 6.11 Consecuencias en el resto del producto

| Área | Consecuencia |
|---|---|
| **Ejes y rejilla** | los «números redondos» de los ticks se calculan **en la unidad mostrada**. Convertir ticks canónicos da 7,25 psi en lugar de 7 psi |
| **Umbrales y alertas** | se guardan en canónica y se editan en la unidad activa; el campo de entrada muestra la unidad junto al valor |
| **Multi-log** | dos logs con el mismo rol y unidades de origen distintas se comparan sin fricción: ambos están en canónica |
| **Canales matemáticos** | las expresiones operan **siempre en canónica**, así que una fórmula es válida sea cual sea la unidad mostrada. Las constantes de la expresión llevan unidad explícita |
| **Exportación** | CSV/Parquet declaran la unidad de cada columna en la cabecera; se puede exportar en canónica o en la unidad mostrada, y la elección se registra en el fichero |
| **Informes** | el informe HTML fija las unidades usadas en su encabezado, para que sea interpretable meses después |
| **Tablas de corrección** | son porcentajes adimensionales: inmunes al cambio de unidad. Sus **ejes** (rpm, kPa) sí se muestran en la unidad activa |
| **Rendimiento** | la conversión se aplica a los cubos visibles, unos miles de valores por panel y fotograma, no a las 73 M muestras |

## 6.12 Pruebas que este subsistema exige

- Ida y vuelta canónica → mostrada → canónica con error < 1 ULP para todas las
  unidades del catálogo.
- **Prueba de la trampa del delta**: Δ de 10 K debe dar 10 °C y 18 °F. Es la
  prueba que impide la regresión más probable de todo el subsistema.
- Casos conocidos: 0 °C = 273,15 K = 32 °F; 1 bar = 100 kPa = 14,5038 psi;
  λ 1,0 = AFR 14,7 con estequiometría de gasolina; λ 0,850 = φ 1,176.
- Cambio de preset con 8 logs abiertos: ni recarga ni invalidación de caché, y
  los umbrales del perfil siguen disparando en los mismos instantes.
- Canal con `confidence = unknown`: el selector de unidad está desactivado y el
  valor se muestra en crudo.
