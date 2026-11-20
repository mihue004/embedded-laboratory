#ifndef SIGNAL_GENERATOR_PICO_H
#define SIGNAL_GENERATOR_PICO_H

#include "resource_manager.h"

#include <stdbool.h>
#include <stdint.h>

#define SIGNAL_GENERATOR_MIN_FREQUENCY 1u
#define SIGNAL_GENERATOR_MAX_FREQUENCY 10000u
#define SIGNAL_GENERATOR_MIN_DUTY 1u
#define SIGNAL_GENERATOR_MAX_DUTY 99u

typedef struct {
    bool active;
    uint8_t pin;
    uint32_t frequency_hz;
    uint8_t duty_percent;
    uint8_t allocation_id;
    uint8_t pio_block;
    uint8_t state_machine;
} signal_generator_status_t;

bool signal_generator_start_pico(
    resource_manager_t *manager,
    uint8_t pin,
    uint32_t frequency_hz,
    uint8_t duty_percent
);

bool signal_generator_stop_pico(resource_manager_t *manager);

void signal_generator_get_status(
    signal_generator_status_t *status
);

#endif
