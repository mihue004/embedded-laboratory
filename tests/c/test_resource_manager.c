#include "device_config.h"
#include "resource_manager.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void test_config_validation(void)
{
    device_config_t config;
    device_config_init(&config);

    assert(device_config_validate(&config));

    config.config_version++;
    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = (device_pin_function_t)-1;
    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = (device_pin_function_t)99;
    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].pio_priority = 4;
    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[23].function = PIN_GPIO_INPUT;
    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = PIN_SIGNAL_GENERATOR;
    assert(device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = PIN_GPIO_INPUT;
    config.pins[0].peripheral_instance = 1;
    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = PIN_SIGNAL_GENERATOR;
    config.pins[0].peripheral_instance = 1;
    assert(!device_config_validate(&config));
}

static void test_i2c_mappings(void)
{
    device_config_t config;
    resource_manager_t manager;

    device_config_init(&config);
    resource_manager_init(&manager);

    config.pins[0].function = PIN_I2C_SDA;
    config.pins[1].function = PIN_I2C_SCL;

    assert(resource_manager_apply_config(&manager, &config) == RESOURCE_OK);
    assert(resource_manager_gpio_is_reserved(&manager, 0));
    assert(resource_manager_gpio_is_reserved(&manager, 1));

    device_config_init(&config);
    config.pins[2].function = PIN_I2C_SDA;
    config.pins[3].function = PIN_I2C_SCL;
    config.pins[2].peripheral_instance = 1;
    config.pins[3].peripheral_instance = 1;

    assert(resource_manager_apply_config(&manager, &config) == RESOURCE_OK);

    /* GPIO 1 is I2C0 SCL, not I2C0 SDA. */
    device_config_init(&config);
    config.pins[1].function = PIN_I2C_SDA;
    config.pins[0].function = PIN_I2C_SCL;

    assert(resource_manager_apply_config(&manager, &config) ==
           RESOURCE_INVALID_PIN_MAPPING);

    /* SDA without SCL is incomplete. */
    device_config_init(&config);
    config.pins[0].function = PIN_I2C_SDA;

    assert(resource_manager_apply_config(&manager, &config) ==
           RESOURCE_INCOMPLETE_I2C);
}

static void test_spi_mappings(void)
{
    device_config_t config;
    resource_manager_t manager;

    device_config_init(&config);
    resource_manager_init(&manager);

    config.pins[0].function = PIN_SPI_RX;
    config.pins[1].function = PIN_SPI_CS;
    config.pins[2].function = PIN_SPI_SCK;
    config.pins[3].function = PIN_SPI_TX;

    assert(resource_manager_apply_config(&manager, &config) == RESOURCE_OK);

    device_config_init(&config);
    config.pins[8].function = PIN_SPI_RX;
    config.pins[9].function = PIN_SPI_CS;
    config.pins[10].function = PIN_SPI_SCK;
    config.pins[11].function = PIN_SPI_TX;

    for (unsigned int pin = 8; pin <= 11; pin++) {
        config.pins[pin].peripheral_instance = 1;
    }

    assert(resource_manager_apply_config(&manager, &config) == RESOURCE_OK);

    /* GPIO 1 supports SPI0 CS, but not SPI0 RX. */
    device_config_init(&config);
    config.pins[1].function = PIN_SPI_RX;
    config.pins[2].function = PIN_SPI_SCK;

    assert(resource_manager_apply_config(&manager, &config) ==
           RESOURCE_INVALID_PIN_MAPPING);

    /* SCK without RX or TX is incomplete. */
    device_config_init(&config);
    config.pins[2].function = PIN_SPI_SCK;

    assert(resource_manager_apply_config(&manager, &config) ==
           RESOURCE_INCOMPLETE_SPI);
}

static void test_uart_mappings(void)
{
    device_config_t config;
    resource_manager_t manager;

    device_config_init(&config);
    resource_manager_init(&manager);

    config.pins[0].function = PIN_UART_TX;
    config.pins[1].function = PIN_UART_RX;

    assert(resource_manager_apply_config(&manager, &config) == RESOURCE_OK);

    device_config_init(&config);
    config.pins[4].function = PIN_UART_TX;
    config.pins[5].function = PIN_UART_RX;
    config.pins[4].peripheral_instance = 1;
    config.pins[5].peripheral_instance = 1;

    assert(resource_manager_apply_config(&manager, &config) == RESOURCE_OK);

    /* GPIO 1 supports UART0 RX, not UART0 TX. */
    device_config_init(&config);
    config.pins[1].function = PIN_UART_TX;

    assert(resource_manager_apply_config(&manager, &config) ==
           RESOURCE_INVALID_PIN_MAPPING);

    /* TX-only UART configuration is intentionally allowed. */
    device_config_init(&config);
    config.pins[0].function = PIN_UART_TX;

    assert(resource_manager_apply_config(&manager, &config) == RESOURCE_OK);
}

static void test_duplicate_peripheral_functions(void)
{
    device_config_t config;

    device_config_init(&config);
    config.pins[0].function = PIN_I2C_SDA;
    config.pins[4].function = PIN_I2C_SDA;

    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = PIN_SPI_RX;
    config.pins[4].function = PIN_SPI_RX;

    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = PIN_UART_TX;
    config.pins[2].function = PIN_UART_TX;

    assert(!device_config_validate(&config));
}

static void test_atomic_config_apply(void)
{
    device_config_t config;
    resource_manager_t manager;
    resource_manager_t before;

    device_config_init(&config);
    resource_manager_init(&manager);

    config.pins[0].function = PIN_GPIO_OUTPUT;

    assert(resource_manager_apply_config(&manager, &config) == RESOURCE_OK);

    before = manager;

    device_config_init(&config);
    config.pins[0].function = PIN_I2C_SDA;

    assert(resource_manager_apply_config(&manager, &config) ==
           RESOURCE_INCOMPLETE_I2C);

    assert(memcmp(&manager, &before, sizeof(manager)) == 0);
}

static void test_gpio_priority_and_pio_claims(void)
{
    device_config_t config;
    resource_manager_t manager;
    uint8_t pin = 255;

    device_config_init(&config);
    resource_manager_init(&manager);

    config.pins[2].pio_priority = 1;
    config.pins[5].pio_priority = 3;
    config.pins[7].pio_priority = 3;

    assert(resource_manager_apply_config(&manager, &config) == RESOURCE_OK);

    assert(resource_manager_get_free_gpio(&manager, 0, &pin));
    assert(pin == 5);

    assert(resource_manager_get_free_gpio(&manager, 1, &pin));
    assert(pin == 7);

    assert(resource_manager_claim_pio_gpio(&manager, 5));
    assert(resource_manager_gpio_is_reserved(&manager, 5));
    assert(!resource_manager_gpio_is_available(&manager, 5));

    assert(resource_manager_release_pio_gpio(&manager, 5));
    assert(resource_manager_gpio_is_available(&manager, 5));

    assert(!resource_manager_release_pio_gpio(&manager, 5));
}

static void test_pio_state_machines(void)
{
    resource_manager_t manager;
    uint8_t blocks[RESOURCE_PIO_SM_COUNT];
    uint8_t machines[RESOURCE_PIO_SM_COUNT];

    resource_manager_init(&manager);

    for (unsigned int i = 0; i < RESOURCE_PIO_SM_COUNT; i++) {
        assert(resource_manager_allocate_pio_sm(
            &manager, &blocks[i], &machines[i]
        ));

        assert(blocks[i] < RESOURCE_PIO_BLOCK_COUNT);
        assert(machines[i] < RESOURCE_PIO_SM_PER_BLOCK);
    }

    uint8_t block;
    uint8_t machine;

    assert(!resource_manager_allocate_pio_sm(
        &manager, &block, &machine
    ));

    for (unsigned int i = 0; i < RESOURCE_PIO_SM_COUNT; i++) {
        assert(resource_manager_release_pio_sm(
            &manager, blocks[i], machines[i]
        ));
    }

    assert(resource_manager_allocate_pio_sm(
        &manager, &block, &machine
    ));
}

static void test_pio_claims_survive_config_updates(void)
{
    device_config_t config;
    resource_manager_t manager;

    device_config_init(&config);
    resource_manager_init(&manager);

    assert(resource_manager_apply_config(&manager, &config) == RESOURCE_OK);
    assert(resource_manager_claim_pio_gpio(&manager, 5));

    /* Unrelated configuration changes must preserve the PIO claim. */
    config.pins[2].function = PIN_GPIO_OUTPUT;

    assert(resource_manager_apply_config(&manager, &config) == RESOURCE_OK);
    assert(resource_manager_gpio_is_reserved(&manager, 5));

    /* A claimed PIO pin cannot be assigned to a peripheral. */
    config.pins[5].function = PIN_UART_RX;
    config.pins[5].peripheral_instance = 1;

    assert(resource_manager_apply_config(&manager, &config) ==
           RESOURCE_GPIO_IN_USE);

    /* Failed update must leave the manager unchanged. */
    assert(resource_manager_gpio_is_reserved(&manager, 5));
    assert(!resource_manager_gpio_is_available(&manager, 5));

    assert(resource_manager_release_pio_gpio(&manager, 5));
}

static void test_signal_pins_are_reserved(void)
{
    device_config_t config;
    resource_manager_t manager;

    device_config_init(&config);
    resource_manager_init(&manager);

    config.pins[4].function = PIN_SIGNAL_GENERATOR;

    config.pins[5].function = PIN_SIGNAL_ANALYZER;

    assert(resource_manager_apply_config(
        &manager, &config
    ) == RESOURCE_OK);

    assert(resource_manager_gpio_is_reserved(&manager, 4));
    assert(resource_manager_gpio_is_reserved(&manager, 5));

    assert(!resource_manager_gpio_is_available(&manager, 4));
    assert(!resource_manager_gpio_is_available(&manager, 5));

    assert(!resource_manager_claim_pio_gpio(&manager, 4));
    assert(!resource_manager_claim_pio_gpio(&manager, 5));
}


static void test_gpio_electrical_config(void)
{
    device_config_t config;

    device_config_init(&config);
    config.pins[0].function = PIN_GPIO_INPUT;
    config.pins[0].pull = GPIO_PULL_UP;
    config.pins[0].input_filter_us = 1000;
    assert(device_config_validate(&config));

    device_config_init(&config);
    config.pins[1].function = PIN_GPIO_OUTPUT;
    config.pins[1].pull = GPIO_PULL_DOWN;
    config.pins[1].initial_level = GPIO_LEVEL_HIGH;
    assert(device_config_validate(&config));

    device_config_init(&config);
    config.pins[2].function = PIN_SIGNAL_ANALYZER;
    config.pins[2].pull = GPIO_PULL_UP;
    assert(device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = PIN_GPIO_INPUT;
    config.pins[0].pull = (device_gpio_pull_t)99;
    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = PIN_GPIO_INPUT;
    config.pins[0].input_filter_us = DEVICE_INPUT_FILTER_MAX_US + 1;
    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = PIN_GPIO_INPUT;
    config.pins[0].initial_level = GPIO_LEVEL_HIGH;
    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = PIN_GPIO_OUTPUT;
    config.pins[0].input_filter_us = 100;
    assert(!device_config_validate(&config));

    device_config_init(&config);
    config.pins[0].function = PIN_SIGNAL_ANALYZER;
    config.pins[0].input_filter_us = 100;
    assert(device_config_validate(&config));
}

int main(void)
{
    test_config_validation();
    test_gpio_electrical_config();
    test_i2c_mappings();
    test_spi_mappings();
    test_uart_mappings();
    test_duplicate_peripheral_functions();
    test_atomic_config_apply();
    test_gpio_priority_and_pio_claims();
    test_pio_state_machines();
    test_pio_claims_survive_config_updates();
    test_signal_pins_are_reserved();

    puts("All resource manager tests passed.");
    return 0;
}
