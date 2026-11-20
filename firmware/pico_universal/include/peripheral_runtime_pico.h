#ifndef PERIPHERAL_RUNTIME_PICO_H
#define PERIPHERAL_RUNTIME_PICO_H

#include <stdbool.h>
#include "resource_manager.h"

bool peripheral_runtime_init_pico(const device_config_t *config);
void peripheral_runtime_reset_pico(const resource_manager_t *manager);

#endif
