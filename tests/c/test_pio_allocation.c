
#include "resource_manager.h"

#include <assert.h>
#include <stdio.h>

static void init_manager(
    resource_manager_t *manager,
    device_config_t *config
)
{
    resource_manager_init(manager);
    device_config_init(config);

    assert(resource_manager_apply_config(manager, config) == RESOURCE_OK);
}

static void test_manual_allocation(void)
{
    resource_manager_t manager;
    device_config_t config;
    uint8_t requested[] = {2, 3, 4};
    uint8_t assigned[3];
    uint8_t allocation_id;
    uint8_t block;
    uint8_t sm;

    init_manager(&manager, &config);

    assert(resource_manager_allocate_pio(
        &manager, requested, 3, assigned,
        &allocation_id, &block, &sm
    ) == RESOURCE_OK);

    for (unsigned int i = 0; i < 3; i++) {
        assert(assigned[i] == requested[i]);
        assert(!resource_manager_gpio_is_available(
            &manager, assigned[i]
        ));
        assert(!resource_manager_release_pio_gpio(
            &manager, assigned[i]
        ));
    }

    assert(block < RESOURCE_PIO_BLOCK_COUNT);
    assert(sm < RESOURCE_PIO_SM_PER_BLOCK);

    assert(resource_manager_release_pio(
        &manager, allocation_id
    ));

    for (unsigned int i = 0; i < 3; i++) {
        assert(resource_manager_gpio_is_available(
            &manager, requested[i]
        ));
    }
}

static void test_automatic_allocation_priority(void)
{
    resource_manager_t manager;
    device_config_t config;
    uint8_t assigned[2];
    uint8_t allocation_id;
    uint8_t block;
    uint8_t sm;

    device_config_init(&config);
    config.pins[4].pio_priority = 3;
    config.pins[5].pio_priority = 1;
    config.pins[6].pio_priority = 2;

    resource_manager_init(&manager);
    assert(resource_manager_apply_config(
        &manager, &config
    ) == RESOURCE_OK);

    assert(resource_manager_allocate_pio(
        &manager, NULL, 2, assigned,
        &allocation_id, &block, &sm
    ) == RESOURCE_OK);

    assert(assigned[0] == 4);
    assert(assigned[1] == 6);

    assert(resource_manager_release_pio(
        &manager, allocation_id
    ));
}

static void test_invalid_manual_allocation(void)
{
    resource_manager_t manager;
    device_config_t config;
    uint8_t duplicate_pins[] = {7, 7};
    uint8_t assigned[2];
    uint8_t allocation_id;
    uint8_t block;
    uint8_t sm;

    init_manager(&manager, &config);

    assert(resource_manager_allocate_pio(
        &manager, duplicate_pins, 2, assigned,
        &allocation_id, &block, &sm
    ) == RESOURCE_INVALID_ARGUMENT);

    assert(resource_manager_gpio_is_available(&manager, 7));
}

static void test_config_update_preserves_allocation(void)
{
    resource_manager_t manager;
    device_config_t config;
    uint8_t requested[] = {8, 9};
    uint8_t assigned[2];
    uint8_t allocation_id;
    uint8_t block;
    uint8_t sm;

    init_manager(&manager, &config);

    assert(resource_manager_allocate_pio(
        &manager, requested, 2, assigned,
        &allocation_id, &block, &sm
    ) == RESOURCE_OK);

    assert(resource_manager_apply_config(
        &manager, &config
    ) == RESOURCE_OK);

    assert(!resource_manager_gpio_is_available(&manager, 8));
    assert(!resource_manager_gpio_is_available(&manager, 9));

    assert(resource_manager_release_pio(
        &manager, allocation_id
    ));
}

static void test_pio_state_machine_exhaustion(void)
{
    resource_manager_t manager;
    device_config_t config;
    uint8_t assigned[RESOURCE_PIO_ALLOCATION_COUNT];
    uint8_t allocation_ids[RESOURCE_PIO_ALLOCATION_COUNT];
    uint8_t block;
    uint8_t sm;

    init_manager(&manager, &config);

    for (uint8_t i = 0; i < RESOURCE_PIO_ALLOCATION_COUNT; i++) {
        uint8_t pin = i;

        assert(resource_manager_allocate_pio(
            &manager, &pin, 1, &assigned[i],
            &allocation_ids[i], &block, &sm
        ) == RESOURCE_OK);
    }

    uint8_t extra_pin = 20;
    uint8_t extra_assigned;
    uint8_t extra_id;

    assert(resource_manager_allocate_pio(
        &manager, &extra_pin, 1, &extra_assigned,
        &extra_id, &block, &sm
    ) == RESOURCE_PIO_EXHAUSTED);

    assert(resource_manager_gpio_is_available(
        &manager, extra_pin
    ));

    for (uint8_t i = 0; i < RESOURCE_PIO_ALLOCATION_COUNT; i++) {
        assert(resource_manager_release_pio(
            &manager, allocation_ids[i]
        ));
    }
}

static void test_allocation_conflict_is_atomic(void)
{
    resource_manager_t manager;
    device_config_t config;
    uint8_t first_pin[] = {10};
    uint8_t conflicting_pin[] = {10};
    uint8_t assigned;
    uint8_t allocation_id;
    uint8_t block;
    uint8_t sm;

    init_manager(&manager, &config);

    assert(resource_manager_allocate_pio(
        &manager, first_pin, 1, &assigned,
        &allocation_id, &block, &sm
    ) == RESOURCE_OK);

    uint8_t second_id;

    assert(resource_manager_allocate_pio(
        &manager, conflicting_pin, 1, &assigned,
        &second_id, &block, &sm
    ) == RESOURCE_GPIO_IN_USE);

    /* Die erste Reservierung bleibt erhalten. */
    assert(!resource_manager_gpio_is_available(&manager, 10));

    /* Ein anderer GPIO muss weiterhin reservierbar sein. */
    uint8_t other_pin[] = {11};
    uint8_t other_id;

    assert(resource_manager_allocate_pio(
        &manager, other_pin, 1, &assigned,
        &other_id, &block, &sm
    ) == RESOURCE_OK);

    assert(resource_manager_release_pio(&manager, allocation_id));
    assert(resource_manager_release_pio(&manager, other_id));
}

static void test_automatic_gpio_exhaustion(void)
{
    resource_manager_t manager;
    device_config_t config;
    uint8_t assigned[2];
    uint8_t allocation_id;
    uint8_t block;
    uint8_t sm;

    init_manager(&manager, &config);

    /* Alle gültigen GPIOs bis auf GPIO 28 einzeln reservieren. */
    for (uint8_t pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        if (pin == 28 ||
            (pin > 22 && pin < 26) ||
            pin > 28) {
            continue;
        }

        assert(resource_manager_claim_pio_gpio(
            &manager, pin
        ));
    }

    assert(resource_manager_allocate_pio(
        &manager, NULL, 2, assigned,
        &allocation_id, &block, &sm
    ) == RESOURCE_GPIO_EXHAUSTED);

    /* Der verbliebene GPIO darf nicht teilweise reserviert sein. */
    assert(resource_manager_gpio_is_available(&manager, 28));

    /* Nach Freigabe der Einzelreservierungen muss es funktionieren. */
    for (uint8_t pin = 0; pin < DEVICE_GPIO_COUNT; pin++) {
        if (pin == 28 ||
            (pin > 22 && pin < 26) ||
            pin > 28) {
            continue;
        }

        assert(resource_manager_release_pio_gpio(
            &manager, pin
        ));
    }

    assert(resource_manager_allocate_pio(
        &manager, NULL, 2, assigned,
        &allocation_id, &block, &sm
    ) == RESOURCE_OK);

    assert(resource_manager_release_pio(
        &manager, allocation_id
    ));
}

static void test_signal_generator_pin_allocation(void)
{
    resource_manager_t manager;
    device_config_t config;
    uint8_t pin = 12;
    uint8_t assigned;
    uint8_t allocation_id;
    uint8_t block;
    uint8_t sm;

    device_config_init(&config);

    config.pins[pin].function = PIN_SIGNAL_GENERATOR;

    resource_manager_init(&manager);
    assert(resource_manager_apply_config(
        &manager, &config
    ) == RESOURCE_OK);

    assert(resource_manager_allocate_pio(
        &manager, &pin, 1, &assigned,
        &allocation_id, &block, &sm
    ) == RESOURCE_OK);

    assert(assigned == pin);
    assert(manager.gpio[pin].assigned);
    assert(manager.gpio[pin].pio_claimed);
    assert(!resource_manager_gpio_is_available(&manager, pin));

    assert(resource_manager_release_pio(
        &manager, allocation_id
    ));

    assert(manager.gpio[pin].assigned);
    assert(!manager.gpio[pin].pio_claimed);
    assert(!resource_manager_gpio_is_available(&manager, pin));
}

int main(void)
{
    test_manual_allocation();
    test_automatic_allocation_priority();
    test_invalid_manual_allocation();
    test_config_update_preserves_allocation();
    test_pio_state_machine_exhaustion();
    test_allocation_conflict_is_atomic();
    test_automatic_gpio_exhaustion();
    test_signal_generator_pin_allocation();

    puts("All PIO allocation tests passed.");
    return 0;
}
