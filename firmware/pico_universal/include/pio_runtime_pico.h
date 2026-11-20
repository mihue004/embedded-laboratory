#ifndef PIO_RUNTIME_PICO_H
#define PIO_RUNTIME_PICO_H

#include "pio_runtime.h"

bool pio_runtime_sync_pico(resource_manager_t *manager);

resource_status_t pio_runtime_allocate_pico(
    resource_manager_t *manager,
    const uint8_t *requested_pins,
    uint8_t pin_count,
    uint8_t *assigned_pins,
    uint8_t *allocation_id
);

bool pio_runtime_release_pico(
    resource_manager_t *manager,
    uint8_t allocation_id
);

#endif
