package io.github.foreverinlaw.personalwatch.companion

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val app = application as CompanionApp
        setContent {
            MaterialTheme {
                StatusScreen(isRelayConfigured = app.isRelayConfigured, deliveryStatus = app.deliveryStatus)
            }
        }
    }
}
