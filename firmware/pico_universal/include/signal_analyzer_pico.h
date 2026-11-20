#ifndef SIGNAL_ANALYZER_PICO_H
#define SIGNAL_ANALYZER_PICO_H

#include "resource_manager.h"

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    bool valid;
    uint8_t pin;
    uint64_t period_us;
    uint64_t high_time_us;
    float frequency_hz;
    float duty_percent;
    uint32_t sequence;
} signal_analyzer_measurement_t;

bool signal_analyzer_start_pico(
    resource_manager_t *manager,
    uint8_t pin
);

bool signal_analyzer_stop_pico(void);

bool signal_analyzer_get_measurement(
    signal_analyzer_measurement_t *measurement
);

void signal_analyzer_set_stream(bool enabled);
bool signal_analyzer_get_stream(void);

#endif
