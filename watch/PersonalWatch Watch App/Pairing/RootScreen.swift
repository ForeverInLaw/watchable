import SwiftUI

/// The only screen: pairing progress, the code for the Companion, or the paired status (TZ F1, F8).
struct RootScreen: View {
    let pairing: Pairing
    let registration: PushRegistration

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                content
                if pairing.canCancel {
                    Button("Отмена", action: pairing.cancelPairing)
                }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch pairing.state {
        case .notConfigured:
            Text("Relay не настроен")
        case .waitingForPushToken:
            RegistrationStatus(status: registration.status)
        case .starting:
            ProgressView("Получение кода")
        case .showingCode(let code):
            Text("Введите код в Companion")
                .font(.footnote)
            Text("\(code.prefix(4)) \(code.suffix(4))")
                .font(.system(.largeTitle, design: .monospaced))
                .minimumScaleFactor(0.5)
                .lineLimit(1)
        case .offline:
            Text("Подключите часы к Wi-Fi или iPhone")
            retryButton
        case .secretMismatch:
            Text("Сборка не совпадает с relay: он отклонил её pairing-секрет")
        case .storageFailed:
            Text("Не удалось сохранить pairing")
            retryButton
        case .failed(let error):
            Text(failureText(error))
            retryButton
        case .connected:
            Text("Подключено")
                .font(.title3)
            Button("Спарить заново", action: pairing.startPairing)
                .disabled(!pairing.canStartPairing)
        }
    }

    private var retryButton: some View {
        Button("Повторить", action: pairing.startPairing)
    }

    private func failureText(_ error: RelayError) -> String {
        switch error {
        case .refused(429, _): "Слишком много попыток, повторите через минуту"
        case .refused(let status, _): "Relay отклонил запрос (\(status))"
        case .malformedAnswer, .unreachable: "Relay ответил непонятно"
        }
    }
}

/// Notification permission and APNs registration, which an unpaired watch waits for.
private struct RegistrationStatus: View {
    let status: PushRegistration.Status

    var body: some View {
        switch status {
        case .requestingPermission, .registering, .registered:
            ProgressView("Регистрация в APNs")
        case .permissionDenied:
            Text("Уведомления запрещены. Разрешите их в настройках часов и перезапустите приложение.")
        case .failed(let message):
            Text("Не удалось зарегистрироваться в APNs: \(message)")
        }
    }
}
