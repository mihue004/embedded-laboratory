#include "pio_runtime_pico.h"

#include "hardware/gpio.h"
#include "hardware/pio.h"

static bool pico_is_sm_claimed(
    void *context, uint8_t block, uint8_t sm
)
{
    (void)context;

    if (block >= RESOURCE_PIO_BLOCK_COUNT ||
        sm >= RESOURCE_PIO_SM_PER_BLOCK) {
        return true;
    }

    return pio_sm_is_claimed(pio_get_instance(block), sm);
}

static bool pico_claim_sm(
    void *context, uint8_t block, uint8_t sm
)
{
    (void)context;

    if (block >= RESOURCE_PIO_BLOCK_COUNT ||
        sm >= RESOURCE_PIO_SM_PER_BLOCK) {
        return false;
    }

    PIO pio = pio_get_instance(block);

    if (pio_sm_is_claimed(pio, sm)) {
        return false;
    }

    pio_sm_claim(pio, sm);
    return true;
}

static void pico_unclaim_sm(
    void *context,
    uint8_t block,
    uint8_t sm
)
{
    (void)context;

    if (block >= RESOURCE_PIO_BLOCK_COUNT ||
        sm >= RESOURCE_PIO_SM_PER_BLOCK) {
        return;
    }

    PIO pio = pio_get_instance(block);
    pio_sm_set_enabled(pio, sm, false);
    pio_sm_unclaim(pio, sm);
}

static bool pico_set_gpio_pio(
    void *context, uint8_t pin, uint8_t block
)
{
    (void)context;

    if (block >= RESOURCE_PIO_BLOCK_COUNT ||
        pin >= DEVICE_GPIO_COUNT) {
        return false;
    }

    pio_gpio_init(pio_get_instance(block), pin);
    return true;
}

static void pico_set_gpio_sio(void *context, uint8_t pin)
{
    (void)context;
    gpio_set_function(pin, GPIO_FUNC_SIO);
}

static const pio_runtime_ops_t pico_ops = {
    .is_sm_claimed = pico_is_sm_claimed,
    .claim_sm = pico_claim_sm,
    .unclaim_sm = pico_unclaim_sm,
    .set_gpio_pio = pico_set_gpio_pio,
    .set_gpio_sio = pico_set_gpio_sio
};

bool pio_runtime_sync_pico(resource_manager_t *manager)
{
    return pio_runtime_sync(manager, &pico_ops, NULL);
}

resource_status_t pio_runtime_allocate_pico(
    resource_manager_t *manager,
    const uint8_t *requested_pins,
    uint8_t pin_count,
    uint8_t *assigned_pins,
    uint8_t *allocation_id
)
{
    return pio_runtime_allocate(
        manager,
        requested_pins,
        pin_count,
        assigned_pins,
        allocation_id,
        &pico_ops,
        NULL
    );
}

bool pio_runtime_release_pico(
    resource_manager_t *manager,
    uint8_t allocation_id
)
{
    return pio_runtime_release(
        manager,
        allocation_id,
        &pico_ops,
        NULL
    );
}
