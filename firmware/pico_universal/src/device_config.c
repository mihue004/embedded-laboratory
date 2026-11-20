
#include "device_config.h"

#include <stddef.h>
#include <string.h>

static bool valid_gpio(unsigned int pin)
{
    return pin <= 22 || (pin >= 26 && pin <= 28);
}

static bool uses_peripheral(device_pin_function_t function)
{
    return function == PIN_I2C_SDA ||
           function == PIN_I2C_SCL ||
           function == PIN_SPI_RX ||
           function == PIN_SPI_TX ||
           function == PIN_SPI_SCK ||
           function == PIN_SPI_CS ||
           function == PIN_UART_TX ||
           function == PIN_UART_RX;
}

void device_config_init(device_config_t *config)
{
    if (config == NULL) {
        return;
    }

    memset(config, 0, sizeof(*config));
    config->config_version = DEVICE_CONFIG_VERSION;

    for (unsigned int i = 0; i < 2; ++i) {
        config->peripherals.i2c[i].baudrate = 100000u;

        config->peripherals.spi[i].baudrate = 1000000u;
        config->peripherals.spi[i].data_bits = 8;
        config->peripherals.spi[i].cpol = 0;
        config->peripherals.spi[i].cpha = 0;
        config->peripherals.spi[i].lsb_first = false;

        config->peripherals.uart[i].baudrate = 115200u;
        config->peripherals.uart[i].data_bits = 8;
        config->peripherals.uart[i].stop_bits = 1;
        config->peripherals.uart[i].parity = DEVICE_UART_PARITY_NONE;
    }
}

bool device_config_validate(const device_config_t *config)
{
    if (config == NULL ||
        config->config_version != DEVICE_CONFIG_VERSION) {
        return false;
    }

    for (unsigned int pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        const device_pin_config_t *entry = &config->pins[pin];

        if ((int)entry->function < (int)PIN_UNUSED ||
            (int)entry->function > (int)PIN_UART_RX) {
            return false;
        }

        if (entry->pio_priority > DEVICE_PIO_PRIORITY_MAX ||
            entry->pull > GPIO_PULL_DOWN ||
            entry->initial_level > GPIO_LEVEL_HIGH ||
            entry->input_filter_us > DEVICE_INPUT_FILTER_MAX_US) {
            return false;
        }

        if (!valid_gpio(pin)) {
            if (entry->function != PIN_UNUSED ||
                entry->pio_priority != DEVICE_PIO_PRIORITY_MIN ||
                entry->pull != GPIO_PULL_NONE ||
                entry->initial_level != GPIO_LEVEL_LOW ||
                entry->input_filter_us != 0) {
                return false;
            }
        }

        if (entry->function == PIN_SIGNAL_GENERATOR) {
            if (entry->peripheral_instance != 0 ||
                entry->initial_level != GPIO_LEVEL_LOW ||
                entry->input_filter_us != 0) {
                return false;
            }
        } else {
            if (!uses_peripheral(entry->function) &&
                entry->peripheral_instance != 0) {
                return false;
            }
        }

        if (entry->function != PIN_GPIO_INPUT &&
            entry->function != PIN_SIGNAL_ANALYZER &&
            entry->input_filter_us != 0) {
            return false;
        }

        if (entry->function != PIN_GPIO_OUTPUT &&
            entry->initial_level != GPIO_LEVEL_LOW) {
            return false;
        }

        if (uses_peripheral(entry->function) &&
            entry->peripheral_instance > 1) {
            return false;
        }

        for (unsigned int other = pin + 1;
             other < DEVICE_GPIO_COUNT; other++) {
            const device_pin_config_t *candidate =
                &config->pins[other];

            if (entry->function == PIN_UNUSED ||
                entry->function != candidate->function ||
                entry->peripheral_instance !=
                    candidate->peripheral_instance) {
                continue;
            }

            if (uses_peripheral(entry->function)) {
                return false;
            }
        }
    }

    for (unsigned int i = 0; i < 2; ++i) {
        const device_peripheral_config_t *p = &config->peripherals;

        if (p->i2c[i].baudrate == 0 ||
            p->i2c[i].baudrate > 1000000u) {
            return false;
        }

        if (p->spi[i].baudrate == 0 ||
            p->spi[i].data_bits < 4 ||
            p->spi[i].data_bits > 16 ||
            p->spi[i].cpol > 1 ||
            p->spi[i].cpha > 1) {
            return false;
        }

        if (p->uart[i].baudrate == 0 ||
            p->uart[i].data_bits < 5 ||
            p->uart[i].data_bits > 8 ||
            (p->uart[i].stop_bits != 1 &&
             p->uart[i].stop_bits != 2) ||
            p->uart[i].parity > DEVICE_UART_PARITY_ODD) {
            return false;
        }
    }

    return true;
}
