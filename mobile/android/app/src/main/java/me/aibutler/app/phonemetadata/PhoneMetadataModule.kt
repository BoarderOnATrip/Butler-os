package me.aibutler.app.phonemetadata

import android.Manifest
import android.content.pm.PackageManager
import android.database.Cursor
import android.provider.CallLog
import android.provider.Telephony
import androidx.core.content.ContextCompat
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableMap
import com.facebook.react.bridge.WritableArray
import com.facebook.react.bridge.WritableMap
import com.facebook.react.module.annotations.ReactModule
import java.text.SimpleDateFormat
import java.util.LinkedHashMap
import java.util.Locale
import java.util.TimeZone

@ReactModule(name = PhoneMetadataModule.NAME)
class PhoneMetadataModule(private val reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

  data class SnapshotItem(
      val kind: String,
      val recordId: String,
      val timestampMs: Long,
      val title: String,
      val summary: String,
      val source: Map<String, Any?>,
  )

  companion object {
    const val NAME = "PhoneMetadata"
    private const val DEFAULT_CALL_LIMIT = 8
    private const val DEFAULT_SMS_LIMIT = 8
    private const val BODY_PREVIEW_LIMIT = 120
  }

  override fun getName(): String = NAME

  @ReactMethod
  fun getStatus(promise: Promise) {
    promise.resolve(buildStatusMap())
  }

  @ReactMethod
  fun getSnapshot(options: ReadableMap?, promise: Promise) {
    try {
      val callLimit = options?.let {
        if (it.hasKey("limitCalls")) it.getInt("limitCalls") else DEFAULT_CALL_LIMIT
      } ?: DEFAULT_CALL_LIMIT
      val smsLimit = options?.let {
        if (it.hasKey("limitSms")) it.getInt("limitSms") else DEFAULT_SMS_LIMIT
      } ?: DEFAULT_SMS_LIMIT

      val permissions = buildPermissionMap()
      val status = buildStatusMap(permissions)
      val ready = status.getBoolean("ready")
      val callLog = if (ready) readCallLog(callLimit) else Arguments.createArray()
      val smsThreads = if (ready) readSmsThreads(smsLimit) else Arguments.createArray()
      val reviewQueue = if (ready) buildReviewQueue(callLog, smsThreads) else Arguments.createArray()

      val payload = Arguments.createMap().apply {
        putString("generated_at", nowIso())
        putBoolean("ready", ready)
        putMap("permissions", permissions)
        putArray("missing_permissions", status.getArray("missing_permissions"))
        putString("status_label", status.getString("status_label"))
        putArray("call_log", callLog)
        putArray("sms_threads", smsThreads)
        putArray("review_queue", reviewQueue)
        putString(
            "error",
            if (ready) null else "Grant call log and SMS permissions to inspect phone metadata.",
        )
      }
      promise.resolve(payload)
    } catch (error: Throwable) {
      val payload = Arguments.createMap().apply {
        putString("generated_at", nowIso())
        putBoolean("ready", false)
        val status = buildStatusMap()
        putMap("permissions", status.getMap("permissions"))
        putArray("missing_permissions", status.getArray("missing_permissions"))
        putString("status_label", status.getString("status_label"))
        putArray("call_log", Arguments.createArray())
        putArray("sms_threads", Arguments.createArray())
        putArray("review_queue", Arguments.createArray())
        putString("error", error.message ?: error.toString())
      }
      promise.resolve(payload)
    }
  }

  private fun buildStatusMap(permissions: WritableMap = buildPermissionMap()): WritableMap {
    val ready =
        permissions.getString("read_call_log") == "granted" &&
            permissions.getString("read_sms") == "granted"
    return Arguments.createMap().apply {
      putBoolean("ready", ready)
      putMap("permissions", permissions)
      val missing = Arguments.createArray()
      if (permissions.getString("read_call_log") != "granted") {
        missing.pushString("READ_CALL_LOG")
      }
      if (permissions.getString("read_sms") != "granted") {
        missing.pushString("READ_SMS")
      }
      putArray("missing_permissions", missing)
      putString("status_label", if (ready) "Ready" else "Permissions needed")
    }
  }

  private fun buildPermissionMap(): WritableMap {
    return Arguments.createMap().apply {
      putString(
          "read_call_log",
          permissionState(Manifest.permission.READ_CALL_LOG),
      )
      putString(
          "read_sms",
          permissionState(Manifest.permission.READ_SMS),
      )
    }
  }

  private fun permissionState(permission: String): String {
    return when {
      ContextCompat.checkSelfPermission(reactContext, permission) == PackageManager.PERMISSION_GRANTED -> "granted"
      else -> "denied"
    }
  }

  private fun readCallLog(limit: Int): WritableArray {
    val rows = Arguments.createArray()
    val projection =
        arrayOf(
            CallLog.Calls._ID,
            CallLog.Calls.NUMBER,
            CallLog.Calls.CACHED_NAME,
            CallLog.Calls.DATE,
            CallLog.Calls.DURATION,
            CallLog.Calls.TYPE,
            CallLog.Calls.NEW,
            CallLog.Calls.PHONE_ACCOUNT_ID,
        )
    val resolver = reactContext.contentResolver
    val cursor =
        resolver.query(
            CallLog.Calls.CONTENT_URI,
            projection,
            null,
            null,
            "${CallLog.Calls.DATE} DESC",
        )

    cursor?.use {
      var count = 0
      while (it.moveToNext() && count < limit) {
        val row = Arguments.createMap()
        val timestamp = getLong(it, CallLog.Calls.DATE)
        val number = getString(it, CallLog.Calls.NUMBER)
        val cachedName = getString(it, CallLog.Calls.CACHED_NAME)
        val callId = getLong(it, CallLog.Calls._ID)
        val callType = callTypeLabel(getInt(it, CallLog.Calls.TYPE))
        row.putString("kind", "call")
        row.putString("record_id", "call:$callId")
        row.putDouble("timestamp_ms", timestamp.toDouble())
        row.putString("timestamp_iso", formatIso(timestamp))
        row.putString("title", cachedName.ifBlank { number.ifBlank { "Unknown caller" } })
        row.putString(
            "summary",
            listOf(
                    callType,
                    if (number.isNotBlank()) number else null,
                )
                .filterNotNull()
                .joinToString(" • "),
        )
        row.putMap(
            "source",
            Arguments.createMap().apply {
              putString("record_id", "call:$callId")
              putString("number", number)
              putString("cached_name", cachedName)
              putDouble("duration_seconds", getLong(it, CallLog.Calls.DURATION).toDouble())
              putString("type", callType)
              putBoolean("new", getInt(it, CallLog.Calls.NEW) == 1)
              putString("phone_account_id", getString(it, CallLog.Calls.PHONE_ACCOUNT_ID))
            },
        )
        rows.pushMap(row)
        count += 1
      }
    }

    return rows
  }

  private fun readSmsThreads(limit: Int): WritableArray {
    val projection =
        arrayOf(
            Telephony.Sms._ID,
            Telephony.Sms.THREAD_ID,
            Telephony.Sms.ADDRESS,
            Telephony.Sms.DATE,
            Telephony.Sms.TYPE,
            Telephony.Sms.BODY,
            Telephony.Sms.READ,
            Telephony.Sms.SUBJECT,
        )

    val threads = LinkedHashMap<Long, MutableMap<String, Any?>>()
    val cursor =
        reactContext.contentResolver.query(
            Telephony.Sms.CONTENT_URI,
            projection,
            null,
            null,
            "${Telephony.Sms.DATE} DESC",
        )

    cursor?.use {
      while (it.moveToNext()) {
        val threadId = getLong(it, Telephony.Sms.THREAD_ID)
        if (threadId <= 0) {
          continue
        }

        val timestamp = getLong(it, Telephony.Sms.DATE)
        val body = getString(it, Telephony.Sms.BODY)
        val address = getString(it, Telephony.Sms.ADDRESS)
        val subject = getString(it, Telephony.Sms.SUBJECT)
        val messageType = getInt(it, Telephony.Sms.TYPE)
        val read = getInt(it, Telephony.Sms.READ) == 1
        val existing = threads[threadId]

        if (existing == null) {
          threads[threadId] =
              mutableMapOf(
                  "thread_id" to threadId,
                  "timestamp_ms" to timestamp,
                  "timestamp_iso" to formatIso(timestamp),
                  "record_id" to "sms_thread:$threadId:$timestamp",
                  "title" to (address.ifBlank { subject.ifBlank { "SMS thread $threadId" } }),
                  "summary" to smsTypeLabel(messageType),
                  "count" to 1,
                  "unread_count" to if (read) 0 else 1,
                  "source" to
                      mapOf(
                          "record_id" to "sms_thread:$threadId:$timestamp",
                          "address" to address,
                          "subject" to subject,
                          "type" to smsTypeLabel(messageType),
                          "read" to read,
                          "body_preview" to preview(body),
                      ),
              )
        } else {
          existing["count"] = (existing["count"] as Int) + 1
          if (!read) {
            existing["unread_count"] = (existing["unread_count"] as Int) + 1
          }
        }

        if (threads.size >= limit && threads.containsKey(threadId)) {
          // Keep reading so counts stay accurate for already selected threads.
          continue
        }
      }
    }

    val rows = Arguments.createArray()
    threads.values.take(limit).forEach { thread ->
      val source = thread["source"] as Map<*, *>
      rows.pushMap(
          Arguments.createMap().apply {
            putString("kind", "sms_thread")
            putString("record_id", thread["record_id"] as String)
            putDouble("timestamp_ms", (thread["timestamp_ms"] as Long).toDouble())
            putString("timestamp_iso", thread["timestamp_iso"] as String)
            putString("title", thread["title"] as String)
            putString("summary", thread["summary"] as String)
            putDouble("thread_id", (thread["thread_id"] as Long).toDouble())
            putInt("count", thread["count"] as Int)
            putInt("unread_count", thread["unread_count"] as Int)
            putMap(
                "source",
                Arguments.createMap().apply {
                  putString("address", source["address"] as String?)
                  putString("subject", source["subject"] as String?)
                  putString("type", source["type"] as String?)
                  putBoolean("read", source["read"] as Boolean)
                  putString("body_preview", source["body_preview"] as String?)
                },
            )
          },
      )
    }
    return rows
  }

  private fun buildReviewQueue(callLog: WritableArray, smsThreads: WritableArray): WritableArray {
    val combined = mutableListOf<SnapshotItem>()

    for (index in 0 until callLog.size()) {
      val item = callLog.getMap(index) ?: continue
      combined.add(
          SnapshotItem(
              kind = item.getString("kind") ?: "call",
              recordId = item.getString("record_id") ?: "",
              timestampMs = item.getDouble("timestamp_ms").toLong(),
              title = item.getString("title") ?: "Call",
              summary = item.getString("summary") ?: "",
              source = mapOf(
                  "record_id" to item.getMap("source")?.getString("record_id"),
                  "number" to item.getMap("source")?.getString("number"),
                  "cached_name" to item.getMap("source")?.getString("cached_name"),
                  "type" to item.getMap("source")?.getString("type"),
                  "duration_seconds" to item.getMap("source")?.getDouble("duration_seconds"),
                  "new" to item.getMap("source")?.getBoolean("new"),
              ),
          ),
      )
    }

    for (index in 0 until smsThreads.size()) {
      val item = smsThreads.getMap(index) ?: continue
      combined.add(
          SnapshotItem(
              kind = item.getString("kind") ?: "sms_thread",
              recordId = item.getString("record_id") ?: "",
              timestampMs = item.getDouble("timestamp_ms").toLong(),
              title = item.getString("title") ?: "SMS thread",
              summary = item.getString("summary") ?: "",
              source = mapOf(
                  "record_id" to item.getMap("source")?.getString("record_id"),
                  "address" to item.getMap("source")?.getString("address"),
                  "body_preview" to item.getMap("source")?.getString("body_preview"),
                  "thread_id" to item.getDouble("thread_id").toLong(),
                  "type" to item.getMap("source")?.getString("type"),
                  "read" to item.getMap("source")?.getBoolean("read"),
              ),
          ),
      )
    }

    combined.sortByDescending { it.timestampMs }

    val rows = Arguments.createArray()
    combined.forEach { item ->
      rows.pushMap(
          Arguments.createMap().apply {
            putString("kind", item.kind)
            putString("record_id", item.recordId)
            putDouble("timestamp_ms", item.timestampMs.toDouble())
            putString("timestamp_iso", formatIso(item.timestampMs))
            putString("title", item.title)
            putString("summary", item.summary)
            putMap("source", writableMapFromAnyMap(item.source))
          },
      )
    }
    return rows
  }

  private fun writableMapFromAnyMap(values: Map<String, Any?>): WritableMap {
    return Arguments.createMap().apply {
      values.forEach { (key, value) ->
        when (value) {
          null -> putNull(key)
          is String -> putString(key, value)
          is Boolean -> putBoolean(key, value)
          is Int -> putInt(key, value)
          is Long -> putDouble(key, value.toDouble())
          is Double -> putDouble(key, value)
          is Map<*, *> ->
              putMap(
                  key,
                  writableMapFromAnyMap(
                      value.entries.associate { it.key.toString() to it.value },
                  ),
              )
          else -> putString(key, value.toString())
        }
      }
    }
  }

  private fun callTypeLabel(type: Int): String {
    return when (type) {
      CallLog.Calls.INCOMING_TYPE -> "incoming"
      CallLog.Calls.OUTGOING_TYPE -> "outgoing"
      CallLog.Calls.MISSED_TYPE -> "missed"
      CallLog.Calls.VOICEMAIL_TYPE -> "voicemail"
      CallLog.Calls.REJECTED_TYPE -> "rejected"
      CallLog.Calls.BLOCKED_TYPE -> "blocked"
      CallLog.Calls.ANSWERED_EXTERNALLY_TYPE -> "answered_externally"
      else -> "unknown"
    }
  }

  private fun smsTypeLabel(type: Int): String {
    return when (type) {
      Telephony.Sms.MESSAGE_TYPE_INBOX -> "inbox"
      Telephony.Sms.MESSAGE_TYPE_SENT -> "sent"
      Telephony.Sms.MESSAGE_TYPE_DRAFT -> "draft"
      Telephony.Sms.MESSAGE_TYPE_OUTBOX -> "outbox"
      Telephony.Sms.MESSAGE_TYPE_FAILED -> "failed"
      Telephony.Sms.MESSAGE_TYPE_QUEUED -> "queued"
      else -> "unknown"
    }
  }

  private fun getString(cursor: Cursor, columnName: String): String {
    val idx = cursor.getColumnIndex(columnName)
    return if (idx >= 0) cursor.getString(idx).orEmpty() else ""
  }

  private fun getInt(cursor: Cursor, columnName: String): Int {
    val idx = cursor.getColumnIndex(columnName)
    return if (idx >= 0) cursor.getInt(idx) else 0
  }

  private fun getLong(cursor: Cursor, columnName: String): Long {
    val idx = cursor.getColumnIndex(columnName)
    return if (idx >= 0) cursor.getLong(idx) else 0L
  }

  private fun preview(value: String): String {
    val compact = value.trim().replace(Regex("\\s+"), " ")
    return if (compact.length <= BODY_PREVIEW_LIMIT) compact else compact.take(BODY_PREVIEW_LIMIT).trimEnd() + "…"
  }

  private fun nowIso(): String {
    val formatter = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
    formatter.timeZone = TimeZone.getTimeZone("UTC")
    return formatter.format(System.currentTimeMillis())
  }

  private fun formatIso(millis: Long): String {
    val formatter = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
    formatter.timeZone = TimeZone.getTimeZone("UTC")
    return formatter.format(millis)
  }
}
