# Техническое задание: личный Apple Watch ↔ Android companion

> **Статус:** v0.2, принят для M0 (спайк APNs). Архитектура: public-API companion. Если допущения ниже неверны — меняем соответствующие разделы, а не весь документ.
>
> **Допущения:**
> - Основной путь — **B: public-API companion**. Full clone (эмуляция системного сопряжения) — параллельный исследовательский трек R1 (ADR 0005).
> - Локального Mac нет: watch app собирается и подписывается на macOS-раннере GitHub Actions (ADR 0004).
> - Есть iPhone (XS или новее, iOS 17+), Android-телефон (12+), платный Apple Developer Program.
> - A2093 спарен с iPhone для установки watchOS-приложения; Android-телефон используется как основной.
> - MVP: уведомления с ответами, здоровье/сон, музыка. Будильники и Find Watch — v1.1.
> - Relay: self-hosted VPS + APNs; команды на Android — через FCM HTTP v1.
> - Распространение: только TestFlight, без App Store.
> - Репозиторий открытый (open source); секреты и локальные инструкции агента в него не попадают.
> - Clean-room: код, строки, ресурсы и ключи третьих лиц не используются.
> - Один пользователь, один Android-телефон, одни часы, один Apple ID.

---

## 1. Цель и границы

### 1.1 Цель

Сделать личное приложение, которое закрывает повседневные повседневные функции:

- показывает уведомления Android на Apple Watch;
- позволяет отвечать на поддерживаемые уведомления с часов;
- синхронизирует здоровье и сон;
- управляет музыкой на Android с часов;
- в v1.1 — будильники и Find Watch.

Приложение не использует сторонние серверы, подписки и код третьих лиц. Оно не пытается полностью заменить системное сопряжение Apple Watch с iPhone.

### 1.2 В scope

- Android-приложение (Kotlin, Jetpack Compose).
- watchOS-приложение (SwiftUI, watchOS 10.0+).
- Self-hosted relay (Python/FastAPI, SQLite, APNs, FCM).
- Протокол обмена и JSON-схемы.
- BLE-канал для близких действий — v1.1, не в MVP.
- Документация, тесты, Docker-развёртывание.

### 1.3 Вне scope

- Системные звонки, SMS/iMessage, CallKit-интеграция.
- Автоматическое подключение часов к Wi-Fi.
- Critical Alerts и приоритетные уведомления.
- App Store, публикация, ревью.
- Мультипользовательский режим, аккаунты, подписки.
- Android Wear / Wear OS, iPad, macOS.
- Копирование кода, ресурсов, строк, иконок, логотипов или ключей третьих лиц.

### 1.4 Критерии успеха

- Уведомление из WhatsApp/Telegram/Signal/SMS появляется на часах менее чем за 3 секунды при онлайн-телефоне и часах в Wi-Fi.
- Ответ с часов доходит до исходного приложения менее чем за 5 секунд, если приложение поддерживает `RemoteInput`.
- Данные здоровья появляются на Android не позже чем через 15 минут; тренировка — не позже чем через 1 минуту после завершения.
- Команда музыки выполняется менее чем за 2 секунды.
- Приложение переживает 24 часа без падений и не теряет события при перезапуске relay.
- В репозитории нет секретов, ключей и литерального кода третьих лиц.

---

## 2. Целевые устройства и ограничения

### 2.1 Apple Watch

- Модель: **A2093** — Series 5, 44 мм, GPS.
- ОС: **watchOS 10.x** (максимальная для Series 5).
- Связь: Wi-Fi **802.11b/g/n, 2.4 ГГц**, Bluetooth 5.0.
- LTE: **нет**.
- Экран: 368×448.
- Динамик и микрофон: есть.
- ECG: есть.
- Для установки watchOS-приложения нужен спаренный iPhone.

### 2.2 iPhone

- Модель: iPhone XS или новее.
- ОС: iOS 17+ (для watchOS 10).
- Роль: только provisioning, установка watchOS-приложения, обновления.
- В повседневной работе iPhone не обязателен рядом, но часы остаются к нему привязаны.

### 2.3 Android

- ОС: Android 12+ (API 31), targetSdk 35.
- Google Play services: обязательны для FCM.
- Доступ к уведомлениям: обязателен.
- Bluetooth: BLE 5.0.
- Батарея: нужен foreground service и исключение из оптимизации.

### 2.4 Relay

- Linux VPS: 1 vCPU, 1 ГБ RAM, 10 ГБ SSD.
- Docker + Docker Compose.
- Публичный HTTPS-домен.
- Исходящий HTTPS/HTTP2 к APNs и FCM.
- Резервные копии SQLite.

### 2.5 Ограничения платформ

| Ограничение | Следствие |
|---|---|
| Apple Watch не спаривается с Android | Нужен iPhone для установки watch app; full clone — только через исследование протокола (R1) |
| A2093 без LTE | Вне известного Wi-Fi/iPhone push не дойдёт; вне дома часы подключаются к точке доступа Android (2.4 ГГц) |
| Apple Watch не использует интернет Android по Bluetooth: часы видят Android в списке Bluetooth, но не подключаются, и Bluetooth-модем не помогает | Интернет с телефона — только через Wi-Fi-точку доступа |
| Пока часы считают iPhone подключённым, они ходят в сеть через него, даже если у iPhone нет интернета (авиарежим) | iPhone рядом без интернета блокирует доставку; держать его выключенным или с интернетом |
| Обычное приложение на Android 8+ не может включить точку доступа с интернетом | Точка доступа включена постоянно или включается автоматизацией с повышенными правами (WATCH-19) |
| APNs — best effort | Нужен backlog и повторная доставка |
| APNs payload 4 КБ | Длинный текст режем; полный текст храним на relay |
| BLE background — 5 timely alerts в сутки | BLE не основной транспорт уведомлений |
| HealthKit background — 4 обновления в час | Не ждём real-time по всем типам |
| Critical Alerts — entitlement | Не обещаем критические будильники |
| Нет публичного API для Wi-Fi join | Только ручное подключение |
| Нет доступа к чужим уведомлениям на watchOS | Уведомления показывает только наш watch app |
| Нет системных звонков/SMS | Только свои уведомления и команды |

#### Проверка доставки в M0

Ручная проверка на A2093 25.11.2026 (WATCH-7): TestFlight-сборка, пуш скриптом `send-test-push` в production APNs, iPhone вне сценариев 1–2 выключен.

| Сценарий | Результат |
|---|---|
| iPhone рядом, подключён по Bluetooth | Доставлен, < 1 с |
| iPhone в авиарежиме, часы в домашнем Wi-Fi; часы считают iPhone подключённым даже после выключения Bluetooth на нём | Не доставлен (4 пуша) |
| iPhone выключен, часы в домашнем Wi-Fi | Доставлен, < 1 с |
| Часы на точке доступа Android (2.4 ГГц) | Доставлен, < 1 с; после 23 минут простоя тоже < 1 с |
| Wi-Fi на часах выключен, рядом только Android по Bluetooth, в том числе с Bluetooth-модемом | Не доставлен |

Выводы:

- Без iPhone пуш доходит до часов, если у них есть Wi-Fi. Архитектура APNs из §3.3 подтверждена, M1 начинается без пересмотра.
- Точка доступа Android — единственный путь в интернет вне дома. Мобильная сеть не рвёт соединение часов с APNs как минимум за 23 минуты простоя.
- Хранит ли APNs пуш, отправленный, пока часы сидели на iPhone без интернета, не проверено: уведомления стёрли до проверки. Relay в любом случае держит свой backlog (строка «APNs — best effort» выше).

---

## 3. Архитектура

### 3.1 Компоненты

```
┌────────────────────┐        HTTPS         ┌────────────────────┐
│ Android apps       │                      │ Relay              │
│ (WhatsApp, etc.)   │                      │ FastAPI + SQLite   │
└─────────┬──────────┘                      │ APNs + FCM         │
          │ NotificationListenerService     └───────┬─────┬──────┘
          ▼                                         │     │
┌────────────────────┐        HTTPS                 │     │ APNs
│ Companion          │◄─────────────────────────────┘     │
│ Kotlin/Compose     │                                     ▼
│ FCM + foreground   │        FCM                 ┌────────────────────┐
│ service            │◄─────────────────────────── │ Watch app          │
└─────────┬──────────┘                             │ SwiftUI/watchOS 10 │
          │                                        │ UserNotifications  │
          │ BLE GATT (v1.1, optional)              │ HealthKit          │
          └───────────────────────────────────────►│ CoreBluetooth      │
                                                   └────────────────────┘
```

### 3.2 Потоки данных

**Уведомление:**
1. Android-приложение получает `StatusBarNotification`.
2. Companion нормализует его в `Notification event`.
3. Отправляет `POST /v1/events/notification` на relay.
4. Relay сохраняет событие и отправляет APNs alert на watch.
5. Watch app показывает уведомление.
6. Watch app отправляет `POST /v1/receipts` (опционально).

**Ответ:**
1. Пользователь нажимает Reply на часах.
2. Watch app отправляет `POST /v1/events/{id}/reply`.
3. Relay ставит команду в очередь и отправляет FCM `reply.execute` на Android.
4. Companion находит исходное уведомление и применяет `RemoteInput`.
5. Companion отправляет `POST /v1/replies/{id}/result`.
6. Watch app показывает результат локально.

**Здоровье:**
1. Watch app читает HealthKit.
2. Батчем отправляет `POST /v1/health/samples`.
3. Relay хранит и отдаёт Android через `GET /v1/health/samples`.
4. Companion показывает данные и опционально пишет в Health Connect.

**Музыка:**
1. Watch app отправляет `POST /v1/commands` `music.*`.
2. Relay отправляет FCM на Android.
3. Companion управляет активной `MediaSession`.
4. Watch app получает результат через локальный статус или FCM-ответ.

### 3.3 Почему APNs + FCM

- APNs — единственный надёжный способ разбудить watch app в фоне и показать уведомление.
- BLE в фоне ограничен пятью timely alerts в сутки; для потока уведомлений не подходит.
- FCM — надёжная доставка команд на Android, когда экран выключен.
- WebSocket — только dev-fallback; в production не основной транспорт.

### 3.4 BLE (v1.1)

BLE нужен для:
- низкой задержки музыки и ответов, когда телефон рядом;
- работы без интернета;
- экономии APNs/FCM.

BLE не используется для основного потока уведомлений. Реализация — после MVP.

---

## 4. Функциональные требования

### F1. Pairing

- Watch app при первом запуске вызывает `POST /v1/pair/start`.
- Передаёт: `platform=watchos`, `apns_token`, `public_key`, `name`.
- Relay создаёт watch-устройство с provisional-токеном и возвращает:
  - `pairing_id`
  - `pairing_code` (8 цифр)
  - `watch_device_token` (32 байта, base64url)
  - `expires_at` (10 минут)
- Watch app сохраняет `watch_device_token` в Keychain и показывает код крупным шрифтом.
- Пользователь вводит код в Companion.
- Companion вызывает `POST /v1/pair/complete`:
  - `pairing_code`
  - `platform=android`
  - `fcm_token`
  - `public_key`
  - `name`
- Relay связывает устройства, возвращает:
  - `android_device_id`
  - `android_device_token` (32 байта, base64url)
  - `watch_device_id`
  - `watch_public_key`
- Relay отправляет APNs «Paired» на часы.
- Watch app либо принимает APNs, либо опрашивает `GET /v1/pair/status?pairing_id=...` с `watch_device_token` до `paired=true`.
- Companion сохраняет токен в `EncryptedSharedPreferences`; watch app — в Keychain.
- Relay URL зашит в build config обоих приложений; для личного проекта настройка в UI не обязательна.
- Код одноразовый; повторная пара сбрасывает старые токены.
- Если часы не в сети, pairing не начинается; показать «Подключите часы к Wi-Fi или iPhone».

**Acceptance:** после pairing тестовое уведомление доходит до часов; повторный ввод кода отклоняется.

### F2. Notification mirroring

- Companion слушает `NotificationListenerService`.
- Фильтры:
  - пропускать свои уведомления;
  - пропускать `isOngoing` и `CATEGORY_CALL` — звонки вне scope, даже если приложение не пометило их ongoing;
  - пропускать групповой summary, пока активно хотя бы одно дочернее уведомление его группы; summary без активных дочерних (некоторые приложения публикуют только его) отправляется с `is_group_summary: true`;
  - blocklist по package name;
  - дедуп: повторная публикация с тем же `notification_key` и тем же текстом (`title`, `body`, `subtext` после нормализации) менее чем через 5 секунд по `postTime` после предыдущей публикации этого ключа пропускается. Новый текст под тем же ключом (второе сообщение в чате через 2 секунды) отправляется всегда.
- Извлекать:
  - `packageName`, `applicationInfo.loadLabel`;
  - `title`, `text`, `bigText`, `subText`, `conversationTitle`;
  - `category`, `isClearable`, `isOngoing`;
  - `notification_key`, `groupKey`, `postTime`;
  - `replyable` = есть `Notification.Action` с `RemoteInput`, принимающим свободный текст.
- Нормализация текста:
  - MessagingStyle: `title` — `conversationTitle`, иначе отправитель последнего сообщения, иначе `EXTRA_TITLE`; `body` — текст последнего сообщения, в групповом чате с префиксом «Отправитель: »;
  - остальные: `title` — `EXTRA_TITLE`, `body` — `EXTRA_BIG_TEXT`, иначе `EXTRA_TEXT`;
  - `subtext` — `EXTRA_SUB_TEXT`; пустые строки — `null`; одиночные суррогаты заменяются на U+FFFD, иначе relay ответит `400` (§5.4);
  - `group_key` — ключ группы, только если приложение или системная автогруппировка сгруппировали уведомление, иначе `null`;
  - `actions` — первое действие со свободным текстом как `{"id": "reply", "type": "text"}`.
- До pairing (M2) URL relay и статический токен берутся при сборке из `android/local.properties` (`relay.url`, `relay.token`); без них приложение собирается и показывает «Relay не настроен».
- До Room (§6.2) неотправленные события живут только в памяти: до 12 попыток с backoff из §5.1, затем событие отбрасывается.
- Отправлять `POST /v1/events/notification`.
- Relay:
  - сохраняет событие;
  - дедуп по `event_id` и `notification_key`;
  - отправляет APNs alert;
  - при ошибке APNs — retry/backoff;
  - при `BadDeviceToken`/`Unregistered` — помечает токен недействительным и уведомляет Android.
- Watch app показывает уведомление через `UNUserNotificationCenter`.
- Если часы были офлайн:
  - relay хранит события 7 дней;
  - при следующем запуске watch app запрашивает `GET /v1/events?since=...`;
  - если событий > 5, показывает одно summary-уведомление «N новых уведомлений»;
  - полный список — внутри watch app.

**Acceptance:** уведомление WhatsApp появляется на часах; повторное событие не дублируется; блокированное приложение не появляется.

### F3. Reply

- Если `replyable=true`, APNs payload содержит `category=MESSAGE_REPLY`.
- Watch app регистрирует `UNNotificationCategory` с `UNTextInputNotificationAction`.
- Пользователь вводит текст (dictation/scribble).
- Watch app отправляет `POST /v1/events/{event_id}/reply`:
  ```json
  {"reply_id":"uuid","text":"...","sent_at":"..."}
  ```
- Relay сохраняет reply и отправляет FCM `reply.execute` на Android.
- Companion:
  - находит исходное `StatusBarNotification` по `notification_key`;
  - проверяет `Notification.Action` с `RemoteInput`;
  - собирает `Intent` с `RemoteInput.addResultsToIntent`;
  - вызывает `actionIntent.send()`;
  - отправляет результат `POST /v1/replies/{reply_id}/result`.
- Если уведомление уже исчезло или RemoteInput не поддерживается:
  - результат `failed` с кодом `notification_gone` / `remote_input_unsupported`;
  - watch app показывает локальное уведомление «Не удалось отправить ответ».
- Watch app оптимистично показывает «Отправлено» после HTTP 202; ошибка приходит отдельно.

**Acceptance:** ответ из WhatsApp/Telegram/Signal появляется в чате; для приложения без RemoteInput показывается ошибка.

### F4. Health и сон

- Watch app запрашивает HealthKit-доступ:
  - heart rate;
  - resting heart rate;
  - HRV;
  - sleep analysis;
  - steps;
  - active energy;
  - workouts;
  - oxygen saturation;
  - ECG — v1.2, опционально.
- Использовать `HKObserverQuery` + `HKAnchoredObjectQuery`.
- `enableBackgroundDelivery` для поддерживаемых типов.
- На активном циферблате должен быть complication — иначе фоновые обновления могут не приходить.
- Батч: до 500 сэмплов или 15 минут.
- `POST /v1/health/samples`; при офлайне — локальная очередь в watch app.
- Relay хранит 30 дней; Android забирает `GET /v1/health/samples?since=...`.
- Companion хранит в Room; экран «Здоровье»: пульс, сон, шаги, тренировки.
- Health Connect — опционально, v1.1.
- Тренировка: `HKWorkoutSession` + `HKLiveWorkoutBuilder`; live HR отправлять раз в 5 секунд, пока тренировка активна.
- Сон: сессии `sleepAnalysis`; агрегировать по стадиям.

**Acceptance:** новый пульс появляется на Android в течение 15 минут; завершённая тренировка — в течение 1 минуты.

### F5. Music

- Watch app: экран с кнопками play/pause, next, previous, volume up/down.
- Команда: `POST /v1/commands`:
  ```json
  {"command_id":"uuid","type":"music.play","payload":{}}
  ```
- Relay → FCM → Companion.
- Companion:
  - `MediaSessionManager.getActiveSessions(notificationListenerComponent)`;
  - выбирает активную сессию;
  - вызывает `TransportControls`.
- Если активной сессии нет — `failed/no_active_session`; watch app показывает «Нет музыки».
- Латентность: < 2 секунды через FCM; < 500 мс через BLE (v1.1).

**Acceptance:** play/pause/next работают в YouTube Music/Spotify/локальном плеере.

### F6. Alarms (v1.1)

- Companion отправляет `alarm.schedule`:
  ```json
  {"alarm_id":"uuid","time":"2026-11-25T07:30:00+03:00","label":"...","sound":"default"}
  ```
- Watch app планирует `UNCalendarNotificationTrigger`.
- Идентификатор уведомления: `alarm:<alarm_id>`.
- `alarm.cancel` отменяет.
- Critical Alerts не используем; будильник respects Focus.
- Watch app может создавать локальные будильники; синхронизация на Android — v1.2.

**Acceptance:** будильник срабатывает на часах в заданное время; повторное schedule не дублирует.

### F7. Find Watch (v1.1)

- Companion отправляет `find_watch`.
- Relay → APNs alert/background.
- Watch app:
  - если активен — играет звук 10 секунд через `AVAudioPlayer`;
  - если в фоне — локальное уведомление со звуком.
- Пользователь может остановить на часах.

**Acceptance:** команда заставляет часы звонить; звук остановим.

### F8. Settings и статус

Companion:
- статус pairing;
- статус relay;
- доступ к уведомлениям;
- исключение из оптимизации батареи;
- blocklist приложений;
- тестовое уведомление;
- экспорт логов без текста уведомлений.

Watch app:
- статус связи;
- последняя синхронизация;
- тестовое уведомление;
- unpair;
- версия.

Relay:
- `GET /healthz`;
- `GET /version`;
- `GET /metrics` (опционально).

### F9. Complications (v1.1)

- WidgetKit complication:
  - unread count;
  - статус связи.
- Обновление раз в 15 минут.
- APNs `complication` push — опционально.

---

## 5. Протокол

### 5.1 Общие правила

- Транспорт: HTTPS, JSON UTF-8.
- Версия API: `/v1`.
- Заголовки:
  - `Authorization: Bearer <device_token>`
  - `Content-Type: application/json`
  - `Idempotency-Key: <uuid>` для POST.
- Максимальный размер тела: 32 КБ.
- Время: RFC3339 UTC.
- Ошибки:
  ```json
  {"error":{"code":"...","message":"...","retryable":true}}
  ```
  Схема: `protocol/schema/error.schema.json`. `message` не повторяет содержимое запроса.
- HTTP-коды: 200, 201, 202, 204, 400, 401, 403, 404, 409, 413, 429, 500, 503.
- Retry: экспоненциальный backoff с jitter, максимум 5 минут.
- Rate limit: 120 событий/мин, 30 ответов/мин, 60 команд/мин.

### 5.2 Аутентификация

- Pairing code: 8 цифр, TTL 10 минут, одноразовый.
- Device token: 32 байта, base64url; хранится на сервере как SHA-256.
- При re-pair старые токены инвалидируются.
- Опционально: HMAC-SHA256 для BLE и критичных запросов.
  - `X-Timestamp`, `X-Signature`.
  - Окно 5 минут.
- APNs/FCM токены обновляются через `POST /v1/devices/{id}/push-token`.

### 5.3 Envelope

Envelope оборачивает сообщения в транспортах, где нет пути и токена: FCM и BLE.

```json
{
  "v": 1,
  "id": "018f...",
  "type": "reply.execute",
  "sent_at": "2026-11-24T12:00:00Z",
  "device_id": "018f...",
  "payload": {}
}
```

- `v` — версия протокола; в HTTP её роль играет префикс `/v1`, и breaking change увеличивает оба.
- `id` — UUID сообщения. Повторная отправка сохраняет его, и получатель по нему отбрасывает дубли; в FCM это `id` записи `outbox` (§9.5).
- `type` — тип сообщения, например `reply.execute`.
- `sent_at` — момент, когда отправитель передал сообщение в транспорт, RFC3339 UTC. Для FCM это время отправки relay, а не доменное время из `payload`.
- `device_id` — устройство, на котором возникло сообщение; для Command это часы.
- `payload` — тело сообщения этого `type`, например §5.6 для `reply.execute`.

По транспортам:

- **HTTP** — без envelope: тело запроса и ответа — сам объект эндпоинта без обёртки или ошибка из §5.1. Поля envelope задают:
  - `v` — префикс пути `/v1`;
  - `type` — метод и путь, например `POST /v1/events/notification`;
  - `device_id` — устройство, которому выдан Bearer-токен; в теле его нет;
  - `id` — заголовок `Idempotency-Key`; id сущностей (`event_id`, `reply_id`, `command_id`, `sample_id`) остаются в теле;
  - `sent_at` — не нужен; доменное время лежит в теле (`posted_at`, `sent_at`, `at`).
- **APNs** — без envelope: формат задаёт Apple (§5.5). Тип пуша задаёт `apns-push-type`, а событие — `event_id` в payload.
- **FCM** — envelope в `data`. FCM принимает только строки, поэтому `v` передаётся как `"1"`, а `payload` — как JSON-строка (§9.4).
- **BLE (v1.1)** — envelope передаётся как payload кадра (§5.11).

### 5.4 Notification event

Companion отправляет событие телом `POST /v1/events/notification`. Relay отдаёт часам в `GET /v1/events` тот же объект с полем `body_truncated`.

```json
{
  "event_id": "018f...",
  "source_package": "com.whatsapp",
  "source_app": "WhatsApp",
  "notification_key": "0|com.whatsapp|1234|null|10001",
  "group_key": "0|com.whatsapp|1234",
  "posted_at": "2026-11-24T12:00:00Z",
  "title": "Alice",
  "body": "Привет",
  "subtext": null,
  "category": "msg",
  "is_ongoing": false,
  "is_clearable": true,
  "is_group_summary": false,
  "replyable": true,
  "actions": [
    {"id": "reply", "title": "Reply", "type": "text"}
  ]
}
```

Правила:
- Все ключи обязательны. `null` допустим только у `source_app`, `group_key`, `title`, `body`, `subtext` и `category`; неизвестные поля и строки с одиночными суррогатами (`\ud800` в JSON), которые нельзя записать в UTF-8, — `400 invalid_request`.
- Companion присылает `body` целиком, его ограничивает только размер тела (§5.1). Relay хранит полный текст в `body_full` (§6.1). Если он длиннее 3000 символов (Unicode code points), relay отдаёт часам первые 3000 и `body_truncated: true`, а полный текст — через `GET /v1/events/{id}`.
- `posted_at` — RFC3339 UTC с суффиксом `Z`.
- `notification_key` обязателен для reply.
- `source_app` — человекочитаемое имя.
- `actions` — только действия, которые можно выполнить, может быть пустым; MVP — reply (`type: text`).
- Схемы: `protocol/schema/notification-event.schema.json` (Companion → relay) и `notification-event-watch.schema.json` (relay → Watch app).

Ответы `POST /v1/events/notification`:
- `202` без тела — событие сохранено, APNs принял пуш.
- `409 duplicate` — APNs уже принимал пуш с этим `event_id`; второго пуша нет.
- `503 apns_unavailable` или `503 apns_rejected` с `retryable: true` — APNs недоступен, троттлит (429) или отвечает 5xx. Событие сохранено, но пуш не принят: повтор с тем же `event_id` отправляет пуш снова.
- `500 apns_rejected` с `retryable: false` — APNs отклонил пуш (например, `BadDeviceToken`).

### 5.5 APNs payload

```json
{
  "aps": {
    "alert": {"title": "WhatsApp · Alice", "body": "Привет"},
    "sound": "default",
    "category": "MESSAGE_REPLY",
    "thread-id": "com.whatsapp",
    "interruption-level": "active"
  },
  "event_id": "018f...",
  "replyable": true,
  "source_package": "com.whatsapp"
}
```

- `title` — `source_app · title`: приложение и отправитель, например «Telegram · Алиса». Без `source_app` — `source_package`; без `title` — только приложение.
- `body` — `body` события; при `body: null` поля нет, и alert показывает только заголовок.
- `category: MESSAGE_REPLY` — только при `replyable: true`; у остальных уведомлений поля нет.
- `thread-id` = `source_package`: уведомления одного приложения группируются на часах.

Заголовки:
- `apns-push-type: alert`
- `apns-priority: 10`
- `apns-topic: <bundle id watch app>`
- `apns-expiration`: момент отправки + TTL; TTL по умолчанию 3600 с — APNs хранит пуш, пока часы офлайн; TTL 0 — APNs не хранит пуш и пробует доставить один раз
- `apns-collapse-id: <notification_key>` только для обновлений
- `apns-id`: UUID

Ограничения:
- payload ≤ 4 КБ;
- если payload длиннее — relay и тестовый скрипт обрезают `alert.body` до самого длинного начала, с которым payload в UTF-8 JSON с `…` в конце укладывается в 4 КБ; если не помещается даже заголовок с `…` вместо тела, тело убирается и так же обрезается `alert.title`; полный текст доступен через `GET /v1/events/{id}`;
- для фоновой синхронизации — `apns-push-type: background`, `content-available: 1`, priority 5; не гарантируется.

### 5.6 Reply

Запрос:
```json
{
  "reply_id": "018f...",
  "text": "Ок",
  "sent_at": "2026-11-24T12:00:05Z"
}
```

FCM-сообщение — envelope `reply.execute` (§5.3) с `payload`:
```json
{
  "reply_id": "018f...",
  "event_id": "018f...",
  "notification_key": "0|com.whatsapp|...",
  "source_package": "com.whatsapp",
  "text": "Ок"
}
```

Результат:
```json
{"status":"sent"}
```
или
```json
{"status":"failed","error":"remote_input_unsupported"}
```

### 5.7 Health

```json
{
  "samples": [
    {
      "sample_id": "018f...",
      "type": "heart_rate",
      "value": 72,
      "unit": "count/min",
      "start_at": "2026-11-24T12:00:00Z",
      "end_at": "2026-11-24T12:00:00Z",
      "source": "watch"
    }
  ]
}
```

Типы: `heart_rate`, `resting_heart_rate`, `hrv`, `sleep`, `steps`, `active_energy`, `workout`, `oxygen_saturation`, `ecg`.
Батч ≤ 500, тело ≤ 64 КБ.
Идемпотентность по `sample_id`.

### 5.8 Commands

```json
{
  "command_id": "018f...",
  "type": "music.play",
  "payload": {}
}
```

Типы:
- `music.play`, `music.pause`, `music.next`, `music.previous`, `music.volume_up`, `music.volume_down`;
- `find_watch`;
- `alarm.schedule`, `alarm.cancel`.

### 5.9 Receipts

```json
{"event_id":"018f...","status":"displayed","at":"..."}
```
Статусы: `displayed`, `opened`, `dismissed`.

### 5.10 Ошибки и retry

- `400 invalid_request` — не retry.
- `401 invalid_token` — re-pair.
- `403 forbidden` — не retry.
- `404 not_found` — не retry.
- `409 duplicate` — считать успехом.
- `413 payload_too_large` — тело больше 32 КБ (§5.1), не retry.
- `429 rate_limited` — retry с `Retry-After`.
- `500/503` — retry, если в теле ошибки `retryable: true`; при `retryable: false` повтор не поможет (например, APNs отклонил токен часов).
- APNs: `BadDeviceToken`, `Unregistered` — пометить токен; `TooManyRequests` — backoff; `PayloadTooLarge` — обрезать.
- FCM: `UNREGISTERED` — пометить токен; `QUOTA_EXCEEDED` — backoff.

### 5.11 BLE GATT (v1.1)

Service UUID: сгенерировать, зафиксировать в `protocol/ble.md`.

Characteristics:
- `pairing` — read/write, требует шифрование;
- `rx` — write without response;
- `tx` — notify;
- `status` — read/notify.

Frame:
```
version(1) | type(1) | flags(1) | length(2 LE) | payload
```
- payload: JSON или CBOR;
- max 4096 байт;
- chunking при MTU < 200;
- HMAC-SHA256 с pairing secret;
- sequence number, replay window 32;
- ack по `tx`.

---

## 6. Модель данных

### 6.1 Relay (SQLite)

```sql
devices(
  id TEXT PRIMARY KEY,
  role TEXT NOT NULL,              -- android | watchos
  name TEXT,
  platform TEXT NOT NULL,
  push_token TEXT,                 -- APNs or FCM
  push_environment TEXT,           -- sandbox | production
  public_key TEXT,
  token_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_seen_at TEXT,
  revoked_at TEXT
)

pairing_sessions(
  code_hash TEXT PRIMARY KEY,
  watch_device_id TEXT,
  android_device_id TEXT,
  expires_at TEXT NOT NULL,
  used_at TEXT
)

notification_events(
  id TEXT PRIMARY KEY,
  android_device_id TEXT NOT NULL,
  source_package TEXT NOT NULL,
  source_app TEXT,
  notification_key TEXT NOT NULL,
  group_key TEXT,
  title TEXT,
  body TEXT,
  body_full TEXT,
  category TEXT,
  posted_at TEXT NOT NULL,
  replyable INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
)

deliveries(
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  watch_device_id TEXT NOT NULL,
  status TEXT NOT NULL,            -- pending | sent | failed | displayed
  apns_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  next_attempt_at TEXT,
  updated_at TEXT NOT NULL
)

replies(
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  watch_device_id TEXT NOT NULL,
  text TEXT NOT NULL,
  status TEXT NOT NULL,            -- queued | sent | failed
  error TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
)

health_samples(
  id TEXT PRIMARY KEY,
  watch_device_id TEXT NOT NULL,
  type TEXT NOT NULL,
  value_json TEXT NOT NULL,
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  created_at TEXT NOT NULL
)

commands(
  id TEXT PRIMARY KEY,
  watch_device_id TEXT NOT NULL,
  type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL,            -- queued | sent | failed
  error TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
)

outbox(
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,              -- apns | fcm
  target_device_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL,            -- pending | sent | failed
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL
)
```

Индексы:
- `notification_events(android_device_id, created_at)`;
- `deliveries(status, next_attempt_at)`;
- `health_samples(watch_device_id, start_at)`;
- `outbox(status, next_attempt_at)`.

Retention:
- notifications: 7 дней;
- health: 30 дней;
- commands/replies: 30 дней;
- outbox: 7 дней после успеха.

### 6.2 Android (Room)

- `NotificationEntity` — последние 200 событий для reply.
- `HealthEntity` — здоровье.
- `SettingsEntity` — blocklist, relay URL, device id.
- `PendingEventEntity` — очередь при офлайне.

### 6.3 Watch app

- `Keychain` — device token.
- `UserDefaults` — last event id, pairing state.
- `AlarmStore` — будильники.
- `HealthQueue` — неотправленные сэмплы (файл/SQLite).

---

## 7. Android companion

### 7.1 Стек

- Kotlin 2.4, встроенная поддержка Kotlin в AGP 9.5; Gradle 9.9, JDK 21.
- compileSdk 37.1 (его требуют текущие AndroidX и OkHttp), minSdk 31, targetSdk 35.
- Jetpack Compose (Material 3).
- Room.
- DataStore.
- WorkManager.
- OkHttp + Kotlinx Serialization.
- Hilt.
- Firebase Messaging.

### 7.2 Модули

```
android/
  app/
  core/protocol/
  core/notifications/
  core/network/
  core/database/
  feature/pairing/
  feature/settings/
  feature/health/
```

### 7.3 Notification normalization

`NotificationListenerService`:
- `onListenerConnected()` — обновить состояние, `requestRebind()`.
- `onNotificationPosted(sbn)`:
  - пропустить свой package;
  - пропустить `FLAG_ONGOING_EVENT`;
  - пропустить `FLAG_GROUP_SUMMARY`, если есть группа;
  - извлечь extras;
  - определить `replyable`;
  - сохранить в Room;
  - поставить в очередь `EventUploader`.
- `onNotificationRemoved(sbn)` — пометить событие удалённым; reply по нему невозможен.

Извлечение текста:
- `EXTRA_TITLE`, `EXTRA_TEXT`, `EXTRA_BIG_TEXT`, `EXTRA_SUB_TEXT`, `EXTRA_CONVERSATION_TITLE`;
- `Notification.EXTRA_MESSAGES` для `MessagingStyle` — брать последнее сообщение;
- ` CATEGORY_MESSAGE`, `CATEGORY_EMAIL`, `CATEGORY_SOCIAL`, `CATEGORY_EVENT`, `CATEGORY_PROMO`, `CATEGORY_ALARM`, `CATEGORY_CALL` (calls skip);
- `Notification.Action.getRemoteInputs()`.

### 7.4 Reply execution

`ReplyCommandHandler`:
- вход: `reply.execute` из FCM.
- найти `StatusBarNotification` в кэше по `notification_key`;
- найти action с `RemoteInput`;
- `Bundle results = new Bundle(); results.putCharSequence(remoteInput.getResultKey(), text);`
- `Intent fillIn = new Intent(); RemoteInput.addResultsToIntent(remoteInputs, fillIn, results);`
- `action.actionIntent.send(context, 0, fillIn);`
- вернуть результат.

Если уведомление не найдено — `notification_gone`.
Если action не найден — `remote_input_unsupported`.
Таймаут — 10 секунд.

### 7.5 FCM

`BridgeMessagingService : FirebaseMessagingService`:
- `onNewToken` → `POST /v1/devices/{id}/push-token`.
- `onMessageReceived`:
  - `reply.execute` → `ReplyCommandHandler`;
  - `music.*` → `MusicCommandHandler`;
  - `alarm.*` → `AlarmCommandHandler` (v1.1);
  - `find_watch` → не на Android.
- Высокий приоритет только для user-visible команд; не злоупотреблять.

### 7.6 Permissions

- `BIND_NOTIFICATION_LISTENER_SERVICE` (service).
- `POST_NOTIFICATIONS` (runtime).
- `INTERNET`, `ACCESS_NETWORK_STATE`.
- `BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT`, `BLUETOOTH_ADVERTISE` (v1.1).
- `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_CONNECTED_DEVICE`, `FOREGROUND_SERVICE_DATA_SYNC`.
- `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` — через `Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`.

### 7.7 Foreground service и батарея

`BridgeForegroundService`:
- постоянное уведомление «Watch Bridge подключён»;
- тип `connectedDevice|dataSync`;
- держит WebSocket (dev fallback) и BLE GATT server (v1.1);
- перезапуск через `START_STICKY`;
- `onTaskRemoved` — не убивать.

Инструкции для OEM:
- Xiaomi: Autostart, No restrictions.
- Samsung: Unmonitored apps.
- Huawei: Protected apps.
- OnePlus: Battery optimization off.

### 7.8 Настройки

- Relay URL.
- Pairing.
- Notification access.
- Battery optimization.
- Blocklist.
- Test notification.
- Logs (без текста уведомлений).
- Версия.

---

## 8. watchOS app

### 8.1 Стек

- Swift 6.
- SwiftUI.
- watchOS 10.0 deployment target.
- UserNotifications.
- CoreBluetooth (v1.1).
- HealthKit.
- WidgetKit (v1.1).
- URLSession.
- QR-код токена: SwiftPM-пакет `fwcd/swift-qrcode-generator` (MIT, чистый Swift; CoreImage на watchOS нет).
- Проект: XcodeGen (`watch/project.yml`); `.xcodeproj` генерируется и не коммитится.
- Тип: **watch-only/independent**; iOS companion не нужен. Xcode создаёт stub iOS wrapper только для упаковки и установки.

### 8.2 Структура

```
watch/
  PersonalWatch Watch App/
    PersonalWatchApp.swift
    Pairing/
    Notifications/
    Relay/
    Health/
    Music/
    Alarms/
    Settings/
    Complications/
```

### 8.3 Lifecycle и push

- `@WKApplicationDelegateAdaptor` (один watch-таргет, без WatchKit extension) → `WKApplication.shared().registerForRemoteNotifications()` на каждом запуске.
- `didRegisterForRemoteNotifications(withDeviceToken:)` → отправить на relay (в M0 — показать на экране как QR-код и hex-текст).
- `userNotificationCenter(_:willPresent:)` возвращает `.banner`, `.list`, `.sound`, иначе пуш при открытом приложении не показывается.
- `UNUserNotificationCenter.current().delegate`.
- Запросить `.alert`, `.sound`, `.badge`.
- Категории:
  - `MESSAGE_REPLY` — `UNTextInputNotificationAction`.
  - `GENERIC` — без действий.
- При получении push:
  - показать alert;
  - сохранить `event_id`;
  - отправить receipt `displayed`.

### 8.4 Ответы

- `userNotificationCenter(_:didReceive:withCompletionHandler:)`.
- Для `UNTextInputNotificationResponse`:
  - взять `userText`;
  - `POST /v1/events/{event_id}/reply`;
  - показать локальный статус.
- Если ошибка сети — сохранить в очередь и повторить.
- Таймаут — 10 секунд.

### 8.5 HealthKit

- `HKHealthStore.requestAuthorization`.
- `HKObserverQuery` для типов.
- `enableBackgroundDelivery(for:frequency:)`.
- `HKAnchoredObjectQuery` для инкремента.
- `HKWorkoutSession` + `HKLiveWorkoutBuilder`.
- Батч и очередь.
- Complication на активном циферблате обязателен для фоновых обновлений.
- Лимит: 4 обновления в час.

### 8.6 Музыка

- Экран с кнопками.
- `POST /v1/commands`.
- Показывать статус: sent/failed.
- Опционально: `WKExtendedRuntimeSession` для удержания экрана.

### 8.7 Будильники (v1.1)

- `UNCalendarNotificationTrigger`.
- Идентификатор `alarm:<id>`.
- `alarm.schedule` / `alarm.cancel`.
- Без critical alerts.

### 8.8 Find Watch (v1.1)

- `AVAudioPlayer` с локальным файлом.
- Если приложение в фоне — локальное уведомление со звуком.
- Остановка по кнопке.

### 8.9 Complications (v1.1)

- WidgetKit.
- `accessoryCircular`, `accessoryRectangular`.
- unread count / connection status.
- Timeline 15 минут.

### 8.10 Фоновые лимиты

- APNs — основной канал.
- BLE — 5 timely alerts в сутки; только v1.1.
- HealthKit — 4 обновления в час.
- `WKApplicationRefreshBackgroundTask` — по возможности.
- Не рассчитывать на точное время; дизайн с fallback.

---

## 9. Relay

### 9.1 Стек

- Python 3.12.
- FastAPI.
- SQLModel/SQLAlchemy.
- SQLite WAL.
- Alembic.
- `aioapns`.
- `httpx` + `google-auth` для FCM.
- Pydantic Settings.
- Uvicorn.
- Docker.

### 9.2 API

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/v1/pair/start` | watch app создаёт код |
| GET | `/v1/pair/status` | watch app проверяет, завершён ли pairing |
| POST | `/v1/pair/complete` | Android подтверждает код |
| POST | `/v1/devices/{id}/push-token` | обновить APNs/FCM токен |
| POST | `/v1/events/notification` | Android прислал уведомление |
| GET | `/v1/events` | watch app забирает backlog |
| GET | `/v1/events/{id}` | полный текст |
| POST | `/v1/events/{id}/reply` | ответ с часов |
| POST | `/v1/replies/{id}/result` | Android сообщил результат |
| POST | `/v1/receipts` | watch app подтвердил показ |
| POST | `/v1/health/samples` | watch app прислал здоровье |
| GET | `/v1/health/samples` | Android забирает здоровье |
| POST | `/v1/commands` | watch app → Android |
| GET | `/v1/commands/{id}` | статус команды |
| GET | `/healthz` | health check |
| GET | `/version` | версия |

### 9.3 APNs

- `aioapns.APNs`.
- Конфиг:
  - `APNS_KEY_PATH` — `.p8`;
  - `APNS_KEY_ID`;
  - `APNS_TEAM_ID`;
  - `APNS_TOPIC` — bundle id watch app;
  - `APNS_USE_SANDBOX` — true для development, false для TestFlight/production.
- Payload по §5.5.
- Заголовки по §5.5.
- Обработка ошибок:
  - `BadDeviceToken`, `Unregistered` → revoked;
  - `PayloadTooLarge` → truncate;
  - `TooManyRequests` → backoff;
  - `InternalServerError` → retry.
- Один `APNsClient` на процесс; переиспользовать соединение.

### 9.4 FCM

- Service account JSON.
- OAuth2 access token, кэш до истечения.
- HTTP v1:
  `POST https://fcm.googleapis.com/v1/projects/{project}/messages:send`
- Сообщение:
  ```json
  {
    "message": {
      "token": "<fcm_token>",
      "data": {
        "v": "1",
        "id": "018f...",
        "type": "reply.execute",
        "sent_at": "2026-11-24T12:00:06Z",
        "device_id": "018f...",
        "payload": "{...}"
      },
      "android": {"priority":"high","ttl":"3600s"}
    }
  }
  ```
- Обработка `UNREGISTERED`, `QUOTA_EXCEEDED`.

### 9.5 Outbox worker

- Таблица `outbox`.
- Один worker на процесс.
- Цикл: выбрать `pending` с `next_attempt_at <= now`, отправить, обновить.
- Backoff: 1s, 2s, 4s, ... max 5 min, jitter.
- Идемпотентность по `id`.
- При рестарте — продолжить с `pending`.

### 9.6 Deployment

`docker-compose.yml`:
- `relay` — FastAPI.
- `caddy` — TLS.
- volume `./data:/data`.
- env file `.env`.
- healthcheck `/healthz`.
- backup cron: `sqlite3 .backup`.

Caddy:
```
watch.example.com {
  reverse_proxy relay:8000
}
```

### 9.7 Observability

- JSON logs.
- `request_id`, `device_id`, `event_id`.
- Не логировать `title/body/text`.
- `/healthz` — DB, APNs config, FCM config.
- `/metrics` — Prometheus (опционально): events, pushes, errors, latency.

---

## 10. Безопасность и приватность

- TLS 1.2+; HSTS; Caddy.
- APNs `.p8`, FCM service account — только на relay; `.gitignore`, permissions 600.
- Device tokens — SHA-256 на сервере.
- Pairing code — rate limit, TTL, one-time.
- HMAC для BLE обязателен; для HTTP — опционально.
- Шифрование notification text at rest:
  - AES-GCM с ключом `DATA_KEY` из env;
  - хранить `nonce|ciphertext`;
  - ключ не в репозитории.
- Логи без текста уведомлений.
- Retention: 7/30 дней.
- Удаление данных при unpair.
- Backup encrypted.
- Нет аналитики, Crashlytics, сторонних SDK, кроме FCM/APNs.
- Не использовать `android:allowBackup="true"` для чувствительных данных; `dataExtractionRules`.
- Watch app: Keychain для токена; `NSFileProtectionComplete`.

---

## 11. Тестирование

### 11.1 Unit

- Relay: pairing, auth, dedupe, retry, retention, APNs/FCM mocks.
- Protocol: JSON Schema validation, golden payloads.
- Android: нормализация уведомлений, reply mapping, blocklist.
- watchOS: декодирование payload, категории, alarm scheduling.

### 11.2 Integration

- Relay + SQLite + mock APNs/FCM.
- Android + fake relay (MockWebServer).
- watchOS + fake relay (URLProtocol).

### 11.3 E2E

- Физические устройства: A2093 + iPhone + Android.
- APNs production: сборки из TestFlight получают production-токены.
- Сценарии:
  1. Pairing.
  2. Уведомление WhatsApp.
  3. Уведомление Telegram.
  4. SMS.
  5. Reply.
  6. Приложение без RemoteInput.
  7. Часы офлайн → backlog.
  8. Телефон офлайн → очередь.
  9. Relay restart.
  10. Watch reboot.
  11. Phone reboot.
  12. Music play/pause/next.
  13. Health sync.
  14. Alarm.
  15. Find Watch.
  16. 24h battery.

### 11.4 Performance

- Уведомление: p95 < 3s (Wi-Fi), < 1s (BLE v1.1).
- Reply: p95 < 5s.
- Music: p95 < 2s.
- Health: < 15 мин.
- Relay: p95 < 200ms на API (без APNs).

### 11.5 Test matrix

- Apple Watch Series 5, watchOS 10.6.x.
- iPhone XS/11/12+ (только установка).
- Android 12, 13, 14, 15.
- Xiaomi/Samsung/Pixel (OEM battery).
- Wi-Fi 2.4 ГГц; Wi-Fi off; Bluetooth off.

---

## 12. Репозиторий и CI

### 12.1 Структура

```
/
├── android/
├── watch/
├── relay/
├── protocol/
│   ├── schema/
│   └── examples/
├── docs/
│   ├── TZ.md
│   ├── adr/
│   └── runbooks/
├── AGENTS.md          (локальный, в .gitignore)
└── README.md
```

### 12.2 AGENTS.md

Локальный файл инструкций для кодинг-агента; не публикуется. Должен содержать:
- как собрать Android;
- как собрать watchOS;
- как запустить relay;
- как прогнать тесты;
- где лежат схемы;
- запрет на литеральное копирование кода и ассетов третьих лиц;
- правила секретов.

### 12.3 CI

- GitHub Actions:
  - Linux: Android `assembleDebug`, `test`.
  - Linux: relay `ruff`, `mypy --strict`, `pytest` — на PR, который меняет `relay/`, `protocol/` (тесты relay проверяют примеры по схемам) или сам workflow, и на push в `main`, чтобы PR начинали с тёплого кэша uv.
  - macOS: `xcodegen generate` + `xcodebuild` для watch app без подписи — на каждом PR, который меняет `watch/`, сам workflow или его action `.github/actions/xcodegen`. `.xcodeproj` генерируется из `watch/project.yml` и не коммитится.
  - macOS: подписанный archive и загрузка в TestFlight — только на push в `main`, который меняет `watch/` или workflow, на теги `vX.Y.Z` и на ручной `workflow_dispatch` (с любой ветки — проверить сборку на часах до merge или продлить 90-дневную сборку) (ADR 0004).
  - Номер сборки (`CURRENT_PROJECT_VERSION`) — `github.run_number` workflow `watch`; он растёт и на PR-запусках, поэтому в TestFlight номера идут с пропусками. Перезапуск уже выгруженного run App Store Connect отклонит как дубликат — нужен новый запуск. Переименование `watch.yml` обнулит счётчик — тогда к номеру нужно прибавить смещение. Выгрузки идут по одной (общая concurrency-группа job), чтобы меньший номер не пришёл после большего.
  - Версия (`MARKETING_VERSION`) берётся из `watch/project.yml`; тег `vX.Y.Z` переопределяет её на `X.Y.Z`. После релизного тега поднять версию в `project.yml`.
  - Оба macOS-job используют Xcode 26.3 (`DEVELOPER_DIR`): App Store Connect принимает только сборки на SDK 26, а один Xcode гарантирует, что зелёный PR соберётся и при выгрузке.
  - Подпись только в конфигурации Release: `CODE_SIGN_STYLE=Manual`, профили выбираются по UUID, которые CI читает из самих профилей; bundle id нигде, кроме `project.yml`, не повторяется.
  - Watch app объявляет `ITSAppUsesNonExemptEncryption=NO` (только HTTPS), чтобы TestFlight не спрашивал про экспортный контроль на каждой сборке. Пересмотреть, если появится собственное шифрование.
- Подписывающие секреты — только в GitHub Actions secrets: `DIST_CERT_P12_BASE64` и `DIST_CERT_P12_PASSWORD` (сертификат distribution), `PROFILE_IOS_BASE64` и `PROFILE_WATCH_BASE64` (App Store profiles iOS-обёртки и watch app), `ASC_KEY_P8_BASE64`, `ASC_KEY_ID`, `ASC_ISSUER_ID` (App Store Connect API key), `APPLE_TEAM_ID`.
- Job с секретами не запускается на `pull_request`, в том числе из форков; `pull_request_target` не используется.
- Ни один ключ, сертификат или профиль не коммитится в репозиторий.

### 12.4 Provisioning

- Apple Developer Program (платный).
- App ID для watch app; включить **Push Notifications**.
- APNs Auth Key `.p8` + Key ID + Team ID; положить на relay, не в репозиторий.
- Distribution-сертификат и два App Store provisioning profile: для iOS-обёртки и для watch app (`aps-environment=production`).
- App Store Connect API key для загрузки сборок из CI.
- Приложение в App Store Connect (без публикации) для TestFlight.
- iPhone спарен с A2093; установка watch app — через TestFlight на iPhone.
- Firebase project; `google-services.json` в Android; service account JSON только на relay.
- Relay работает с production APNs (`APNS_USE_SANDBOX=false`); sandbox не используется, пока нет локальной development-сборки.

---

## 13. Этапы

| Этап | Содержание | Оценка |
|---|---|---|
| M0 | Спайк: минимальный watch app через CI → TestFlight, регистрация в APNs, пуш скриптом без relay. Проверить доставку при iPhone рядом, iPhone в авиарежиме, часах на точке доступа Android | 1–2 дня |
| M1 | Сквозной путь: Android listener → relay → APNs → watch display. Статический токен вместо pairing, relay локально через туннель; схемы уведомления в `protocol/` | 3–5 дней |
| M2 | Pairing вместо статического токена | 1–2 дня |
| M3 | Reply через FCM и RemoteInput | 2–3 дня |
| M4 | Music control | 1–2 дня |
| M5 | Health/sleep sync | 2–3 дня |
| M6 | Деплой на VPS, outbox, retention, hardening, battery, docs | 2–3 дня |
| M7 | Alarms + Find Watch | 1–2 дня |
| M8 | BLE, complications, ECG | опционально |
| R1 | Full clone, параллельно M0–M8: спецификация протокола со слов человека, публичные исследования, трафик своих iPhone и часов, оценка зависимости от серверов Apple, go/no-go в ADR | исследование |

Каждый этап строится поверх работающего предыдущего. Если M0 покажет, что APNs не доходит до часов без iPhone, архитектура пересматривается до начала M1.

---

## 14. Риски

| Риск | Митигация |
|---|---|
| Apple provisioning/APNs | Платный аккаунт, ранняя настройка, TestFlight |
| watchOS background limits | APNs основной, backlog, summary |
| Android OEM battery | Foreground service, инструкции, тесты |
| Notification access policy | Личное использование, не Play Store |
| FCM dependency | WebSocket fallback, документировать |
| A2093 без LTE | Домашний Wi-Fi или точка доступа Android; предупреждать |
| Нет локального Mac | Сборка и подпись в CI; цикл «push → TestFlight» долгий и без отладчика — держать watch-часть тонкой, логи слать на relay |
| APNs 4 КБ | Обрезка + полный текст на relay |
| APNs best effort | Outbox, backlog, receipts |
| Нет iPhone рядом | Часы в Wi-Fi; иначе push не дойдёт |
| Сложность Swift/HealthKit | Начать с notification MVP |

---

## 15. Вопросы для человека (не блокируют M0)

1. Подтвердить железо: iPhone, Android, платный Apple Developer. Mac — не нужен, сборка в GitHub Actions.
2. MVP и порядок этапов подтверждены (v0.2).
3. Хостинг relay: VPS/домен.
4. FCM или WebSocket для команд на Android.
5. Нужен ли ECG.
6. Нужен ли BLE в MVP.
7. Нужен ли Health Connect.
8. Нужны ли будильники в MVP.

---

## 16. Приёмка

ТЗ считается принятым для M0:
- допущения из шапки зафиксированы как рабочие;
- MVP и этапы согласованы;
- создан `AGENTS.md`;
- кодинг-агент может начать M0 без дополнительных вопросов.

Финальная приёмка — после подтверждения железа и credentials человеком.
