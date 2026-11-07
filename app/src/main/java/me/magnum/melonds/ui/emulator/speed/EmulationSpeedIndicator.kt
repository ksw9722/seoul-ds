package me.magnum.melonds.ui.emulator.speed

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.util.AttributeSet
import androidx.appcompat.widget.AppCompatTextView
import androidx.core.view.isVisible
import me.magnum.melonds.R

/** Shows the requested speed even when the FPS counter or on-screen controls are hidden. */
class EmulationSpeedIndicator(context: Context, attrs: AttributeSet? = null) : AppCompatTextView(context, attrs) {
    init {
        setTextColor(Color.WHITE)
        setBackgroundColor(0xA0000000.toInt())
        setTypeface(typeface, Typeface.BOLD)
        textSize = 14f
        val padding = (6 * resources.displayMetrics.density).toInt()
        setPadding(padding, padding, padding, padding)
        isVisible = false
    }

    fun showSpeed(multiplier: Int, sessionRunning: Boolean = true) {
        text = context.getString(R.string.emulation_speed_status, multiplier)
        isVisible = sessionRunning && multiplier > 1
    }
}
