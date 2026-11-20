#include "device_runtime.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    bool result;
    unsigned int calls;
} mock_hardware_t;

static bool mock_apply(
    const device_config_t *config,
    void *context
)
{
    mock_hardware_t *mock = context;
    assert(device_config_validate(config));
    mock->calls++;
    return mock->result;
}

static void test_successful_apply(void)
{
    resource_manager_t manager;
    device_config_t config;
    mock_hardware_t mock = {.result = true};

    resource_manager_init(&manager);
    device_config_init(&config);

    config.pins[4].function = PIN_GPIO_OUTPUT;
    config.pins[4].initial_level = GPIO_LEVEL_HIGH;

    assert(device_runtime_apply_config(
        &manager, &config, mock_apply, &mock
    ) == RESOURCE_OK);

    assert(mock.calls == 1);
    assert(resource_manager_gpio_is_reserved(&manager, 4));
}

static void test_hardware_failure_is_not_committed(void)
{
    resource_manager_t manager;
    resource_manager_t before;
    device_config_t config;
    mock_hardware_t mock = {.result = false};

    resource_manager_init(&manager);
    before = manager;
    device_config_init(&config);

    config.pins[5].function = PIN_GPIO_OUTPUT;

    assert(device_runtime_apply_config(
        &manager, &config, mock_apply, &mock
    ) == RESOURCE_HARDWARE_ERROR);

    assert(mock.calls == 1);
    assert(memcmp(&manager, &before, sizeof(manager)) == 0);
}

static void test_resource_error_prevents_hardware_apply(void)
{
    resource_manager_t manager;
    device_config_t config;
    mock_hardware_t mock = {.result = true};

    resource_manager_init(&manager);
    device_config_init(&config);

    config.pins[0].function = PIN_I2C_SDA;

    assert(device_runtime_apply_config(
        &manager, &config, mock_apply, &mock
    ) == RESOURCE_INCOMPLETE_I2C);

    assert(mock.calls == 0);
}

static void test_pio_reservations_survive_apply(void)
{
    resource_manager_t manager;
    device_config_t config;
    mock_hardware_t mock = {.result = true};
    uint8_t pin = 7;
    uint8_t assigned[1];
    uint8_t allocation_id;
    uint8_t block;
    uint8_t sm;

    resource_manager_init(&manager);

    assert(resource_manager_allocate_pio(
        &manager, &pin, 1, assigned,
        &allocation_id, &block, &sm
    ) == RESOURCE_OK);

    device_config_init(&config);

    assert(device_runtime_apply_config(
        &manager, &config, mock_apply, &mock
    ) == RESOURCE_OK);

    assert(resource_manager_gpio_is_reserved(&manager, pin));
    assert(manager.pio_allocations[allocation_id].active);
}

int main(void)
{
    test_successful_apply();
    test_hardware_failure_is_not_committed();
    test_resource_error_prevents_hardware_apply();
    test_pio_reservations_survive_apply();

    puts("All device runtime tests passed.");
    return 0;
}
