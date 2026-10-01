#!/system/bin/sh
# Temporary diagnostic capture. Does not change HALs, encryption or SELinux mode.
[ "$(getprop ro.debuggable)" = "1" ] || exit 0
if ! awk '$2 == "/cache" && $4 ~ /(^|,)rw(,|$)/ { found=1 } END { exit !found }' /proc/mounts; then
    echo 'keymaster-boot-debug: /cache is not mounted read-write; capture skipped' > /dev/kmsg
    exit 1
fi
umask 077
base=/cache/keymaster-boot-debug
boot_id=$(cat /proc/sys/kernel/random/boot_id)
[ -n "$boot_id" ] || exit 1
run="$base/$boot_id"
mkdir -p "$run" || exit 1
ln -sfn "$boot_id" "$base/latest"
exec >> "$run/logger-status.txt" 2>&1
printf 'Capture start: '
date
id
id -Z
cat /proc/uptime
getprop > "$run/properties-start.txt"
cat /proc/mounts > "$run/mounts-start.txt"
cat /linkerconfig/ld.config.txt > "$run/linkerconfig-start.txt" 2>&1
for libdir in lib lib64; do
    for relative in hw/android.hardware.keymaster@3.0-impl-qti.so \
                    hw/android.hardware.gatekeeper@1.0-impl-qti.so \
                    libkeymasterdeviceutils.so; do
        sha256sum "/vendor/$libdir/$relative"
    done
done > "$run/hal-sha256.txt" 2>&1
logcat -b all -v threadtime -f "$run/logcat.txt" -r 4096 -n 3 \
    > "$run/logcat-status.txt" 2>&1 &
log_pid=$!
cat /dev/kmsg > "$run/kernel.txt" 2> "$run/kernel-status.txt" &
kernel_pid=$!
trap 'kill "$log_pid" "$kernel_pid" 2>/dev/null; sync' EXIT
iteration=0
while [ "$iteration" -lt 36 ]; do
    {
        printf '\n=== State %s: ' "$iteration"
        cat /proc/uptime
        for property in init.svc.keymaster-3-0 init.svc.gatekeeper-1-0 \
                        init.svc.vendor.qseecomd init.svc.vold init.svc.logd \
                        init.svc.bootanim init.svc.zygote sys.boot_completed \
                        vold.decrypt; do
            printf '%s=' "$property"
            getprop "$property"
        done
        ps -A -T | grep -E 'keymaster|gatekeeper|qseecom|vold|logd|bootanim|zygote'
        for executable in android.hardware.keymaster@3.0-service-qti \
                          android.hardware.gatekeeper@1.0-service-qti \
                          qseecomd vold; do
            for proc_id in $(pidof "$executable"); do
                printf '\nPROCESS %s PID %s\n' "$executable" "$proc_id"
                cat "/proc/$proc_id/wchan" "/proc/$proc_id/stack" 2>&1
                for thread in /proc/"$proc_id"/task/*; do
                    printf 'THREAD %s ' "${thread##*/}"
                    cat "$thread/wchan" 2>&1
                done
                if [ "$iteration" -eq 0 ] || [ "$iteration" -eq 6 ]; then
                    cat "/proc/$proc_id/maps" > "$run/maps-$proc_id-$iteration.txt" 2>&1
                fi
            done
        done
    } >> "$run/service-state.txt" 2>&1
    if [ "$iteration" -eq 6 ]; then
        cat /linkerconfig/ld.config.txt > "$run/linkerconfig-later.txt" 2>&1
    fi
    sync
    sleep 5
    iteration=$((iteration + 1))
done
getprop > "$run/properties-end.txt"
printf 'Capture end: '
date
