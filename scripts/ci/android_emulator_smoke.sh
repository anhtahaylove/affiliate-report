#!/usr/bin/env bash
set -euo pipefail

api_level="${1:?Android API level is required}"
apk="$GITHUB_WORKSPACE/candidate/AffiliateReport-v2.1.0-x86_64-debug.apk"
package="$RUNNER_TEMP/android-${api_level}.affsync"

read_token() {
  ANDROID_LOCAL_TOKEN="$(adb exec-out run-as vn.io.huuhungn.affiliatereport cat files/android-local-token | tr -d '\r\n')"
  test "${#ANDROID_LOCAL_TOKEN}" -ge 32
  echo "::add-mask::$ANDROID_LOCAL_TOKEN"
  export ANDROID_LOCAL_TOKEN
}

adb install -r "$apk"
adb shell am start -W -n vn.io.huuhungn.affiliatereport/.MainActivity
adb forward tcp:9876 tcp:8765
read_token
python scripts/ci/android_runtime_smoke.py --phase seed --package "$package"
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 1
sleep 2
python scripts/ci/android_runtime_smoke.py --phase persist --package "$package"
adb shell am force-stop vn.io.huuhungn.affiliatereport
adb shell am start -W -n vn.io.huuhungn.affiliatereport/.MainActivity
python scripts/ci/android_runtime_smoke.py --phase persist --package "$package"
adb shell pm clear vn.io.huuhungn.affiliatereport
adb shell am start -W -n vn.io.huuhungn.affiliatereport/.MainActivity
read_token
python scripts/ci/android_runtime_smoke.py --phase restore --package "$package"
adb shell pidof vn.io.huuhungn.affiliatereport
