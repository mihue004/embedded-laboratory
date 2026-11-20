#ifndef PIO_RUNTIME_H
#define PIO_RUNTIME_H

#include "resource_manager.h"

typedef struct {
    bool (*is_sm_claimed)(
        void *context, uint8_t block, uint8_t sm
    );
    bool (*claim_sm)(
        void *context, uint8_t block, uint8_t sm
    );
    void (*unclaim_sm)(
        void *context, uint8_t block, uint8_t sm
    );
    bool (*set_gpio_pio)(
        void *context, uint8_t pin, uint8_t block
    );
    void (*set_gpio_sio)(
        void *context, uint8_t pin
    );
} pio_runtime_ops_t;

bool pio_runtime_sync(
    resource_manager_t *manager,
    const pio_runtime_ops_t *ops,
    void *context
);

resource_status_t pio_runtime_allocate(
    resource_manager_t *manager,
    const uint8_t *requested_pins,
    uint8_t pin_count,
    uint8_t *assigned_pins,
    uint8_t *allocation_id,
    const pio_runtime_ops_t *ops,
    void *context
);

bool pio_runtime_release(
    resource_manager_t *manager,
    uint8_t allocation_id,
    const pio_runtime_ops_t *ops,
    void *context
);

#endif
