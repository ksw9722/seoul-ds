package me.magnum.melonds.ui.setup

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.Divider
import androidx.compose.material.MaterialTheme
import androidx.compose.material.Surface
import androidx.compose.material.Text
import androidx.compose.material.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import me.magnum.melonds.R
import java.io.IOException

/** Fixed bundled documents only; no external URLs, scripts, or user filesystem paths. */
internal enum class LicenseDocument(val assetPath: String, val titleResource: Int) {
    GPL("licenses/GPL-3.0.txt", R.string.setup_license_gpl),
    THIRD_PARTY("licenses/THIRD-PARTY-NOTICES.txt", R.string.setup_license_notices),
}

@Composable
internal fun LicenseDialog(document: LicenseDocument, onDismiss: () -> Unit) {
    val context = LocalContext.current
    val unavailable = stringResource(R.string.setup_license_unavailable)
    val text by produceState<String?>(initialValue = null, document) {
        value = withContext(Dispatchers.IO) {
            try {
                context.assets.open(document.assetPath).bufferedReader(Charsets.UTF_8).use { it.readText() }
            } catch (_: IOException) {
                unavailable
            }
        }
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false),
    ) {
        Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colors.surface) {
            Column(modifier = Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        stringResource(document.titleResource),
                        style = MaterialTheme.typography.h6,
                        modifier = Modifier.weight(1f).semantics { heading() },
                    )
                    TextButton(onClick = onDismiss) { Text(stringResource(R.string.setup_license_close)) }
                }
                Divider()
                SelectionContainer(modifier = Modifier.weight(1f)) {
                    Text(
                        text ?: stringResource(R.string.setup_status_loading),
                        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
                        style = MaterialTheme.typography.body2,
                    )
                }
            }
        }
    }
}
