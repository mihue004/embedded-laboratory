
(async () => {
  const url = document.getElementById('build-logs-config').dataset.url;
  const status = document.getElementById('build-status');
  const resultSection = [...document.querySelectorAll('h3')]
    .find(element => element.textContent.trim() === 'Build-Ergebnis');

  if (!resultSection || !status) return;

  const container = document.createElement('div');
  container.id = 'live-build-commands';
  resultSection.insertAdjacentElement('afterend', container);

  const commands = new Map();
  let count = 0;

  function getCommand(index, argv) {
    if (commands.has(index)) return commands.get(index);

    const card = document.createElement('div');
    card.className = 'notice';

    const heading = document.createElement('strong');
    heading.textContent = 'Kommando – Status: läuft';

    const commandLine = document.createElement('p');
    const code = document.createElement('code');
    code.textContent = Array.isArray(argv) ? argv.join(' ') : '';
    commandLine.appendChild(code);

    const output = document.createElement('pre');
    output.style.cssText =
      'white-space:pre-wrap;overflow-wrap:anywhere;max-height:400px;overflow:auto';

    card.append(heading, commandLine, output);
    container.appendChild(card);

    const item = { heading, output };
    commands.set(index, item);
    return item;
  }

  while (true) {
    try {
      const response = await fetch(`${url}?after=${count}`);
      if (!response.ok) {
        status.textContent = 'Fehler beim Abrufen der Build-Ausgabe';
        break;
      }

      const data = await response.json();

      for (const event of data.events) {
        if (event.type === 'command_started') {
          getCommand(event.command_index, event.argv);
        } else if (event.type === 'command_output') {
          const item = getCommand(event.command_index);
          item.output.textContent += `[${event.stream}] ${event.line}\n`;
          item.output.scrollTop = item.output.scrollHeight;
        } else if (event.type === 'command_finished') {
          const item = getCommand(event.command_index, event.argv);
          item.heading.textContent =
            `Kommando – Status: ${event.status}` +
            (event.returncode !== undefined
              ? ` (Rückgabecode: ${event.returncode})`
              : '');
        }
      }

      count = data.next;

      if (data.finished) {
        if (data.error) {
          status.textContent = `Fehler: ${data.error}`;
        } else if (data.result) {
          status.textContent = data.result.status;
        }
        break;
      }
    } catch (error) {
      status.textContent = `Verbindungsfehler: ${error}`;
      break;
    }

    await new Promise(resolve => setTimeout(resolve, 500));
  }
})();
