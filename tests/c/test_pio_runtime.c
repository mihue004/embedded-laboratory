#include "pio_runtime.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    bool claimed[RESOURCE_PIO_BLOCK_COUNT]
                [RESOURCE_PIO_SM_PER_BLOCK];
    bool gpio_pio[DEVICE_GPIO_COUNT];
    uint8_t gpio_block[DEVICE_GPIO_COUNT];
    int fail_gpio;
} mock_hardware_t;

static bool mock_is_claimed(void *context, uint8_t block, uint8_t sm)
{
    mock_hardware_t *hw = context;
    return hw->claimed[block][sm];
}

static bool mock_claim(void *context, uint8_t block, uint8_t sm)
{
    mock_hardware_t *hw = context;

    if (hw->claimed[block][sm]) {
        return false;
    }

    hw->claimed[block][sm] = true;
    return true;
}

static void mock_unclaim(void *context, uint8_t block, uint8_t sm)
{
    mock_hardware_t *hw = context;
    hw->claimed[block][sm] = false;
}

static bool mock_set_pio(void *context, uint8_t pin, uint8_t block)
{
    mock_hardware_t *hw = context;

    hw->gpio_pio[pin] = true;
    hw->gpio_block[pin] = block;

    if (hw->fail_gpio == pin) {
        return false;
    }

    return true;
}

static void mock_set_sio(void *context, uint8_t pin)
{
    mock_hardware_t *hw = context;
    hw->gpio_pio[pin] = false;
}

static const pio_runtime_ops_t mock_ops = {
    .is_sm_claimed = mock_is_claimed,
    .claim_sm = mock_claim,
    .unclaim_sm = mock_unclaim,
    .set_gpio_pio = mock_set_pio,
    .set_gpio_sio = mock_set_sio
};

static void init(
    resource_manager_t *manager,
    device_config_t *config
)
{
    resource_manager_init(manager);
    device_config_init(config);
    assert(resource_manager_apply_config(manager, config) == RESOURCE_OK);
}

static void test_allocate_and_release(void)
{
    resource_manager_t manager;
    device_config_t config;
    mock_hardware_t hw = { .fail_gpio = -1 };
    uint8_t pins[] = {17, 28};
    uint8_t assigned[2];
    uint8_t id;

    init(&manager, &config);

    assert(pio_runtime_allocate(
        &manager, pins, 2, assigned, &id, &mock_ops, &hw
    ) == RESOURCE_OK);

    assert(assigned[0] == 17 && assigned[1] == 28);
    assert(hw.claimed[0][0]);
    assert(hw.gpio_pio[17] && hw.gpio_pio[28]);
    assert(hw.gpio_block[17] == 0);
    assert(!resource_manager_gpio_is_available(&manager, 28));

    assert(pio_runtime_release(&manager, id, &mock_ops, &hw));

    assert(!hw.claimed[0][0]);
    assert(!hw.gpio_pio[17] && !hw.gpio_pio[28]);
    assert(resource_manager_gpio_is_available(&manager, 28));
}

static void test_hardware_claim_conflict(void)
{
    resource_manager_t manager;
    device_config_t config;
    mock_hardware_t hw = { .fail_gpio = -1 };
    uint8_t pin = 4;
    uint8_t assigned;
    uint8_t id;

    init(&manager, &config);
    hw.claimed[0][0] = true;

    assert(pio_runtime_allocate(
        &manager, &pin, 1, &assigned, &id, &mock_ops, &hw
    ) == RESOURCE_HARDWARE_ERROR);

    assert(resource_manager_gpio_is_available(&manager, pin));
    assert(manager.pio_sm_reserved_mask == 0);
}

static void test_gpio_failure_rolls_back(void)
{
    resource_manager_t manager;
    device_config_t config;
    mock_hardware_t hw = { .fail_gpio = 9 };
    uint8_t pins[] = {8, 9};
    uint8_t assigned[2];
    uint8_t id;

    init(&manager, &config);

    assert(pio_runtime_allocate(
        &manager, pins, 2, assigned, &id, &mock_ops, &hw
    ) == RESOURCE_HARDWARE_ERROR);

    assert(!hw.claimed[0][0]);
    assert(!hw.gpio_pio[8]);
    assert(!hw.gpio_pio[9]);
    assert(resource_manager_gpio_is_available(&manager, 8));
    assert(resource_manager_gpio_is_available(&manager, 9));
    assert(manager.pio_sm_reserved_mask == 0);
}


static void test_release_after_external_sm_unclaim(void)
{
    resource_manager_t manager;
    device_config_t config;
    mock_hardware_t hw = { .fail_gpio = -1 };
    uint8_t pin = 12;
    uint8_t assigned;
    uint8_t id;

    init(&manager, &config);

    assert(pio_runtime_allocate(
        &manager, &pin, 1, &assigned, &id, &mock_ops, &hw
    ) == RESOURCE_OK);

    assert(!resource_manager_gpio_is_available(&manager, pin));

    /* Simulate an external release of the hardware state machine. */
    hw.claimed[0][0] = false;

    assert(!pio_runtime_release(&manager, id, &mock_ops, &hw));

    /* Synchronization must reclaim the stale logical allocation. */
    assert(!manager.pio_allocations[id].active);
    assert(resource_manager_gpio_is_available(&manager, pin));
    assert(!hw.gpio_pio[pin]);
}


static void test_sync_multiple_allocations(void)
{
    resource_manager_t manager;
    device_config_t config;
    mock_hardware_t hw = { .fail_gpio = -1 };

    uint8_t pin_a = 13;
    uint8_t pin_b = 14;
    uint8_t assigned_a;
    uint8_t assigned_b;
    uint8_t id_a;
    uint8_t id_b;

    init(&manager, &config);

    assert(pio_runtime_allocate(
        &manager, &pin_a, 1, &assigned_a, &id_a, &mock_ops, &hw
    ) == RESOURCE_OK);

    assert(pio_runtime_allocate(
        &manager, &pin_b, 1, &assigned_b, &id_b, &mock_ops, &hw
    ) == RESOURCE_OK);

    uint8_t block_a = manager.pio_allocations[id_a].pio_block;
    uint8_t sm_a = manager.pio_allocations[id_a].state_machine;
    uint8_t block_b = manager.pio_allocations[id_b].pio_block;
    uint8_t sm_b = manager.pio_allocations[id_b].state_machine;

    /* Externally release only the first state machine. */
    hw.claimed[block_a][sm_a] = false;

    assert(pio_runtime_sync(&manager, &mock_ops, &hw));

    assert(!manager.pio_allocations[id_a].active);
    assert(manager.pio_allocations[id_b].active);
    assert(resource_manager_gpio_is_available(&manager, pin_a));
    assert(!resource_manager_gpio_is_available(&manager, pin_b));
    assert(!hw.gpio_pio[pin_a]);
    assert(hw.gpio_pio[pin_b]);
    assert(hw.claimed[block_b][sm_b]);

    /* Now release the second allocation externally as well. */
    hw.claimed[block_b][sm_b] = false;

    assert(pio_runtime_sync(&manager, &mock_ops, &hw));

    assert(!manager.pio_allocations[id_b].active);
    assert(resource_manager_gpio_is_available(&manager, pin_b));
    assert(!hw.gpio_pio[pin_b]);
    assert(manager.pio_sm_reserved_mask == 0);
}

int main(void)
{
    test_allocate_and_release();
    test_hardware_claim_conflict();
    test_gpio_failure_rolls_back();
    test_release_after_external_sm_unclaim();
    test_sync_multiple_allocations();

    puts("All PIO runtime tests passed.");
    return 0;
}
