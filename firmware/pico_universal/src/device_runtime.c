#include "device_runtime.h"

#include <stddef.h>

resource_status_t device_runtime_apply_config(
    resource_manager_t *manager,
    const device_config_t *config,
    device_runtime_hardware_apply_fn hardware_apply,
    void *context
)
{
    if (manager == NULL || config == NULL || hardware_apply == NULL) {
        return RESOURCE_INVALID_ARGUMENT;
    }

    if (!device_config_validate(config)) {
        return RESOURCE_INVALID_CONFIG;
    }

    resource_manager_t next = *manager;

    resource_status_t status =
        resource_manager_apply_config(&next, config);

    if (status != RESOURCE_OK) {
        return status;
    }

    if (!hardware_apply(config, context)) {
        return RESOURCE_HARDWARE_ERROR;
    }

    *manager = next;
    return RESOURCE_OK;
}
