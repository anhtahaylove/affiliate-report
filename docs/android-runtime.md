# Android local runtime

Affiliate Report for Android is a local-first Capacitor 8.5 container. Chaquopy 17 starts
CPython 3.12 and the existing FastAPI app on `127.0.0.1:8765`; SQLite and user files stay
inside Android internal app storage. The packaged Next.js export is copied into a
versioned internal directory and served by FastAPI, so the browser UI and `/api` calls
remain same-origin.

## Supported build variants

- `arm64Release`: production APK, `arm64-v8a`, requires the four signing environment
  variables below and fails before Gradle configuration if any is missing.
- `ciRelease`: signed `x86_64` fixture used only by the exact-SHA synthetic upgrade gate;
  it is never published as a release asset.
- `ciDebug`: emulator APK, `x86_64`, signed with the normal Android debug key.

Release signing variables:

```text
ANDROID_KEYSTORE_PATH
ANDROID_KEYSTORE_PASSWORD
ANDROID_KEY_ALIAS
ANDROID_KEY_PASSWORD
```

Build on a machine with JDK 21, Android SDK 36 and Python 3.12:

```powershell
pwsh -File scripts/ci/build_android_candidate.ps1 -Variant ciDebug
pwsh -File scripts/ci/build_android_candidate.ps1 -Variant arm64Release
```

The production artifact is written to
`artifacts/android/AffiliateReport-v2.2.0-arm64.apk`. The build script never creates or
falls back to a signing key.

## Storage and lifecycle

- The manifest requests only `INTERNET`, for the in-process loopback server.
- Cleartext traffic is denied except for `127.0.0.1`/`localhost`.
- HTML file inputs use Android's system document picker; downloads from the trusted
  loopback origin open `ACTION_CREATE_DOCUMENT` and are streamed to the selected URI.
- A verified APK served by the trusted loopback API is copied only to `cache/updates`,
  exposed through a read-only `FileProvider` URI and handed to Android's system package
  installer. Android still requires the user to allow this source and confirm installation.
- Android Back navigates WebView history, then backgrounds the app at the root.
- The Python runtime starts once per process from `Application.onCreate`, so Activity
  recreation does not create a second database/server.

## Android dependency boundary

Chaquopy's CPython 3.12 repository currently provides `pandas 2.1.3` and
`cryptography 42.0.8`, so `requirements-android.txt` pins those versions. Pydantic-core
does not provide an Android wheel; Android therefore uses Pydantic 1.10 with a small
source-compatible API shim in the shared core. Desktop-only packages (`pystray`,
`psycopg`, OIDC/Authlib and `uvicorn[standard]`) are intentionally excluded.

## Official references

- [Chaquopy version matrix](https://chaquo.com/chaquopy/doc/current/versions.html)
- [Chaquopy Gradle and Python configuration](https://chaquo.com/chaquopy/doc/current/android.html)
- [Capacitor Android](https://capacitorjs.com/docs/android)
- [Capacitor app lifecycle and Back behavior](https://capacitorjs.com/docs/apis/app)
- [Android Storage Access Framework](https://developer.android.com/training/data-storage/shared/documents-files)
