#!/vendor/bin/sh
# Read keyboard layout type from traceability partition and set keypad name.
# trace_util r 8 returns: "N layout_name" (e.g. "1 qwerty", "3 qwertz")
# Write the number directly to sysfs to switch input device name.

KL=$(/vendor/bin/trace_util r 8 2>/dev/null)
NUM=${KL%% *}

KL_NODE=

for node in \
    /sys/devices/keypad/kl \
    /sys/devices/platform/keypad/kl \
    /sys/bus/i2c/devices/1-0040/kl
do
    if [ -w "$node" ]; then
        KL_NODE="$node"
        break
    fi
done

if [ -n "$NUM" ] && [ -n "$KL_NODE" ]; then
    echo "$NUM" > "$KL_NODE" || exit 1
    setprop ro.hwf.keypadlanguage "$KL"
fi
