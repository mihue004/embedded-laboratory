#ifndef RESOURCE_MANAGER_H
#define RESOURCE_MANAGER_H

#include "device_config.h"

#include <stdbool.h>
#include <stdint.h>

#define RESOURCE_PIO_BLOCK_COUNT 3
#define RESOURCE_PIO_SM_PER_BLOCK 4
#define RESOURCE_PIO_SM_COUNT \
    (RESOURCE_PIO_BLOCK_COUNT * RESOURCE_PIO_SM_PER_BLOCK)

#define RESOURCE_PIO_ALLOCATION_COUNT RESOURCE_PIO_SM_COUNT

typedef enum {
    RESOURCE_OK = 0,
    RESOURCE_INVALID_CONFIG,
    RESOURCE_INVALID_ARGUMENT,
    RESOURCE_INVALID_PIN_MAPPING,
    RESOURCE_INCOMPLETE_I2C,
    RESOURCE_INCOMPLETE_SPI,
    RESOURCE_GPIO_IN_USE,
    RESOURCE_PIO_EXHAUSTED,
    RESOURCE_GPIO_EXHAUSTED,
    RESOURCE_HARDWARE_ERROR
} resource_status_t;

typedef struct {
    bool available;
    bool assigned;
    bool pio_claimed;

    device_pin_function_t function;
    uint8_t peripheral_instance;
    uint8_t pio_priority;
} resource_gpio_t;

typedef struct {
    bool active;
    uint32_t gpio_mask;
    uint8_t pio_block;
    uint8_t state_machine;
} resource_pio_allocation_t;

typedef struct {
    resource_gpio_t gpio[DEVICE_GPIO_COUNT];

    uint8_t i2c_instance_mask;
    uint8_t spi_instance_mask;
    uint8_t uart_instance_mask;

    uint16_t pio_sm_reserved_mask;

    resource_pio_allocation_t
        pio_allocations[RESOURCE_PIO_ALLOCATION_COUNT];
} resource_manager_t;

void resource_manager_init(resource_manager_t *manager);

resource_status_t resource_manager_apply_config(
    resource_manager_t *manager,
    const device_config_t *config
);

bool resource_manager_gpio_is_available(
    const resource_manager_t *manager,
    uint8_t pin
);

bool resource_manager_gpio_is_reserved(
    const resource_manager_t *manager,
    uint8_t pin
);

const resource_gpio_t *resource_manager_get_gpio(
    const resource_manager_t *manager,
    uint8_t pin
);

uint8_t resource_manager_get_free_gpio_count(
    const resource_manager_t *manager
);

bool resource_manager_get_free_gpio(
    const resource_manager_t *manager,
    uint8_t index,
    uint8_t *pin
);

bool resource_manager_claim_pio_gpio(
    resource_manager_t *manager,
    uint8_t pin
);

bool resource_manager_release_pio_gpio(
    resource_manager_t *manager,
    uint8_t pin
);

/*
 * Allocate one PIO state machine and multiple GPIOs atomically.
 *
 * requested_pins == NULL:
 *     Select GPIOs automatically by descending PIO priority.
 *
 * requested_pins != NULL:
 *     Use exactly the requested GPIOs.
 *
 * assigned_pins receives the actual GPIO assignments.
 * allocation_id identifies the allocation for later release.
 */
resource_status_t resource_manager_allocate_pio(
    resource_manager_t *manager,
    const uint8_t *requested_pins,
    uint8_t pin_count,
    uint8_t *assigned_pins,
    uint8_t *allocation_id,
    uint8_t *pio_block,
    uint8_t *state_machine
);

bool resource_manager_release_pio(
    resource_manager_t *manager,
    uint8_t allocation_id
);

bool resource_manager_allocate_pio_sm(
    resource_manager_t *manager,
    uint8_t *pio_block,
    uint8_t *state_machine
);

bool resource_manager_release_pio_sm(
    resource_manager_t *manager,
    uint8_t pio_block,
    uint8_t state_machine
);

#endif
