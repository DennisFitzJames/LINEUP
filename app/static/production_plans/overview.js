(() => {
  const search = document.getElementById('wc-search');
  const filter = document.getElementById('wc-filter');
  const cards = [...document.querySelectorAll('.wc-card')];
  const resultCount = document.getElementById('wc-result-count');
  const emptyState = document.getElementById('wc-empty-state');

  const normalise = (value) => String(value || '').trim().toLowerCase();

  function applyFilters() {
    const query = normalise(search?.value);
    const selectedArea = normalise(filter?.value || 'all');
    let visibleCount = 0;

    cards.forEach((card) => {
      const name = normalise(card.dataset.name);
      const areas = normalise(card.dataset.areas)
        .split('|')
        .map((area) => area.trim())
        .filter(Boolean);

      const matchesText = !query || name.includes(query);
      const matchesArea = selectedArea === 'all'
        || (selectedArea === 'unmapped' && areas.length === 0)
        || areas.includes(selectedArea);
      const isVisible = matchesText && matchesArea;

      // Use an explicit inline display value rather than relying on the HTML
      // hidden attribute, which was being overridden in some browser/CSS builds.
      card.style.display = isVisible ? '' : 'none';
      card.setAttribute('aria-hidden', isVisible ? 'false' : 'true');

      if (isVisible) visibleCount += 1;
    });

    if (resultCount) {
      resultCount.textContent = `${visibleCount} work centre${visibleCount === 1 ? '' : 's'}`;
    }

    if (emptyState) {
      emptyState.style.display = visibleCount === 0 ? 'block' : 'none';
    }
  }

  search?.addEventListener('input', applyFilters);
  search?.addEventListener('search', applyFilters);
  filter?.addEventListener('change', applyFilters);

  applyFilters();
})();
