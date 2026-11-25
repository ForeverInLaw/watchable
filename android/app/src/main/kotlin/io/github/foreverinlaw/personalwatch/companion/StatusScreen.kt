package io.github.foreverinlaw.personalwatch.companion

import android.content.Context
import android.content.Intent
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.currentStateAsState
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.foreverinlaw.personalwatch.core.network.RelayOutcome
import io.github.foreverinlaw.personalwatch.core.protocol.PairCompleteResponse
import kotlinx.coroutines.flow.StateFlow
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

/**
 * Notification access, relay configuration, pairing and how the relay took the last event.
 * [pairing] is null when the relay is not configured; [onPair] opens code entry.
 */
@Composable
fun StatusScreen(pairing: StateFlow<PairCompleteResponse?>?, relayStatus: RelayStatus, onPair: () -> Unit) {
    val context = LocalContext.current
    // Re-read on every lifecycle change, so returning from the system settings shows the new state.
    val lifecycleState by LocalLifecycleOwner.current.lifecycle.currentStateAsState()
    val hasAccess = remember(lifecycleState) { context.hasNotificationAccess() }
    val lastResult by relayStatus.lastResult.collectAsStateWithLifecycle()
    val isPaired = pairing?.collectAsStateWithLifecycle()?.value != null

    Column(
        modifier = Modifier.fillMaxSize().safeDrawingPadding().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(stringResource(R.string.app_name), style = MaterialTheme.typography.headlineMedium)
        ListItem(
            headlineContent = { Text(stringResource(R.string.notification_access)) },
            supportingContent = {
                Text(stringResource(if (hasAccess) R.string.notification_access_granted else R.string.notification_access_missing))
            },
        )
        if (!hasAccess) {
            Button(onClick = { context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }) {
                Text(stringResource(R.string.grant_notification_access))
            }
        }
        ListItem(
            headlineContent = { Text(stringResource(R.string.relay)) },
            supportingContent = {
                Text(stringResource(if (pairing != null) R.string.relay_configured else R.string.relay_not_configured))
            },
        )
        if (pairing != null) {
            ListItem(
                headlineContent = { Text(stringResource(R.string.pairing)) },
                supportingContent = { Text(stringResource(if (isPaired) R.string.pairing_paired else R.string.pairing_unpaired)) },
            )
            Button(onClick = onPair) {
                Text(stringResource(if (isPaired) R.string.repair else R.string.pair))
            }
        }
        ListItem(
            headlineContent = { Text(stringResource(R.string.last_event)) },
            supportingContent = { Text(lastResult?.let { resultText(it) } ?: stringResource(R.string.last_event_none)) },
        )
    }
}

@Composable
private fun resultText(result: RelayStatus.Result): String {
    val time = TIME_FORMAT.format(result.at.atZone(ZoneId.systemDefault()))
    return when (result.outcome) {
        is RelayOutcome.Accepted -> stringResource(R.string.last_event_accepted, time)
        is RelayOutcome.Retry -> stringResource(R.string.last_event_unreachable, time)
        is RelayOutcome.Rejected -> stringResource(R.string.last_event_rejected, time)
    }
}

private val TIME_FORMAT: DateTimeFormatter = DateTimeFormatter.ofLocalizedTime(FormatStyle.MEDIUM)

private fun Context.hasNotificationAccess() = packageName in NotificationManagerCompat.getEnabledListenerPackages(this)
