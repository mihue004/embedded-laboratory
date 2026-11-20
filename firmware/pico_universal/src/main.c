#include "device_config.h"
#include "device_runtime_pico.h"
#include "resource_manager.h"
#include "signal_analyzer_pico.h"
#include "signal_generator_pico.h"
#include "config_storage.h"

#include "hardware/gpio.h"
#include "pico/stdlib.h"

#include <stdio.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>

static resource_manager_t manager;
static device_config_t config;

static void print_help(void)
{
    printf("COMMANDS\n");
    printf("PIN,<pin>,<INPUT|OUTPUT|GEN|ANALYZER>\n");
    printf("SIG,<pin>,<frequency_hz>,<duty_percent>\n");
    printf("ANALYZE,<pin>\n");
    printf("STOP\n");
    printf("READ,<pin>\n");
    printf("WRITE,<pin>,<0|1>\n");
    printf("MEASURE\n");
    printf("STREAM,<0|1>\n");
    printf("STATUS\n");
    printf("HELP\n");
    printf("I2C,<instance>,<baudrate>\n");
    printf("SPI,<instance>,<baudrate>,<bits>,<cpol>,<cpha>,<lsb>\n");
    printf("UART,<instance>,<baudrate>,<bits>,<stopbits>,<parity>\n");
}

static bool parse_pin_function(
    const char *name,
    device_pin_function_t *function
)
{
    if (strcmp(name, "INPUT") == 0) {
        *function = PIN_GPIO_INPUT;
    } else if (strcmp(name, "OUTPUT") == 0) {
        *function = PIN_GPIO_OUTPUT;
    } else if (strcmp(name, "GEN") == 0) {
        *function = PIN_SIGNAL_GENERATOR;
    } else if (strcmp(name, "ANALYZER") == 0) {
        *function = PIN_SIGNAL_ANALYZER;
    } else {
        return false;
    }

    return true;
}

static bool parse_unsigned(
    const char *text,
    unsigned long maximum,
    unsigned long *value
);

static bool apply_and_save_config(const device_config_t *next)
{
    if (next == NULL || !device_config_validate(next)) {
        printf("ERR,INVALID_CONFIG\n");
        return false;
    }

    device_config_t previous = config;

    resource_status_t result =
        device_runtime_apply_config_pico(&manager, next);

    if (result != RESOURCE_OK) {
        printf("ERR,CONFIG,%d\n", (int)result);
        return false;
    }

    if (!config_storage_save(next)) {
        printf("ERR,CONFIG_SAVE\n");

        resource_status_t rollback =
            device_runtime_apply_config_pico(&manager, &previous);

        if (rollback != RESOURCE_OK) {
            printf("ERR,CONFIG_ROLLBACK,%d\n", (int)rollback);
        }

        return false;
    }

    config = *next;
    printf("CONFIG,SAVED\n");
    return true;
}

static void command_pin(char *arguments)
{
    if (arguments == NULL) {
        printf("ERR,USAGE,PIN,<pin>,<function>\n");
        return;
    }

    char *pin_text = arguments;
    char *separator = strchr(pin_text, ',');
    if (separator == NULL) {
        printf("ERR,USAGE,PIN,<pin>,<function>\n");
        return;
    }
    *separator++ = '\0';

    char *function_text = separator;
    if (*function_text == '\0' || strchr(function_text, ',') != NULL) {
        printf("ERR,USAGE,PIN,<pin>,<function>\n");
        return;
    }

    unsigned long pin_value;
    if (!parse_unsigned(pin_text, DEVICE_GPIO_COUNT - 1, &pin_value)) {
        printf("ERR,INVALID_PIN\n");
        return;
    }

    device_pin_function_t function;
    if (!parse_pin_function(function_text, &function)) {
        printf("ERR,INVALID_FUNCTION\n");
        return;
    }

    device_config_t next_config = config;
    device_pin_config_t *pin_config = &next_config.pins[pin_value];

    pin_config->function = function;
    pin_config->peripheral_instance = 0;
    pin_config->pull = GPIO_PULL_NONE;
    pin_config->initial_level = GPIO_LEVEL_LOW;
    pin_config->input_filter_us = 0;

    if (!device_config_validate(&next_config)) {
        printf("ERR,INVALID_CONFIG\n");
        return;
    }

    if (!apply_and_save_config(&next_config)) {
        return;
    }

    printf("OK,PIN,%lu,%s\n", pin_value, function_text);
}

static bool parse_unsigned(
    const char *text,
    unsigned long maximum,
    unsigned long *value
)
{
    if (text == NULL || *text == '\0' || *text == '-') {
        return false;
    }

    errno = 0;
    char *end = NULL;
    unsigned long parsed = strtoul(text, &end, 10);

    if (errno == ERANGE ||
        end == text ||
        *end != '\0' ||
        parsed > maximum) {
        return false;
    }

    *value = parsed;
    return true;
}

static void command_signal(char *arguments)
{
    if (arguments == NULL) {
        printf("ERR,USAGE,SIG,<pin>,<frequency>,<duty>\n");
        return;
    }

    char *pin_text = arguments;
    char *separator = strchr(pin_text, ',');
    if (separator == NULL) {
        printf("ERR,USAGE,SIG,<pin>,<frequency>,<duty>\n");
        return;
    }
    *separator++ = '\0';

    char *frequency_text = separator;
    separator = strchr(frequency_text, ',');
    if (separator == NULL) {
        printf("ERR,USAGE,SIG,<pin>,<frequency>,<duty>\n");
        return;
    }
    *separator++ = '\0';

    char *duty_text = separator;
    if (strchr(duty_text, ',') != NULL) {
        printf("ERR,USAGE,SIG,<pin>,<frequency>,<duty>\n");
        return;
    }

    unsigned long pin;
    unsigned long frequency;
    unsigned long duty;

    if (!parse_unsigned(pin_text, DEVICE_GPIO_COUNT - 1, &pin) ||
        !parse_unsigned(frequency_text, UINT32_MAX, &frequency) ||
        !parse_unsigned(duty_text, UINT8_MAX, &duty)) {
        printf("ERR,INVALID_ARGUMENT\n");
        return;
    }

    if (frequency == 0 || duty > 100) {
        printf("ERR,INVALID_SIGNAL\n");
        return;
    }

    if (!signal_generator_start_pico(
            &manager,
            (uint8_t)pin,
            (uint32_t)frequency,
            (uint8_t)duty)) {
        printf("ERR,SIGNAL_START\n");
        return;
    }

    printf(
        "OK,SIGNAL,GPIO=%lu,FREQ=%lu,DUTY=%lu\n",
        pin, frequency, duty
    );
}

static void command_analyze(char *arguments)
{
    unsigned long pin;

    if (arguments == NULL ||
        strchr(arguments, ',') != NULL ||
        !parse_unsigned(arguments, DEVICE_GPIO_COUNT - 1, &pin)) {
        printf("ERR,USAGE,ANALYZE,<pin>\n");
        return;
    }

    if (!signal_analyzer_start_pico(&manager, (uint8_t)pin)) {
        printf("ERR,ANALYZER_START\n");
        return;
    }

    printf("OK,ANALYZE,%lu\n", pin);
}

static void command_read(char *arguments)
{
    unsigned long pin;

    if (arguments == NULL ||
        strchr(arguments, ',') != NULL ||
        !parse_unsigned(arguments, DEVICE_GPIO_COUNT - 1, &pin)) {
        printf("ERR,USAGE,READ,<pin>\n");
        return;
    }

    if (!manager.gpio[pin].assigned ||
        manager.gpio[pin].function != PIN_GPIO_INPUT) {
        printf("ERR,PIN_NOT_INPUT\n");
        return;
    }

    printf("VALUE,%lu,%u\n", pin, gpio_get((uint)pin) ? 1u : 0u);
}

static void command_write(char *arguments)
{
    if (arguments == NULL) {
        printf("ERR,USAGE,WRITE,<pin>,<0|1>\n");
        return;
    }

    char *pin_text = arguments;
    char *separator = strchr(pin_text, ',');
    if (separator == NULL) {
        printf("ERR,USAGE,WRITE,<pin>,<0|1>\n");
        return;
    }
    *separator++ = '\0';

    char *level_text = separator;
    if (strchr(level_text, ',') != NULL) {
        printf("ERR,USAGE,WRITE,<pin>,<0|1>\n");
        return;
    }

    unsigned long pin;
    unsigned long level;

    if (!parse_unsigned(pin_text, DEVICE_GPIO_COUNT - 1, &pin) ||
        !parse_unsigned(level_text, 1, &level)) {
        printf("ERR,INVALID_ARGUMENT\n");
        return;
    }

    if (!manager.gpio[pin].assigned ||
        manager.gpio[pin].function != PIN_GPIO_OUTPUT) {
        printf("ERR,PIN_NOT_OUTPUT\n");
        return;
    }

    gpio_put((uint)pin, level != 0);
    printf("OK,WRITE,GPIO=%lu,VALUE=%lu\n", pin, level);
}

static void command_measure(void)
{
    signal_analyzer_measurement_t measurement;

    if (!signal_analyzer_get_measurement(&measurement)) {
        printf("MEASURE,NO_DATA\n");
        return;
    }

    printf(
        "MEASURE,%u,%llu,%llu,%.3f,%.2f,%lu\n",
        measurement.pin,
        (unsigned long long)measurement.period_us,
        (unsigned long long)measurement.high_time_us,
        measurement.frequency_hz,
        measurement.duty_percent,
        (unsigned long)measurement.sequence
    );
}

static void command_status(void)
{
    signal_generator_status_t generator;
    signal_generator_get_status(&generator);

    printf(
        "STATUS,ACTIVE=%u,GPIO=%u,FREQ=%lu,DUTY=%u\n",
        generator.active ? 1u : 0u,
        generator.active ? generator.pin : 0u,
        generator.active ? (unsigned long)generator.frequency_hz : 0ul,
        generator.active ? generator.duty_percent : 0u
    );
}

static bool parse_values(
    char *arguments,
    unsigned long *values,
    const unsigned long *limits,
    size_t count)
{
    if (arguments == NULL) {
        return false;
    }

    char *current = arguments;

    for (size_t i = 0; i < count; ++i) {
        char *separator = strchr(current, ',');

        if (i < count - 1) {
            if (separator == NULL) {
                return false;
            }
            *separator = '\0';
        } else if (separator != NULL) {
            return false;
        }

        if (!parse_unsigned(current, limits[i], &values[i])) {
            return false;
        }

        if (i < count - 1) {
            current = separator + 1;
        }
    }

    return true;
}

static bool save_peripheral_config(const device_config_t *next)
{
    return apply_and_save_config(next);
}

static void command_i2c(char *arguments)
{
    unsigned long values[2];
    const unsigned long limits[] = {1, 1000000};

    if (!parse_values(arguments, values, limits, 2) ||
        values[1] == 0) {
        printf("ERR,USAGE,I2C,<instance>,<baudrate>\n");
        return;
    }

    device_config_t next = config;
    next.peripherals.i2c[values[0]].baudrate = values[1];

    if (save_peripheral_config(&next)) {
        printf("OK,I2C,%lu,%lu\n", values[0], values[1]);
    }
}

static void command_spi(char *arguments)
{
    unsigned long values[6];
    const unsigned long limits[] = {
        1, 10000000, 16, 1, 1, 1
    };

    if (!parse_values(arguments, values, limits, 6) ||
        values[1] == 0 || values[2] < 4) {
        printf("ERR,USAGE,SPI,<instance>,<baudrate>,<bits>,<cpol>,<cpha>,<lsb>\n");
        return;
    }

    device_config_t next = config;
    device_spi_config_t *settings =
        &next.peripherals.spi[values[0]];

    settings->baudrate = values[1];
    settings->data_bits = values[2];
    settings->cpol = values[3];
    settings->cpha = values[4];
    settings->lsb_first = values[5] != 0;

    if (save_peripheral_config(&next)) {
        printf("OK,SPI,%lu\n", values[0]);
    }
}

static void command_uart(char *arguments)
{
    unsigned long values[5];
    const unsigned long limits[] = {
        1, 4000000, 8, 2, 2
    };

    if (!parse_values(arguments, values, limits, 5) ||
        values[1] == 0 || values[2] < 5 || values[3] == 0) {
        printf("ERR,USAGE,UART,<instance>,<baudrate>,<bits>,<stopbits>,<parity>\n");
        return;
    }

    device_config_t next = config;
    device_uart_config_t *settings =
        &next.peripherals.uart[values[0]];

    settings->baudrate = values[1];
    settings->data_bits = values[2];
    settings->stop_bits = values[3];
    settings->parity = (device_uart_parity_t)values[4];

    if (save_peripheral_config(&next)) {
        printf("OK,UART,%lu\n", values[0]);
    }
}

static void process_command(char *line)
{
    char *arguments = strchr(line, ',');
    if (arguments != NULL) {
        *arguments++ = '\0';
    }

    char *command = line;

    if (*command == '\0') {
        return;
    }

    if (strcmp(command, "HELP") == 0) {
        if (arguments == NULL || *arguments == '\0') {
            print_help();
        } else {
            printf("ERR,UNEXPECTED_ARGUMENT\n");
        }
    } else if (strcmp(command, "PIN") == 0) {
        command_pin(arguments);
    } else if (strcmp(command, "SIG") == 0) {
        command_signal(arguments);
    } else if (strcmp(command, "ANALYZE") == 0) {
        command_analyze(arguments);
    } else if (strcmp(command, "I2C") == 0) {
        command_i2c(arguments);
    } else if (strcmp(command, "SPI") == 0) {
        command_spi(arguments);
    } else if (strcmp(command, "UART") == 0) {
        command_uart(arguments);
    } else if (strcmp(command, "STOP") == 0) {
        if (arguments != NULL && *arguments != '\0') {
            printf("ERR,UNEXPECTED_ARGUMENT\n");
            return;
        }

        bool generator_stopped =
            signal_generator_stop_pico(&manager);
        bool analyzer_stopped = signal_analyzer_stop_pico();

        if (generator_stopped && analyzer_stopped) {
            printf("OK,STOPPED\n");
        } else {
            printf("ERR,STOP_FAILED\n");
        }
    } else if (strcmp(command, "READ") == 0) {
        command_read(arguments);
    } else if (strcmp(command, "WRITE") == 0) {
        command_write(arguments);
    } else if (strcmp(command, "MEASURE") == 0) {
        if (arguments == NULL || *arguments == '\0') {
            command_measure();
        } else {
            printf("ERR,UNEXPECTED_ARGUMENT\n");
        }
    } else if (strcmp(command, "STREAM") == 0) {
        unsigned long enabled;

        if (arguments == NULL ||
            strchr(arguments, ',') != NULL ||
            !parse_unsigned(arguments, 1, &enabled)) {
            printf("ERR,USAGE,STREAM,<0|1>\n");
            return;
        }

        signal_analyzer_set_stream(enabled != 0);
        printf(
            "OK,STREAM,%u\n",
            signal_analyzer_get_stream() ? 1u : 0u
        );
    } else if (strcmp(command, "STATUS") == 0) {
        if (arguments == NULL || *arguments == '\0') {
            command_status();
        } else {
            printf("ERR,UNEXPECTED_ARGUMENT\n");
        }
    } else {
        printf("ERR,UNKNOWN_COMMAND\n");
    }
}

int main(void)
{
    stdio_init_all();

    resource_manager_init(&manager);
    device_config_init(&config);

    if (config_storage_load(&config)) {
        if (device_runtime_apply_config_pico(&manager, &config)) {
            printf("CONFIG,LOADED\n");
        } else {
            device_config_init(&config);
            device_runtime_apply_config_pico(&manager, &config);
            printf("CONFIG,DEFAULT\n");
        }
    } else {
        device_runtime_apply_config_pico(&manager, &config);
        printf("CONFIG,DEFAULT\n");
    }

    printf("READY,TESTBENCH,1\n");

    char line[128];
    size_t length = 0;

    while (true) {
        int character = getchar_timeout_us(1000);

        if (character == PICO_ERROR_TIMEOUT) {
            if (signal_analyzer_get_stream()) {
                static uint32_t last_sequence;
                signal_analyzer_measurement_t measurement;

                if (signal_analyzer_get_measurement(&measurement) &&
                    measurement.sequence != last_sequence) {
                    last_sequence = measurement.sequence;
                    command_measure();
                }
            }
            continue;
        }

        if (character == '\r') {
            continue;
        }

        if (character == '\n') {
            line[length] = '\0';
            process_command(line);
            length = 0;
            continue;
        }

        if (length < sizeof(line) - 1) {
            line[length++] = (char)character;
        } else {
            length = 0;
            printf("ERR,LINE_TOO_LONG\n");
        }
    }

    return 0;
}
