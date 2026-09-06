# Lobstersgram Technical Reference

## Main Modules

- `lobstersgram.main`: command-line flow and scheduled orchestration.
- `lobstersgram.content`: content extraction and Telegraph publishing glue.
- `lobstersgram.telegram`: Telegram API calls.
- `lobstersgram.state`: local state files.
- `lobstersgram.config`: environment configuration.

## Runtime State

Do not overwrite `state.json`, `subscribers.json`, `message_map.json`, or
bookmark state unless a task explicitly requires it.
