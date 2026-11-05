package me.magnum.melonds.ui.emulator.input

import me.magnum.melonds.domain.model.Input
import me.magnum.melonds.domain.model.Point
import org.junit.Test

class MelonTouchHandlerTest {
    @Test
    fun disabledSessionDoesNotInvokeNativeInputIncludingTouchRelease() {
        // No JNI library is loaded in JVM unit tests: any accidental native call fails this test.
        val handler = MelonTouchHandler { false }
        Input.entries.forEach {
            handler.onKeyPress(it)
            handler.onKeyReleased(it)
        }
        handler.onTouch(Point())
    }
}
