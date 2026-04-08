# Android Phone Test

Date: 2026-04-07

## Current State

What is ready:

- Expo dependencies are aligned for SDK 52
- mobile assets exist for icon, adaptive icon, and splash
- `mobile/android` has been generated with `expo prebuild --platform android`
- mobile typecheck passes
- relationship ingest, contact import, pending capture, and journal feed are wired

What is still machine-blocked:

- this machine does not have Android SDK tools installed
- `adb` is not present
- `ANDROID_HOME` / `ANDROID_SDK_ROOT` are not set
- Gradle stops at SDK discovery without `mobile/android/local.properties` or SDK env vars

## Verified Commands

From `mobile/`:

```bash
npx expo-doctor
npm run typecheck
npx expo prebuild --platform android
```

From `mobile/android/`:

```bash
./gradlew help
```

`./gradlew help` reached Android/Expo project evaluation and then failed because the SDK path is not configured.

## To Install And Test On Android

1. Install Android Studio or Android command-line tools.
2. Install a platform SDK and build tools compatible with compile SDK 35.
3. Set one of:

```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
```

Or create `mobile/android/local.properties`:

```properties
sdk.dir=/Users/tylersteeves/Library/Android/sdk
```

4. Confirm tools exist:

```bash
adb version
```

5. Re-run the native smoke:

```bash
cd mobile/android
./gradlew help
```

6. Build debug APK:

```bash
./gradlew :app:assembleDebug
```

7. Install to a connected phone:

```bash
adb devices
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## First Device Test Flow

1. Launch the desktop bridge on the Mac.
2. Open the phone app.
3. Pair with the desktop token.
4. Tap `Import Desktop Contacts`.
5. Log one relationship interaction.
6. Pin that relationship from the follow-up queue.
7. Capture one receipt or artifact photo.
8. Confirm the journal updates in LIFO order and the pending queue refreshes.
