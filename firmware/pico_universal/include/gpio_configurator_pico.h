#ifndef GPIO_CONFIGURATOR_PICO_H
#define GPIO_CONFIGURATOR_PICO_H

#include "device_config.h"

#include <stdbool.h>

bool gpio_configurator_apply_pico(const device_config_t *config);

#endif
