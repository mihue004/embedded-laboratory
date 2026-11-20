#include "config_storage.h"

#include "hardware/flash.h"
#include "hardware/sync.h"
#include "pico/flash.h"
#include "pico/platform.h"
#include "pico/error.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define CONFIG_STORAGE_MAGIC       0x454C4142u
#define CONFIG_STORAGE_VERSION     1u

/* Raspberry Pi Pico 2: 4 MiB Flash */
#define CONFIG_FLASH_OFFSET \
    (4u * 1024u * 1024u - FLASH_SECTOR_SIZE)

#define CONFIG_DATA_SIZE \
    ((sizeof(config_storage_record_t) + FLASH_PAGE_SIZE - 1u) \
     / FLASH_PAGE_SIZE * FLASH_PAGE_SIZE)

typedef struct {
    uint32_t magic;
    uint32_t version;
    uint32_t data_size;
    uint32_t crc32;
    device_config_t config;
} config_storage_record_t;

_Static_assert(
    CONFIG_DATA_SIZE <= FLASH_SECTOR_SIZE,
    "Configuration exceeds reserved flash sector"
);

typedef struct {
    uint8_t data[CONFIG_DATA_SIZE];
} config_flash_buffer_t;

static uint32_t calculate_crc32(const uint8_t *data, size_t length)
{
    uint32_t crc = 0xFFFFFFFFu;

    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];

        for (unsigned int bit = 0; bit < 8; ++bit) {
            uint32_t mask = (uint32_t)-(int32_t)(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }

    return ~crc;
}

bool config_storage_load(device_config_t *config)
{
    if (config == NULL) {
        return false;
    }

    const config_storage_record_t *record =
        (const config_storage_record_t *)(XIP_BASE + CONFIG_FLASH_OFFSET);

    if (record->magic != CONFIG_STORAGE_MAGIC ||
        record->version != CONFIG_STORAGE_VERSION ||
        record->data_size != sizeof(device_config_t)) {
        return false;
    }

    uint32_t crc = calculate_crc32(
        (const uint8_t *)&record->config,
        sizeof(device_config_t)
    );

    if (crc != record->crc32) {
        return false;
    }

    if (!device_config_validate(&record->config)) {
        return false;
    }

    memcpy(config, &record->config, sizeof(device_config_t));
    return true;
}

static void flash_write_callback(void *param)
{
    const config_flash_buffer_t *buffer =
        (const config_flash_buffer_t *)param;

    flash_range_erase(CONFIG_FLASH_OFFSET, FLASH_SECTOR_SIZE);

    flash_range_program(
        CONFIG_FLASH_OFFSET,
        buffer->data,
        CONFIG_DATA_SIZE
    );
}

bool config_storage_save(const device_config_t *config)
{
    if (config == NULL || !device_config_validate(config)) {
        return false;
    }

    static config_flash_buffer_t buffer
        __attribute__((aligned(4)));

    memset(buffer.data, 0xFF, sizeof(buffer.data));

    config_storage_record_t record = {
        .magic = CONFIG_STORAGE_MAGIC,
        .version = CONFIG_STORAGE_VERSION,
        .data_size = sizeof(device_config_t),
        .crc32 = 0,
        .config = *config
    };

    record.crc32 = calculate_crc32(
        (const uint8_t *)&record.config,
        sizeof(record.config)
    );

    memcpy(buffer.data, &record, sizeof(record));

    int result = flash_safe_execute(
        flash_write_callback,
        &buffer,
        1000
    );

    return result == PICO_OK;
}
