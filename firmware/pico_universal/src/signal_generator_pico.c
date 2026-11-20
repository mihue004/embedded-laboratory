#include "signal_generator_pico.h"

#include "pio_runtime_pico.h"
#include "squarewave.pio.h"

#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"

#include <string.h>

#define SIGNAL_GENERATOR_PERIOD_CYCLES 10000u

static signal_generator_status_t generator_status;
static uint8_t program_offset;
static bool program_loaded;

bool signal_generator_stop_pico(resource_manager_t *manager)
{
    if (!generator_status.active && !program_loaded) {
        return true;
    }

    if (generator_status.pio_block >= RESOURCE_PIO_BLOCK_COUNT ||
        generator_status.state_machine >= RESOURCE_PIO_SM_PER_BLOCK ||
        generator_status.pin >= DEVICE_GPIO_COUNT ||
        generator_status.allocation_id >= RESOURCE_PIO_ALLOCATION_COUNT) {
        return false;
    }

    if (manager == NULL) {
        return false;
    }

    PIO pio = pio_get_instance(generator_status.pio_block);
    uint8_t sm = generator_status.state_machine;
    uint8_t pin = generator_status.pin;
    uint8_t allocation_id = generator_status.allocation_id;

    pio_sm_set_enabled(pio, sm, false);
    pio_sm_clear_fifos(pio, sm);

    if (manager->pio_allocations[allocation_id].active) {
        bool released = pio_runtime_release_pico(
            manager,
            allocation_id
        );

        /*
         * A failed release can mean that synchronization already
         * removed an externally released allocation. Only continue
         * if the allocation is actually inactive now.
         */
        if (!released &&
            manager->pio_allocations[allocation_id].active) {
            return false;
        }
    }

    gpio_set_function(pin, GPIO_FUNC_SIO);
    gpio_init(pin);
    gpio_put(pin, 0);
    gpio_set_dir(pin, GPIO_OUT);

    if (program_loaded) {
        pio_remove_program(
            pio,
            &squarewave_program,
            program_offset
        );
    }

    memset(&generator_status, 0, sizeof(generator_status));
    program_loaded = false;
    program_offset = 0;

    return true;
}

bool signal_generator_start_pico(
    resource_manager_t *manager,
    uint8_t pin,
    uint32_t frequency_hz,
    uint8_t duty_percent
)
{
    if (manager == NULL ||
        pin >= DEVICE_GPIO_COUNT ||
        frequency_hz < SIGNAL_GENERATOR_MIN_FREQUENCY ||
        frequency_hz > SIGNAL_GENERATOR_MAX_FREQUENCY ||
        duty_percent < SIGNAL_GENERATOR_MIN_DUTY ||
        duty_percent > SIGNAL_GENERATOR_MAX_DUTY) {
        return false;
    }

    if (!manager->gpio[pin].assigned ||
        manager->gpio[pin].function != PIN_SIGNAL_GENERATOR) {
        return false;
    }

    bool same_active_pin =
        generator_status.active &&
        generator_status.pin == pin;

    if (manager->gpio[pin].pio_claimed && !same_active_pin) {
        return false;
    }

    /*
     * Stop the previous signal before allocating the new one.
     * This also supports changing frequency and duty cycle
     * while keeping the same configured GPIO.
     */
    if (generator_status.active || program_loaded) {
        if (!signal_generator_stop_pico(manager)) {
            return false;
        }
    }

    if (manager->gpio[pin].pio_claimed) {
        return false;
    }

    uint8_t assigned_pin = 0;
    uint8_t allocation_id = 0;

    resource_status_t result = pio_runtime_allocate_pico(
        manager,
        &pin,
        1,
        &assigned_pin,
        &allocation_id
    );

    if (result != RESOURCE_OK) {
        return false;
    }

    if (assigned_pin != pin ||
        allocation_id >= RESOURCE_PIO_ALLOCATION_COUNT ||
        !manager->pio_allocations[allocation_id].active) {
        pio_runtime_release_pico(manager, allocation_id);
        return false;
    }

    resource_pio_allocation_t *allocation =
        &manager->pio_allocations[allocation_id];

    uint8_t block = allocation->pio_block;
    uint8_t sm = allocation->state_machine;

    if (block >= RESOURCE_PIO_BLOCK_COUNT ||
        sm >= RESOURCE_PIO_SM_PER_BLOCK) {
        pio_runtime_release_pico(manager, allocation_id);
        return false;
    }

    PIO pio = pio_get_instance(block);

    generator_status.active = true;
    generator_status.pin = pin;
    generator_status.frequency_hz = frequency_hz;
    generator_status.duty_percent = duty_percent;
    generator_status.allocation_id = allocation_id;
    generator_status.pio_block = block;
    generator_status.state_machine = sm;

    if (!pio_can_add_program(pio, &squarewave_program)) {
        signal_generator_stop_pico(manager);
        return false;
    }

    program_offset = pio_add_program(pio, &squarewave_program);
    program_loaded = true;

    uint32_t high_cycles =
        (SIGNAL_GENERATOR_PERIOD_CYCLES * duty_percent + 50u) / 100u;

    uint32_t low_cycles =
        SIGNAL_GENERATOR_PERIOD_CYCLES - high_cycles;

    uint32_t high_count = high_cycles - 3u;
    uint32_t low_count = low_cycles - 3u;

    float divider =
        (float)clock_get_hz(clk_sys) /
        ((float)frequency_hz * SIGNAL_GENERATOR_PERIOD_CYCLES);

    pio_sm_config config =
        squarewave_program_get_default_config(program_offset);

    sm_config_set_set_pins(&config, pin, 1);
    sm_config_set_clkdiv(&config, divider);

    pio_sm_set_consecutive_pindirs(pio, sm, pin, 1, true);
    pio_sm_init(pio, sm, program_offset, &config);

    pio_sm_put_blocking(pio, sm, high_count);
    pio_sm_put_blocking(pio, sm, low_count);

    pio_sm_set_enabled(pio, sm, true);

    return true;
}

void signal_generator_get_status(
    signal_generator_status_t *status
)
{
    if (status == NULL) {
        return;
    }

    *status = generator_status;
}
