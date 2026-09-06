# markdown-this Extractor Roadmap

This work covers issues #83, #88, #91, #92, #93, #97 and related issues
#84, #89, #90, #94 and #95.

## Extraction Contract

URL downloads, local files and browser-supplied HTML must share content
extraction and Markdown normalization. A website using a supported format
should work without adding a new Python function for that website.

1. Fetch HTML, or accept supplied HTML with its source URL.
2. Read document metadata and embedded structured content.
3. Select content using a supported format (such as Arc Fusion or schema.org)
   or a small declarative CSS rule backed by a failing fixture.
4. Use Readability when no more reliable content is available.
5. Normalize images, links, figures and structural chrome in one HTML path.
6. Convert to Markdown and derive front matter and preview text.

External APIs belong at the acquisition boundary. Reuse protocols such as
oEmbed across providers; keep API-specific operations such as transcripts
isolated. Do not grow the pipeline with domain conditionals or hide the same
conditionals inside a registry of per-site functions.

## Work Order

1. **Offline benchmark (#91):** assert required and forbidden phrases in the
   publishable Markdown body, measure body length without front matter, and
   check metadata separately. Include ordinary articles, embedded data,
   media, social pages and noisy layouts.
2. **Shared pipeline (#93):** keep acquisition separate from parsing. Use
   plain functions and data tables where they suffice. Supplied HTML must
   exercise the same parsers as downloaded HTML.
3. **Embedded article formats (#88, #97, #94):** parse Fusion JSON and
   schema.org using the standard JSON decoder. Test both source paths and
   more than one hostname to prove format-based extraction.
4. **Media protocols (#92):** share oEmbed requests and rendering across
   Vimeo, Dailymotion and YouTube while retaining transcripts.
5. **Declarative rules (#90, #89):** add selectors only when a fixture shows
   generic extraction losing content. Readeck/FiveFilters are references,
   not rule sets to vendor wholesale.
6. **HTML normalization (#95):** preserve code, tables, footnotes and
   content-bearing callouts; remove known chrome conservatively.
7. **Social content (#83, #93):** use available structured data and shared
   protocols first. Add API-specific logic only for demonstrated gaps.

## Ponytail Criteria For Every PR

- Prefer the standard library and already-installed parsers.
- Keep domain differences in data when they are selectors or endpoints.
- Share normalization across every extraction path.
- Keep readable code and meaningful offline checks in the introducing PR.
- Avoid plugin frameworks, speculative configuration and custom async code.
- Compare alternatives on the same corpus before adding another extractor
  dependency. Browser rendering stays outside this synchronous package.

Reusable extraction stays in `markdown-this`; web and Telegram orchestration
stay in their application packages.
