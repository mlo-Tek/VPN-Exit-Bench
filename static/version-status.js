(() => {
  function githubIcon() {
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .7a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2.23c-3.22.7-3.9-1.37-3.9-1.37-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.7.08-.7 1.16.08 1.78 1.2 1.78 1.2 1.03 1.77 2.71 1.26 3.37.96.1-.75.4-1.26.73-1.55-2.57-.29-5.27-1.29-5.27-5.73 0-1.27.45-2.3 1.2-3.11-.12-.3-.52-1.48.11-3.08 0 0 .98-.31 3.16 1.19a10.9 10.9 0 0 1 5.76 0c2.18-1.5 3.16-1.19 3.16-1.19.63 1.6.23 2.78.11 3.08.75.81 1.2 1.84 1.2 3.11 0 4.45-2.71 5.43-5.29 5.72.42.36.79 1.07.79 2.16v3.2c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z"/></svg>';
  }

  function makeStatus(data) {
    const wrap = document.createElement('div');
    wrap.className = 'version-status';

    const installed = data?.installed?.label || 'unbekannt';
    let stateClass = 'version-unknown';
    let stateText = 'Update-Status unbekannt';
    let title = data?.error || '';

    if (data?.update_available === false) {
      stateClass = 'version-current';
      stateText = 'Aktuell';
    } else if (data?.update_available === true) {
      stateClass = 'version-update';
      stateText = `Update verfügbar · ${data?.latest?.label || 'neuer Build'}`;
    }

    wrap.innerHTML = `
      <a class="version-github" href="${data?.repository || 'https://github.com/mlo-Tek/VPN-Exit-Bench'}" target="_blank" rel="noopener noreferrer" aria-label="VPN Exit Bench auf GitHub öffnen" title="GitHub Repository">${githubIcon()}</a>
      <div class="version-build" title="Installierter Docker-Build">Version <strong>${installed}</strong></div>
      <div class="version-state ${stateClass}" title="${title}"><span class="version-dot"></span>${stateText}</div>
    `;
    return wrap;
  }

  function prepareBrandArea() {
    const top = document.querySelector('.top');
    if (!top) return null;
    const brand = top.firstElementChild;
    if (!brand) return null;

    brand.classList.add('brand');
    [...brand.children].forEach((child) => {
      if (child.matches('.muted')) child.remove();
    });
    return brand;
  }

  async function loadVersionStatus() {
    const brand = prepareBrandArea();
    if (!brand || document.querySelector('.version-status')) return;
    try {
      const response = await fetch('/api/version', { cache: 'no-store' });
      const data = await response.json();
      brand.appendChild(makeStatus(data));
    } catch (_) {
      brand.appendChild(makeStatus({ installed: { label: 'unbekannt' }, update_available: null }));
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadVersionStatus, { once: true });
  } else {
    loadVersionStatus();
  }
})();
