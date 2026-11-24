
#ifndef DEVICE_CONFIG_H
#define DEVICE_CONFIG_H

#include <stdbool.h>
#include <stdint.h>

#define DEVICE_CONFIG_VERSION 5
#define DEVICE_GPIO_COUNT 30

#define DEVICE_PIO_PRIORITY_MIN 0
#define DEVICE_PIO_PRIORITY_MAX 3

#define DEVICE_INPUT_FILTER_MAX_US 1000000

typedef enum {
    DEVICE_UART_PARITY_NONE = 0,
    DEVICE_UART_PARITY_EVEN,
    DEVICE_UART_PARITY_ODD
} device_uart_parity_t;

typedef struct {
    uint32_t baudrate;
} device_i2c_config_t;

typedef struct {
    uint32_t baudrate;
    uint8_t data_bits;
    uint8_t cpol;
    uint8_t cpha;
    bool lsb_first;
} device_spi_config_t;

typedef struct {
    uint32_t baudrate;
    uint8_t data_bits;
    uint8_t stop_bits;
    device_uart_parity_t parity;
} device_uart_config_t;

typedef struct {
    device_i2c_config_t i2c[2];
    device_spi_config_t spi[2];
    device_uart_config_t uart[2];
} device_peripheral_config_t;

typedef enum {
    PIN_UNUSED = 0,
    PIN_GPIO_INPUT,
    PIN_GPIO_OUTPUT,
    PIN_SIGNAL_GENERATOR,
    PIN_SIGNAL_ANALYZER,
    PIN_I2C_SDA,
    PIN_I2C_SCL,
    PIN_SPI_RX,
    PIN_SPI_TX,
    PIN_SPI_SCK,
    PIN_SPI_CS,
    PIN_UART_TX,
    PIN_UART_RX,
    PIN_ADC_INPUT = 13
} device_pin_function_t;

typedef enum {
    GPIO_PULL_NONE = 0,
    GPIO_PULL_UP,
    GPIO_PULL_DOWN
} device_gpio_pull_t;

typedef enum {
    GPIO_LEVEL_LOW = 0,
    GPIO_LEVEL_HIGH
} device_gpio_level_t;

typedef struct {
    device_pin_function_t function;
    uint8_t peripheral_instance;
    uint8_t pio_priority;

    device_gpio_pull_t pull;
    device_gpio_level_t initial_level;
    uint32_t input_filter_us;
} device_pin_config_t;

typedef struct {
    uint32_t config_version;
    device_pin_config_t pins[DEVICE_GPIO_COUNT];
    device_peripheral_config_t peripherals;
} device_config_t;

void device_config_init(device_config_t *config);
bool device_config_validate(const device_config_t *config);

#endif
