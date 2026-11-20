#include "gpio_configurator.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    unsigned int init_count;
    unsigned int pull_count;
    unsigned int put_count;
    unsigned int direction_count;

    uint8_t last_pin;
    device_gpio_pull_t last_pull;
    device_gpio_level_t last_level;
    gpio_config_direction_t last_direction;

    int fail_operation;
    unsigned int operation_count;
} mock_t;

static bool should_fail(mock_t *mock)
{
    mock->operation_count++;
    return mock->fail_operation != 0 &&
           mock->operation_count == (unsigned int)mock->fail_operation;
}

static bool mock_init(void *context, uint8_t pin)
{
    mock_t *mock = context;
    mock->init_count++;
    mock->last_pin = pin;
    return !should_fail(mock);
}

static bool mock_pull(
    void *context,
    uint8_t pin,
    device_gpio_pull_t pull
)
{
    mock_t *mock = context;
    mock->pull_count++;
    mock->last_pin = pin;
    mock->last_pull = pull;
    return !should_fail(mock);
}

static bool mock_put(
    void *context,
    uint8_t pin,
    device_gpio_level_t level
)
{
    mock_t *mock = context;
    mock->put_count++;
    mock->last_pin = pin;
    mock->last_level = level;
    return !should_fail(mock);
}

static bool mock_direction(
    void *context,
    uint8_t pin,
    gpio_config_direction_t direction
)
{
    mock_t *mock = context;
    mock->direction_count++;
    mock->last_pin = pin;
    mock->last_direction = direction;
    return !should_fail(mock);
}

static const gpio_configurator_ops_t mock_ops = {
    .init = mock_init,
    .set_pull = mock_pull,
    .put = mock_put,
    .set_direction = mock_direction
};

static void test_input_configuration(void)
{
    device_config_t config;
    mock_t mock = {0};

    device_config_init(&config);
    config.pins[0].function = PIN_GPIO_INPUT;
    config.pins[0].pull = GPIO_PULL_UP;

    assert(gpio_configurator_apply(&config, &mock_ops, &mock));
    assert(mock.init_count == 1);
    assert(mock.pull_count == 1);
    assert(mock.put_count == 0);
    assert(mock.direction_count == 1);
    assert(mock.last_direction == GPIO_CONFIG_INPUT);
    assert(mock.last_pull == GPIO_PULL_UP);
}

static void test_output_configuration(void)
{
    device_config_t config;
    mock_t mock = {0};

    device_config_init(&config);
    config.pins[1].function = PIN_GPIO_OUTPUT;
    config.pins[1].initial_level = GPIO_LEVEL_HIGH;

    assert(gpio_configurator_apply(&config, &mock_ops, &mock));
    assert(mock.init_count == 1);
    assert(mock.pull_count == 1);
    assert(mock.put_count == 1);
    assert(mock.direction_count == 1);
    assert(mock.last_level == GPIO_LEVEL_HIGH);
    assert(mock.last_direction == GPIO_CONFIG_OUTPUT);
}

static void test_signal_pins(void)
{
    device_config_t config;
    mock_t mock = {0};

    device_config_init(&config);
    config.pins[2].function = PIN_SIGNAL_GENERATOR;

    config.pins[3].function = PIN_SIGNAL_ANALYZER;

    assert(gpio_configurator_apply(&config, &mock_ops, &mock));
    assert(mock.init_count == 2);
    assert(mock.put_count == 1);
    assert(mock.direction_count == 2);
}

static void test_unused_and_peripheral_pins_are_skipped(void)
{
    device_config_t config;
    mock_t mock = {0};

    device_config_init(&config);
    config.pins[0].function = PIN_I2C_SDA;
    config.pins[1].function = PIN_I2C_SCL;

    assert(gpio_configurator_apply(&config, &mock_ops, &mock));
    assert(mock.init_count == 0);
}

static void test_invalid_config_rejected(void)
{
    device_config_t config;
    mock_t mock = {0};

    device_config_init(&config);
    config.pins[0].function = PIN_GPIO_INPUT;
    config.pins[0].pull = (device_gpio_pull_t)99;

    assert(!gpio_configurator_apply(&config, &mock_ops, &mock));
    assert(mock.operation_count == 0);
}

static void test_hardware_error_propagated(void)
{
    device_config_t config;
    mock_t mock = {0};

    device_config_init(&config);
    config.pins[0].function = PIN_GPIO_OUTPUT;
    mock.fail_operation = 3;

    assert(!gpio_configurator_apply(&config, &mock_ops, &mock));
    assert(mock.init_count == 1);
    assert(mock.pull_count == 1);
    assert(mock.put_count == 1);
    assert(mock.direction_count == 0);
}

static void test_missing_operations_rejected(void)
{
    device_config_t config;
    mock_t mock = {0};
    gpio_configurator_ops_t incomplete = mock_ops;

    device_config_init(&config);
    incomplete.put = NULL;

    assert(!gpio_configurator_apply(&config, &incomplete, &mock));
    assert(mock.operation_count == 0);
}

int main(void)
{
    test_input_configuration();
    test_output_configuration();
    test_signal_pins();
    test_unused_and_peripheral_pins_are_skipped();
    test_invalid_config_rejected();
    test_hardware_error_propagated();
    test_missing_operations_rejected();

    puts("All GPIO configurator tests passed.");
    return 0;
}
