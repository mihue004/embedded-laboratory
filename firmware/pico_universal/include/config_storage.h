#ifndef CONFIG_STORAGE_H
#define CONFIG_STORAGE_H

#include <stdbool.h>
#include "device_config.h"

bool config_storage_load(device_config_t *config);
bool config_storage_save(const device_config_t *config);

void config_storage_debug(void);

#endif
