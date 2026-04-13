/**
 * sensor_bridge.c
 *
 * See sensor_bridge.h for module overview and pin configuration.
 *
 * Behaviour summary:
 *   - One FreeRTOS task wakes every SENSOR_BRIDGE_TASK_PERIOD_MS (3 s default)
 *   - Each cycle: read DS18B20, sample+compensate TDS, drain pH UART,
 *     then transmit  "TEMP:xx.xx,SAL:x.xxx,PH:xx.xx\n"  on the Jetson UART.
 *   - The pH module streams readings continuously; we drain whatever bytes
 *     are available and keep the last valid (0 < pH < 14) value between ticks.
 *   - If any sensor is missing or faulty, the last known good value is
 *     retained and the cycle still transmits — the Jetson-side parser is
 *     forgiving, and partial data is better than nothing.
 *
 * Salinity math: ported verbatim from Jamie's Arduino prototype
 * (project-docs/sensors-code.txt).  We read calibrated millivolts from the
 * ESP-IDF oneshot ADC rather than raw counts, which removes the need for
 * the raw*(3.3/4095) conversion and gives more accurate readings across
 * the full input range.
 */

#include "sensor_bridge.h"

#include <stdio.h>
#include <string.h>
#include <math.h>
#include <stdlib.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"

#include "driver/uart.h"
#include "driver/gpio.h"

#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"

#include "onewire_bus.h"
#include "ds18b20.h"

static const char *TAG = "SENSOR_BRIDGE";

// ============================================================================
// INTERNAL STATE
// ============================================================================

typedef struct {
    /* DS18B20 / 1-Wire */
    onewire_bus_handle_t        onewire_bus;
    ds18b20_device_handle_t     ds18b20;
    bool                        ds18b20_ok;

    /* TDS / ADC */
    adc_oneshot_unit_handle_t   adc_handle;
    adc_cali_handle_t           adc_cali;
    bool                        adc_ok;
    bool                        adc_cali_ok;

    /* pH UART */
    bool                        ph_uart_ok;
    char                        ph_rx_accum[32];        // line accumulator
    int                         ph_rx_len;
    uint32_t                    ph_last_update_ms;

    /* Jetson UART */
    bool                        jetson_uart_ok;

    /* Latest readings */
    sensor_bridge_snapshot_t    snapshot;

    /* Task */
    TaskHandle_t                task_handle;
    bool                        initialized;
    bool                        running;
} sensor_bridge_state_t;

static sensor_bridge_state_t s_state = {0};

// ============================================================================
// DS18B20 INIT
// ============================================================================

static esp_err_t init_onewire_and_ds18b20(void)
{
    onewire_bus_config_t bus_cfg = {
        .bus_gpio_num = SENSOR_BRIDGE_ONEWIRE_GPIO,
    };
    onewire_bus_rmt_config_t rmt_cfg = {
        .max_rx_bytes = 10,     // DS18B20 scratchpad is 9 bytes; 10 leaves slack
    };

    esp_err_t err = onewire_new_bus_rmt(&bus_cfg, &rmt_cfg, &s_state.onewire_bus);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "onewire_new_bus_rmt failed on GPIO %d: %s",
                 SENSOR_BRIDGE_ONEWIRE_GPIO, esp_err_to_name(err));
        return err;
    }

    /* Walk the 1-Wire bus and take the first DS18B20 we find.
     * We only support a single temperature probe for now. */
    onewire_device_iter_handle_t iter = NULL;
    err = onewire_new_device_iter(s_state.onewire_bus, &iter);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "onewire_new_device_iter failed: %s", esp_err_to_name(err));
        return err;
    }

    onewire_device_t device;
    bool found = false;
    while (onewire_device_iter_get_next(iter, &device) == ESP_OK) {
        ds18b20_config_t ds_cfg = {};
        if (ds18b20_new_device_from_enumeration(&device, &ds_cfg, &s_state.ds18b20) == ESP_OK) {
            ESP_LOGI(TAG, "DS18B20 found, ROM: 0x%016llX",
                     (unsigned long long)device.address);
            found = true;
            break;
        }
    }
    onewire_del_device_iter(iter);

    if (!found) {
        ESP_LOGW(TAG, "No DS18B20 detected on GPIO %d — temperature will be 0.0",
                 SENSOR_BRIDGE_ONEWIRE_GPIO);
        return ESP_ERR_NOT_FOUND;
    }

    err = ds18b20_set_resolution(s_state.ds18b20, SENSOR_BRIDGE_DS18B20_RESOLUTION);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "ds18b20_set_resolution failed: %s", esp_err_to_name(err));
        /* Non-fatal; sensor still readable at default resolution. */
    }

    s_state.ds18b20_ok = true;
    return ESP_OK;
}

// ============================================================================
// TDS / ADC INIT
// ============================================================================

static esp_err_t init_tds_adc(void)
{
    adc_oneshot_unit_init_cfg_t unit_cfg = {
        .unit_id = SENSOR_BRIDGE_TDS_ADC_UNIT,
    };
    esp_err_t err = adc_oneshot_new_unit(&unit_cfg, &s_state.adc_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "adc_oneshot_new_unit failed: %s", esp_err_to_name(err));
        return err;
    }

    adc_oneshot_chan_cfg_t chan_cfg = {
        .bitwidth = SENSOR_BRIDGE_TDS_ADC_BITWIDTH,
        .atten    = SENSOR_BRIDGE_TDS_ADC_ATTEN,
    };
    err = adc_oneshot_config_channel(s_state.adc_handle,
                                     SENSOR_BRIDGE_TDS_ADC_CHANNEL,
                                     &chan_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "adc_oneshot_config_channel failed: %s", esp_err_to_name(err));
        return err;
    }

    s_state.adc_ok = true;

    /* Calibration — best-effort.  On ESP32-S3 the curve-fitting scheme
     * reads efuse parameters; if they are missing we fall back to an
     * uncalibrated conversion in sample_tds_voltage_mv(). */
    adc_cali_curve_fitting_config_t cali_cfg = {
        .unit_id  = SENSOR_BRIDGE_TDS_ADC_UNIT,
        .atten    = SENSOR_BRIDGE_TDS_ADC_ATTEN,
        .bitwidth = SENSOR_BRIDGE_TDS_ADC_BITWIDTH,
    };
    err = adc_cali_create_scheme_curve_fitting(&cali_cfg, &s_state.adc_cali);
    if (err == ESP_OK) {
        s_state.adc_cali_ok = true;
        ESP_LOGI(TAG, "ADC curve-fitting calibration enabled");
    } else {
        ESP_LOGW(TAG, "ADC calibration unavailable (%s) — using raw-scaled voltage",
                 esp_err_to_name(err));
    }

    return ESP_OK;
}

// ============================================================================
// pH UART INIT
// ============================================================================

static esp_err_t init_ph_uart(void)
{
    const uart_config_t cfg = {
        .baud_rate  = SENSOR_BRIDGE_PH_UART_BAUD,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    esp_err_t err = uart_driver_install(SENSOR_BRIDGE_PH_UART_NUM,
                                        SENSOR_BRIDGE_PH_UART_BUF_SIZE * 2,
                                        0, 0, NULL, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "pH uart_driver_install failed: %s", esp_err_to_name(err));
        return err;
    }

    err = uart_param_config(SENSOR_BRIDGE_PH_UART_NUM, &cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "pH uart_param_config failed: %s", esp_err_to_name(err));
        return err;
    }

    err = uart_set_pin(SENSOR_BRIDGE_PH_UART_NUM,
                       SENSOR_BRIDGE_PH_UART_TX_GPIO,
                       SENSOR_BRIDGE_PH_UART_RX_GPIO,
                       UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "pH uart_set_pin failed: %s", esp_err_to_name(err));
        return err;
    }

    s_state.ph_uart_ok = true;
    ESP_LOGI(TAG, "pH UART%d on RX=%d TX=%d @ %d baud",
             SENSOR_BRIDGE_PH_UART_NUM,
             SENSOR_BRIDGE_PH_UART_RX_GPIO,
             SENSOR_BRIDGE_PH_UART_TX_GPIO,
             SENSOR_BRIDGE_PH_UART_BAUD);
    return ESP_OK;
}

// ============================================================================
// JETSON UART INIT
// ============================================================================

static esp_err_t init_jetson_uart(void)
{
    /* UART0 is owned by the IDF console; installing our own driver collides
     * with NODE_CONFIG's serial console and reboots the chip.  Skip the
     * install and let send_to_jetson() go through stdout instead. */
    if (SENSOR_BRIDGE_JETSON_UART_NUM == UART_NUM_0) {
        s_state.jetson_uart_ok = true;
        ESP_LOGI(TAG, "Jetson output via console (UART0, TX=%d RX=%d, shared with swarm console)",
                 SENSOR_BRIDGE_JETSON_UART_TX_GPIO,
                 SENSOR_BRIDGE_JETSON_UART_RX_GPIO);
        return ESP_OK;
    }

    const uart_config_t cfg = {
        .baud_rate  = SENSOR_BRIDGE_JETSON_UART_BAUD,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    esp_err_t err = uart_driver_install(SENSOR_BRIDGE_JETSON_UART_NUM,
                                        SENSOR_BRIDGE_JETSON_UART_BUF_SIZE,
                                        SENSOR_BRIDGE_JETSON_UART_BUF_SIZE,
                                        0, NULL, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Jetson uart_driver_install failed: %s", esp_err_to_name(err));
        return err;
    }

    err = uart_param_config(SENSOR_BRIDGE_JETSON_UART_NUM, &cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Jetson uart_param_config failed: %s", esp_err_to_name(err));
        return err;
    }

    err = uart_set_pin(SENSOR_BRIDGE_JETSON_UART_NUM,
                       SENSOR_BRIDGE_JETSON_UART_TX_GPIO,
                       SENSOR_BRIDGE_JETSON_UART_RX_GPIO,
                       UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Jetson uart_set_pin failed: %s", esp_err_to_name(err));
        return err;
    }

    s_state.jetson_uart_ok = true;
    ESP_LOGI(TAG, "Jetson UART%d on TX=%d RX=%d @ %d baud",
             SENSOR_BRIDGE_JETSON_UART_NUM,
             SENSOR_BRIDGE_JETSON_UART_TX_GPIO,
             SENSOR_BRIDGE_JETSON_UART_RX_GPIO,
             SENSOR_BRIDGE_JETSON_UART_BAUD);
    return ESP_OK;
}

// ============================================================================
// SENSOR READS
// ============================================================================

/**
 * Trigger a conversion and read temperature from the DS18B20.
 * Returns true and fills *out_c on success.
 */
static bool read_temperature(float *out_c)
{
    if (!s_state.ds18b20_ok) {
        return false;
    }

    esp_err_t err = ds18b20_trigger_temperature_conversion(s_state.ds18b20);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "ds18b20 trigger failed: %s", esp_err_to_name(err));
        return false;
    }

    float c;
    err = ds18b20_get_temperature(s_state.ds18b20, &c);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "ds18b20 read failed: %s", esp_err_to_name(err));
        return false;
    }

    /* DS18B20 returns -127 or similar sentinels on error; guard like Jamie did. */
    if (c < -100.0f || c > 125.0f) {
        return false;
    }

    *out_c = c;
    return true;
}

/**
 * Sample the TDS pin SENSOR_BRIDGE_TDS_SAMPLES times and return the
 * averaged voltage in millivolts at the ADC pin (i.e. BEFORE the
 * divider-ratio correction).
 */
static bool sample_tds_voltage_mv(int *out_mv)
{
    if (!s_state.adc_ok) {
        return false;
    }

    long sum_mv = 0;
    int  count  = 0;

    for (int i = 0; i < SENSOR_BRIDGE_TDS_SAMPLES; i++) {
        int raw;
        esp_err_t err = adc_oneshot_read(s_state.adc_handle,
                                         SENSOR_BRIDGE_TDS_ADC_CHANNEL,
                                         &raw);
        if (err != ESP_OK) {
            continue;
        }

        int mv;
        if (s_state.adc_cali_ok &&
            adc_cali_raw_to_voltage(s_state.adc_cali, raw, &mv) == ESP_OK) {
            /* Calibrated path. */
        } else {
            /* Uncalibrated fallback: 12-bit ADC, nominal 3.3 V full-scale with
             * 12 dB attenuation.  Matches Jamie's raw*(3.3/4095) behaviour. */
            mv = (int)((raw * 3300L) / 4095);
        }

        sum_mv += mv;
        count++;
    }

    if (count == 0) {
        return false;
    }

    *out_mv = (int)(sum_mv / count);
    return true;
}

/**
 * Convert a pin-side voltage (mV) and current water temperature into
 * salinity in parts per thousand, using the cubic EC polynomial from
 * Jamie's Arduino prototype.
 */
static float compute_salinity_ppt(int voltage_mv, float temperature_c)
{
    float voltage_v     = voltage_mv / 1000.0f;
    float real_voltage  = voltage_v * SENSOR_BRIDGE_TDS_DIVIDER_RATIO;

    float comp_coef     = 1.0f + 0.02f * (temperature_c - 25.0f);
    if (comp_coef < 0.1f) {
        comp_coef = 0.1f;       /* guard against extreme/bogus temperatures */
    }
    float comp_voltage  = real_voltage / comp_coef;

    float ec = 133.42f * comp_voltage * comp_voltage * comp_voltage
             - 255.86f * comp_voltage * comp_voltage
             + 857.39f * comp_voltage;

    float tds_ppm       = ec * 0.5f;
    float salinity_ppt  = tds_ppm / 1000.0f;

    if (salinity_ppt < 0.0f) {
        salinity_ppt = 0.0f;
    }
    return salinity_ppt;
}

/**
 * Drain anything currently waiting in the pH UART RX buffer and parse
 * newline-terminated ASCII pH readings.  On a valid reading, update
 * s_state.snapshot.ph and s_state.ph_last_update_ms.
 */
static void drain_ph_uart(void)
{
    if (!s_state.ph_uart_ok) {
        return;
    }

    size_t available = 0;
    if (uart_get_buffered_data_len(SENSOR_BRIDGE_PH_UART_NUM, &available) != ESP_OK) {
        return;
    }
    if (available == 0) {
        return;
    }

    uint8_t buf[64];
    while (available > 0) {
        size_t chunk = available < sizeof(buf) ? available : sizeof(buf);
        int n = uart_read_bytes(SENSOR_BRIDGE_PH_UART_NUM, buf, chunk, 0);
        if (n <= 0) {
            break;
        }
        available -= n;

        for (int i = 0; i < n; i++) {
            char c = (char)buf[i];

            if (c == '\r' || c == '\n') {
                if (s_state.ph_rx_len > 0) {
                    s_state.ph_rx_accum[s_state.ph_rx_len] = '\0';
                    float ph = strtof(s_state.ph_rx_accum, NULL);
                    if (ph > 0.0f && ph < 14.0f) {
                        s_state.snapshot.ph = ph;
                        s_state.snapshot.ph_valid = true;
                        s_state.ph_last_update_ms =
                            (uint32_t)(esp_timer_get_time() / 1000);
                    }
                    s_state.ph_rx_len = 0;
                }
            } else if (s_state.ph_rx_len < (int)sizeof(s_state.ph_rx_accum) - 1) {
                s_state.ph_rx_accum[s_state.ph_rx_len++] = c;
            } else {
                /* Line too long — discard and resync on next newline. */
                s_state.ph_rx_len = 0;
            }
        }
    }
}

// ============================================================================
// JETSON TX
// ============================================================================

static void send_to_jetson(const sensor_bridge_snapshot_t *snap)
{
    if (!s_state.jetson_uart_ok) {
        return;
    }

    char line[96];
    int n = snprintf(line, sizeof(line),
                     "TEMP:%.2f,SAL:%.3f,PH:%.2f\n",
                     snap->temperature_c,
                     snap->salinity_ppt,
                     snap->ph);
    if (n <= 0) {
        return;
    }
    if (n >= (int)sizeof(line)) {
        n = sizeof(line) - 1;
    }

    if (SENSOR_BRIDGE_JETSON_UART_NUM == UART_NUM_0) {
        /* Share the console stream — Jetson-side parser keys on "TEMP:". */
        fwrite(line, 1, n, stdout);
        fflush(stdout);
    } else {
        uart_write_bytes(SENSOR_BRIDGE_JETSON_UART_NUM, line, n);
    }
}

// ============================================================================
// TASK
// ============================================================================

static void sensor_bridge_task(void *arg)
{
    (void)arg;

    ESP_LOGI(TAG, "Sensor bridge task running (period %d ms)",
             SENSOR_BRIDGE_TASK_PERIOD_MS);

    TickType_t last_wake = xTaskGetTickCount();
    const TickType_t period = pdMS_TO_TICKS(SENSOR_BRIDGE_TASK_PERIOD_MS);

    while (s_state.running) {
        /* Drain any pH bytes that arrived since last tick. */
        drain_ph_uart();

        /* Temperature (also feeds the salinity compensation). */
        float temp_c = s_state.snapshot.temperature_c;
        if (read_temperature(&temp_c)) {
            s_state.snapshot.temperature_c = temp_c;
            s_state.snapshot.temp_valid = true;
        }

        /* Salinity. */
        int mv = 0;
        if (sample_tds_voltage_mv(&mv)) {
            s_state.snapshot.salinity_ppt =
                compute_salinity_ppt(mv, s_state.snapshot.temperature_c);
            s_state.snapshot.sal_valid = true;
        }

        /* Age-out check on pH — value is still reported, just logged. */
        if (s_state.snapshot.ph_valid) {
            uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000);
            if ((now_ms - s_state.ph_last_update_ms) > SENSOR_BRIDGE_PH_STALE_MS) {
                ESP_LOGW(TAG, "pH reading is stale (%lu ms old)",
                         (unsigned long)(now_ms - s_state.ph_last_update_ms));
            }
        }

        s_state.snapshot.last_update_ms = (uint32_t)(esp_timer_get_time() / 1000);
        send_to_jetson(&s_state.snapshot);

        ESP_LOGD(TAG, "TX  TEMP=%.2f  SAL=%.3f  PH=%.2f",
                 s_state.snapshot.temperature_c,
                 s_state.snapshot.salinity_ppt,
                 s_state.snapshot.ph);

        vTaskDelayUntil(&last_wake, period);
    }

    s_state.task_handle = NULL;
    vTaskDelete(NULL);
}

// ============================================================================
// PUBLIC API
// ============================================================================

esp_err_t sensor_bridge_init(void)
{
    if (s_state.initialized) {
        ESP_LOGW(TAG, "sensor_bridge_init called twice");
        return ESP_OK;
    }

    memset(&s_state, 0, sizeof(s_state));
    s_state.snapshot.ph = 7.0f;     /* neutral default until first real reading */

    /* Jetson UART is mandatory — everything else is best-effort. */
    esp_err_t err = init_jetson_uart();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Jetson UART init failed — sensor bridge aborting");
        return err;
    }

    if (init_onewire_and_ds18b20() != ESP_OK) {
        ESP_LOGW(TAG, "Temperature sensor unavailable — reporting 0.0 °C");
    }
    if (init_tds_adc() != ESP_OK) {
        ESP_LOGW(TAG, "TDS/salinity ADC unavailable — reporting 0.0 ppt");
    }
    if (init_ph_uart() != ESP_OK) {
        ESP_LOGW(TAG, "pH UART unavailable — reporting cached default");
    }

    s_state.initialized = true;
    ESP_LOGI(TAG, "sensor_bridge_init complete");
    return ESP_OK;
}

esp_err_t sensor_bridge_start(void)
{
    if (!s_state.initialized) {
        ESP_LOGE(TAG, "sensor_bridge_start called before init");
        return ESP_ERR_INVALID_STATE;
    }
    if (s_state.running) {
        ESP_LOGW(TAG, "sensor_bridge already running");
        return ESP_OK;
    }

    s_state.running = true;
    BaseType_t ok = xTaskCreate(sensor_bridge_task, "sensor_bridge",
                                SENSOR_BRIDGE_TASK_STACK, NULL,
                                SENSOR_BRIDGE_TASK_PRIORITY,
                                &s_state.task_handle);
    if (ok != pdPASS) {
        s_state.running = false;
        ESP_LOGE(TAG, "xTaskCreate failed for sensor_bridge");
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

void sensor_bridge_stop(void)
{
    s_state.running = false;
    /* The task will vTaskDelete itself on the next loop iteration. */
}

esp_err_t sensor_bridge_get_snapshot(sensor_bridge_snapshot_t *out)
{
    if (out == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    *out = s_state.snapshot;
    return ESP_OK;
}

float sensor_bridge_get_temp_c(void)        { return s_state.snapshot.temperature_c; }
float sensor_bridge_get_salinity_ppt(void)  { return s_state.snapshot.salinity_ppt; }
float sensor_bridge_get_ph(void)            { return s_state.snapshot.ph; }
