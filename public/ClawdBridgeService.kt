package com.tsobbb.clawdbridge

import android.content.ComponentName
import android.content.Context
import android.media.MediaMetadata
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.os.SystemClock
import android.service.notification.NotificationListenerService
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import java.io.File

/**
 * Clawd Bridge Service v1.3
 * Реализация спецификации ТЗ v1.3:
 * 1. Локальный HTTP сервер на 127.0.0.1:44444.
 * 2. Проверка Host: только 127.0.0.1 и localhost, иначе 403 Forbidden.
 * 3. Access-Control-Allow-Origin удален.
 * 4. Точный расчет позиции: дельта SystemClock.elapsedRealtime() строго при STATE_PLAYING.
 * 5. getActiveSessions() при onListenerConnected() (холодный старт).
 * 6. Запись резервного sync.json в Downloads/ClaudePet/sync.json.
 */
class ClawdBridgeService : NotificationListenerService() {

    private var server: BridgeHttpServer? = null
    private var mediaSessionManager: MediaSessionManager? = null
    private var activeController: MediaController? = null

    // Текущее состояние медиа
    private var hasMedia = false
    private var isPlaying = false
    private var playerName = "Unknown"
    private var artistName = ""
    private var trackTitle = ""
    private var basePositionMs: Long = 0
    private var baseElapsedRealtime: Long = 0
    private var durationMs: Long = 0
    private var positionKnown = true

    override fun onCreate() {
        super.onCreate()
        server = BridgeHttpServer(44444)
        server?.start()
    }

    override fun onDestroy() {
        server?.stop()
        server = null
        super.onDestroy()
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        // Холодный старт: немедленный перехват активных медиа-сессий
        val component = ComponentName(this, ClawdBridgeService::class.java)
        mediaSessionManager = getSystemService(Context.MEDIA_SESSION_SERVICE) as MediaSessionManager
        try {
            val sessions = mediaSessionManager?.getActiveSessions(component)
            if (!sessions.isNullOrEmpty()) {
                attachController(sessions[0])
            }
            mediaSessionManager?.addOnActiveSessionsChangedListener({ controllers ->
                if (!controllers.isNullOrEmpty()) {
                    attachController(controllers[0])
                } else {
                    detachController()
                }
            }, component)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private val callback = object : MediaController.Callback() {
        override fun onPlaybackStateChanged(state: PlaybackState?) {
            updatePlaybackState(state)
        }

        override fun onMetadataChanged(metadata: MediaMetadata?) {
            updateMetadata(metadata)
        }
    }

    private fun attachController(controller: MediaController) {
        activeController?.unregisterCallback(callback)
        activeController = controller
        playerName = controller.packageName ?: "MusicPlayer"
        controller.registerCallback(callback)
        updateMetadata(controller.metadata)
        updatePlaybackState(controller.playbackState)
    }

    private fun detachController() {
        activeController?.unregisterCallback(callback)
        activeController = null
        hasMedia = false
        isPlaying = false
        writeSyncJson()
    }

    private fun updateMetadata(metadata: MediaMetadata?) {
        if (metadata != null) {
            artistName = metadata.getString(MediaMetadata.METADATA_KEY_ARTIST) ?: ""
            trackTitle = metadata.getString(MediaMetadata.METADATA_KEY_TITLE) ?: ""
            durationMs = metadata.getLong(MediaMetadata.METADATA_KEY_DURATION)
            hasMedia = trackTitle.isNotEmpty()
            writeSyncJson()
        }
    }

    private fun updatePlaybackState(state: PlaybackState?) {
        if (state != null) {
            isPlaying = state.state == PlaybackState.STATE_PLAYING
            basePositionMs = state.position
            baseElapsedRealtime = SystemClock.elapsedRealtime()
            positionKnown = state.position >= 0
            hasMedia = true
            writeSyncJson()
        }
    }

    private fun getCurrentCalculatedPosition(): Long {
        if (!isPlaying) {
            return basePositionMs
        }
        val delta = SystemClock.elapsedRealtime() - baseElapsedRealtime
        val pos = basePositionMs + delta
        return if (durationMs > 0) Math.min(pos, durationMs) else pos
    }

    private fun writeSyncJson() {
        try {
            val downloadsDir = android.os.Environment.getExternalStoragePublicDirectory(
                android.os.Environment.DIRECTORY_DOWNLOADS
            )
            val dir = File(downloadsDir, "ClaudePet")
            if (!dir.exists()) dir.mkdirs()
            val file = File(dir, "sync.json")

            val json = JSONObject().apply {
                put("has_media", hasMedia)
                put("is_playing", isPlaying)
                put("player", playerName)
                put("artist", artistName)
                put("title", trackTitle)
                put("timestamp", System.currentTimeMillis() / 1000)
            }
            file.writeText(json.toString())
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    inner class BridgeHttpServer(port: Int) : NanoHTTPD("127.0.0.1", port) {
        override fun serve(session: IHTTPSession): Response {
            val hostHeader = session.headers["host"] ?: ""
            val hostClean = hostHeader.split(":")[0].trim().lowercase()

            // 1. Проверка Host: только 127.0.0.1 и localhost, иначе 403
            if (hostClean != "127.0.0.1" && hostClean != "localhost") {
                return newFixedLengthResponse(
                    Response.Status.FORBIDDEN,
                    MIME_PLAINTEXT,
                    "403 Forbidden"
                )
            }

            if (session.uri == "/now-playing") {
                val json = JSONObject().apply {
                    put("has_media", hasMedia)
                    put("is_playing", isPlaying)
                    put("player", playerName)
                    put("artist", artistName)
                    put("title", trackTitle)
                    put("position_ms", getCurrentCalculatedPosition())
                    put("duration_ms", durationMs)
                    put("position_known", positionKnown)
                    put("timestamp", System.currentTimeMillis() / 1000)
                }

                val resp = newFixedLengthResponse(
                    Response.Status.OK,
                    "application/json; charset=utf-8",
                    json.toString()
                )
                // Access-Control-Allow-Origin удален по ТЗ v1.3
                return resp
            }

            return newFixedLengthResponse(Response.Status.NOT_FOUND, MIME_PLAINTEXT, "404 Not Found")
        }
    }
}
