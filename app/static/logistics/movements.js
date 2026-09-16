(() => {
    const daysSelect = document.getElementById("movement-days");
    const refreshButton = document.getElementById("refresh-movements");
    const clearFiltersButton = document.getElementById("clear-movement-filters");
    const clearWeekFilterButton = document.getElementById("clear-week-filter");
    const changedOrdersSection = document.getElementById("changed-orders-section");
    const trendCanvas = document.getElementById("movement-trend-chart");
    const trendTooltip = document.getElementById("movement-trend-tooltip");
    const directionCanvas = document.getElementById("movement-direction-chart");
    const directionTooltip = document.getElementById("movement-direction-tooltip");
    const pulledInCard = document.getElementById("movement-pulled-in-card");
    const pushedOutCard = document.getElementById("movement-pushed-out-card");

    const filters = {
        date: document.getElementById("movement-filter-date"),
        order: document.getElementById("movement-filter-order"),
        area: document.getElementById("movement-filter-area"),
        type: document.getElementById("movement-filter-type"),
        oldValue: document.getElementById("movement-filter-old"),
        newValue: document.getElementById("movement-filter-new"),
        direction: document.getElementById("movement-filter-direction"),
    };

    const state = {
        data: null,
        changes: [],
        activeDirection: "",
        weekTransition: "",
    };

    function prepareCanvas(canvas) {
        const rect = canvas.getBoundingClientRect();
        const ratio = window.devicePixelRatio || 1;
        const cssHeight = Number(canvas.dataset.chartHeight || 250);

        canvas.style.height = `${cssHeight}px`;
        canvas.width = Math.max(1, Math.round(rect.width * ratio));
        canvas.height = Math.max(1, Math.round(cssHeight * ratio));

        const context = canvas.getContext("2d");
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        return {
            context,
            width: rect.width,
            height: cssHeight,
        };
    }

    function roundedRect(context, x, y, width, height, radius) {
        const r = Math.min(radius, width / 2, height / 2);
        context.beginPath();
        context.roundRect(x, y, width, height, r);
    }

    function drawEmptyChart(canvas, message) {
        const {context, width, height} = prepareCanvas(canvas);
        context.clearRect(0, 0, width, height);
        context.fillStyle = "#8b8fa1";
        context.font = "12px Segoe UI";
        context.textAlign = "center";
        context.fillText(message, width / 2, height / 2);
    }

    function drawTrend(canvas, daily, dailyAreas = {}) {
        const totalEvents = daily.reduce(
            (sum, row) => sum + Number(row.date_moves || 0) + Number(row.teco_count || 0),
            0,
        );
        if (!daily.length || totalEvents === 0) {
            canvas._movementTrendRegions = [];
            drawEmptyChart(canvas, "No date moves or TECOs have been recorded in this window.");
            return;
        }

        const {context, width, height} = prepareCanvas(canvas);
        const margin = {top: 22, right: 16, bottom: 36, left: 34};
        const chartWidth = width - margin.left - margin.right;
        const chartHeight = height - margin.top - margin.bottom;
        const maxValue = Math.max(
            1,
            ...daily.flatMap(row => [
                Number(row.date_moves || 0),
                Number(row.teco_count || 0),
            ]),
        );
        const regions = [];

        context.clearRect(0, 0, width, height);
        context.strokeStyle = "#e8e9f1";
        context.lineWidth = 1;
        context.fillStyle = "#8b8fa1";
        context.font = "10px Segoe UI";

        for (let step = 0; step <= 4; step += 1) {
            const y = margin.top + chartHeight - chartHeight * step / 4;
            context.beginPath();
            context.moveTo(margin.left, y);
            context.lineTo(width - margin.right, y);
            context.stroke();
            context.textAlign = "right";
            context.fillText(String(Math.round(maxValue * step / 4)), margin.left - 7, y + 3);
        }

        const xForIndex = index => (
            daily.length === 1
                ? margin.left + chartWidth / 2
                : margin.left + chartWidth * index / (daily.length - 1)
        );

        function drawSeries(dataKey, changeType, label, color, fillColor) {
            const points = daily.map((row, index) => ({
                x: xForIndex(index),
                y: margin.top + chartHeight
                    - chartHeight * Number(row[dataKey] || 0) / maxValue,
                row,
                value: Number(row[dataKey] || 0),
            }));

            if (fillColor) {
                const gradient = context.createLinearGradient(0, margin.top, 0, margin.top + chartHeight);
                gradient.addColorStop(0, fillColor);
                gradient.addColorStop(1, "rgba(105, 97, 209, 0.01)");
                context.beginPath();
                context.moveTo(points[0].x, margin.top + chartHeight);
                points.forEach(point => context.lineTo(point.x, point.y));
                context.lineTo(points.at(-1).x, margin.top + chartHeight);
                context.closePath();
                context.fillStyle = gradient;
                context.fill();
            }

            context.beginPath();
            points.forEach((point, index) => {
                if (index === 0) context.moveTo(point.x, point.y);
                else context.lineTo(point.x, point.y);
            });
            context.strokeStyle = color;
            context.lineWidth = 3;
            context.lineJoin = "round";
            context.lineCap = "round";
            context.stroke();

            points.forEach(point => {
                context.beginPath();
                context.arc(point.x, point.y, 4, 0, Math.PI * 2);
                context.fillStyle = "#ffffff";
                context.fill();
                context.strokeStyle = color;
                context.lineWidth = 2;
                context.stroke();

                regions.push({
                    x: point.x,
                    y: point.y,
                    radius: 12,
                    changeDate: point.row.change_date,
                    changeType,
                    label,
                    value: point.value,
                    color,
                    breakdown: dailyAreas?.[point.row.change_date]?.[changeType] || [],
                });
            });
        }

        drawSeries("date_moves", "date_moved", "Date moved", "#6961d1", "rgba(105, 97, 209, 0.18)");
        drawSeries("teco_count", "teco", "TECO", "#d24a57", null);

        daily.forEach((row, index) => {
            context.fillStyle = "#8b8fa1";
            context.font = "9px Segoe UI";
            context.textAlign = "center";
            const label = new Date(`${row.change_date}T00:00:00`).toLocaleDateString("en-GB", {
                day: "2-digit",
                month: "2-digit",
            });
            context.fillText(label, xForIndex(index), height - 12);
        });

        canvas._movementTrendRegions = regions;
    }

    function drawDirections(canvas, summary, directionAreas = {}) {
        const values = [
            {
                key: "earlier",
                label: "Earlier",
                value: Number(summary.moved_earlier || 0),
                color: "#4d9078",
                breakdown: directionAreas.earlier || [],
            },
            {
                key: "later",
                label: "Later",
                value: Number(summary.moved_later || 0),
                color: "#ef8d32",
                breakdown: directionAreas.later || [],
            },
            {
                key: "teco",
                label: "TECO",
                value: Number(summary.teco || 0),
                color: "#d24a57",
                breakdown: directionAreas.teco || [],
            },
        ];

        const {context, width, height} = prepareCanvas(canvas);
        const maxValue = Math.max(1, ...values.map(item => item.value));
        const margin = {top: 24, right: 20, bottom: 38, left: 24};
        const chartWidth = width - margin.left - margin.right;
        const chartHeight = height - margin.top - margin.bottom;
        const slotWidth = chartWidth / values.length;
        const barWidth = Math.min(76, slotWidth * 0.55);
        const regions = [];

        context.clearRect(0, 0, width, height);

        values.forEach((item, index) => {
            const barHeight = chartHeight * item.value / maxValue;
            const x = margin.left + slotWidth * index + (slotWidth - barWidth) / 2;
            const y = margin.top + chartHeight - barHeight;
            const visibleHeight = Math.max(3, barHeight);

            context.save();
            if (state.activeDirection && state.activeDirection !== item.key) {
                context.globalAlpha = 0.38;
            }

            roundedRect(context, x, y, barWidth, visibleHeight, 8);
            context.fillStyle = item.color;
            context.fill();

            if (state.activeDirection === item.key) {
                context.strokeStyle = "#312c72";
                context.lineWidth = 3;
                context.stroke();
            }
            context.restore();

            context.fillStyle = "#34384d";
            context.font = "700 16px Segoe UI";
            context.textAlign = "center";
            context.fillText(String(item.value), x + barWidth / 2, Math.max(15, y - 7));

            context.fillStyle = "#85899a";
            context.font = "10px Segoe UI";
            context.fillText(item.label, x + barWidth / 2, height - 14);

            regions.push({
                ...item,
                x,
                y: Math.min(y, margin.top + chartHeight - 10),
                width: barWidth,
                height: Math.max(12, visibleHeight),
            });
        });

        canvas._movementBarRegions = regions;
    }

    function renderRanking(areas) {
        const container = document.getElementById("area-ranking");
        container.replaceChildren();

        if (!areas.length) {
            const empty = document.createElement("div");
            empty.className = "empty-state";
            empty.innerHTML = "<strong>No area changes</strong><span>Area rankings appear after a second data snapshot detects date moves or TECOs.</span>";
            container.appendChild(empty);
            return;
        }

        const maxValue = Math.max(1, ...areas.map(area => Number(area.gross_days || area.change_count || 0)));
        areas.slice(0, 10).forEach(area => {
            const value = Number(area.gross_days || 0);
            const row = document.createElement("button");
            row.type = "button";
            row.className = "ranking-row ranking-button";
            row.title = `Show changes for ${area.area_name}`;
            row.innerHTML = `
                <span class="ranking-label" title="${Logistics.escapeHTML(area.area_name)}">${Logistics.escapeHTML(area.area_name)}</span>
                <span class="ranking-track"><span class="ranking-fill" style="width:${Math.max(3, value / maxValue * 100)}%"></span></span>
                <span class="ranking-value">${value}d</span>
            `;
            row.addEventListener("click", () => {
                filters.area.value = area.area_id;
                applyFilters({scroll: true});
            });
            container.appendChild(row);
        });
    }

    function changeLabel(type) {
        const labels = {
            date_moved: "Date moved",
            teco: "TECO'd",
        };
        return labels[type] || type;
    }

    function weekTransitionLabel(value) {
        if (value === "pulled_in") return "Into this week";
        if (value === "pushed_out") return "Out of this week";
        return "";
    }

    function normalise(value) {
        return String(value ?? "").trim().toLocaleLowerCase("en-GB");
    }

    function dateSearchText(change) {
        return `${change.detected_at || ""} ${Logistics.formatTimestamp(change.detected_at || "")}`;
    }

    function directionForChange(change) {
        if (change.change_type === "teco") return "teco";
        if (change.change_type !== "date_moved") return "none";
        const delta = Number(change.days_delta || 0);
        if (delta < 0) return "earlier";
        if (delta > 0) return "later";
        return "none";
    }

    function filteredChanges() {
        const criteria = {
            date: normalise(filters.date.value),
            order: normalise(filters.order.value),
            area: filters.area.value,
            type: filters.type.value,
            oldValue: normalise(filters.oldValue.value),
            newValue: normalise(filters.newValue.value),
            direction: filters.direction.value,
            weekTransition: state.weekTransition,
        };

        return state.changes.filter(change => {
            if (criteria.date && !normalise(dateSearchText(change)).includes(criteria.date)) return false;
            if (criteria.order && !normalise(change.order_number).includes(criteria.order)) return false;
            if (criteria.area && change.area_id !== criteria.area) return false;
            if (criteria.type && change.change_type !== criteria.type) return false;
            if (criteria.oldValue && !normalise(change.old_value).includes(criteria.oldValue)) return false;
            if (criteria.newValue && !normalise(change.new_value).includes(criteria.newValue)) return false;
            if (criteria.weekTransition && change.week_transition !== criteria.weekTransition) return false;

            if (criteria.direction) {
                const direction = directionForChange(change);
                if (criteria.direction !== direction) return false;
            }
            return true;
        });
    }

    function renderChanges(changes) {
        const body = document.getElementById("movement-change-body");
        const empty = document.getElementById("movement-empty");
        body.replaceChildren();

        changes.forEach(change => {
            const row = document.createElement("tr");
            const delta = change.days_delta;
            const deltaClass = Number(delta) < 0 ? "earlier" : Number(delta) > 0 ? "later" : "";
            const transitionLabel = weekTransitionLabel(change.week_transition);
            const transitionBadge = transitionLabel
                ? `<span class="week-transition-chip ${Logistics.escapeHTML(change.week_transition)}">${Logistics.escapeHTML(transitionLabel)}</span>`
                : "";
            row.innerHTML = `
                <td>${Logistics.escapeHTML(Logistics.formatTimestamp(change.detected_at))}</td>
                <td><strong>${Logistics.escapeHTML(change.order_number)}</strong></td>
                <td>${Logistics.escapeHTML(change.area_name)}</td>
                <td><span class="change-label-stack"><span class="change-type ${Logistics.escapeHTML(change.change_type)}">${Logistics.escapeHTML(changeLabel(change.change_type))}</span>${transitionBadge}</span></td>
                <td>${Logistics.escapeHTML(change.old_value || "—")}</td>
                <td>${Logistics.escapeHTML(change.new_value || "—")}</td>
                <td class="delta ${deltaClass}">${delta === null || delta === undefined ? "—" : `${delta > 0 ? "+" : ""}${delta}`}</td>
            `;
            body.appendChild(row);
        });

        empty.classList.toggle("hidden", changes.length > 0);
        document.getElementById("movement-filter-count").textContent =
            `Showing ${changes.length.toLocaleString("en-GB")} of ${state.changes.length.toLocaleString("en-GB")} changes`;
    }

    function deriveActiveDirection() {
        if (filters.type.value === "teco") return "teco";
        if (filters.type.value === "date_moved" && ["earlier", "later"].includes(filters.direction.value)) {
            return filters.direction.value;
        }
        return "";
    }

    function updateWeekCardState() {
        pulledInCard.classList.toggle("active", state.weekTransition === "pulled_in");
        pushedOutCard.classList.toggle("active", state.weekTransition === "pushed_out");
        clearWeekFilterButton.classList.toggle("hidden", !state.weekTransition);
    }

    function applyFilters({scroll = false} = {}) {
        state.activeDirection = deriveActiveDirection();
        updateWeekCardState();
        renderChanges(filteredChanges());

        if (state.data) {
            drawDirections(
                directionCanvas,
                state.data.summary || {},
                state.data.direction_areas || {},
            );
        }

        if (scroll) {
            changedOrdersSection.scrollIntoView({behavior: "smooth", block: "start"});
        }
    }

    function populateAreaFilter(changes) {
        const selected = filters.area.value;
        const areas = new Map();
        changes.forEach(change => {
            if (change.area_id && change.area_name) {
                areas.set(change.area_id, change.area_name);
            }
        });

        const options = [...areas.entries()].sort((a, b) => a[1].localeCompare(b[1], "en-GB"));
        filters.area.replaceChildren();

        const all = document.createElement("option");
        all.value = "";
        all.textContent = "All areas";
        filters.area.appendChild(all);

        options.forEach(([areaId, areaName]) => {
            const option = document.createElement("option");
            option.value = areaId;
            option.textContent = areaName;
            filters.area.appendChild(option);
        });

        if ([...filters.area.options].some(option => option.value === selected)) {
            filters.area.value = selected;
        }
    }

    function renderWeekBoundary(weekBoundary) {
        const pulledOrders = Number(weekBoundary.pulled_in_orders || 0);
        const pulledEvents = Number(weekBoundary.pulled_in_events || 0);
        const pushedOrders = Number(weekBoundary.pushed_out_orders || 0);
        const pushedEvents = Number(weekBoundary.pushed_out_events || 0);

        Logistics.animateNumber(document.getElementById("movement-pulled-in"), pulledOrders, 0);
        Logistics.animateNumber(document.getElementById("movement-pushed-out"), pushedOrders, 0);

        document.getElementById("movement-pulled-in-detail").textContent =
            `${pulledEvents.toLocaleString("en-GB")} date-change event${pulledEvents === 1 ? "" : "s"}`;
        document.getElementById("movement-pushed-out-detail").textContent =
            `${pushedEvents.toLocaleString("en-GB")} date-change event${pushedEvents === 1 ? "" : "s"}`;

        const start = weekBoundary.week_start_display || "";
        const end = weekBoundary.week_end_display || "";
        document.getElementById("movement-week-range").textContent = start && end
            ? `Current week: ${start} to ${end}. Counts use changes detected in the selected window.`
            : "Measured against the current Monday-to-Sunday week.";
    }

    function render(data) {
        state.data = data;
        state.changes = data.changes || [];

        const summary = data.summary || {};
        Logistics.animateNumber(document.getElementById("movement-gross-days"), summary.gross_days, 0);
        Logistics.animateNumber(document.getElementById("movement-date-count"), summary.orders_moved, 0);
        Logistics.animateNumber(document.getElementById("movement-earlier"), summary.moved_earlier, 0);
        Logistics.animateNumber(document.getElementById("movement-later"), summary.moved_later, 0);
        Logistics.animateNumber(document.getElementById("movement-teco"), summary.teco, 0);

        const dateEvents = Number(summary.date_moves || 0);
        document.getElementById("movement-date-detail").textContent =
            `${dateEvents.toLocaleString("en-GB")} date-change event${dateEvents === 1 ? "" : "s"}`;

        renderWeekBoundary(data.week_boundary || {});
        populateAreaFilter(state.changes);
        renderRanking(data.areas || []);
        drawTrend(trendCanvas, data.daily || [], data.daily_areas || {});
        applyFilters();
    }

    function clearFilters({scroll = false} = {}) {
        Object.values(filters).forEach(control => {
            control.value = "";
        });
        state.weekTransition = "";
        hideDirectionTooltip();
        hideTrendTooltip();
        applyFilters({scroll});
    }

    function applyWeekFilter(transition) {
        state.weekTransition = state.weekTransition === transition ? "" : transition;
        filters.type.value = state.weekTransition ? "date_moved" : "";
        filters.direction.value = "";
        applyFilters({scroll: true});
    }

    function trendPointAtEvent(event) {
        const rect = trendCanvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        let closest = null;
        let closestDistance = Infinity;

        (trendCanvas._movementTrendRegions || []).forEach(region => {
            const distance = Math.hypot(x - region.x, y - region.y);
            if (distance <= region.radius && distance < closestDistance) {
                closest = region;
                closestDistance = distance;
            }
        });

        return closest;
    }

    function showTrendTooltip(event, region) {
        if (!region) {
            hideTrendTooltip();
            return;
        }

        const breakdown = region.breakdown || [];
        const topAreas = breakdown.slice(0, 7);
        const remainder = breakdown.slice(7).reduce(
            (sum, row) => sum + Number(row.event_count || 0),
            0,
        );
        const rows = topAreas.map(row => {
            const events = Number(row.event_count || 0);
            const grossDays = Number(row.gross_days || 0);
            const detail = region.changeType === "date_moved" && grossDays
                ? `${events.toLocaleString("en-GB")} · ${grossDays.toLocaleString("en-GB")}d`
                : events.toLocaleString("en-GB");
            return `
                <span><b>${Logistics.escapeHTML(row.area_name)}</b><em>${detail}</em></span>
            `;
        }).join("");

        const dateLabel = new Date(`${region.changeDate}T00:00:00`).toLocaleDateString("en-GB", {
            weekday: "short",
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        });

        trendTooltip.innerHTML = `
            <strong>${Logistics.escapeHTML(region.label)} · ${Logistics.escapeHTML(dateLabel)}</strong>
            <small>${region.value.toLocaleString("en-GB")} event${region.value === 1 ? "" : "s"}</small>
            <div class="chart-tooltip-breakdown">${rows || "<span><b>No area changes</b><em>0</em></span>"}</div>
            ${remainder ? `<small>+ ${remainder.toLocaleString("en-GB")} events across other areas</small>` : ""}
        `;

        const wrapper = trendTooltip.parentElement.getBoundingClientRect();
        const left = Math.min(wrapper.width - 225, Math.max(8, event.clientX - wrapper.left + 12));
        const top = Math.min(wrapper.height - 120, Math.max(8, event.clientY - wrapper.top - 18));
        trendTooltip.style.left = `${left}px`;
        trendTooltip.style.top = `${top}px`;
        trendTooltip.classList.remove("hidden");
    }

    function hideTrendTooltip() {
        trendTooltip.classList.add("hidden");
    }

    function barAtEvent(event) {
        const rect = directionCanvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        return (directionCanvas._movementBarRegions || []).find(region => (
            x >= region.x && x <= region.x + region.width
            && y >= region.y && y <= region.y + region.height
        ));
    }

    function showDirectionTooltip(event, region) {
        if (!region) {
            hideDirectionTooltip();
            return;
        }

        const breakdown = region.breakdown || [];
        const topAreas = breakdown.slice(0, 6);
        const remainder = breakdown.slice(6).reduce((sum, row) => sum + Number(row.event_count || 0), 0);
        const rows = topAreas.map(row => `
            <span><b>${Logistics.escapeHTML(row.area_name)}</b><em>${Number(row.event_count || 0).toLocaleString("en-GB")}</em></span>
        `).join("");

        directionTooltip.innerHTML = `
            <strong>${Logistics.escapeHTML(region.label)}</strong>
            <small>${region.value.toLocaleString("en-GB")} event${region.value === 1 ? "" : "s"}</small>
            <div class="chart-tooltip-breakdown">${rows || "<span><b>No area changes</b><em>0</em></span>"}</div>
            ${remainder ? `<small>+ ${remainder.toLocaleString("en-GB")} events across other areas</small>` : ""}
        `;

        const wrapper = directionTooltip.parentElement.getBoundingClientRect();
        const left = Math.min(wrapper.width - 225, Math.max(8, event.clientX - wrapper.left + 12));
        const top = Math.min(wrapper.height - 120, Math.max(8, event.clientY - wrapper.top - 18));
        directionTooltip.style.left = `${left}px`;
        directionTooltip.style.top = `${top}px`;
        directionTooltip.classList.remove("hidden");
    }

    function hideDirectionTooltip() {
        directionTooltip.classList.add("hidden");
    }

    function applyBarFilter(region) {
        if (!region) return;

        if (state.activeDirection === region.key) {
            clearFilters({scroll: true});
            return;
        }

        filters.date.value = "";
        filters.order.value = "";
        filters.area.value = "";
        filters.oldValue.value = "";
        filters.newValue.value = "";
        state.weekTransition = "";

        if (region.key === "teco") {
            filters.type.value = "teco";
            filters.direction.value = "";
        } else {
            filters.type.value = "date_moved";
            filters.direction.value = region.key;
        }

        hideDirectionTooltip();
        applyFilters({scroll: true});
    }

    async function refresh(showMessage = false) {
        refreshButton.disabled = true;
        try {
            const selectedWindow = daysSelect.value || "7";
            const params = new URLSearchParams({limit: "2000"});

            if (selectedWindow === "today") {
                params.set("window", "today");
            } else {
                params.set("days", selectedWindow);
            }

            const data = await Logistics.fetchJSON(`/api/logistics/movements?${params.toString()}`);
            render(data);
            if (showMessage) Logistics.showToast("Movement tracker refreshed.");
        } catch (error) {
            Logistics.showToast(`Could not load movements: ${error.message}`);
        } finally {
            refreshButton.disabled = false;
        }
    }

    Object.values(filters).forEach(control => {
        const eventName = control.tagName === "INPUT" ? "input" : "change";
        control.addEventListener(eventName, () => applyFilters());
    });

    pulledInCard.addEventListener("click", () => applyWeekFilter("pulled_in"));
    pushedOutCard.addEventListener("click", () => applyWeekFilter("pushed_out"));
    clearWeekFilterButton.addEventListener("click", () => {
        state.weekTransition = "";
        applyFilters();
    });

    trendCanvas.addEventListener("mousemove", event => {
        const region = trendPointAtEvent(event);
        trendCanvas.style.cursor = region ? "help" : "default";
        showTrendTooltip(event, region);
    });
    trendCanvas.addEventListener("mouseleave", hideTrendTooltip);

    directionCanvas.addEventListener("mousemove", event => {
        const region = barAtEvent(event);
        directionCanvas.style.cursor = region ? "pointer" : "default";
        showDirectionTooltip(event, region);
    });
    directionCanvas.addEventListener("mouseleave", hideDirectionTooltip);
    directionCanvas.addEventListener("click", event => applyBarFilter(barAtEvent(event)));

    refreshButton.addEventListener("click", () => refresh(true));
    daysSelect.addEventListener("change", () => refresh(false));
    clearFiltersButton.addEventListener("click", () => clearFilters({scroll: false}));

    let resizeTimer = null;
    window.addEventListener("resize", () => {
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(() => {
            if (!state.data) return;
            drawTrend(trendCanvas, state.data.daily || [], state.data.daily_areas || {});
            drawDirections(directionCanvas, state.data.summary || {}, state.data.direction_areas || {});
        }, 120);
    });

    refresh(false);
})();
