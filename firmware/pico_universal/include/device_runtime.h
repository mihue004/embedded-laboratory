#ifndef DEVICE_RUNTIME_H
#define DEVICE_RUNTIME_H

#include "resource_manager.h"

typedef bool (*device_runtime_hardware_apply_fn)(
    const device_config_t *config,
    void *context
);

resource_status_t device_runtime_apply_config(
    resource_manager_t *manager,
    const device_config_t *config,
    device_runtime_hardware_apply_fn hardware_apply,
    void *context
);

#endif
