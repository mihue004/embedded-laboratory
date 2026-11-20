
#include "resource_manager.h"

#include <stddef.h>
#include <string.h>

static bool valid_gpio(unsigned int pin)
{
    return pin <= 22 || (pin >= 26 && pin <= 28);
}

static bool pin_in_list(
    unsigned int pin,
    const uint8_t *pins,
    size_t count
)
{
    for (size_t i = 0; i < count; i++) {
        if (pin == pins[i]) {
            return true;
        }
    }

    return false;
}

static bool pin_supports_spi(
    unsigned int pin,
    device_pin_function_t function,
    uint8_t instance
)
{
    static const uint8_t spi0_rx[]  = {0, 4, 16, 20};
    static const uint8_t spi0_cs[]  = {1, 5, 17, 21};
    static const uint8_t spi0_sck[] = {2, 6, 18, 22};
    static const uint8_t spi0_tx[]  = {3, 7, 19, 23};

    static const uint8_t spi1_rx[]  = {8, 12, 24, 28};
    static const uint8_t spi1_cs[]  = {9, 13, 25, 29};
    static const uint8_t spi1_sck[] = {10, 14, 26};
    static const uint8_t spi1_tx[]  = {11, 15, 27};

    const uint8_t *pins = NULL;
    size_t count = 0;

    if (instance == 0) {
        switch (function) {
            case PIN_SPI_RX:
                pins = spi0_rx;
                count = sizeof(spi0_rx) / sizeof(spi0_rx[0]);
                break;
            case PIN_SPI_CS:
                pins = spi0_cs;
                count = sizeof(spi0_cs) / sizeof(spi0_cs[0]);
                break;
            case PIN_SPI_SCK:
                pins = spi0_sck;
                count = sizeof(spi0_sck) / sizeof(spi0_sck[0]);
                break;
            case PIN_SPI_TX:
                pins = spi0_tx;
                count = sizeof(spi0_tx) / sizeof(spi0_tx[0]);
                break;
            default:
                return false;
        }
    } else if (instance == 1) {
        switch (function) {
            case PIN_SPI_RX:
                pins = spi1_rx;
                count = sizeof(spi1_rx) / sizeof(spi1_rx[0]);
                break;
            case PIN_SPI_CS:
                pins = spi1_cs;
                count = sizeof(spi1_cs) / sizeof(spi1_cs[0]);
                break;
            case PIN_SPI_SCK:
                pins = spi1_sck;
                count = sizeof(spi1_sck) / sizeof(spi1_sck[0]);
                break;
            case PIN_SPI_TX:
                pins = spi1_tx;
                count = sizeof(spi1_tx) / sizeof(spi1_tx[0]);
                break;
            default:
                return false;
        }
    } else {
        return false;
    }

    return pin_in_list(pin, pins, count);
}

static bool pin_supports_i2c(
    unsigned int pin,
    device_pin_function_t function,
    uint8_t instance
)
{
    static const uint8_t i2c0_sda[] = {
        0, 4, 8, 12, 16, 20, 24, 28
    };
    static const uint8_t i2c0_scl[] = {
        1, 5, 9, 13, 17, 21, 25, 29
    };
    static const uint8_t i2c1_sda[] = {
        2, 6, 10, 14, 18, 22, 26
    };
    static const uint8_t i2c1_scl[] = {
        3, 7, 11, 15, 19, 23, 27
    };

    if (instance == 0 && function == PIN_I2C_SDA) {
        return pin_in_list(
            pin, i2c0_sda,
            sizeof(i2c0_sda) / sizeof(i2c0_sda[0])
        );
    }

    if (instance == 0 && function == PIN_I2C_SCL) {
        return pin_in_list(
            pin, i2c0_scl,
            sizeof(i2c0_scl) / sizeof(i2c0_scl[0])
        );
    }

    if (instance == 1 && function == PIN_I2C_SDA) {
        return pin_in_list(
            pin, i2c1_sda,
            sizeof(i2c1_sda) / sizeof(i2c1_sda[0])
        );
    }

    if (instance == 1 && function == PIN_I2C_SCL) {
        return pin_in_list(
            pin, i2c1_scl,
            sizeof(i2c1_scl) / sizeof(i2c1_scl[0])
        );
    }

    return false;
}

static bool pin_supports_uart(
    unsigned int pin,
    device_pin_function_t function,
    uint8_t instance
)
{
    static const uint8_t uart0_tx[] = {
        0, 2, 12, 14, 16, 18, 28
    };
    static const uint8_t uart0_rx[] = {
        1, 3, 13, 15, 17, 19, 29
    };
    static const uint8_t uart1_tx[] = {
        4, 6, 8, 10, 20, 22, 24, 26
    };
    static const uint8_t uart1_rx[] = {
        5, 7, 9, 11, 21, 23, 25, 27
    };

    if (instance == 0 && function == PIN_UART_TX) {
        return pin_in_list(
            pin, uart0_tx,
            sizeof(uart0_tx) / sizeof(uart0_tx[0])
        );
    }

    if (instance == 0 && function == PIN_UART_RX) {
        return pin_in_list(
            pin, uart0_rx,
            sizeof(uart0_rx) / sizeof(uart0_rx[0])
        );
    }

    if (instance == 1 && function == PIN_UART_TX) {
        return pin_in_list(
            pin, uart1_tx,
            sizeof(uart1_tx) / sizeof(uart1_tx[0])
        );
    }

    if (instance == 1 && function == PIN_UART_RX) {
        return pin_in_list(
            pin, uart1_rx,
            sizeof(uart1_rx) / sizeof(uart1_rx[0])
        );
    }

    return false;
}

static bool pin_supports_peripheral(
    unsigned int pin,
    const device_pin_config_t *entry
)
{
    switch (entry->function) {
        case PIN_I2C_SDA:
        case PIN_I2C_SCL:
            return pin_supports_i2c(
                pin, entry->function, entry->peripheral_instance
            );

        case PIN_SPI_RX:
        case PIN_SPI_TX:
        case PIN_SPI_SCK:
        case PIN_SPI_CS:
            return pin_supports_spi(
                pin, entry->function, entry->peripheral_instance
            );

        case PIN_UART_TX:
        case PIN_UART_RX:
            return pin_supports_uart(
                pin, entry->function, entry->peripheral_instance
            );

        default:
            return true;
    }
}

static bool has_function(
    const device_config_t *config,
    device_pin_function_t function,
    uint8_t instance
)
{
    for (unsigned int pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        const device_pin_config_t *entry = &config->pins[pin];

        if (entry->function == function &&
            entry->peripheral_instance == instance) {
            return true;
        }
    }

    return false;
}

static bool has_any_function(
    const device_config_t *config,
    const device_pin_function_t *functions,
    size_t count,
    uint8_t instance
)
{
    for (size_t i = 0; i < count; i++) {
        if (has_function(config, functions[i], instance)) {
            return true;
        }
    }

    return false;
}

static bool pio_sm_is_managed(
    const resource_manager_t *manager,
    uint8_t block,
    uint8_t state_machine
)
{
    for (uint8_t i = 0; i < RESOURCE_PIO_ALLOCATION_COUNT; i++) {
        const resource_pio_allocation_t *allocation =
            &manager->pio_allocations[i];

        if (allocation->active &&
            allocation->pio_block == block &&
            allocation->state_machine == state_machine) {
            return true;
        }
    }

    return false;
}

void resource_manager_init(resource_manager_t *manager)
{
    if (manager == NULL) {
        return;
    }

    memset(manager, 0, sizeof(*manager));

    for (unsigned int pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        manager->gpio[pin].available = valid_gpio(pin);
        manager->gpio[pin].function = PIN_UNUSED;
    }
}

resource_status_t resource_manager_apply_config(
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

    static const device_pin_function_t i2c_functions[] = {
        PIN_I2C_SDA, PIN_I2C_SCL
    };

    static const device_pin_function_t spi_functions[] = {
        PIN_SPI_RX, PIN_SPI_TX, PIN_SPI_SCK, PIN_SPI_CS
    };

    static const device_pin_function_t uart_functions[] = {
        PIN_UART_TX, PIN_UART_RX
    };

    resource_manager_t next;
    resource_manager_init(&next);

    next.pio_sm_reserved_mask = manager->pio_sm_reserved_mask;

    memcpy(
        next.pio_allocations,
        manager->pio_allocations,
        sizeof(next.pio_allocations)
    );

    for (unsigned int pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        next.gpio[pin].pio_claimed =
            manager->gpio[pin].pio_claimed;
    }

    for (unsigned int pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        const device_pin_config_t *entry = &config->pins[pin];

        if (entry->function != PIN_UNUSED && !valid_gpio(pin)) {
            return RESOURCE_INVALID_PIN_MAPPING;
        }

        if (!pin_supports_peripheral(pin, entry)) {
            return RESOURCE_INVALID_PIN_MAPPING;
        }

        if (entry->function != PIN_UNUSED &&
            next.gpio[pin].pio_claimed &&
            !(manager->gpio[pin].assigned &&
              manager->gpio[pin].function == PIN_SIGNAL_GENERATOR &&
              entry->function == PIN_SIGNAL_GENERATOR)) {
            return RESOURCE_GPIO_IN_USE;
        }
    }

    for (uint8_t instance = 0; instance < 2; instance++) {
        bool has_i2c = has_any_function(
            config, i2c_functions,
            sizeof(i2c_functions) / sizeof(i2c_functions[0]),
            instance
        );

        if (has_i2c) {
            if (!has_function(config, PIN_I2C_SDA, instance) ||
                !has_function(config, PIN_I2C_SCL, instance)) {
                return RESOURCE_INCOMPLETE_I2C;
            }

            next.i2c_instance_mask |= (uint8_t)(1u << instance);
        }

        bool has_spi = has_any_function(
            config, spi_functions,
            sizeof(spi_functions) / sizeof(spi_functions[0]),
            instance
        );

        if (has_spi) {
            bool has_data =
                has_function(config, PIN_SPI_RX, instance) ||
                has_function(config, PIN_SPI_TX, instance);

            if (!has_function(config, PIN_SPI_SCK, instance) ||
                !has_data) {
                return RESOURCE_INCOMPLETE_SPI;
            }

            next.spi_instance_mask |= (uint8_t)(1u << instance);
        }

        bool has_uart = has_any_function(
            config, uart_functions,
            sizeof(uart_functions) / sizeof(uart_functions[0]),
            instance
        );

        if (has_uart) {
            next.uart_instance_mask |= (uint8_t)(1u << instance);
        }
    }

    for (unsigned int pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        const device_pin_config_t *entry = &config->pins[pin];

        next.gpio[pin].pio_priority = entry->pio_priority;

        if (entry->function == PIN_UNUSED) {
            continue;
        }

        next.gpio[pin].assigned = true;
        next.gpio[pin].function = entry->function;
        next.gpio[pin].peripheral_instance =
            entry->peripheral_instance;
    }

    *manager = next;

    return RESOURCE_OK;
}

bool resource_manager_gpio_is_available(
    const resource_manager_t *manager,
    uint8_t pin
)
{
    if (manager == NULL || pin >= DEVICE_GPIO_COUNT) {
        return false;
    }

    const resource_gpio_t *gpio = &manager->gpio[pin];

    return gpio->available &&
           !gpio->assigned &&
           !gpio->pio_claimed;
}

bool resource_manager_gpio_is_reserved(
    const resource_manager_t *manager,
    uint8_t pin
)
{
    if (manager == NULL || pin >= DEVICE_GPIO_COUNT) {
        return false;
    }

    return manager->gpio[pin].assigned ||
           manager->gpio[pin].pio_claimed;
}

const resource_gpio_t *resource_manager_get_gpio(
    const resource_manager_t *manager,
    uint8_t pin
)
{
    if (manager == NULL || pin >= DEVICE_GPIO_COUNT) {
        return NULL;
    }

    return &manager->gpio[pin];
}

uint8_t resource_manager_get_free_gpio_count(
    const resource_manager_t *manager
)
{
    if (manager == NULL) {
        return 0;
    }

    uint8_t count = 0;

    for (uint8_t pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        if (resource_manager_gpio_is_available(manager, pin)) {
            count++;
        }
    }

    return count;
}

bool resource_manager_get_free_gpio(
    const resource_manager_t *manager,
    uint8_t index,
    uint8_t *pin
)
{
    if (manager == NULL || pin == NULL) {
        return false;
    }

    uint8_t current = 0;

    for (int priority = DEVICE_PIO_PRIORITY_MAX;
         priority >= DEVICE_PIO_PRIORITY_MIN;
         priority--) {

        for (uint8_t gpio = 0; gpio < DEVICE_GPIO_COUNT; gpio++) {
            if (!resource_manager_gpio_is_available(manager, gpio) ||
                manager->gpio[gpio].pio_priority != priority) {
                continue;
            }

            if (current == index) {
                *pin = gpio;
                return true;
            }

            current++;
        }
    }

    return false;
}

bool resource_manager_claim_pio_gpio(
    resource_manager_t *manager,
    uint8_t pin
)
{
    if (!resource_manager_gpio_is_available(manager, pin)) {
        return false;
    }

    manager->gpio[pin].pio_claimed = true;
    return true;
}

bool resource_manager_release_pio_gpio(
    resource_manager_t *manager,
    uint8_t pin
)
{
    if (manager == NULL || pin >= DEVICE_GPIO_COUNT ||
        !manager->gpio[pin].pio_claimed) {
        return false;
    }

    for (uint8_t i = 0; i < RESOURCE_PIO_ALLOCATION_COUNT; i++) {
        const resource_pio_allocation_t *allocation =
            &manager->pio_allocations[i];

        if (allocation->active &&
            (allocation->gpio_mask & (uint32_t)(1u << pin))) {
            return false;
        }
    }

    manager->gpio[pin].pio_claimed = false;
    return true;
}

resource_status_t resource_manager_allocate_pio(
    resource_manager_t *manager,
    const uint8_t *requested_pins,
    uint8_t pin_count,
    uint8_t *assigned_pins,
    uint8_t *allocation_id,
    uint8_t *pio_block,
    uint8_t *state_machine
)
{
    if (manager == NULL ||
        pin_count == 0 ||
        pin_count > DEVICE_GPIO_COUNT ||
        assigned_pins == NULL ||
        allocation_id == NULL ||
        pio_block == NULL ||
        state_machine == NULL) {
        return RESOURCE_INVALID_ARGUMENT;
    }

    int allocation_slot = -1;

    for (uint8_t i = 0; i < RESOURCE_PIO_ALLOCATION_COUNT; i++) {
        if (!manager->pio_allocations[i].active) {
            allocation_slot = i;
            break;
        }
    }

    if (allocation_slot < 0) {
        return RESOURCE_PIO_EXHAUSTED;
    }

    int sm_index = -1;

    for (uint8_t i = 0; i < RESOURCE_PIO_SM_COUNT; i++) {
        if ((manager->pio_sm_reserved_mask & (uint16_t)(1u << i)) == 0) {
            sm_index = i;
            break;
        }
    }

    if (sm_index < 0) {
        return RESOURCE_PIO_EXHAUSTED;
    }

    uint8_t selected[DEVICE_GPIO_COUNT];
    uint32_t gpio_mask = 0;

    if (requested_pins != NULL) {
        for (uint8_t i = 0; i < pin_count; i++) {
            uint8_t pin = requested_pins[i];

            if (pin >= DEVICE_GPIO_COUNT) {
                return RESOURCE_GPIO_IN_USE;
            }

            bool available =
                resource_manager_gpio_is_available(manager, pin);

            bool configured_signal_generator =
                manager->gpio[pin].assigned &&
                manager->gpio[pin].function == PIN_SIGNAL_GENERATOR &&
                !manager->gpio[pin].pio_claimed;

            if (!available && !configured_signal_generator) {
                return RESOURCE_GPIO_IN_USE;
            }

            uint32_t mask = (uint32_t)(1u << pin);

            if (gpio_mask & mask) {
                return RESOURCE_INVALID_ARGUMENT;
            }

            gpio_mask |= mask;
            selected[i] = pin;
        }
    } else {
        uint8_t selected_count = 0;

        for (int priority = DEVICE_PIO_PRIORITY_MAX;
             priority >= DEVICE_PIO_PRIORITY_MIN &&
             selected_count < pin_count;
             priority--) {

            for (uint8_t pin = 0;
                 pin < DEVICE_GPIO_COUNT &&
                 selected_count < pin_count;
                 pin++) {

                if (!resource_manager_gpio_is_available(manager, pin) ||
                    manager->gpio[pin].pio_priority != priority) {
                    continue;
                }

                selected[selected_count++] = pin;
                gpio_mask |= (uint32_t)(1u << pin);
            }
        }

        if (selected_count != pin_count) {
            return RESOURCE_GPIO_EXHAUSTED;
        }
    }

    /*
     * Commit all resources only after every check has succeeded.
     */
    for (uint8_t i = 0; i < pin_count; i++) {
        manager->gpio[selected[i]].pio_claimed = true;
        assigned_pins[i] = selected[i];
    }

    manager->pio_sm_reserved_mask |= (uint16_t)(1u << sm_index);

    resource_pio_allocation_t *allocation =
        &manager->pio_allocations[allocation_slot];

    allocation->active = true;
    allocation->gpio_mask = gpio_mask;
    allocation->pio_block =
        (uint8_t)(sm_index / RESOURCE_PIO_SM_PER_BLOCK);
    allocation->state_machine =
        (uint8_t)(sm_index % RESOURCE_PIO_SM_PER_BLOCK);

    *allocation_id = (uint8_t)allocation_slot;
    *pio_block = allocation->pio_block;
    *state_machine = allocation->state_machine;

    return RESOURCE_OK;
}

bool resource_manager_release_pio(
    resource_manager_t *manager,
    uint8_t allocation_id
)
{
    if (manager == NULL ||
        allocation_id >= RESOURCE_PIO_ALLOCATION_COUNT) {
        return false;
    }

    resource_pio_allocation_t *allocation =
        &manager->pio_allocations[allocation_id];

    if (!allocation->active) {
        return false;
    }

    for (uint8_t pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        if (allocation->gpio_mask & (uint32_t)(1u << pin)) {
            manager->gpio[pin].pio_claimed = false;
        }
    }

    uint8_t sm_index =
        allocation->pio_block * RESOURCE_PIO_SM_PER_BLOCK +
        allocation->state_machine;

    manager->pio_sm_reserved_mask &=
        (uint16_t)~(1u << sm_index);

    memset(allocation, 0, sizeof(*allocation));

    return true;
}

bool resource_manager_allocate_pio_sm(
    resource_manager_t *manager,
    uint8_t *pio_block,
    uint8_t *state_machine
)
{
    if (manager == NULL ||
        pio_block == NULL ||
        state_machine == NULL) {
        return false;
    }

    for (uint8_t index = 0; index < RESOURCE_PIO_SM_COUNT; index++) {
        uint16_t mask = (uint16_t)(1u << index);

        if ((manager->pio_sm_reserved_mask & mask) != 0) {
            continue;
        }

        manager->pio_sm_reserved_mask |= mask;

        *pio_block = index / RESOURCE_PIO_SM_PER_BLOCK;
        *state_machine = index % RESOURCE_PIO_SM_PER_BLOCK;

        return true;
    }

    return false;
}

bool resource_manager_release_pio_sm(
    resource_manager_t *manager,
    uint8_t pio_block,
    uint8_t state_machine
)
{
    if (manager == NULL ||
        pio_block >= RESOURCE_PIO_BLOCK_COUNT ||
        state_machine >= RESOURCE_PIO_SM_PER_BLOCK) {
        return false;
    }

    if (pio_sm_is_managed(manager, pio_block, state_machine)) {
        return false;
    }

    uint8_t index =
        pio_block * RESOURCE_PIO_SM_PER_BLOCK + state_machine;

    uint16_t mask = (uint16_t)(1u << index);

    if ((manager->pio_sm_reserved_mask & mask) == 0) {
        return false;
    }

    manager->pio_sm_reserved_mask &= (uint16_t)~mask;

    return true;
}
