document.addEventListener("DOMContentLoaded", () => {
  const tabs = document.querySelectorAll("[data-settings-tab]");
  const panels = document.querySelectorAll("[data-settings-panel]");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.settingsTab;

      tabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", String(active));
      });

      panels.forEach((panel) => {
        panel.hidden = panel.dataset.settingsPanel !== target;
      });
    });
  });

  const deviceList = document.getElementById("device-list");
  const deviceStatus = document.getElementById("device-status");
  const selectedDeviceName = document.getElementById("selected-device-name");
  const configSection = document.getElementById("device-config-section");

  if (!deviceList || !deviceStatus || !selectedDeviceName || !configSection) {
    return;
  }

  const csrfToken = document.querySelector(
    'meta[name="csrf-token"]'
  )?.content;

  let deviceData = null;
  let selectedDeviceId = null;
  let deviceRefreshInProgress = false;
  const firmwareCache = new Map();
  const firmwareRequests = new Set();


  const saveConfigButton = document.getElementById("save-device-config");
  const configStatus = document.getElementById("config-status");
  const configEditor = document.getElementById("device-config-editor");

  let currentConfig = null;

  function resetConfigView(message) {
    currentConfig = null;
    saveConfigButton.disabled = true;
    configEditor.replaceChildren();
    configStatus.textContent = message;
  }



  function getSelectedDevice() {
    return selectedDeviceId;
  }


  function renderConfiguration() {
    configEditor.replaceChildren();

    const board = document.createElement("div");
    board.className = "pico-pinout";

    const left = document.createElement("div");
    left.className = "pico-pin-column";

    const center = document.createElement("div");
    center.className = "pico-board-center";
    center.textContent = "RASPBERRY PI PICO 2";

    const right = document.createElement("div");
    right.className = "pico-pin-column";

    const supported = number => number <= 22 || (number >= 26 && number <= 28);

    const functions = [
      [0, "Unused"], [1, "GPIO Input"], [2, "GPIO Output"],
      [3, "Signal Generator"], [4, "Signal Analyzer"],
      [5, "I2C SDA"], [6, "I2C SCL"],
      [7, "SPI RX"], [8, "SPI TX"], [9, "SPI SCK"], [10, "SPI CS"],
      [11, "UART TX"], [12, "UART RX"],
      [13, "ADC Input"]
    ];

    const peripheral = new Set([5,6,7,8,9,10,11,12]);

    const pin = number => currentConfig.pins.find(p => p.pin === number);

    const groups = {
      i2c: {
        0: [
          {sda:0,scl:1},
          {sda:4,scl:5},
          {sda:8,scl:9},
          {sda:12,scl:13},
          {sda:16,scl:17},
          {sda:20,scl:21}
        ],
        1: [
          {sda:2,scl:3},
          {sda:6,scl:7},
          {sda:10,scl:11},
          {sda:14,scl:15},
          {sda:18,scl:19},
          {sda:26,scl:27}
        ]
      },
      spi: {
        0: [
          {rx:0,cs:1,sck:2,tx:3},
          {rx:4,cs:5,sck:6,tx:7},
          {rx:16,cs:17,sck:18,tx:19}
        ],
        1: [
          {rx:8,cs:9,sck:10,tx:11},
          {rx:12,cs:13,sck:14,tx:15}
        ]
      },
      uart: {
        0: [
          {tx:0,rx:1},
          {tx:12,rx:13},
          {tx:16,rx:17}
        ],
        1: [
          {tx:4,rx:5},
          {tx:8,rx:9}
        ]
      }
    };

    const typeFor = fn =>
      fn === 5 || fn === 6 ? "i2c" :
      fn >= 7 && fn <= 10 ? "spi" :
      fn === 11 || fn === 12 ? "uart" : null;

    const fieldFor = fn => ({
      5:"sda", 6:"scl", 7:"rx", 8:"tx",
      9:"sck", 10:"cs", 11:"tx", 12:"rx"
    })[fn];

    const functionFor = {
      i2c: {sda:5,scl:6},
      spi: {rx:7,cs:10,sck:9,tx:8},
      uart: {tx:11,rx:12}
    };

    function usableGroup(type, instance, group) {
      return Object.values(group).every(number =>
        supported(number) && pin(number)
      );
    }

    function availableGroups(type, instance) {
      return (groups[type]?.[instance] || []).filter(group =>
        usableGroup(type, instance, group)
      );
    }

    function groupForPin(fn, instance, number) {
      const type = typeFor(fn);
      if (!type) return null;
      const field = fieldFor(fn);
      return availableGroups(type, instance).find(group =>
        group[field] === number
      ) || null;
    }

    function clearPreviousGroup(entry) {
      const type = typeFor(entry.function);
      if (!type) return;

      const group = groupForPin(entry.function, entry.peripheral_instance, entry.pin);
      if (!group) return;

      Object.entries(group).forEach(([field, number]) => {
        if (number === entry.pin) return;
        const other = pin(number);
        if (
          other &&
          other.function === functionFor[type][field] &&
          other.peripheral_instance === entry.peripheral_instance
        ) {
          other.function = 0;
          other.peripheral_instance = 0;
        }
      });
    }

    function assignGroup(entry, fn, instance) {
      const type = typeFor(fn);
      const field = fieldFor(fn);
      const group = groupForPin(fn, instance, entry.pin);

      if (!group) {
        return "This GPIO cannot provide a complete peripheral pin group for that instance.";
      }

      const groupPins = new Set(Object.values(group));
      const existingInstance = currentConfig.pins.find(candidate =>
        typeFor(candidate.function) === type &&
        candidate.peripheral_instance === instance &&
        !groupPins.has(candidate.pin)
      );

      if (existingInstance) {
        return `${type.toUpperCase()}${instance} is already assigned to GPIO ${existingInstance.pin}. Clear its current pin group first.`;
      }

      for (const [signal, number] of Object.entries(group)) {
        const target = pin(number);
        const expectedFunction = functionFor[type][signal];

        if (
          number !== entry.pin &&
          target.function !== 0 &&
          !(target.function === expectedFunction &&
            target.peripheral_instance === instance)
        ) {
          return `GPIO ${number} is already assigned. The ${type.toUpperCase()} group was not changed.`;
        }
      }

      clearPreviousGroup(entry);

      for (const [signal, number] of Object.entries(group)) {
        const target = pin(number);
        target.function = functionFor[type][signal];
        target.peripheral_instance = instance;
      }

      return null;
    }

    function rerender() {
      renderConfiguration();
      renderPeripheralConfiguration();
    }

    function createPin(number) {
      const entry = pin(number);
      const wrapper = document.createElement("div");
      wrapper.className = "pico-pin";

      if (!entry || !supported(number)) {
        wrapper.classList.add("pico-pin-unavailable");
        wrapper.textContent = `GP${number} unavailable`;
        return wrapper;
      }

      const label = document.createElement("strong");
      label.textContent = `GP${number}`;

      const select = document.createElement("select");
      select.className = "pico-function";

      functions.filter(([fn]) => {
        if (fn === 13) {
          return (number >= 26 && number <= 28) || entry.function === 13;
        }
        if (!peripheral.has(fn)) return true;
        const type = typeFor(fn);
        const field = fieldFor(fn);
        return [0,1].some(instance =>
          availableGroups(type, instance).some(group => group[field] === number)
        ) || entry.function === fn;
      }).forEach(([fn,name]) => {
        const option = document.createElement("option");
        option.value = fn;
        option.textContent = name;
        select.appendChild(option);
      });

      select.value = entry.function;

      const instance = document.createElement("select");
      instance.className = "pico-instance";

      [0,1].forEach(value => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = `Instance ${value}`;
        instance.appendChild(option);
      });

      instance.value = entry.peripheral_instance;

      select.addEventListener("change", () => {
        const next = Number(select.value);
        const oldFunction = entry.function;
        const oldInstance = entry.peripheral_instance;

        if (peripheral.has(next)) {
          const choices = [0,1].filter(i =>
            groupForPin(next, i, number)
          );
          const nextInstance = choices.includes(oldInstance)
            ? oldInstance : choices[0];

          const error = assignGroup(entry, next, nextInstance);
          if (error) {
            select.value = oldFunction;
            configStatus.textContent = error;
            return;
          }

          entry.function = next;
          entry.peripheral_instance = nextInstance;
        } else {
          clearPreviousGroup(entry);
          entry.function = next;
          entry.peripheral_instance = 0;
        }

        configStatus.textContent = "Pin configuration updated.";
        rerender();
      });

      instance.addEventListener("change", () => {
        const next = Number(instance.value);
        const error = assignGroup(entry, entry.function, next);

        if (error) {
          instance.value = entry.peripheral_instance;
          configStatus.textContent = error;
          return;
        }

        entry.peripheral_instance = next;
        configStatus.textContent = "Peripheral group updated.";
        rerender();
      });

      wrapper.append(label, select);

      if (peripheral.has(entry.function)) {
        instance.value = entry.peripheral_instance;
        wrapper.append(instance);
      }

      if (entry.function === 13) {
        entry.pull = 0;
      } else {
        const pull = document.createElement("select");
        pull.className = "pico-pull";

        [["None",0],["Pull-up",1],["Pull-down",2]].forEach(([name,value]) => {
          const option = document.createElement("option");
          option.value = value;
          option.textContent = name;
          pull.appendChild(option);
        });

        pull.value = entry.pull;
        pull.addEventListener("change", () => {
          entry.pull = Number(pull.value);
        });

        wrapper.append(pull);
      }

      if (entry.function === 3 || entry.function === 4) {
        const priority = document.createElement("input");
        priority.type = "number";
        priority.min = 0;
        priority.max = 3;
        priority.value = entry.pio_priority;
        priority.title = "PIO priority";
        priority.addEventListener("change", () => {
          const value = Number(priority.value);
          if (Number.isInteger(value) && value >= 0 && value <= 3)
            entry.pio_priority = value;
        });
        wrapper.append(priority);
      }

      if (entry.function === 1 || entry.function === 4) {
        const filter = document.createElement("input");
        filter.type = "number";
        filter.min = 0;
        filter.max = 1000000;
        filter.value = entry.input_filter_us;
        filter.title = "Input filter (µs)";
        filter.addEventListener("change", () => {
          const value = Number(filter.value);
          if (Number.isInteger(value) && value >= 0 && value <= 1000000)
            entry.input_filter_us = value;
        });
        wrapper.append(filter);
      }

      if (entry.function === 2) {
        const level = document.createElement("select");
        [["Low",0],["High",1]].forEach(([name,value]) => {
          const option = document.createElement("option");
          option.value = value;
          option.textContent = name;
          level.appendChild(option);
        });
        level.value = entry.initial_level;
        level.addEventListener("change", () => {
          entry.initial_level = Number(level.value);
        });
        wrapper.append(level);
      }

      return wrapper;
    }

    function createHeaderPin(value) {
      if (typeof value === "number") return createPin(value);

      const item = document.createElement("div");
      item.className = "pico-header-pin";
      item.textContent = value;
      return item;
    }

    const leftPins = [
      0,1,"GND",2,3,4,5,"GND",6,7,8,9,"GND",
      10,11,12,13,"GND",14,15
    ];

    const rightPins = [
      "VBUS","VSYS","GND","3V3_EN","3V3_OUT","ADC_VREF",
      "GND",28,27,26,"RUN",22,"GND",21,20,19,18,"GND",17,16
    ];

    leftPins.forEach(value => left.append(createHeaderPin(value)));
    rightPins.forEach(value => right.append(createHeaderPin(value)));

    board.append(left,center,right);
    configEditor.append(board);
  }

  function renderPeripheralConfiguration() {
    const container = document.createElement("div");
    container.className = "peripheral-config";

    function createNumberInput(label, value, min, max, onChange) {
      const wrapper = document.createElement("label");
      wrapper.textContent = label;

      const input = document.createElement("input");
      input.type = "number";
      input.min = String(min);
      input.max = String(max);
      input.step = "1";
      input.value = value;

      input.addEventListener("change", () => {
        const parsed = Number(input.value);

        if (
          !Number.isInteger(parsed) ||
          parsed < min ||
          parsed > max
        ) {
          input.setCustomValidity(`Enter a value from ${min} to ${max}.`);
          input.reportValidity();
          return;
        }

        input.setCustomValidity("");
        onChange(parsed);
      });

      wrapper.appendChild(input);
      return wrapper;
    }

    function createSelect(label, values, currentValue, onChange) {
      const wrapper = document.createElement("label");
      wrapper.textContent = label;

      const select = document.createElement("select");

      values.forEach(([name, value]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = name;
        select.appendChild(option);
      });

      select.value = currentValue;
      select.addEventListener("change", () => {
        onChange(Number(select.value));
      });

      wrapper.appendChild(select);
      return wrapper;
    }

    function addSection(title, entries, fields) {
      const functionCodes = {
        I2C: [5, 6],
        SPI: [7, 8, 9, 10],
        UART: [11, 12]
      }[title];

      entries
        .filter(entry =>
          currentConfig.pins.some(pin =>
            pin.peripheral_instance === entry.instance &&
            functionCodes.includes(pin.function)
          )
        )
        .forEach(entry => {
          const section = document.createElement("section");
          section.className = "peripheral-section";

          const heading = document.createElement("h4");
          heading.textContent = `${title}${entry.instance}`;
          section.appendChild(heading);

          const group = document.createElement("div");
          group.className = "peripheral-instance";

          fields(entry, group);
          section.appendChild(group);
          container.appendChild(section);
        });
    }

    addSection("I2C", currentConfig.peripherals.i2c, (entry, group) => {
      group.appendChild(createNumberInput(
        "Baudrate (Hz)",
        entry.baudrate,
        1,
        1000000,
        (value) => { entry.baudrate = value; }
      ));
    });

    addSection("SPI", currentConfig.peripherals.spi, (entry, group) => {
      group.appendChild(createNumberInput(
        "Baudrate (Hz)",
        entry.baudrate,
        1,
        10000000,
        (value) => { entry.baudrate = value; }
      ));

      group.appendChild(createNumberInput(
        "Data bits",
        entry.data_bits,
        4,
        16,
        (value) => { entry.data_bits = value; }
      ));

      group.appendChild(createSelect(
        "Clock polarity",
        [["CPOL 0", 0], ["CPOL 1", 1]],
        entry.cpol,
        (value) => { entry.cpol = value; }
      ));

      group.appendChild(createSelect(
        "Clock phase",
        [["CPHA 0", 0], ["CPHA 1", 1]],
        entry.cpha,
        (value) => { entry.cpha = value; }
      ));

      group.appendChild(createSelect(
        "Bit order",
        [["MSB first", 0], ["LSB first", 1]],
        entry.lsb_first,
        (value) => { entry.lsb_first = value; }
      ));
    });

    addSection("UART", currentConfig.peripherals.uart, (entry, group) => {
      group.appendChild(createNumberInput(
        "Baudrate",
        entry.baudrate,
        1,
        4000000,
        (value) => { entry.baudrate = value; }
      ));

      group.appendChild(createNumberInput(
        "Data bits",
        entry.data_bits,
        5,
        8,
        (value) => { entry.data_bits = value; }
      ));

      group.appendChild(createSelect(
        "Stop bits",
        [["1", 1], ["2", 2]],
        entry.stop_bits,
        (value) => { entry.stop_bits = value; }
      ));

      group.appendChild(createSelect(
        "Parity",
        [["None", 0], ["Even", 1], ["Odd", 2]],
        entry.parity,
        (value) => { entry.parity = value; }
      ));
    });

    const adcPins = currentConfig.pins
      .filter(pin => pin.function === 13)
      .sort((a, b) => a.pin - b.pin);

    if (adcPins.length > 0) {
      const section = document.createElement("section");
      section.className = "peripheral-section";

      const heading = document.createElement("h4");
      heading.textContent = "ADC Inputs";
      section.appendChild(heading);

      const group = document.createElement("div");
      group.className = "peripheral-instance";

      adcPins.forEach(pin => {
        const channel = pin.pin - 26;
        const item = document.createElement("div");
        item.textContent = `ADC${channel} – GPIO${pin.pin}`;
        group.appendChild(item);
      });

      section.appendChild(group);
      container.appendChild(section);
    }

    configEditor.appendChild(container);
  }

  async function loadConfiguration() {
    const deviceId = getSelectedDevice();
    if (!deviceId) return;

    currentConfig = null;
    configEditor.replaceChildren();
    saveConfigButton.disabled = true;
    configStatus.textContent = "Reading configuration from device...";

    try {
      const response = await fetch(
        `/settings/api/devices/${encodeURIComponent(deviceId)}/config`
      );
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || `HTTP ${response.status}`);
      }
      if (!result.config) {
        throw new Error("Device returned no configuration.");
      }
      if (selectedDeviceId !== deviceId) return;

      currentConfig = result.config;
      renderConfiguration();
      renderPeripheralConfiguration();

      saveConfigButton.disabled = false;
      configStatus.textContent =
        "Configuration loaded. GPIO assignments can now be edited.";
    } catch (error) {
      if (selectedDeviceId !== deviceId) return;
      currentConfig = null;
      configEditor.replaceChildren();
      saveConfigButton.disabled = true;
      configStatus.textContent =
        `Configuration read failed: ${error.message}`;
    }
  }



  function validateConfiguration() {
    const errors = [];
    const peripheralAssignments = new Set();

    const peripheralFunctions = new Set([5, 6, 7, 8, 9, 10, 11, 12]);

    const isIntegerInRange = (value, min, max) =>
      Number.isInteger(value) && value >= min && value <= max;

    const supportedPins = (pin) =>
      pin <= 22 || (pin >= 26 && pin <= 28);

    if (currentConfig.config_version !== 5) {
      errors.push("Unsupported configuration version.");
    }

    if (!Array.isArray(currentConfig.pins) ||
        currentConfig.pins.length !== 30) {
      errors.push("Configuration must contain exactly 30 GPIO entries.");
    }

    if (!currentConfig.peripherals ||
        !Array.isArray(currentConfig.peripherals.i2c) ||
        !Array.isArray(currentConfig.peripherals.spi) ||
        !Array.isArray(currentConfig.peripherals.uart)) {
      errors.push("Peripheral configuration is incomplete.");
      return errors;
    }

    if (errors.length > 0) {
      return errors;
    }

    const seenPins = new Set();

    currentConfig.pins.forEach((pin) => {
      if (!pin || !Number.isInteger(pin.pin) ||
          pin.pin < 0 || pin.pin > 29) {
        errors.push("Invalid GPIO entry.");
        return;
      }

      const prefix = `GPIO ${pin.pin}:`;

      if (seenPins.has(pin.pin)) {
        errors.push(`${prefix} Duplicate GPIO entry.`);
        return;
      }

      seenPins.add(pin.pin);

      if (!isIntegerInRange(pin.function, 0, 13)) {
        errors.push(`${prefix} Invalid function.`);
        return;
      }

      if (!isIntegerInRange(pin.peripheral_instance, 0, 1)) {
        errors.push(`${prefix} Invalid peripheral instance.`);
      }

      if (!isIntegerInRange(pin.pio_priority, 0, 3)) {
        errors.push(`${prefix} PIO priority must be 0–3.`);
      }

      if (!isIntegerInRange(pin.pull, 0, 2)) {
        errors.push(`${prefix} Invalid pull setting.`);
      }

      if (!isIntegerInRange(pin.initial_level, 0, 1)) {
        errors.push(`${prefix} Invalid initial GPIO level.`);
      }

      if (!isIntegerInRange(pin.input_filter_us, 0, 1000000)) {
        errors.push(`${prefix} Input filter must be 0–1000000 µs.`);
      }

      if (!supportedPins(pin.pin)) {
        if (
          pin.function !== 0 ||
          pin.peripheral_instance !== 0 ||
          pin.pio_priority !== 0 ||
          pin.pull !== 0 ||
          pin.initial_level !== 0 ||
          pin.input_filter_us !== 0
        ) {
          errors.push(`${prefix} Pin is not available.`);
        }
        return;
      }

      if (!peripheralFunctions.has(pin.function) &&
          pin.function !== 3 &&
          pin.peripheral_instance !== 0) {
        errors.push(`${prefix} Peripheral instance must be 0.`);
      }

      if (pin.function === 3) {
        if (
          pin.peripheral_instance !== 0 ||
          pin.initial_level !== 0 ||
          pin.input_filter_us !== 0
        ) {
          errors.push(`${prefix} Invalid signal generator settings.`);
        }
      }

      if (pin.function === 13) {
        if (
          pin.pin < 26 ||
          pin.pin > 28 ||
          pin.peripheral_instance !== 0 ||
          pin.pull !== 0 ||
          pin.initial_level !== 0 ||
          pin.input_filter_us !== 0
        ) {
          errors.push(`${prefix} Invalid ADC input settings.`);
        }
      }

      if (pin.input_filter_us !== 0 &&
          pin.function !== 1 &&
          pin.function !== 4) {
        errors.push(`${prefix} Input filter is not supported for this function.`);
      }

      if (pin.initial_level !== 0 && pin.function !== 2) {
        errors.push(`${prefix} Initial level is only valid for GPIO Output.`);
      }

      if (peripheralFunctions.has(pin.function)) {
        const key = `${pin.function}:${pin.peripheral_instance}`;

        if (peripheralAssignments.has(key)) {
          errors.push(
            `${prefix} Peripheral function is already assigned to this instance.`
          );
        }

        peripheralAssignments.add(key);
      }
    });

    if (seenPins.size !== 30) {
      errors.push("One or more GPIO entries are missing.");
    }

    function validateInstances(entries, name) {
      if (entries.length !== 2) {
        errors.push(`${name}: Exactly two instances are required.`);
        return;
      }

      const instances = new Set();

      entries.forEach((entry) => {
        if (!entry || !isIntegerInRange(entry.instance, 0, 1)) {
          errors.push(`${name}: Invalid instance number.`);
          return;
        }

        if (instances.has(entry.instance)) {
          errors.push(`${name}: Duplicate instance ${entry.instance}.`);
        }

        instances.add(entry.instance);
      });

      if (instances.size !== 2) {
        errors.push(`${name}: Instance 0 or 1 is missing.`);
      }
    }

    validateInstances(currentConfig.peripherals.i2c, "I2C");
    validateInstances(currentConfig.peripherals.spi, "SPI");
    validateInstances(currentConfig.peripherals.uart, "UART");

    currentConfig.peripherals.i2c.forEach((entry) => {
      if (!isIntegerInRange(entry.baudrate, 1, 1000000)) {
        errors.push(`I2C ${entry.instance}: Invalid baudrate.`);
      }
    });

    currentConfig.peripherals.spi.forEach((entry) => {
      if (!isIntegerInRange(entry.baudrate, 1, 10000000)) {
        errors.push(`SPI ${entry.instance}: Invalid baudrate.`);
      }

      if (!isIntegerInRange(entry.data_bits, 4, 16)) {
        errors.push(`SPI ${entry.instance}: Data bits must be 4–16.`);
      }

      if (![0, 1].includes(entry.cpol) ||
          ![0, 1].includes(entry.cpha)) {
        errors.push(`SPI ${entry.instance}: Invalid clock mode.`);
      }

      if (![0, 1].includes(entry.lsb_first)) {
        errors.push(`SPI ${entry.instance}: Invalid bit order.`);
      }
    });

    currentConfig.peripherals.uart.forEach((entry) => {
      if (!isIntegerInRange(entry.baudrate, 1, 4000000)) {
        errors.push(`UART ${entry.instance}: Invalid baudrate.`);
      }

      if (!isIntegerInRange(entry.data_bits, 5, 8)) {
        errors.push(`UART ${entry.instance}: Data bits must be 5–8.`);
      }

      if (![1, 2].includes(entry.stop_bits)) {
        errors.push(`UART ${entry.instance}: Stop bits must be 1 or 2.`);
      }

      if (![0, 1, 2].includes(entry.parity)) {
        errors.push(`UART ${entry.instance}: Invalid parity.`);
      }
    });

    return errors;
  }

  saveConfigButton.addEventListener("click", async () => {
    const deviceId = getSelectedDevice();

    if (!currentConfig || !getSelectedDevice()) {
      return;
    }

    const validationErrors = validateConfiguration();

    if (validationErrors.length > 0) {
      configStatus.textContent =
        "Configuration invalid:\n" + validationErrors.join("\n");
      return;
    }

    saveConfigButton.disabled = true;
    configStatus.textContent = "Applying configuration to device...";

    try {
      const response = await fetch(
        `/settings/api/devices/${encodeURIComponent(deviceId)}/config`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrfToken,
          },
          body: JSON.stringify({ config: currentConfig }),
        }
      );

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || `HTTP ${response.status}`);
      }

      currentConfig = result.config;
      renderConfiguration();
      renderPeripheralConfiguration();

      configStatus.textContent =
        "Configuration successfully applied and saved.";
    } catch (error) {
      configStatus.textContent =
        `Configuration failed: ${error.message}`;
    } finally {
      saveConfigButton.disabled = false;
    }
  });

  async function loadDevices() {
    if (deviceRefreshInProgress) return;
    deviceRefreshInProgress = true;

    try {
      const response = await fetch("/settings/api/devices");

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      deviceData = await response.json();

      const connected = deviceData.devices.filter(
        (device) => device.connected && device.device_id
      );

      renderDevices(connected);

      if (selectedDeviceId &&
          !connected.some((device) => device.device_id === selectedDeviceId)) {
        selectedDeviceId = null;
        configSection.hidden = true;
        resetConfigView("Selected device disconnected.");
      }

      deviceStatus.textContent =
        `${connected.length} connected device(s) found.` +
        (connected.length > 4 ? " Only the first four are displayed." : "");

      connected.slice(0, 4).forEach(loadCardFirmware);
    } catch (error) {
      deviceStatus.textContent = `Could not load devices: ${error.message}`;
    } finally {
      deviceRefreshInProgress = false;
    }
  }

  async function loadCardFirmware(device) {
    const id = device.device_id;

    if (firmwareCache.has(id) || firmwareRequests.has(id)) return;

    firmwareRequests.add(id);

    try {
      const response = await fetch(
        `/settings/api/devices/${encodeURIComponent(id)}/version`
      );
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || `HTTP ${response.status}`);
      }

      firmwareCache.set(id, result.version);
    } catch (error) {
      firmwareCache.set(id, { error: error.message });
    } finally {
      firmwareRequests.delete(id);
      if (deviceData) {
        const connected = deviceData.devices.filter(
          (entry) => entry.connected && entry.device_id
        );
        renderDevices(connected);
      }
    }
  }

  async function selectDevice(device) {
    selectedDeviceId = device.device_id;
    configSection.hidden = false;

    selectedDeviceName.textContent =
      `${device.manufacturer || "Unknown manufacturer"} ` +
      `${device.product || "Pico"} · ${device.port || "USB"}`;

    resetConfigView("Loading device configuration...");
    renderDevices(
      deviceData.devices.filter(entry => entry.connected && entry.device_id)
    );

    await loadConfiguration();
  }



  function renderDevices(connectedDevices) {
    deviceList.replaceChildren();

    connectedDevices.slice(0, 4).forEach((device) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "device-card";
      card.classList.toggle(
        "selected",
        device.device_id === selectedDeviceId
      );

      const heading = document.createElement("h3");
      heading.textContent =
        `${device.manufacturer || "Unknown manufacturer"} ` +
        `${device.product || "Pico"}`;

      const description = document.createElement("p");
      description.textContent =
        `${device.description || "USB device"} · ${device.port || "USB"}`;

      const status = document.createElement("p");
      status.className = "device-status connected";
      status.textContent = "Connected";

      const firmware = document.createElement("p");
      const version = firmwareCache.get(device.device_id);

      if (version?.firmware_version) {
        firmware.textContent = `Firmware: ${version.firmware_version}`;
      } else if (version?.error) {
        firmware.textContent = `Firmware: unavailable (${version.error})`;
      } else {
        firmware.textContent = "Firmware: checking...";
      }

      card.append(heading, description, status, firmware);
      card.addEventListener("click", () => selectDevice(device));
      deviceList.appendChild(card);
    });

    if (connectedDevices.length === 0) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No supported Pico devices connected.";
      deviceList.appendChild(empty);
    }
  }

  loadDevices();
  window.setInterval(loadDevices, 2000);
});
