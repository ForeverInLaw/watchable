# Personal Apple Watch Companion

Личный проект: Android-приложение и watchOS-приложение для Apple Watch, которые связывают телефон и часы без инфраструктуры третьих лиц.

## Language

**Companion**:
Android-приложение проекта, которое захватывает уведомления и обменивается событиями с Watch app.
_Avoid_: Phone app, Android app (когда речь о роли)

**Watch app**:
watchOS-приложение, устанавливаемое на Apple Watch; показывает уведомления и выполняет действия на часах.
_Avoid_: Watch client, watch extension

**Relay**:
Self-hosted сервис, который пересылает события между Companion и Watch app, когда прямой Bluetooth-связи нет.
_Avoid_: Server, backend (когда речь о роли)

**Notification event**:
Нормализованное представление Android-уведомления, предназначенное для показа на часах.
_Avoid_: Push, message

**Reply action**:
Действие пользователя на часах, которое возвращается в Companion и применяется к исходному уведомлению.
_Avoid_: Answer, response

**Pairing**:
Одноразовый обмен кодом, который связывает Companion и Watch app с Relay.
_Avoid_: Login, registration

**Command**:
Действие, инициированное на часах для телефона: ответ, управление музыкой, поиск часов, будильник.
_Avoid_: Request, action

**Delivery receipt**:
Подтверждение того, что Watch app показал Notification event или выполнил Command.
_Avoid_: Ack, read receipt

**Public-API companion**:
Архитектура только на публичных API: Companion + Watch app + Relay или BLE, без приватных протоколов сопряжения Apple.
_Avoid_: Safe clone, limited clone

**Full clone**:
Архитектура, которая воспроизводит системное сопряжение Apple Watch с Android через приватные протоколы Apple; исследовательский трек R1 (ADR 0005).
_Avoid_: Real clone, system clone
