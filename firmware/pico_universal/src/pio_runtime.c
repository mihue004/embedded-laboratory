#include "pio_runtime.h"

#include <stddef.h>

static bool ops_valid(const pio_runtime_ops_t *ops)
{
    return ops != NULL &&
           ops->is_sm_claimed != NULL &&
           ops->claim_sm != NULL &&
           ops->unclaim_sm != NULL &&
           ops->set_gpio_pio != NULL &&
           ops->set_gpio_sio != NULL;
}

static bool allocation_indices_valid(
    uint8_t block,
    uint8_t sm
)
{
    return block < RESOURCE_PIO_BLOCK_COUNT &&
           sm < RESOURCE_PIO_SM_PER_BLOCK;
}

bool  pio_runtime_sync(
    resource_manager_t *manager,
    const pio_runtime_ops_t *ops,
    void *context
)
{
    if (manager == NULL || !ops_valid(ops)) {
        return false;
    }

    for (uint8_t id = 0; id < RESOURCE_PIO_ALLOCATION_COUNT; id++) {
        resource_pio_allocation_t *allocation =
            &manager->pio_allocations[id];

        if (!allocation->active) {
            continue;
        }

        uint8_t block = allocation->pio_block;
        uint8_t sm = allocation->state_machine;

        if (!allocation_indices_valid(block, sm)) {
            return false;
        }

        if (ops->is_sm_claimed(context, block, sm)) {
            continue;
        }

        uint32_t gpio_mask = allocation->gpio_mask;

        if (!resource_manager_release_pio(manager, id)) {
            return false;
        }

        for (uint8_t pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
            if (gpio_mask & (1u << pin)) {
                ops->set_gpio_sio(context, pin);
            }
        }
    }

    return true;
}

resource_status_t pio_runtime_allocate(
    resource_manager_t *manager,
    const uint8_t *requested_pins,
    uint8_t pin_count,
    uint8_t *assigned_pins,
    uint8_t *allocation_id,
    const pio_runtime_ops_t *ops,
    void *context
)
{
    if (manager == NULL || assigned_pins == NULL ||
        allocation_id == NULL || !ops_valid(ops)) {
        return RESOURCE_INVALID_ARGUMENT;
    }

    if (!pio_runtime_sync(manager, ops, context)) {
        return RESOURCE_HARDWARE_ERROR;
    }

    resource_manager_t next = *manager;
    uint8_t next_id;
    uint8_t block;
    uint8_t sm;

    uint8_t assigned[DEVICE_GPIO_COUNT];

    resource_status_t status = resource_manager_allocate_pio(
        &next,
        requested_pins,
        pin_count,
        assigned,
        &next_id,
        &block,
        &sm
    );

    if (status != RESOURCE_OK) {
        return status;
    }

    if (ops->is_sm_claimed(context, block, sm)) {
        return RESOURCE_HARDWARE_ERROR;
    }

    if (!ops->claim_sm(context, block, sm)) {
        return RESOURCE_HARDWARE_ERROR;
    }

    uint8_t configured = 0;

    for (; configured < pin_count; configured++) {
        if (!ops->set_gpio_pio(
                context, assigned[configured], block)) {
            break;
        }
    }

    if (configured != pin_count) {
        for (uint8_t i = 0; i <= configured; i++) {
            ops->set_gpio_sio(context, assigned[i]);
        }

        ops->unclaim_sm(context, block, sm);
        return RESOURCE_HARDWARE_ERROR;
    }

    *manager = next;
    *allocation_id = next_id;

    for (uint8_t i = 0; i < pin_count; i++) {
        assigned_pins[i] = assigned[i];
    }

    return RESOURCE_OK;
}

bool pio_runtime_release(
    resource_manager_t *manager,
    uint8_t allocation_id,
    const pio_runtime_ops_t *ops,
    void *context
)
{
    if (manager == NULL ||
        allocation_id >= RESOURCE_PIO_ALLOCATION_COUNT ||
        !ops_valid(ops)) {
        return false;
    }

    if (!pio_runtime_sync(manager, ops, context)) {
        return false;
    }

    const resource_pio_allocation_t *allocation =
        &manager->pio_allocations[allocation_id];

    if (!allocation->active) {
        return false;
    }

    uint8_t block = allocation->pio_block;
    uint8_t sm = allocation->state_machine;
    uint32_t gpio_mask = allocation->gpio_mask;

    if (!ops->is_sm_claimed(context, block, sm)) {
        return false;
    }

    if (!resource_manager_release_pio(manager, allocation_id)) {
        return false;
    }

    for (uint8_t pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        if (gpio_mask & (1u << pin)) {
            ops->set_gpio_sio(context, pin);
        }
    }

    ops->unclaim_sm(context, block, sm);

    return true;
}
