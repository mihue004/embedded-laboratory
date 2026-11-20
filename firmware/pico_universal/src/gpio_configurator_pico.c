#include "gpio_configurator_pico.h"
#include "gpio_configurator.h"

#include "hardware/gpio.h"

static bool pico_gpio_init(void *context, uint8_t pin)
{
    (void)context;
    gpio_init(pin);
    return true;
}

static bool pico_gpio_set_pull(
    void *context,
    uint8_t pin,
    device_gpio_pull_t pull
)
{
    (void)context;

    switch (pull) {
    case GPIO_PULL_NONE:
        gpio_set_pulls(pin, false, false);
        return true;
    case GPIO_PULL_UP:
        gpio_set_pulls(pin, true, false);
        return true;
    case GPIO_PULL_DOWN:
        gpio_set_pulls(pin, false, true);
        return true;
    default:
        return false;
    }
}

static bool pico_gpio_put(
    void *context,
    uint8_t pin,
    device_gpio_level_t level
)
{
    (void)context;

    if (level != GPIO_LEVEL_LOW && level != GPIO_LEVEL_HIGH) {
        return false;
    }

    gpio_put(pin, level == GPIO_LEVEL_HIGH);
    return true;
}

static bool pico_gpio_set_direction(
    void *context,
    uint8_t pin,
    gpio_config_direction_t direction
)
{
    (void)context;

    if (direction != GPIO_CONFIG_INPUT &&
        direction != GPIO_CONFIG_OUTPUT) {
        return false;
    }

    gpio_set_dir(pin, direction == GPIO_CONFIG_OUTPUT);
    return true;
}

static bool configure_peripheral_pins(const device_config_t *config)
{
    for (uint8_t pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        const device_pin_config_t *entry = &config->pins[pin];

        if (entry->peripheral_instance > 1) {
            switch (entry->function) {
            case PIN_I2C_SDA:
            case PIN_I2C_SCL:
            case PIN_SPI_RX:
            case PIN_SPI_TX:
            case PIN_SPI_SCK:
            case PIN_SPI_CS:
            case PIN_UART_TX:
            case PIN_UART_RX:
                return false;
            default:
                break;
            }
        }

        gpio_function_t function;

        switch (entry->function) {
        case PIN_I2C_SDA:
        case PIN_I2C_SCL:
            function = GPIO_FUNC_I2C;
            break;

        case PIN_SPI_RX:
        case PIN_SPI_TX:
        case PIN_SPI_SCK:
        case PIN_SPI_CS:
            function = GPIO_FUNC_SPI;
            break;

        case PIN_UART_TX:
        case PIN_UART_RX:
            function = GPIO_FUNC_UART;
            break;

        default:
            continue;
        }

        if (!pico_gpio_set_pull(NULL, pin, entry->pull)) {
            return false;
        }

        gpio_set_function(pin, function);
    }

    return true;
}

bool gpio_configurator_apply_pico(const device_config_t *config)
{
    static const gpio_configurator_ops_t ops = {
        .init = pico_gpio_init,
        .set_pull = pico_gpio_set_pull,
        .put = pico_gpio_put,
        .set_direction = pico_gpio_set_direction
    };

    if (!gpio_configurator_apply(config, &ops, NULL)) {
        return false;
    }

    return configure_peripheral_pins(config);
}
