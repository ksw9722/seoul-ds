package me.magnum.melonds.di

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.flow.flowOf
import me.magnum.melonds.domain.model.DownloadProgress
import me.magnum.melonds.domain.model.appupdate.AppUpdate
import me.magnum.melonds.domain.services.UpdateInstallManager
import javax.inject.Singleton

/** Manual, separately signed distribution: no upstream network updater or installer. */
@Module
@InstallIn(SingletonComponent::class)
object GitHubModule {
    @Provides
    @Singleton
    fun provideUpdateInstallManager(): UpdateInstallManager = object : UpdateInstallManager {
        override fun downloadAndInstallUpdate(update: AppUpdate) =
            flowOf<DownloadProgress>(DownloadProgress.DownloadFailed)
    }
}
