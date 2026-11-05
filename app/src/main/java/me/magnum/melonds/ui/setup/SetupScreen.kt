package me.magnum.melonds.ui.setup

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.exclude
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.Button
import androidx.compose.material.Card
import androidx.compose.material.Icon
import androidx.compose.material.IconButton
import androidx.compose.material.MaterialTheme
import androidx.compose.material.OutlinedButton
import androidx.compose.material.Scaffold
import androidx.compose.material.Text
import androidx.compose.material.TopAppBar
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import me.magnum.melonds.R

@Composable
internal fun SetupScreen(
    status: SetupStatus?,
    statusUnavailable: Boolean,
    onBack: () -> Unit,
    onOpenFolders: () -> Unit,
    onOpenFirmware: () -> Unit,
    onOpenSaves: () -> Unit,
    onOpenSystem: () -> Unit,
    onContinue: () -> Unit,
) {
    var selectedLicense by rememberSaveable { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.setup_title), maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.setup_back))
                    }
                },
                windowInsets = WindowInsets.safeDrawing.exclude(WindowInsets(bottom = Int.MAX_VALUE)),
                backgroundColor = MaterialTheme.colors.primary,
            )
        },
        backgroundColor = MaterialTheme.colors.surface,
        contentWindowInsets = WindowInsets.safeDrawing,
    ) { insets ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(insets).consumeWindowInsets(insets),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        stringResource(R.string.setup_welcome),
                        style = MaterialTheme.typography.h5,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.semantics { heading() },
                    )
                    Text(stringResource(R.string.setup_intro), style = MaterialTheme.typography.body1)
                }
            }
            item {
                SetupCard(stringResource(R.string.setup_rights_title)) {
                    Text(stringResource(R.string.setup_rights_body))
                }
            }
            item {
                SetupCard(stringResource(R.string.setup_folders_title)) {
                    when {
                        statusUnavailable -> StatusText(stringResource(R.string.setup_status_unavailable))
                        status == null -> StatusText(stringResource(R.string.setup_status_loading))
                        else -> {
                            val label = when (status.folderStatus) {
                                SetupStatus.FolderStatus.NOT_CONFIGURED -> R.string.setup_folder_none
                                SetupStatus.FolderStatus.MISSING_READ_PERMISSION -> R.string.setup_folder_missing_permission
                                SetupStatus.FolderStatus.READ_ONLY -> R.string.setup_folder_read_only
                                SetupStatus.FolderStatus.GRANTS_RECORDED -> R.string.setup_folder_grants_recorded
                            }
                            StatusText(stringResource(label))
                            Text(stringResource(
                                R.string.setup_folder_count,
                                status.directoryCount,
                                status.readableDirectoryCount,
                                status.writableDirectoryCount,
                            ))
                        }
                    }
                    Text(stringResource(R.string.setup_folder_steps))
                    Text(stringResource(R.string.setup_folder_permission_note), style = MaterialTheme.typography.body2)
                    SetupAction(R.string.setup_open_folders, onOpenFolders)
                }
            }
            item {
                SetupCard(stringResource(R.string.setup_boot_title)) {
                    if (status != null) {
                        StatusText(stringResource(
                            if (status.usesInternalDsDirectBoot) R.string.setup_boot_internal else R.string.setup_boot_advanced,
                        ))
                    }
                    Text(stringResource(R.string.setup_boot_body))
                    Text(stringResource(R.string.setup_boot_advanced_note), style = MaterialTheme.typography.body2)
                    SetupAction(R.string.setup_open_firmware, onOpenFirmware)
                }
            }
            item {
                SetupCard(stringResource(R.string.setup_saves_title)) {
                    if (status != null) {
                        StatusText(stringResource(
                            if (status.usesSeparateSaveDirectory) R.string.setup_saves_separate else R.string.setup_saves_rom_directory,
                        ))
                    }
                    Text(stringResource(R.string.setup_saves_body))
                    Text(stringResource(R.string.setup_saves_backup), style = MaterialTheme.typography.body2)
                    SetupAction(R.string.setup_open_saves, onOpenSaves)
                }
            }
            item {
                SetupCard(stringResource(R.string.setup_device_title)) {
                    StatusText(stringResource(R.string.setup_device_unverified))
                    if (status != null) {
                        Text(stringResource(if (status.jitEnabled) R.string.setup_jit_enabled else R.string.setup_jit_disabled))
                    }
                    Text(stringResource(R.string.setup_device_checks))
                    Text(stringResource(R.string.setup_device_performance), style = MaterialTheme.typography.body2)
                    SetupAction(R.string.setup_open_system, onOpenSystem)
                }
            }
            item {
                SetupCard(stringResource(R.string.setup_licenses_title)) {
                    Text(stringResource(R.string.setup_licenses_body))
                    Text(stringResource(R.string.setup_licenses_source_note), style = MaterialTheme.typography.body2)
                    SetupAction(R.string.setup_license_gpl) { selectedLicense = LicenseDocument.GPL.name }
                    SetupAction(R.string.setup_license_notices) { selectedLicense = LicenseDocument.THIRD_PARTY.name }
                }
            }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = onContinue, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.setup_continue))
                    }
                    Text(stringResource(R.string.setup_reopen_note), style = MaterialTheme.typography.body2)
                }
            }
        }
    }

    LicenseDocument.entries.firstOrNull { it.name == selectedLicense }?.let { document ->
        LicenseDialog(document = document, onDismiss = { selectedLicense = null })
    }
}

@Composable
private fun SetupCard(title: String, content: @Composable () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth(), elevation = 2.dp) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(title, style = MaterialTheme.typography.h6, modifier = Modifier.semantics { heading() })
            content()
        }
    }
}

@Composable
private fun StatusText(text: String) {
    Text(text, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colors.onSurface)
}

@Composable
private fun SetupAction(label: Int, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Text(stringResource(label))
    }
}
