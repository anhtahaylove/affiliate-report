#!/usr/bin/env bash
set -euo pipefail

current="$GITHUB_WORKSPACE/candidate/AffiliateReport-v2.1.0-x86_64-release.apk"
target="$GITHUB_WORKSPACE/candidate/AffiliateReport-v2.1.1-x86_64-release.apk"
package="$RUNNER_TEMP/android-signed-upgrade.affsync"

adb install "$current"
adb shell am start -W -n vn.io.huuhungn.affiliatereport/.MainActivity
adb forward tcp:9876 tcp:8765
ANDROID_LOCAL_TOKEN="$(adb exec-out run-as vn.io.huuhungn.affiliatereport cat files/android-local-token | tr -d '\r\n')"
test "${#ANDROID_LOCAL_TOKEN}" -ge 32
echo "::add-mask::$ANDROID_LOCAL_TOKEN"
export ANDROID_LOCAL_TOKEN
python scripts/ci/android_runtime_smoke.py --phase seed --package "$package" --expected-version 2.1.0
adb install -r "$target"
adb shell am force-stop vn.io.huuhungn.affiliatereport
adb shell am start -W -n vn.io.huuhungn.affiliatereport/.MainActivity
python scripts/ci/android_runtime_smoke.py --phase persist --package "$package" --expected-version 2.1.1
adb shell dumpsys package vn.io.huuhungn.affiliatereport | grep -q 'versionCode=2001001'
