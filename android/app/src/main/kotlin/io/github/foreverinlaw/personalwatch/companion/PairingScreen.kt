package io.github.foreverinlaw.personalwatch.companion

import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import io.github.foreverinlaw.personalwatch.core.network.PairedRelay
import io.github.foreverinlaw.personalwatch.core.network.RelayOutcome
import kotlinx.coroutines.launch

private const val CODE_LENGTH = 8

/** Entry of the 8-digit code the watch shows (TZ F1); [onDone] leaves the screen. */
@Composable
fun PairingScreen(relay: PairedRelay, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var code by rememberSaveable { mutableStateOf("") }
    var inProgress by remember { mutableStateOf(false) }
    var failure by remember { mutableStateOf<RelayOutcome<Nothing>?>(null) }

    fun submit() {
        inProgress = true
        failure = null
        scope.launch {
            when (val outcome = relay.pair(code, deviceName())) {
                is RelayOutcome.Accepted -> onDone()
                is RelayOutcome.Retry, is RelayOutcome.Rejected -> failure = outcome
            }
            inProgress = false
        }
    }

    BackHandler(onBack = onDone)
    Column(
        modifier = Modifier.fillMaxSize().safeDrawingPadding().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(stringResource(R.string.pairing), style = MaterialTheme.typography.headlineMedium)
        OutlinedTextField(
            value = code,
            onValueChange = { input -> code = input.filter(Char::isDigit).take(CODE_LENGTH) },
            label = { Text(stringResource(R.string.pairing_code)) },
            singleLine = true,
            isError = failure != null,
            supportingText = failure?.let { { Text(failureText(it)) } },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            textStyle = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.fillMaxWidth(),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = ::submit, enabled = code.length == CODE_LENGTH && !inProgress) {
                Text(stringResource(R.string.pairing_submit))
            }
            TextButton(onClick = onDone) {
                Text(stringResource(R.string.pairing_back))
            }
        }
    }
}

@Composable
private fun failureText(failure: RelayOutcome<Nothing>): String = when (failure) {
    is RelayOutcome.Rejected if failure.code == "invalid_pairing_code" -> stringResource(R.string.pairing_invalid_code)
    is RelayOutcome.Rejected -> stringResource(R.string.pairing_rejected)
    else -> stringResource(R.string.pairing_unreachable)
}

/** The phone's model, so the relay can tell devices apart; the schema allows 1 to 100 characters. */
private fun deviceName(): String? = Build.MODEL.take(100).ifBlank { null }
