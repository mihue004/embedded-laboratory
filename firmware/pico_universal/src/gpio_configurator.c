#include "gpio_configurator.h"
#include <stddef.h>

static bool configure_pin(
    uint8_t pin,
    const device_pin_config_t *entry,
    const gpio_configurator_ops_t *ops,
    void *context
)
{
    gpio_config_direction_t direction;

    switch (entry->function) {
    case PIN_GPIO_INPUT:
    case PIN_SIGNAL_ANALYZER:
        direction = GPIO_CONFIG_INPUT;
        break;

    case PIN_GPIO_OUTPUT:
    case PIN_SIGNAL_GENERATOR:
        direction = GPIO_CONFIG_OUTPUT;
        break;

    default:
        return true;
    }

    if (!ops->init(context, pin)) {
        return false;
    }

    if (!ops->set_pull(context, pin, entry->pull)) {
        return false;
    }

    /*
     * Set the output level before enabling output direction
     * to avoid an unintended transition during initialization.
     */
    if (direction == GPIO_CONFIG_OUTPUT) {
        if (!ops->put(context, pin, entry->initial_level)) {
            return false;
        }
    }

    return ops->set_direction(context, pin, direction);
}

bool gpio_configurator_apply(
    const device_config_t *config,
    const gpio_configurator_ops_t *ops,
    void *context
)
{
    if (!device_config_validate(config) ||
        ops == NULL ||
        ops->init == NULL ||
        ops->set_pull == NULL ||
        ops->put == NULL ||
        ops->set_direction == NULL) {
        return false;
    }

    for (uint8_t pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        if (!configure_pin(
                pin,
                &config->pins[pin],
                ops,
                context)) {
            return false;
        }
    }

    return true;
}
