Prepará y publicá un brief sobre política y actualidad, con prioridad clara para Argentina y, en segundo lugar, para la agenda internacional.

## 1. Determiná el modo de edición

Antes de investigar, determiná la fecha y el día de la semana actuales en la zona horaria `America/Argentina/Buenos_Aires`.

- De lunes a viernes, usá el modo **EDICIÓN DIARIA** y seleccioná entre 5 y 8 piezas. Priorizá noticias y análisis publicados hoy o desde la edición anterior.
- Los sábados y domingos, usá el modo **EDICIÓN DE FIN DE SEMANA** y seleccioná entre 8 y 14 piezas realmente valiosas. Ampliá la búsqueda a los últimos días y desarrollá una lectura de conjunto más extensa. No completes el cupo con material débil.
- Los domingos, si tenés acceso a la edición del sábado, no repitas su selección sin cambios. Priorizá novedades, piezas que hayan quedado afuera y nuevas interpretaciones. Repetí una pieza solamente si sigue siendo indispensable o tuvo novedades relevantes.

La cantidad elegida para esa ejecución será `N`. Todas las instrucciones posteriores que mencionan `N` deben respetar exactamente esa cantidad.

## 2. Investigá y seleccioná

Buscá activamente en la web y abrí cada fuente antes de seleccionarla. No atribuyas un texto a un autor, medio o fecha sin haberlo verificado en la fuente.

Revisá especialmente medios argentinos y regionales como Cenital, Revista Anfibia, Página/12, El Cohete a la Luna, Panamá Revista, Letra P y La Política Online, además de otras fuentes argentinas relevantes. Esta lista es un punto de partida, no una cuota ni un límite.

Sumá un radar prioritario de firmas: Noelia Barral Grigera, Gabriela Pepe, Diego Genoud, Leandro Renou, Alejandro Bercovich, Iván Schargrodsky, Pablo Ibáñez, Jairo Straccia, Maia Jastreblansky, Carlos Pagni, Hugo Alconada Mon, Santiago Fioritti, Jorge Liotti, Juan Elman, María O'Donnell, Nicolás Gandini, Alejandro Rebossio y Florencia Donovan.

Priorizá especialmente:

- información propia, fuentes, documentos, datos y primicias;
- columnas que permitan interpretar el poder y el clima político y económico;
- análisis con contexto, consecuencias e impacto real;
- buenas crónicas, columnas y artículos de opinión, además de noticias informativas;
- periodistas y medios sectoriales de calidad cuando el tema sea especializado

Las firmas del radar no necesitan coincidir con la sensibilidad editorial general del boletín. Una primicia o un dato relevante publicado por alguna de ellas en redes sociales debe funcionar como señal para investigar el tema en fuentes periodísticas, sectoriales, regulatorias o documentales. No incluyas una publicación aislada de redes como pieza final si no existe una fuente accesible que permita verificarla y enlazarla.

La selección general debe tener sensibilidad progresista o de centroizquierda, con atención a derechos sociales, desigualdad, trabajo, democracia, derechos humanos, ambiente y concentración de poder, pero sin hacer propaganda ni ocultar hechos incómodos para la izquierda.

Prestá particular atención al gobierno de Javier Milei y sus políticas, con una mirada crítica basada en evidencia. Distinguí siempre hechos comprobados, interpretación propia y opinión del autor. Señalá contradicciones e incertidumbres relevantes.

Evitá clickbait, polémicas vacías, repetición temática, contenido superficial y un sesgo excesivo hacia tecnología o economía. Buscá diversidad real de temas, géneros, medios y perspectivas. No selecciones dos URLs de la misma pieza ni versiones sindicadas del mismo artículo.

## 3. Escribí el boletín

Entregá un único documento Markdown, sin texto introductorio ni explicaciones fuera del documento.

- Comenzá el documento con este frontmatter exacto para que Telegraph muestre la autoría y enlace al criterio editorial usado:

```yaml
---
author: ChatGPT
url: https://github.com/mgaitan/lobstersgram/blob/master/boletin_prompt.md
notify_telegram: 390225349
---
```

- Después del frontmatter, dejá una línea en blanco y escribí el título H1 correspondiente.
- Para una edición diaria, comenzá con `# Resumen diario — [día y fecha en Argentina]`.
- Para una edición de fin de semana, comenzá con `# Edición de fin de semana — [día y fecha en Argentina]`.
- Presentá exactamente `N` piezas, ordenadas por relevancia editorial, sin numerarlas.
- Para cada pieza usá un encabezado H2 con el título, sin prefijos como `1.`, `2.` o similares.
- Debajo del título escribí una sola línea con el formato `**Autor o autora** | **Medio**`. No incluyas fecha ni género: la fecha de la edición alcanza.
- Inmediatamente después de esa línea agregá el marcador de imagen de la pieza.
- Después del marcador escribí exactamente dos párrafos: el primero debe sintetizar los hechos y el contenido de la fuente; el segundo debe aportar el análisis editorial y, cuando corresponda, integrar la opinión de la autora o el autor. No antepongas etiquetas como `Información publicada.`, `Opinión de la autora.` o `Lectura editorial.`.
- No repitas una descripción extraída de la fuente: el boletín ya resume la pieza. El enlace `Leer en Telegraph` se agregará al final de cada nota durante la publicación.

Después de la línea de autoría y medio de cada pieza agregá, en una línea independiente, exactamente este marcador con la URL canónica y completa del artículo original:

```markdown
![card](https://URL-ORIGINAL-DEL-ARTICULO)
```

Reglas obligatorias para los marcadores:

- Debe haber exactamente un marcador `![card](...)` por pieza y exactamente `N` marcadores en todo el documento.
- Cada marcador debe contener una URL original única, válida y accesible mediante HTTPS.
- No reemplaces el marcador por un enlace Markdown común ni agregues otro enlace de lectura para la misma pieza.
- No uses el marcador `![card](...)` para ninguna otra finalidad.
- No agregues manualmente un enlace `Leer en Telegraph`: el servicio lo inserta al final de la nota.
- El servicio convierte el marcador en la foto disponible de la nota, enlazada a su página de Telegraph. Si la fuente no tiene una imagen válida, no inventes una.
- Usá una barra separadora `---` únicamente entre una nota y la siguiente; no la uses antes de la primera ni después de la última.

Antes de publicar, comprobá que la cantidad de piezas coincida con el modo elegido, que haya exactamente `N` URLs únicas y que todos los marcadores respeten el formato indicado.

## 4. Publicá en Telegraph

Cuando el documento esté terminado, usá preferentemente el flujo de jobs para evitar que una edición larga dependa de una única solicitud HTTP.

### Flujo recomendado con jobs

Creá un job enviando:

```http
POST https://markdown.fastapicloud.dev/t/jobs
Content-Type: application/json
```

Enviá este cuerpo como JSON válido, serializando correctamente el documento Markdown completo:

```json
{"markdown":"DOCUMENTO MARKDOWN COMPLETO"}
```

No envíes ningún access token. Conservá sin cambios los marcadores `![card](URL original)` dentro del Markdown.

La respuesta inicial normal será HTTP 202 e incluirá al menos:

```json
{
  "id": "...",
  "status": "queued",
  "completed": 0,
  "total": 17,
  "status_url": "https://markdown.fastapicloud.dev/t/jobs/...",
  "run_url": "https://markdown.fastapicloud.dev/t/jobs/.../run"
}
```

Llamá mediante `POST` al `run_url` recibido. Cada llamada avanzará una etapa acotada y devolverá el progreso actualizado. Mientras recibas HTTP 202, seguí llamando al mismo `run_url`. No crees otro job ni vuelvas a enviar el documento completo. Podés consultar `status_url` mediante `GET` para recuperar el estado sin avanzar el trabajo.

Si recibís HTTP 409, el job ya está siendo procesado: esperá unos segundos, consultá `status_url` y continuá sólo si todavía no terminó. El mismo documento produce el mismo job durante su vigencia, por lo que reenviarlo después de un corte recupera el progreso existente en vez de duplicar la publicación.

No simules la publicación ni inventes una URL de Telegraph. El job está completo únicamente cuando una llamada devuelve HTTP 200 con `status` igual a `completed` y una URL de Telegraph:

```json
{"status":"completed","url":"https://telegra.ph/..."}
```

Como el frontmatter incluye `notify_telegram: 390225349`, al completar la
publicación el servicio enviará automáticamente esa URL a Telegram. Para que
llegue el aviso, el usuario debe iniciar antes una conversación privada con
[@MarkdownTelegraphBot](https://t.me/MarkdownTelegraphBot) —por ejemplo, con
`/start`—. Para un grupo, agregá el bot; para un canal, agregalo como
administrador con permiso para publicar mensajes.

Si el job devuelve HTTP 422 con `status` igual a `failed`, usá `source_url` y `error` para identificar la pieza problemática. Si el error parece transitorio, volvé a llamar una vez al mismo `run_url`: un job fallido puede reintentar la etapa pendiente sin perder su progreso. Si la fuente no puede extraerse o su URL no es válida, reemplazala por una fuente accesible de calidad editorial equivalente, volvé a validar el documento completo y creá un job para el documento corregido.

### Alternativa síncrona

Los jobs son opcionales. Solamente si `POST /t/jobs` no está disponible y responde HTTP 404 o HTTP 503, publicá el mismo cuerpo mediante:

```http
POST https://markdown.fastapicloud.dev/t
Content-Type: application/json
```

En este modo, esperá una respuesta HTTP 200 con `{"url":"https://telegra.ph/..."}`. No uses el endpoint síncrono como segundo intento si el job ya comenzó a publicar.

## 5. Respondé

Como respuesta final de la tarea, informá solamente:

- el título del boletín;
- el modo elegido y la cantidad de piezas;
- el enlace de Telegraph recibido.

No pegues nuevamente el boletín completo en el chat.
