(() => {
    const areaId = window.LOGISTICS_AREA_ID;
    let refreshSeconds = Number(window.LOGISTICS_REFRESH_SECONDS || 60);
    let countdown = refreshSeconds;
    let refreshTimer = null;
    let countdownTimer = null;
    let currentArea = null;
    let searchText = "";

    const body = document.getElementById("active-plan-body");
    const table = document.getElementById("active-plan-table");
    const wrap = document.getElementById("plan-table-wrap");
    const empty = document.getElementById("active-empty");
    const forecastMarker = document.getElementById("forecast-marker");
    const targetMarker = document.getElementById("target-marker");
    const searchInput = document.getElementById("order-search");
    const refreshButton = document.getElementById("refresh-area");

    function orderSearchText(order) {
        return [
            order.order_number,
            order.material,
            order.material_description,
            order.customer,
            order.system_status,
            order.user_status,
            ...(order.work_centres || []),
        ].join(" ").toLowerCase();
    }

    function statusClass(status) {
        return String(status || "").toLowerCase();
    }

    function cell(value, className = "", title = "") {
        const td = document.createElement("td");
        if (className) td.className = className;
        td.textContent = value ?? "";
        if (title) td.title = title;
        return td;
    }

    function updateRow(row, order) {
        const previousDate = row.dataset.scheduledStart || "";
        row.dataset.key = order.row_key;
        row.dataset.scheduledStart = order.scheduled_start || "";
        row.dataset.search = orderSearchText(order);
        row.classList.toggle("overdue", Boolean(order.is_overdue));
        row.classList.toggle("next-week", Boolean(order.is_next_week));

        if (previousDate && previousDate !== (order.scheduled_start || "")) {
            row.classList.remove("row-date-changed");
            void row.offsetWidth;
            row.classList.add("row-date-changed");
        }

        row.replaceChildren(
            cell(order.scheduled_start_display),
            cell(order.scheduled_finish_display),
            cell(order.order_number),
            cell(order.material),
            cell(order.material_description, "description-cell", order.material_description),
            cell(order.target_quantity, "number"),
            cell(order.confirmed_quantity, "number"),
            cell(order.customer, "customer-cell", order.customer),
            cell(order.priority),
            (() => {
                const td = cell("");
                const chip = document.createElement("span");
                chip.className = `status-chip ${statusClass(order.status)}`;
                chip.textContent = order.system_status || order.status;
                td.appendChild(chip);
                td.title = order.system_status || "";
                return td;
            })(),
            cell(order.user_status),
            cell(Logistics.formatNumber(order.hours_required, 2), "number"),
        );
    }

    function visibleRows() {
        return [...body.querySelectorAll("tr[data-key]")].filter(row => !row.hidden);
    }

    function applySearch() {
        const query = searchText.trim().toLowerCase();
        body.querySelectorAll("tr[data-key]").forEach(row => {
            row.hidden = Boolean(query && !row.dataset.search.includes(query));
        });
        positionMarkers();
    }

    function renderOrders(orders) {
        const oldRects = new Map();
        body.querySelectorAll("tr[data-key]").forEach(row => {
            oldRects.set(row.dataset.key, row.getBoundingClientRect());
        });

        const newKeys = new Set(orders.map(order => order.row_key));
        body.querySelectorAll("tr[data-key]").forEach(row => {
            if (!newKeys.has(row.dataset.key)) {
                row.classList.add("row-leaving");
                window.setTimeout(() => row.remove(), 320);
            }
        });

        orders.forEach(order => {
            let row = body.querySelector(`tr[data-key="${CSS.escape(order.row_key)}"]`);
            const isNew = !row;
            if (!row) {
                row = document.createElement("tr");
                row.dataset.key = order.row_key;
            }

            updateRow(row, order);
            body.appendChild(row);

            if (isNew) {
                row.classList.add("row-entering");
                window.setTimeout(() => row.classList.remove("row-entering"), 600);
            }
        });

        requestAnimationFrame(() => {
            body.querySelectorAll("tr[data-key]").forEach(row => {
                const oldRect = oldRects.get(row.dataset.key);
                if (!oldRect) return;
                const newRect = row.getBoundingClientRect();
                const dx = oldRect.left - newRect.left;
                const dy = oldRect.top - newRect.top;
                if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;

                row.style.transition = "none";
                row.style.transform = `translate(${dx}px, ${dy}px)`;
                row.style.position = "relative";
                row.style.zIndex = "4";

                requestAnimationFrame(() => {
                    row.style.transition = "transform 680ms cubic-bezier(.22,.8,.27,1)";
                    row.style.transform = "";
                    window.setTimeout(() => {
                        row.style.transition = "";
                        row.style.position = "";
                        row.style.zIndex = "";
                    }, 720);
                });
            });

            applySearch();
            window.setTimeout(positionMarkers, 740);
        });

        empty.classList.toggle("hidden", orders.length > 0);
        table.classList.toggle("hidden", orders.length === 0);
    }

    function renderPickers(pickers) {
        const list = document.getElementById("picker-list");
        list.replaceChildren();

        if (!pickers.length) {
            const state = document.createElement("div");
            state.className = "empty-state";
            state.innerHTML = "<strong>No matched pickers</strong><span>No active LRF2 queue matched this area.</span>";
            list.appendChild(state);
            return;
        }

        pickers.forEach(picker => {
            const item = document.createElement("div");
            item.className = "picker-item";
            item.innerHTML = `
                <span class="picker-avatar">${Logistics.escapeHTML(Logistics.initials(picker.name))}</span>
                <span>
                    <strong>${Logistics.escapeHTML(picker.name)}</strong>
                    <small>${Logistics.escapeHTML(picker.queue)} · ${Logistics.escapeHTML(picker.sap_id)}</small>
                </span>
            `;
            list.appendChild(item);
        });
    }

    function renderStaged(orders) {
        const list = document.getElementById("staged-list");
        list.replaceChildren();

        if (!orders.length) {
            const state = document.createElement("div");
            state.className = "empty-state";
            state.innerHTML = "<strong>Nothing staged</strong><span>Picked orders will move into this panel rather than disappearing.</span>";
            list.appendChild(state);
            return;
        }

        orders.forEach(order => {
            const item = document.createElement("div");
            item.className = "staged-item";
            item.innerHTML = `
                <span class="staged-check">✓</span>
                <span>
                    <strong>${Logistics.escapeHTML(order.order_number)}</strong>
                    <small>${Logistics.escapeHTML(order.material)} · ${Logistics.escapeHTML(order.material_description)}</small>
                    <small>Scheduled ${Logistics.escapeHTML(order.scheduled_start_display || "—")}</small>
                </span>
            `;
            list.appendChild(item);
        });
    }

    function markerTop(position) {
        const rows = visibleRows();
        if (!rows.length) return null;

        const headerHeight = table.tHead?.offsetHeight || 0;
        const tableTop = table.offsetTop || 0;

        if (position <= 0) {
            return tableTop + headerHeight;
        }

        const row = rows[Math.min(position, rows.length) - 1];
        return tableTop + row.offsetTop + row.offsetHeight;
    }

    function syncMarkerGeometry(marker) {
        const label = marker.querySelector("span");
        const contentWidth = Math.max(
            table.scrollWidth || 0,
            table.offsetWidth || 0,
            wrap.clientWidth || 0,
        );

        // The marker is part of the horizontally scrolling content, so give it
        // the full table width rather than the width of the visible viewport.
        marker.style.left = "0px";
        marker.style.right = "auto";
        marker.style.width = `${contentWidth}px`;

        if (!label) return;

        const edgePadding = 14;
        const labelWidth = label.offsetWidth || 0;
        const maxLeft = Math.max(edgePadding, contentWidth - labelWidth - edgePadding);
        const viewportLeft = wrap.scrollLeft || 0;

        // Keep the forecast label on the visible right edge and the target
        // label on the visible left edge as the user scrolls horizontally.
        let labelLeft;
        if (marker.classList.contains("target-marker")) {
            labelLeft = viewportLeft + edgePadding;
        } else {
            labelLeft = viewportLeft + wrap.clientWidth - labelWidth - edgePadding;
        }

        label.style.right = "auto";
        label.style.left = `${Math.max(edgePadding, Math.min(maxLeft, labelLeft))}px`;
    }

    function setMarker(marker, position, enabled = true) {
        if (!enabled || searchText.trim()) {
            marker.classList.remove("visible");
            return;
        }

        const top = markerTop(position);
        if (top === null) {
            marker.classList.remove("visible");
            return;
        }

        const headerHeight = table.tHead?.offsetHeight || 0;
        const visibleTop = wrap.scrollTop + headerHeight;
        const visibleBottom = wrap.scrollTop + wrap.clientHeight;

        // Keep markers in the table body. Sticky header geometry can otherwise
        // make a marker appear above the column headings while scrolling.
        if (top < visibleTop - 1 || top > visibleBottom + 1) {
            marker.classList.remove("visible");
            return;
        }

        marker.style.top = `${Math.max(top, visibleTop)}px`;
        marker.classList.toggle("marker-at-header", Number(position) <= 0);
        syncMarkerGeometry(marker);
        marker.classList.add("visible");
    }

    function positionMarkers() {
        if (!currentArea) return;
        setMarker(
            forecastMarker,
            Number(currentArea.forecast_position || 0),
            Number(currentArea.forecast_count || 0) > 0
        );
        setMarker(
            targetMarker,
            Number(currentArea.target_position || 0),
            Number(currentArea.target_position || 0) > 0
        );
    }

    function updateMetrics(area) {
        Logistics.animateNumber(document.getElementById("metric-pickers"), area.picker_count, 0);
        Logistics.animateNumber(document.getElementById("metric-active"), area.active_count, 0);
        Logistics.animateNumber(document.getElementById("metric-forecast"), area.forecast_count, 1);
        Logistics.animateNumber(document.getElementById("metric-hours"), area.target_hours, 1);
        Logistics.animateNumber(document.getElementById("metric-overdue"), area.overdue_count, 0);
        Logistics.animateNumber(document.getElementById("picker-count-pill"), area.picker_count, 0);
        Logistics.animateNumber(document.getElementById("staged-count-pill"), area.picked_count, 0);

        const names = document.getElementById("metric-picker-names");
        names.textContent = area.pickers.length
            ? area.pickers.map(picker => picker.name).join(", ")
            : "No active queue matches";

        const targetLabel = targetMarker.querySelector("span");
        if (targetLabel) targetLabel.textContent = `Target · ${area.target_date_display}`;
    }

    function render(data) {
        currentArea = data.area;
        refreshSeconds = Number(data.refresh_seconds || refreshSeconds);
        countdown = refreshSeconds;

        updateMetrics(currentArea);
        renderOrders(currentArea.active_orders || []);
        renderPickers(currentArea.pickers || []);
        renderStaged(currentArea.picked_orders || []);

        const updated = document.getElementById("global-updated");
        if (updated) {
            updated.textContent = `Updated ${data.generated_at_display || Logistics.formatTimestamp(data.generated_at)}`;
        }
    }

    async function refresh(showMessage = false) {
        if (refreshButton) refreshButton.disabled = true;
        try {
            const data = await Logistics.fetchJSON(`/api/logistics/area/${encodeURIComponent(areaId)}`);
            render(data);
            if (showMessage) Logistics.showToast(`${data.area.name} refreshed.`);
        } catch (error) {
            Logistics.showToast(`Could not refresh the plan: ${error.message}`);
        } finally {
            if (refreshButton) refreshButton.disabled = false;
            scheduleRefresh();
        }
    }

    function scheduleRefresh() {
        window.clearTimeout(refreshTimer);
        refreshTimer = window.setTimeout(() => refresh(false), Math.max(15, refreshSeconds) * 1000);
    }

    function tickCountdown() {
        countdown = Math.max(0, countdown - 1);
        const element = document.getElementById("refresh-countdown");
        if (element) element.textContent = String(countdown);
        if (countdown <= 0) countdown = refreshSeconds;
    }

    searchInput?.addEventListener("input", event => {
        searchText = event.target.value || "";
        applySearch();
    });
    refreshButton?.addEventListener("click", () => refresh(true));
    window.addEventListener("resize", positionMarkers);
    wrap?.addEventListener("scroll", positionMarkers, {passive: true});

    countdownTimer = window.setInterval(tickCountdown, 1000);
    refresh(false);
})();
