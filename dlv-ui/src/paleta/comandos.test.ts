/**
 * Pruebas de `RegistroComandos` y `filtrarComandos` (F5-09).
 *
 * Lo que protegen: que el registro crezca por grupos sin que uno pise a otro,
 * y que el orden de resultados sea el de relevancia difusa (reutilizando
 * `coincidenciaDifusa`, F1-33) y no el de inserción. Igual que
 * `canales/filtro.test.ts`, no se fija un número de puntuación concreto —eso
 * rompería con cualquier ajuste fino de `difuso.ts`— sino el ORDEN.
 */

import { describe, expect, it } from "vitest";

import { RegistroComandos, filtrarComandos, type Comando } from "./comandos.ts";

function comando(id: string, etiqueta: string): Comando {
  return { id, etiqueta, ejecutar: () => {} };
}

describe("RegistroComandos", () => {
  it("todos() está vacío antes de registrar nada", () => {
    expect(new RegistroComandos().todos()).toEqual([]);
  });

  it("un grupo aporta sus comandos a todos()", () => {
    const registro = new RegistroComandos();
    registro.registrarGrupo("estaticos", [comando("a", "Abrir log sintético")]);
    expect(registro.todos().map((c) => c.id)).toEqual(["a"]);
  });

  it("dos grupos distintos se acumulan", () => {
    const registro = new RegistroComandos();
    registro.registrarGrupo("estaticos", [comando("a", "Abrir log sintético")]);
    registro.registrarGrupo("canales", [comando("c1", "Añadir canal: RPM")]);
    expect(registro.todos().map((c) => c.id).sort()).toEqual(["a", "c1"]);
  });

  it("volver a registrar el MISMO grupo sustituye entero lo anterior, sin tocar otros grupos", () => {
    const registro = new RegistroComandos();
    registro.registrarGrupo("estaticos", [comando("a", "Abrir log sintético")]);
    registro.registrarGrupo("canales", [comando("c1", "Añadir canal: RPM")]);
    // Se abre un log nuevo: los comandos de canal cambian por completo.
    registro.registrarGrupo("canales", [comando("c2", "Añadir canal: Coolant Temperature")]);
    const ids = registro.todos().map((c) => c.id).sort();
    expect(ids).toEqual(["a", "c2"]);
    expect(ids).not.toContain("c1");
  });

  it("quitarGrupo() retira solo ese grupo y no falla si no existía", () => {
    const registro = new RegistroComandos();
    registro.registrarGrupo("estaticos", [comando("a", "Abrir log sintético")]);
    registro.quitarGrupo("canales"); // nunca existió
    expect(registro.todos().map((c) => c.id)).toEqual(["a"]);
    registro.quitarGrupo("estaticos");
    expect(registro.todos()).toEqual([]);
  });
});

describe("filtrarComandos", () => {
  const comandos: Comando[] = [
    comando("log", "Abrir log sintético"),
    comando("tema-oscuro", "Cambiar tema: Oscuro"),
    comando("tema-claro", "Cambiar tema: Claro"),
    comando("tema-alto", "Cambiar tema: Alto contraste"),
    comando("canal-rpm", "Añadir canal: RPM"),
    comando("canal-cool", "Añadir canal: Coolant Temperature"),
    comando("canal-map", "Añadir canal: Manifold Pressure"),
  ];

  function ordenar(consulta: string): string[] {
    return filtrarComandos(comandos, consulta).map((cf) => cf.comando.id);
  }

  it("consulta vacía devuelve TODOS los comandos, con puntuación null", () => {
    const resultado = filtrarComandos(comandos, "");
    expect(resultado).toHaveLength(comandos.length);
    expect(resultado.every((cf) => cf.puntuacion === null)).toBe(true);
  });

  it("una consulta que no coincide con nada deja la lista vacía", () => {
    expect(ordenar("zzzzzz")).toEqual([]);
  });

  it("`tema` encuentra los tres comandos de tema (aunque \"tema\" también sea subsecuencia de \"Coolant Temperature\")", () => {
    // t-e-m-a aparece en ese orden dentro de "TEMperAture", así que la lista de
    // "tema" no es solo los tres de categoría Tema -- se comprueba que estén
    // los tres, no que sean los únicos.
    const encontrados = ordenar("tema").filter((id) => id.startsWith("tema-")).sort();
    expect(encontrados).toEqual(["tema-alto", "tema-claro", "tema-oscuro"]);
  });

  it("`cltmp` (el mismo ejemplo de F1-33) pone Coolant Temperature primero entre los canales", () => {
    const orden = ordenar("cltmp");
    expect(orden[0]).toBe("canal-cool");
  });

  it("`rpm` exacto ordena RPM antes que cualquier otra coincidencia parcial", () => {
    expect(ordenar("rpm")[0]).toBe("canal-rpm");
  });

  it("a igualdad de puntuación, el desempate es alfabético por etiqueta", () => {
    // Dos rótulos de la MISMA longitud que solo difieren en la última letra:
    // "z" empareja en la misma posición (la primera) en los dos, así que la
    // puntuación de `coincidenciaDifusa` es idéntica y lo único que puede
    // decidir el orden es el desempate alfabético, no la relevancia.
    const empatados: Comando[] = [comando("zebro", "Zebro"), comando("zebra", "Zebra")];
    const orden = filtrarComandos(empatados, "z").map((cf) => cf.comando.id);
    expect(orden).toEqual(["zebra", "zebro"]);
  });
});
