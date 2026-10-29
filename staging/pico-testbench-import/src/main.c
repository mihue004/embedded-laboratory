#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "pico/stdlib.h"
#include "hardware/clocks.h"
#include "hardware/pio.h"
#include "squarewave.pio.h"

#define MIN_FREQ 1u
#define MAX_FREQ 10000u
#define PERIOD_CYCLES 10000u

static PIO pio = pio0;
static uint sm;
static uint offset;
static bool signal_active = false;
static uint signal_pin = 15;
static uint current_frequency = 0;
static uint current_duty = 0;

static bool valid_gpio(unsigned int pin)
{
    return pin <= 22 || (pin >= 26 && pin <= 28);
}

static void respond(const char *s)
{
    printf("%s\n", s);
    stdio_flush();
}

static void stop_signal(bool report_response)
{
    pio_sm_set_enabled(pio, sm, false);
    pio_sm_clear_fifos(pio, sm);

    if (signal_active) {
        gpio_init(signal_pin);
        gpio_put(signal_pin, 0);
        gpio_set_dir(signal_pin, GPIO_OUT);
    }

    signal_active = false;
    current_frequency = 0;
    current_duty = 0;
    if (report_response) respond("OK,STOPPED");
}

static void start_signal(unsigned int pin,
                         unsigned int frequency,
                         unsigned int duty)
{
    if (!valid_gpio(pin) ||
        frequency < MIN_FREQ || frequency > MAX_FREQ ||
        duty < 1 || duty > 99) {
        respond("ERR,INVALID_PARAMETERS");
        return;
    }

    pio_sm_set_enabled(pio, sm, false);
    pio_sm_clear_fifos(pio, sm);

    if (signal_active) {
        gpio_init(signal_pin);
        gpio_put(signal_pin, 0);
        gpio_set_dir(signal_pin, GPIO_OUT);
    }

    uint32_t high_cycles =
        (PERIOD_CYCLES * duty + 50u) / 100u;
    uint32_t low_cycles = PERIOD_CYCLES - high_cycles;

    uint32_t high_count = high_cycles - 3u;
    uint32_t low_count = low_cycles - 3u;

    float divider =
        (float)clock_get_hz(clk_sys) /
        ((float)frequency * (float)PERIOD_CYCLES);

    pio_gpio_init(pio, pin);

    pio_sm_config config =
        squarewave_program_get_default_config(offset);
    sm_config_set_set_pins(&config, pin, 1);
    sm_config_set_clkdiv(&config, divider);

    pio_sm_set_consecutive_pindirs(pio, sm, pin, 1, true);
    pio_sm_init(pio, sm, offset, &config);

    pio_sm_put_blocking(pio, sm, high_count);
    pio_sm_put_blocking(pio, sm, low_count);
    pio_sm_set_enabled(pio, sm, true);

    signal_pin = pin;
    signal_active = true;
    current_frequency = frequency;
    current_duty = duty;

    printf("OK,SIGNAL,GPIO=%u,FREQ=%u,DUTY=%u\n",
           pin, frequency, duty);
    stdio_flush();
}

static void process_command(char *line)
{
    unsigned int pin, value, frequency, duty;

    if (strcmp(line, "STATUS") == 0) {
        printf("STATUS,ACTIVE=%u,GPIO=%u,FREQ=%u,DUTY=%u\n",
               signal_active ? 1u : 0u,
               signal_pin, current_frequency, current_duty);
        stdio_flush();
        return;
    }

    if (strcmp(line, "STOP") == 0) {
        stop_signal(true);
        return;
    }

    if (sscanf(line, "WRITE,%u,%u", &pin, &value) == 2) {
        if (!valid_gpio(pin) || value > 1) {
            respond("ERR,INVALID_PARAMETERS");
            return;
        }

        if (signal_active) {
            stop_signal(false);
        }

        gpio_init(pin);
        gpio_put(pin, value);
        gpio_set_dir(pin, GPIO_OUT);

        printf("OK,WRITE,GPIO=%u,VALUE=%u\n", pin, value);
        stdio_flush();
        return;
    }

    if (sscanf(line, "READ,%u", &pin) == 1) {
        if (!valid_gpio(pin)) {
            respond("ERR,INVALID_GPIO");
            return;
        }

        if (signal_active && pin == signal_pin) {
            respond("ERR,PIN_IN_USE");
            return;
        }

        if (gpio_get_dir(pin) != GPIO_OUT) {
	    gpio_init(pin);
	    gpio_set_dir(pin, GPIO_IN);
	    gpio_pull_down(pin);
	}

        printf("VALUE,%u,%u\n", pin, gpio_get(pin) ? 1u : 0u);
        stdio_flush();
        return;
    }

    if (sscanf(line, "SIG,%u,%u,%u", &pin, &frequency, &duty) == 3) {
        start_signal(pin, frequency, duty);
        return;
    }

    respond("ERR,UNKNOWN_COMMAND");
}

int main(void)
{
    stdio_init_all();
    sleep_ms(2000);

    sm = pio_claim_unused_sm(pio, true);
    offset = pio_add_program(pio, &squarewave_program);

    respond("READY,TESTBENCH,1");

    char line[80];
    size_t length = 0;

    while (true) {
        int ch = getchar_timeout_us(0);

        if (ch < 0) {
            sleep_ms(1);
            continue;
        }

        if (ch == '\r') {
            continue;
        }

        if (ch == '\n') {
            line[length] = '\0';
            if (length > 0) {
                process_command(line);
            }
            length = 0;
            continue;
        }

        if (length < sizeof(line) - 1) {
            line[length++] = (char)ch;
        } else {
            length = 0;
            respond("ERR,COMMAND_TOO_LONG");
        }
    }
}
