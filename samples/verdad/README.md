# Log de verdad de referencia (F0-07)

`verdad.csv` es un log Haltech legítimo con eventos inyectados en instantes
conocidos. `verdad.json` dice qué debe detectar cada detector de
`docs/04-perfiles-motorsport.md` §4.3 **y qué no debe detectar**.

Sin este fichero no se puede afirmar que los detectores funcionan. La tarea
F3-09 lo consume para validarlos, en formato nativo y en CSV genérico.

## Por qué la mitad son casos negativos

Un detector que dispara siempre tiene cero falsos negativos y es inútil. Lo
que hace que un usuario confíe en el panel de incidencias es que no le avise
en falso: una alerta falsa repetida le enseña a ignorar las alertas. Por eso
cada positivo lleva su casi-positivo, situado justo al otro lado del umbral.

## Deben disparar (15)

| Detector | t (s) | Severidad | Descripción |
|---|---|---|---|
| D1 | 21.50–21.55 | critica | Evento de knock: incremento del contador |
| D3 | 21.50–25.10 | media | Retardo por knock activo: corrección de encendido negativa |
| D2 | 22.00–22.60 | media | Knock sostenido 600 ms por encima del umbral |
| D1 | 23.00–23.05 | critica | Evento de knock: incremento del contador |
| D1 | 24.50–24.55 | critica | Evento de knock: incremento del contador |
| D10 | 25.00–25.60 | critica | Presión de aceite bajo la curva mínima a alto régimen |
| D4 | 32.00–34.00 | critica | Mezcla pobre en carga: lambda 4,1 % sobre objetivo con TPS 100 % |
| D8 | 43.00–45.00 | alta | Duty de inyección al 88 % |
| D8 | 45.00–46.00 | critica | Duty de inyección al 96 % |
| D9 | 48.50–52.00 | alta | Sobretemperatura de refrigerante 107,5 °C durante 3,5 s |
| D11 | 52.50–54.50 | media | Tensión de batería 11,2 V con el motor en marcha |
| D12 | 55.50–56.00 | critica | Bit de error de trigger activo |
| D13 | 56.00–57.00 | alta | Protección de motor en nivel 2 |
| D14 | 56.00–57.00 | media | Corte activo al 25 % durante la protección |
| D18 | 58.00–58.40 | informativa | Hueco de muestreo de 400 ms |

## NO deben disparar (5)

| Detector | t (s) | Por qué no |
|---|---|---|
| D10 | 4.00–6.00 | el caso que un umbral plano marcaría en falso |
| D2 | 10.00–10.05 | 50 ms < 100 ms de permanencia mínima (docs/04 §4.3) |
| D9 | 12.00–12.80 | Pico de 106,5 °C durante 0,8 s: por debajo de la permanencia de 3 s |
| D4 | 39.00–41.00 | y además con TPS 0: la condición de carga tampoco se cumple |
| D8 | 46.50–47.50 | Duty al 83 %: por debajo del umbral del 85 % |

## Tramos del escenario

| t (s) | Tramo |
|---|---|
| 0–8 | ralentí caliente |
| 8–14 | tirada a plena carga limpia |
| 18–26 | tirada con tres eventos de knock |
| 30–38 | tirada con excursión de mezcla pobre |
| 42–48 | duty de inyección alto |
| 48–52 | sobretemperatura de refrigerante |
| 52–55 | baja tensión de batería |
| 55–58 | error de trigger y protección de motor |
| 58 | hueco de muestreo de 400 ms |
