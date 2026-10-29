#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include "hardware/sync.h"

#define DEFAULT_SIGNAL_PIN 16
#define COMMAND_BUFFER_SIZE 80

static uint signal_pin = DEFAULT_SIGNAL_PIN;

static volatile uint64_t rising_time = 0;
static volatile uint64_t falling_time = 0;
static volatile uint64_t period_us = 0;
static volatile uint64_t high_us = 0;

static volatile bool have_rising = false;
static volatile bool have_falling = false;
static volatile bool measurement_ready = false;

static bool stream_enabled = false;
static bool measurement_requested = false;

static bool valid_gpio(unsigned int pin)
{
    return pin <= 22 || (pin >= 26 && pin <= 28);
}

static void reset_measurement_state(void)
{
    uint32_t irq_state = save_and_disable_interrupts();

    rising_time = 0;
    falling_time = 0;
    period_us = 0;
    high_us = 0;
    have_rising = false;
    have_falling = false;
    measurement_ready = false;

    restore_interrupts(irq_state);
}

static void signal_callback(uint gpio, uint32_t events)
{
    if (gpio != signal_pin) {
        return;
    }

    uint64_t now = time_us_64();

    if (events & GPIO_IRQ_EDGE_RISE) {
        if (have_rising && have_falling) {
            period_us = now - rising_time;
            high_us = falling_time - rising_time;
            measurement_ready = true;
        }

        rising_time = now;
        have_rising = true;
        have_falling = false;
    }

    if ((events & GPIO_IRQ_EDGE_FALL) && have_rising) {
        falling_time = now;
        have_falling = true;
    }
}

static void configure_input(uint pin)
{
    gpio_set_irq_enabled(pin,
                         GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL,
                         false);

    gpio_init(pin);
    gpio_set_dir(pin, GPIO_IN);
    gpio_disable_pulls(pin);

    reset_measurement_state();

    gpio_set_irq_enabled(pin,
                         GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL,
                         true);
}

static void print_status(void)
{
    printf("STATUS,GPIO=%u,STREAM=%u\n",
           signal_pin, stream_enabled ? 1u : 0u);
    stdio_flush();
}

static bool take_measurement(uint64_t *period, uint64_t *high)
{
    bool ready;

    uint32_t irq_state = save_and_disable_interrupts();
    ready = measurement_ready;

    if (ready) {
        *period = period_us;
        *high = high_us;
        measurement_ready = false;
    }

    restore_interrupts(irq_state);
    return ready;
}

static void print_measurement(uint64_t period, uint64_t high)
{
    if (period == 0 || high > period) {
        printf("ERR,INVALID_MEASUREMENT\n");
        stdio_flush();
        return;
    }

    double frequency = 1000000.0 / (double)period;
    double duty = 100.0 * (double)high / (double)period;

    printf("MEASURE,FREQ_HZ=%.2f,DUTY=%.2f,PERIOD_US=%llu,HIGH_US=%llu\n",
           frequency,
           duty,
           (unsigned long long)period,
           (unsigned long long)high);
    stdio_flush();
}

static void process_command(char *line)
{
    unsigned int pin;
    unsigned int enabled;

    if (strcmp(line, "STATUS") == 0) {
        print_status();
        return;
    }

    if (strcmp(line, "MEASURE") == 0) {
        measurement_requested = true;
        measurement_ready = false;
        printf("OK,MEASURE_PENDING\n");
        stdio_flush();
        return;
    }

    if (sscanf(line, "STREAM,%u", &enabled) == 1 &&
        strncmp(line, "STREAM,", 7) == 0) {
        if (enabled > 1) {
            printf("ERR,INVALID_PARAMETERS\n");
        } else {
            stream_enabled = enabled != 0;
            if (!stream_enabled) {
                measurement_requested = false;
            }
            printf("OK,STREAM,%u\n", enabled);
        }
        stdio_flush();
        return;
    }

    if (sscanf(line, "CONFIG,%u", &pin) == 1 &&
        strncmp(line, "CONFIG,", 7) == 0) {
        if (!valid_gpio(pin)) {
            printf("ERR,INVALID_GPIO\n");
            stdio_flush();
            return;
        }

        if (pin != signal_pin) {
            gpio_set_irq_enabled(signal_pin,
                                 GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL,
                                 false);
            signal_pin = pin;
            configure_input(signal_pin);
        } else {
            reset_measurement_state();
        }

        printf("OK,CONFIG,GPIO=%u\n", signal_pin);
        stdio_flush();
        return;
    }

    printf("ERR,UNKNOWN_COMMAND\n");
    stdio_flush();
}

int main(void)
{
    stdio_init_all();
    sleep_ms(2000);

    gpio_init(signal_pin);
    gpio_set_dir(signal_pin, GPIO_IN);
    gpio_disable_pulls(signal_pin);

    gpio_set_irq_enabled_with_callback(
        signal_pin,
        GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL,
        true,
        &signal_callback
    );

    printf("READY,ANALYZER,2\n");
    printf("INPUT,GPIO=%u\n", signal_pin);
    stdio_flush();

    char line[COMMAND_BUFFER_SIZE];
    size_t length = 0;

    while (true) {
        int ch = getchar_timeout_us(0);

        if (ch >= 0) {
            if (ch == '\r') {
                continue;
            }

            if (ch == '\n') {
                line[length] = '\0';

                if (length > 0) {
                    process_command(line);
                }

                length = 0;
            } else if (length < sizeof(line) - 1) {
                line[length++] = (char)ch;
            } else {
                length = 0;
                printf("ERR,COMMAND_TOO_LONG\n");
                stdio_flush();
            }
        }

        uint64_t period = 0;
        uint64_t high = 0;

        if (take_measurement(&period, &high)) {
            if (stream_enabled || measurement_requested) {
                print_measurement(period, high);
                measurement_requested = false;
            }
        }

        sleep_ms(1);
    }
}
