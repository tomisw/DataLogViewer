import { describe, expect, it } from "vitest";

import { resolverUrlBaseApi } from "./resolver-api.ts";

describe("resolverUrlBaseApi", () => {
  it("usa 127.0.0.1 sin cambios (dlv-app, ADR-002)", () => {
    expect(resolverUrlBaseApi("127.0.0.1", "51234", null)).toBe("http://127.0.0.1:51234");
  });

  it("usa localhost sin cambios (npm run dev)", () => {
    expect(resolverUrlBaseApi("localhost", "5173", null)).toBe("http://localhost:5173");
  });

  it("F5-06: usa el host de la página cuando se sirve para la red", () => {
    // Es exactamente el caso que el cableado anterior rompía: la página se
    // cargó desde la IP del equipo servidor, y la API vive en ESE equipo, no
    // en el loopback de quien mira el navegador.
    expect(resolverUrlBaseApi("192.168.1.50", "8001", null)).toBe("http://192.168.1.50:8001");
  });

  it("`api_host` explícito gana al host de la página", () => {
    expect(resolverUrlBaseApi("192.168.1.50", "8001", "dlv-api.taller.local")).toBe(
      "http://dlv-api.taller.local:8001",
    );
  });

  it("`api_host` vacío se trata como ausente", () => {
    expect(resolverUrlBaseApi("192.168.1.50", "8001", "")).toBe("http://192.168.1.50:8001");
  });

  it("IPv6 se envuelve en corchetes: `::1` daría una URL que no resuelve", () => {
    expect(resolverUrlBaseApi("::1", "8000", null)).toBe("http://[::1]:8000");
    expect(resolverUrlBaseApi("fe80::1ff:fe23:4567:890a", "8000", null)).toBe(
      "http://[fe80::1ff:fe23:4567:890a]:8000",
    );
  });

  it("un `api_host` que ya trae corchetes no se anida", () => {
    expect(resolverUrlBaseApi("192.168.1.50", "8000", "[::1]")).toBe("http://[::1]:8000");
  });

  it("host de página vacío cae a 127.0.0.1, no a una URL rota", () => {
    expect(resolverUrlBaseApi("", "8001", null)).toBe("http://127.0.0.1:8001");
  });
});
