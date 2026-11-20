#include "device_runtime_pico.h"

#include "device_runtime.h"
#include "gpio_configurator_pico.h"
#include "pio_runtime_pico.h"
#include "peripheral_runtime_pico.h"

#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "hardware/spi.h"
#include "hardware/uart.h"

#define DEFAULT_I2C_BAUDRATE 100000u
#define DEFAULT_SPI_BAUDRATE 1000000u
#define DEFAULT_UART_BAUDRATE 115200u

static bool is_peripheral_pin(device_pin_function_t function)
{
    switch (function) {
    case PIN_I2C_SDA:
    case PIN_I2C_SCL:
    case PIN_SPI_RX:
    case PIN_SPI_TX:
    case PIN_SPI_SCK:
    case PIN_SPI_CS:
    case PIN_UART_TX:
    case PIN_UART_RX:
        return true;
    default:
        return false;
    }
}

static void reset_previous_peripherals(
    const resource_manager_t *previous
)
{
    for (uint8_t pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        const resource_gpio_t *gpio = &previous->gpio[pin];

        if (!gpio->pio_claimed &&
            is_peripheral_pin(gpio->function)) {
            gpio_set_function(pin, GPIO_FUNC_SIO);
        }
    }
}

static bool apply_hardware_config(
    const device_config_t *config,
    void *context
)
{
    const resource_manager_t *previous = context;

    reset_previous_peripherals(previous);
    peripheral_runtime_reset_pico(previous);

    if (!gpio_configurator_apply_pico(config)) {
        return false;
    }

    return peripheral_runtime_init_pico(config);
}

resource_status_t device_runtime_apply_config_pico(
    resource_manager_t *manager,
    const device_config_t *config
)
{
    if (manager == NULL || config == NULL) {
        return RESOURCE_INVALID_ARGUMENT;
    }

    if (!device_config_validate(config)) {
        return RESOURCE_INVALID_CONFIG;
    }

    if (!pio_runtime_sync_pico(manager)) {
        return RESOURCE_HARDWARE_ERROR;
    }

    return device_runtime_apply_config(
        manager,
        config,
        apply_hardware_config,
        manager
    );
}
