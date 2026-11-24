import QRCodeGenerator
import SwiftUI

/// Draws text as a QR code. watchOS has no CoreImage QR filter, so the matrix
/// comes from a pure-Swift encoder.
struct QRCodeView: View {
    /// White border the QR spec requires around the code, in modules.
    private static let quietZone = 4

    private let code: QRCode

    /// `text` must fit in a QR code (~2.9 KB); an APNs token is at most 200 hex characters.
    init(text: String) {
        do {
            code = try QRCode.encode(text: text, ecl: .medium)
        } catch {
            preconditionFailure("Text does not fit in a QR code: \(error)")
        }
    }

    var body: some View {
        Canvas { context, size in
            let modules = code.size + 2 * Self.quietZone
            // Whole-point modules keep edges crisp; the leftover space is split evenly around the code.
            let side = (min(size.width, size.height) / CGFloat(modules)).rounded(.down)
            let square = CGFloat(modules) * side
            let origin = CGPoint(x: (size.width - square) / 2, y: (size.height - square) / 2)
            var dark = Path()
            for y in 0..<code.size {
                for x in 0..<code.size where code.getModule(x: x, y: y) {
                    dark.addRect(CGRect(
                        x: origin.x + CGFloat(x + Self.quietZone) * side,
                        y: origin.y + CGFloat(y + Self.quietZone) * side,
                        width: side,
                        height: side
                    ))
                }
            }
            context.fill(Path(CGRect(origin: origin, size: CGSize(width: square, height: square))), with: .color(.white))
            context.fill(dark, with: .color(.black))
        }
        .aspectRatio(1, contentMode: .fit)
    }
}
