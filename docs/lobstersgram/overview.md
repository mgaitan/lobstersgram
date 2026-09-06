# Overview

`lobstersgram` is the Telegram application in the workspace. It fetches
Lobsters links, extracts article content, publishes a Telegraph reading view,
and posts the result to a Telegram channel.

## Goals

- Keep the scheduled publishing flow simple and reliable.
- Avoid a long-running bot server.
- Reuse `markdown-this` and `md-to-telegraph` instead of duplicating article
  extraction or Telegraph conversion.

## Functionality

- Scheduled Lobsters RSS ingestion.
- Local state files for processed items and legacy subscribers.
- Telegraph page creation.
- Telegram channel posting and reaction/bookmark synchronization.
