window.Logistics = (() => {
    const toast = () => document.getElementById("toast");

    function showToast(message, duration = 2600) {
        const element = toast();
        if (!element) return;
        element.textContent = message;
        element.classList.add("show");
        window.clearTimeout(element._hideTimer);
        element._hideTimer = window.setTimeout(() => {
            element.classList.remove("show");
        }, duration);
    }

    function escapeHTML(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function initials(name) {
        const parts = String(name || "")
            .trim()
            .split(/\s+/)
            .filter(Boolean);
        if (!parts.length) return "?";
        return parts.slice(0, 2).map(part => part[0].toUpperCase()).join("");
    }

    function formatNumber(value, digits = 0) {
        const number = Number(value || 0);
        return number.toLocaleString("en-GB", {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        });
    }

    function formatTimestamp(value) {
        if (!value) return "";
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return String(value);
        return parsed.toLocaleString("en-GB", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    }

    function formatDate(value) {
        if (!value) return "";
        const parsed = new Date(`${value}T00:00:00`);
        if (Number.isNaN(parsed.getTime())) return String(value);
        return parsed.toLocaleDateString("en-GB");
    }

    function animateNumber(element, nextValue, digits = 0) {
        if (!element) return;
        const startValue = Number(String(element.textContent).replaceAll(",", "")) || 0;
        const target = Number(nextValue || 0);
        const startedAt = performance.now();
        const duration = 420;

        function frame(now) {
            const progress = Math.min(1, (now - startedAt) / duration);
            const eased = 1 - Math.pow(1 - progress, 3);
            const value = startValue + (target - startValue) * eased;
            element.textContent = formatNumber(value, digits);
            if (progress < 1) requestAnimationFrame(frame);
        }

        requestAnimationFrame(frame);
    }

    async function fetchJSON(url, options = {}) {
        const response = await fetch(url, {
            cache: "no-store",
            headers: {
                "Accept": "application/json",
                ...(options.headers || {}),
            },
            ...options,
        });

        if (!response.ok) {
            throw new Error(`Request failed (${response.status})`);
        }
        return response.json();
    }

    return {
        animateNumber,
        escapeHTML,
        fetchJSON,
        formatDate,
        formatNumber,
        formatTimestamp,
        initials,
        showToast,
    };
})();
