#ifndef DEVICE_RUNTIME_PICO_H
#define DEVICE_RUNTIME_PICO_H

#include "resource_manager.h"

resource_status_t device_runtime_apply_config_pico(
    resource_manager_t *manager,
    const device_config_t *config
);

#endif
