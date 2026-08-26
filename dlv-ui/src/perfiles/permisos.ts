/**
 * Qué se puede hacer con un perfil según su origen (F3-05, decisión 3 del
 * informe de la tarea: "¿editar un perfil de fábrica se permite, se bloquea o
 * se avisa?").
 *
 * DECISIÓN: SE BLOQUEA LA EDICIÓN DIRECTA, SE OFRECE DUPLICAR
 * ================================================================
 * `perfil.py` no tiene ningún campo "es de fábrica" — es deliberado (ver su
 * cabecera, decisión 4): el esquema no lleva metadatos de procedencia porque
 * la procedencia no es del PERFIL, es de dónde vive el fichero. `OrigenPerfil`
 * es justo eso, y lo declara quien monta el editor (la ruta de la que vino:
 * el directorio de perfiles integrados frente al directorio de perfiles del
 * usuario), no `perfil.py` ni este módulo.
 *
 * Con esa procedencia, las tres opciones que planteaba la tarea:
 *
 * 1. Permitir editar en el sitio. Descartada: los 10 perfiles de fábrica
 *    (E4.2/F3-03) los reinstala o actualiza cada versión de la aplicación —
 *    son parte de los datos que se despliegan con ella, no algo que el
 *    usuario "posee". Una edición en el sitio desaparecería sin aviso en la
 *    próxima actualización, que es el peor tipo de pérdida de datos: la que
 *    ocurre en silencio y mucho después de que el usuario la olvidó.
 * 2. Bloquear sin más. Descartada sola: bloquear y no ofrecer nada más deja
 *    al usuario sin saber cómo conseguir lo que quería (ajustar el umbral de
 *    aviso de knock a SU motor, por ejemplo), que es precisamente el caso de
 *    uso que E4.4 nombra en primer lugar.
 * 3. **Bloquear los campos y ofrecer "Duplicar para editar" en el mismo
 *    sitio donde se intentó editar.** Es la combinación de las dos anteriores
 *    sin el defecto de ninguna: nada de fábrica se pierde en una actualización
 *    porque nunca se tocó, y el usuario tiene un camino de un clic hacia lo
 *    que quería, que es exactamente `duplicado.ts#duplicarPerfil`.
 *
 * Es el mismo patrón que cualquier "plantilla del sistema, solo lectura +
 * duplicar para personalizar" — no una invención de este módulo, sino la
 * respuesta estándar al mismo problema (una plantilla compartida que una
 * actualización puede volver a escribir).
 */

/**
 * De dónde vino este perfil en memoria. Lo decide quien lo cargó (el
 * directorio del que lo leyó), no el contenido del `.dlvprofile`: el esquema
 * de `perfil.py` no lleva esta información porque no es un dato DEL perfil.
 */
export type OrigenPerfil = "fabrica" | "usuario";

/** Un perfil con la procedencia que decide qué se puede hacer con él aquí. */
export interface PerfilConOrigen<TPerfil> {
  readonly perfil: TPerfil;
  readonly origen: OrigenPerfil;
}

/**
 * `true` si los campos del perfil (nombre, descripción, paneles, límites...)
 * se pueden editar EN EL SITIO. Un perfil de fábrica nunca: la única vía de
 * cambio para uno de fábrica es duplicarlo primero (ver cabecera).
 */
export function puedeEditarDirectamente(origen: OrigenPerfil): boolean {
  return origen === "usuario";
}

/**
 * `true` si este perfil se puede sobrescribir en su propio sitio al guardar
 * (frente a "guardar como" un fichero nuevo). Mismo criterio que
 * `puedeEditarDirectamente`: si no se puede editar en el sitio, tampoco se
 * puede guardar en el sitio — son la misma protección vista desde el editor
 * y desde el guardado.
 */
export function puedeSobrescribir(origen: OrigenPerfil): boolean {
  return origen === "usuario";
}
