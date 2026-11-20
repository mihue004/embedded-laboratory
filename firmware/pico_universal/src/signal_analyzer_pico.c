#include "signal_analyzer_pico.h"

#include "hardware/gpio.h"
#include "hardware/sync.h"
#include "pico/time.h"

#include <string.h>

static volatile bool analyzer_active;
static volatile bool analyzer_stream;
static volatile uint8_t analyzer_pin;

static volatile bool have_rising_edge;
static volatile bool have_falling_edge;

static volatile uint64_t last_rising_us;
static volatile uint64_t pending_high_time_us;

static volatile bool measurement_valid;
static volatile uint64_t measured_period_us;
static volatile uint64_t measured_high_time_us;
static volatile uint32_t measurement_sequence;

static void signal_analyzer_gpio_callback(
    uint gpio,
    uint32_t events
)
{
    if (!analyzer_active || gpio != analyzer_pin) {
        return;
    }

    uint64_t now = time_us_64();

    if (events & GPIO_IRQ_EDGE_RISE) {
        if (have_rising_edge && have_falling_edge) {
            uint64_t period = now - last_rising_us;
            uint64_t high_time = pending_high_time_us;

            if (period > 0 && high_time > 0 && high_time < period) {
                measured_period_us = period;
                measured_high_time_us = high_time;
                measurement_sequence++;
                measurement_valid = true;
            }
        }

        last_rising_us = now;
        have_rising_edge = true;
        have_falling_edge = false;
    }

    if ((events & GPIO_IRQ_EDGE_FALL) && have_rising_edge) {
        uint64_t high_time = now - last_rising_us;

        if (high_time > 0) {
            pending_high_time_us = high_time;
            have_falling_edge = true;
        }
    }
}

bool signal_analyzer_start_pico(
    resource_manager_t *manager,
    uint8_t pin
)
{
    if (manager == NULL || pin >= DEVICE_GPIO_COUNT) {
        return false;
    }

    if (!manager->gpio[pin].assigned ||
        manager->gpio[pin].function != PIN_SIGNAL_ANALYZER ||
        manager->gpio[pin].pio_claimed) {
        return false;
    }

    if (analyzer_active && !signal_analyzer_stop_pico()) {
        return false;
    }

    uint32_t irq_mask =
        GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL;

    gpio_init(pin);
    gpio_set_dir(pin, GPIO_IN);
    gpio_disable_pulls(pin);

    analyzer_pin = pin;
    have_rising_edge = false;
    have_falling_edge = false;
    last_rising_us = 0;
    pending_high_time_us = 0;

    measurement_valid = false;
    measured_period_us = 0;
    measured_high_time_us = 0;
    measurement_sequence = 0;

    analyzer_active = true;

    gpio_set_irq_enabled_with_callback(
        pin,
        irq_mask,
        true,
        signal_analyzer_gpio_callback
    );

    return true;
}

bool signal_analyzer_stop_pico(void)
{
    uint32_t interrupt_state = save_and_disable_interrupts();

    if (!analyzer_active) {
        analyzer_stream = false;
        restore_interrupts(interrupt_state);
        return true;
    }

    uint8_t pin = analyzer_pin;

    analyzer_active = false;
    analyzer_stream = false;

    gpio_set_irq_enabled(
        pin,
        GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL,
        false
    );

    gpio_set_function(pin, GPIO_FUNC_SIO);
    gpio_init(pin);
    gpio_set_dir(pin, GPIO_IN);

    have_rising_edge = false;
    have_falling_edge = false;
    measurement_valid = false;

    restore_interrupts(interrupt_state);

    return true;
}

bool signal_analyzer_get_measurement(
    signal_analyzer_measurement_t *measurement
)
{
    if (measurement == NULL) {
        return false;
    }

    uint32_t interrupt_state = save_and_disable_interrupts();

    bool valid = measurement_valid;

    if (valid) {
        measurement->valid = true;
        measurement->pin = analyzer_pin;
        measurement->period_us = measured_period_us;
        measurement->high_time_us = measured_high_time_us;
        measurement->frequency_hz =
            1000000.0f / (float)measured_period_us;
        measurement->duty_percent =
            ((float)measured_high_time_us * 100.0f) /
            (float)measured_period_us;
        measurement->sequence = measurement_sequence;
    }

    restore_interrupts(interrupt_state);

    return valid;
}

void signal_analyzer_set_stream(bool enabled)
{
    analyzer_stream = enabled;
}

bool signal_analyzer_get_stream(void)
{
    return analyzer_stream;
}
