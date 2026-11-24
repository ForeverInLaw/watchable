# Personal Apple Watch Companion

Личное приложение: Android-компаньон и watchOS-приложение для Apple Watch.

## Статус

- Спецификация: v0.1 (`docs/TZ.md`).
- Код: ещё не начат; первый этап — спайк доставки APNs на часы.
- Это **clean-room** проект: код, ассеты и секреты третьих лиц не используются.

## Структура

```
android/     Android-приложение (Kotlin, Compose)
watch/       watchOS-приложение (SwiftUI, watchOS 10)
relay/       self-hosted relay (Python, FastAPI, SQLite)
protocol/    JSON-схемы и примеры
docs/        ТЗ, ADR, runbooks
```

## С чего начать

1. Прочитать `docs/TZ.md`.
2. Прочитать `GLOSSARY.md`.
3. Посмотреть `protocol/`.

## Правила

- Не использовать код и ассеты сторонних приложений.
- Не копировать код, строки, иконки, ресурсы и ключи третьих лиц.
- Не коммитить секреты: `.env`, `.p8`, service account JSON, keystore.
- Один пользователь, один телефон, одни часы.
