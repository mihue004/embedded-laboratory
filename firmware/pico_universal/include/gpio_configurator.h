#ifndef GPIO_CONFIGURATOR_H
#define GPIO_CONFIGURATOR_H

#include "device_config.h"

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    GPIO_CONFIG_INPUT = 0,
    GPIO_CONFIG_OUTPUT
} gpio_config_direction_t;

typedef struct {
    bool (*init)(void *context, uint8_t pin);
    bool (*set_pull)(
        void *context,
        uint8_t pin,
        device_gpio_pull_t pull
    );
    bool (*put)(
        void *context,
        uint8_t pin,
        device_gpio_level_t level
    );
    bool (*set_direction)(
        void *context,
        uint8_t pin,
        gpio_config_direction_t direction
    );
} gpio_configurator_ops_t;

bool gpio_configurator_apply(
    const device_config_t *config,
    const gpio_configurator_ops_t *ops,
    void *context
);

#endif
