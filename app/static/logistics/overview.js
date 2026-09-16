(() => {
    const refreshButton = document.getElementById("refresh-overview");
    let refreshSeconds = 60;
    let timer = null;

    function updateCard(area) {
        const card = document.querySelector(`[data-area-id="${CSS.escape(area.id)}"]`);
        if (!card) return;

        const fields = {
            active_count: [area.active_count, 0],
            picked_count: [area.picked_count, 0],
            overdue_count: [area.overdue_count, 0],
            target_hours: [area.target_hours, 1],
        };

        let changed = false;
        Object.entries(fields).forEach(([field, [value, digits]]) => {
            const element = card.querySelector(`[data-field="${field}"]`);
            if (!element) return;
            const previous = element.textContent;
            Logistics.animateNumber(element, value, digits);
            if (previous !== String(value)) changed = true;
        });

        const pickerText = card.querySelector(".area-card-top div > span");
        if (pickerText) {
            pickerText.textContent = `${area.picker_count} picker${area.picker_count === 1 ? "" : "s"}`;
        }

        if (changed) {
            card.classList.remove("flash-update");
            void card.offsetWidth;
            card.classList.add("flash-update");
        }
    }

    function updateSourceCard(sourceId, source) {
        const card = document.querySelector(`[data-source-id="${CSS.escape(sourceId)}"]`);
        if (!card || !source) return;

        card.classList.remove("live", "sample", "stale", "missing");
        card.classList.add(source.status || "missing");

        const status = card.querySelector('[data-field="status_label"]');
        const name = card.querySelector('[data-field="name"]');
        const modified = card.querySelector('[data-field="modified_at_display"]');

        if (status) status.textContent = source.status_label || "Missing";
        if (name) name.textContent = source.name || "Not found";
        if (modified) modified.textContent = source.modified_at_display || "No file found";
    }

    async function refresh(showMessage = false) {
        if (refreshButton) refreshButton.disabled = true;
        try {
            const data = await Logistics.fetchJSON("/api/logistics/areas");
            refreshSeconds = Number(data.refresh_seconds || 60);

            Logistics.animateNumber(document.getElementById("total-active"), data.totals.active_count, 0);
            Logistics.animateNumber(document.getElementById("total-pickers"), data.totals.picker_count, 0);
            Logistics.animateNumber(document.getElementById("total-picked"), data.totals.picked_count, 0);
            Logistics.animateNumber(document.getElementById("total-overdue"), data.totals.overdue_count, 0);
            Logistics.animateNumber(document.getElementById("total-hours"), data.totals.target_hours, 1);

            data.areas.forEach(updateCard);
            updateSourceCard("lx02", data.source_state?.lx02);
            updateSourceCard("lrf2", data.source_state?.lrf2);

            const updated = document.getElementById("global-updated");
            if (updated) updated.textContent = `Updated ${data.generated_at_display || Logistics.formatTimestamp(data.generated_at)}`;

            if (showMessage) Logistics.showToast("Area overview refreshed.");
        } catch (error) {
            Logistics.showToast(`Could not refresh: ${error.message}`);
        } finally {
            if (refreshButton) refreshButton.disabled = false;
            schedule();
        }
    }

    function schedule() {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => refresh(false), Math.max(15, refreshSeconds) * 1000);
    }

    refreshButton?.addEventListener("click", () => refresh(true));
    schedule();
})();
