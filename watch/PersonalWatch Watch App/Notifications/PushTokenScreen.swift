import SwiftUI

/// Main screen: shows the APNs registration state and, once registered,
/// the device token as a QR code and as text so a test push can be sent to it.
struct PushTokenScreen: View {
    let registration: PushRegistration

    var body: some View {
        ScrollView {
            switch registration.status {
            case .requestingPermission, .registering:
                ProgressView("Регистрация в APNs")
            case .permissionDenied:
                Text("Уведомления запрещены. Разрешите их в настройках часов и перезапустите приложение.")
            case .registered(let token):
                VStack(spacing: 8) {
                    QRCodeView(text: token.hex)
                    Text(token.hex)
                        .font(.system(.footnote, design: .monospaced))
                }
            case .failed(let message):
                Text("Не удалось зарегистрироваться в APNs: \(message)")
            }
        }
    }
}
