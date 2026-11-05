package me.magnum.melonds.impl

import me.magnum.melonds.domain.model.appupdate.AppUpdate
import me.magnum.melonds.domain.repositories.UpdatesRepository

/**
 * Seoul DS is distributed separately from melonDS. Upstream APKs have a different
 * package/signing identity and must never be offered as updates to this fork.
 * Updates remain manual until a signed, project-owned release channel is established.
 */
class DisabledUpdatesRepository : UpdatesRepository {
    override suspend fun checkNewUpdate(): Result<AppUpdate?> = Result.success(null)
    override fun skipUpdate(update: AppUpdate) = Unit
    override fun notifyUpdateDownloaded(update: AppUpdate) = Unit
}
