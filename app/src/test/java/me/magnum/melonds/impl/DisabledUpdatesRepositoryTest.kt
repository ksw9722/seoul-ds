package me.magnum.melonds.impl

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DisabledUpdatesRepositoryTest {
    @Test
    fun `fork never advertises an upstream APK as its update`() = runBlocking {
        val result = DisabledUpdatesRepository().checkNewUpdate()
        assertTrue(result.isSuccess)
        assertNull(result.getOrThrow())
    }

    @Test
    fun `repeated checks remain offline no-update results`() = runBlocking {
        val repository = DisabledUpdatesRepository()
        repeat(10) {
            assertNull(repository.checkNewUpdate().getOrThrow())
        }
    }
}
