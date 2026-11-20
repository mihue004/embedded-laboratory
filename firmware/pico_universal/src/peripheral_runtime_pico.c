#include "peripheral_runtime_pico.h"

#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "hardware/spi.h"
#include "hardware/uart.h"

#include <stdbool.h>

#define DEFAULT_I2C_BAUDRATE  100000u
#define DEFAULT_SPI_BAUDRATE 1000000u
#define DEFAULT_UART_BAUDRATE 115200u

static bool has_function(
    const device_config_t *config,
    device_pin_function_t first,
    device_pin_function_t second,
    uint8_t instance)
{
    for (unsigned int pin = 0; pin < DEVICE_GPIO_COUNT; ++pin) {
        const device_pin_config_t *entry = &config->pins[pin];

        if (entry->peripheral_instance == instance &&
            (entry->function == first || entry->function == second)) {
            return true;
        }
    }

    return false;
}

static bool init_i2c(const device_config_t *config, unsigned int instance)
{
    bool used = has_function(config, PIN_I2C_SDA, PIN_I2C_SCL, instance);

    if (!used) {
        return true;
    }

    i2c_inst_t *i2c = instance == 0 ? i2c0 : i2c1;

    i2c_init(i2c, config->peripherals.i2c[instance].baudrate);

    return true;
}

static bool init_spi(const device_config_t *config, unsigned int instance)
{
    bool used = has_function(config, PIN_SPI_RX, PIN_SPI_TX, instance) ||
                has_function(config, PIN_SPI_SCK, PIN_SPI_CS, instance);

    if (!used) {
        return true;
    }

    spi_inst_t *spi = instance == 0 ? spi0 : spi1;
    const device_spi_config_t *settings =
        &config->peripherals.spi[instance];

    spi_init(spi, settings->baudrate);

    spi_set_format(
        spi,
        settings->data_bits,
        settings->cpol ? SPI_CPOL_1 : SPI_CPOL_0,
        settings->cpha ? SPI_CPHA_1 : SPI_CPHA_0,
        settings->lsb_first ? SPI_LSB_FIRST : SPI_MSB_FIRST
    );

    return true;
}

static bool init_uart(const device_config_t *config, unsigned int instance)
{
    bool used = has_function(config, PIN_UART_TX, PIN_UART_RX, instance);

    if (!used) {
        return true;
    }

    uart_inst_t *uart = instance == 0 ? uart0 : uart1;
    const device_uart_config_t *settings =
        &config->peripherals.uart[instance];

    uart_init(uart, settings->baudrate);

    uart_set_format(
        uart,
        settings->data_bits,
        settings->stop_bits,
        settings->parity == DEVICE_UART_PARITY_EVEN ? UART_PARITY_EVEN :
        settings->parity == DEVICE_UART_PARITY_ODD ? UART_PARITY_ODD :
        UART_PARITY_NONE
    );

    return true;
}

bool peripheral_runtime_init_pico(const device_config_t *config)
{
    if (config == NULL) {
        return false;
    }

    for (unsigned int instance = 0; instance < 2; ++instance) {
        if (!init_i2c(config, instance) ||
            !init_spi(config, instance) ||
            !init_uart(config, instance)) {
            return false;
        }
    }

    return true;
}

void peripheral_runtime_reset_pico(const resource_manager_t *manager)
{
    if (manager == NULL) {
        return;
    }

    for (unsigned int instance = 0; instance < 2; ++instance) {
        if (manager->i2c_instance_mask & (1u << instance)) {
            i2c_deinit(instance == 0 ? i2c0 : i2c1);
        }

        if (manager->spi_instance_mask & (1u << instance)) {
            spi_deinit(instance == 0 ? spi0 : spi1);
        }

        if (manager->uart_instance_mask & (1u << instance)) {
            uart_deinit(instance == 0 ? uart0 : uart1);
        }
    }
}
