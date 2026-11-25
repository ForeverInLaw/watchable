package io.github.foreverinlaw.personalwatch.companion

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val app = application as CompanionApp
        setContent {
            MaterialTheme {
                var isPairing by rememberSaveable { mutableStateOf(false) }
                val relay = app.relay
                if (isPairing && relay != null) {
                    PairingScreen(relay, onDone = { isPairing = false })
                } else {
                    StatusScreen(pairing = app.pairing, relayStatus = app.relayStatus, onPair = { isPairing = true })
                }
            }
        }
    }
}
