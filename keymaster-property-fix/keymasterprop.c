// SPDX-License-Identifier: Apache-2.0
#include <cutils/properties.h>
#include <string.h>

// Only the stock utility's renamed import calls this function.
int km_prop_get(const char *key, char *value, const char *default_value) {
    if (key != NULL && strcmp(key, "sys.listeners.registered") == 0) {
        key = "vendor.sys.listeners.registered";
    }
    return property_get(key, value, default_value);
}
